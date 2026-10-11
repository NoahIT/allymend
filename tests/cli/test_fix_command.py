import json
import os
import shutil
import subprocess
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, override

import pytest

from allymend.cli import EXIT_CLEAN, EXIT_PROBLEMS, main
from allymend.core.models import Edit
from allymend.fixers import fix_html_has_lang
from allymend.fixers.plan import _Request

pytestmark = pytest.mark.browser

GIT = shutil.which("git")


@pytest.fixture
def site(tmp_path: Path, write_page: Callable[..., Path], monkeypatch: pytest.MonkeyPatch) -> Path:
    write_page("site/index.html", lang=None)
    write_page("site/shop/mug.html", '<img src="mug.png">')
    monkeypatch.chdir(tmp_path)
    return tmp_path / "site"


@pytest.fixture
def claude_requests(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Any]]:
    """Point the Anthropic SDK at a local server that answers with one alt text or link name."""
    received: list[Any] = []
    alt = {"alt": "A blue mug", "decorative": False, "rationale": "The page sells it."}
    name = {"name": "Your cart", "unclear": False, "rationale": "The icon is a cart."}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            request = json.loads(self.rfile.read(int(self.headers["content-length"])))
            received.append(request)
            schema = request["output_config"]["format"]["schema"]
            answer = name if "name" in schema["properties"] else alt
            reply = {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-5-5",
                "content": [{"type": "text", "text": json.dumps(answer)}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
            data = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        @override
        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    try:
        yield received
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.usefixtures("site")
def test_alt_text_from_claude_is_checked_and_listed_for_review(
    claude_requests: list[Any], capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["fix", "site", "--lang", "en", "--text-from", "claude", "--evidence", "e.json"])

    assert code == EXIT_PROBLEMS
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("Wrote fixes for 2 problems in 2 files to allymend.patch.")
    assert lines[2:6] == [
        "The checks behind every fix are in e.json.",
        "",
        "Text written by a model; read each one before applying the patch:",
        '  shop/mug.html: alt text "A blue mug" (claude-opus-5-5)',
    ]
    assert 'alt="A blue mug"' in Path("allymend.patch").read_text(encoding="utf-8")
    [request] = claude_requests
    assert [block["type"] for block in request["messages"][0]["content"]] == ["image", "text"]
    evidence = json.loads(Path("e.json").read_text(encoding="utf-8"))
    values = [fix["value"] for fix in evidence["fixes"] if fix["value"]]
    assert values == [
        {"text": "A blue mug", "rationale": "The page sells it.", "source": "claude-opus-5-5"}
    ]


def test_links_are_named_by_claude_or_by_their_image(
    tmp_path: Path,
    write_page: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    claude_requests: list[Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_page(
        "links/index.html",
        '<a href="cart.html"><svg width="24" height="24"></svg></a> '
        '<a href="shop.html"><img src="mug.png"></a>',
    )
    monkeypatch.chdir(tmp_path)

    assert main(["fix", "links", "--text-from", "claude"]) == EXIT_PROBLEMS

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("Wrote fixes for 2 problems in 1 file to allymend.patch.")
    assert '  index.html: alt text "A blue mug" (claude-opus-5-5)' in lines
    assert '  index.html: link name "Your cart" (claude-opus-5-5)' in lines
    gone = lines.index("Also gone once these fixes were applied (1 problem):")
    assert lines[gone + 1] == "  index.html: Link has no name (link-name), 1 element"
    patch = Path("allymend.patch").read_text(encoding="utf-8")
    assert '<a aria-label="Your cart" href="cart.html">' in patch
    assert '<img alt="A blue mug" src="mug.png">' in patch
    systems = sorted(request["system"].split("\n")[0] for request in claude_requests)
    assert systems == [
        "You name links on web pages, for people who use screen readers or control their "
        "computer by voice.",
        "You write alternative text for images on web pages, for people who use screen readers.",
    ]
    [link] = [r for r in claude_requests if r["system"].startswith("You name links")]
    assert [block["type"] for block in link["messages"][0]["content"]] == ["image", "text"]


@pytest.mark.usefixtures("site")
def test_show_payload_sends_nothing_and_writes_nothing(
    claude_requests: list[Any], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["fix", "site", "--text-from", "claude", "--show-payload"]) == EXIT_CLEAN
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "Would send 1 request to claude-opus-5-5. Nothing has been sent."
    assert "1. shop/mug.html: img" in lines
    assert claude_requests == []
    assert not Path("allymend.patch").exists()


@pytest.mark.skipif(GIT is None, reason="git is not installed")
@pytest.mark.usefixtures("site")
def test_the_patch_applies_and_fixes_the_page(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert GIT is not None
    assert main(["fix", "site", "--lang", "en"]) == EXIT_PROBLEMS

    lines = capsys.readouterr().out.splitlines()
    assert lines[:2] == [
        "Wrote fixes for 1 problem in 1 file to allymend.patch. Each was checked in a browser "
        "first.",
        "Review it, then apply it from this folder with: git apply allymend.patch",
    ]
    assert (
        "  shop/mug.html: Image has no text alternative (image-alt), 1 element: "
        "needs alt text from a person, or from a model (--text-from claude)"
    ) in lines
    assert (
        Path("allymend.patch")
        .read_text(encoding="utf-8")
        .startswith("--- a/site/index.html\n+++ b/site/index.html\n")
    )

    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    subprocess.run([GIT, "apply", "allymend.patch"], check=True)  # noqa: S603  fixed arguments
    assert main(["scan", "site", "--quiet"]) == EXIT_PROBLEMS
    assert "index.html: no problems found" in capsys.readouterr().out.splitlines()


@pytest.mark.usefixtures("site")
def test_evidence_records_every_check(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fix", "site", "--lang", "en", "--evidence", "checks.json"]) == EXIT_PROBLEMS
    assert "The checks behind every fix are in checks.json." in capsys.readouterr().out

    evidence = json.loads(Path("checks.json").read_text(encoding="utf-8"))
    assert (evidence["schema_version"], evidence["axe_version"]) == (1, "4.13.0")
    assert [fix["page"] for fix in evidence["fixes"]] == ["index.html"]
    assert [change["file"] for change in evidence["changes"]] == ["index.html"]
    assert evidence["changes"][0]["diff"].startswith("--- a/site/index.html\n")
    [verification] = evidence["verifications"]
    assert [(c["name"], c["passed"]) for c in verification["checks"]] == [
        ("edits", True),
        ("scanned", True),
        ("fixed", True),
        ("no-new-problems", True),
        ("tree", True),
    ]


@pytest.mark.usefixtures("site")
def test_a_fix_that_fails_its_checks_is_left_out(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def hiding(request: _Request) -> tuple[Edit, None]:
        edit = fix_html_has_lang(request.text, request.location, "en")
        return edit.model_copy(update={"text": f'{edit.text} aria-hidden="true"'}), None

    monkeypatch.setattr("allymend.fixers.plan._FIXERS", {"html-has-lang": hiding})

    assert main(["fix", "site", "--lang", "en"]) == EXIT_PROBLEMS

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "Nothing could be fixed automatically, so allymend.patch is empty."
    assert (
        "  index.html: Page language is not set (html-has-lang), 1 element: "
        "rejected by the check after fixing: an edit adds aria-hidden"
    ) in lines
    assert Path("allymend.patch").read_bytes() == b""


def test_without_a_language_the_patch_is_empty_and_says_why(
    site: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["fix", "site", "--output", "fixes.patch"]) == EXIT_PROBLEMS
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "Nothing could be fixed automatically, so fixes.patch is empty."
    assert (
        "  index.html: Page language is not set (html-has-lang), 1 element: "
        "the pages' language wasn't given (--lang)"
    ) in lines
    assert (site.parent / "fixes.patch").read_bytes() == b""


def test_a_clean_folder_gets_an_empty_patch(
    tmp_path: Path,
    write_page: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_page("index.html")
    monkeypatch.chdir(tmp_path)
    assert main(["fix", ".", "--lang", "en"]) == EXIT_CLEAN
    assert capsys.readouterr().out == "No problems found, so allymend.patch is empty.\n"
    assert (tmp_path / "allymend.patch").read_bytes() == b""
