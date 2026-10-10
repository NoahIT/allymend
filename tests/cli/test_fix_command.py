import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from pataisa.cli import EXIT_CLEAN, EXIT_PROBLEMS, main

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
        "Wrote fixes for 1 problem in 1 file to pataisa.patch.",
        "Review it, apply it from this folder with: git apply pataisa.patch",
    ]
    assert (
        "  shop/mug.html: Image has no text alternative (image-alt), 1 element: "
        "there's no automatic fix for this rule yet"
    ) in lines
    assert (
        Path("pataisa.patch")
        .read_text(encoding="utf-8")
        .startswith("--- a/site/index.html\n+++ b/site/index.html\n")
    )

    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    subprocess.run([GIT, "apply", "pataisa.patch"], check=True)  # noqa: S603  fixed arguments
    assert main(["scan", "site", "--quiet"]) == EXIT_PROBLEMS
    assert "index.html: no problems found" in capsys.readouterr().out.splitlines()


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
    assert capsys.readouterr().out == "No problems found, so pataisa.patch is empty.\n"
    assert (tmp_path / "pataisa.patch").read_bytes() == b""
