import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from allymend.cli import EXIT_CLEAN, EXIT_PROBLEMS, main
from allymend.core.models import Edit, SourceLocation
from allymend.fixers import FixOptions, fix_html_has_lang

pytestmark = pytest.mark.browser

GIT = shutil.which("git")


@pytest.fixture
def site(tmp_path: Path, write_page: Callable[..., Path], monkeypatch: pytest.MonkeyPatch) -> Path:
    write_page("site/index.html", lang=None)
    write_page("site/shop/mug.html", '<img src="mug.png">')
    monkeypatch.chdir(tmp_path)
    return tmp_path / "site"


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
        "there's no automatic fix for this rule yet"
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
    def hiding(text: str, location: SourceLocation, options: FixOptions) -> Edit:
        edit = fix_html_has_lang(text, location, options.language or "en")
        return edit.model_copy(update={"text": f'{edit.text} aria-hidden="true"'})

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
