import logging
import sys
from pathlib import Path

import pytest

from allymend import __version__
from allymend.cli import EXIT_ERROR, main
from allymend.llm.claude import DEFAULT_MODEL


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        main(["--version"])
    assert stop.value.code == 0
    assert capsys.readouterr().out == f"allymend {__version__}\n"


def test_scan_needs_a_target() -> None:
    with pytest.raises(SystemExit) as stop:
        main(["scan"])
    assert stop.value.code == EXIT_ERROR


@pytest.mark.parametrize("timeout", ["0", "-5", "soon"])
def test_timeout_must_be_a_positive_number(tmp_path: Path, timeout: str) -> None:
    with pytest.raises(SystemExit) as stop:
        main(["scan", str(tmp_path), "--timeout", timeout])
    assert stop.value.code == EXIT_ERROR


def test_accepts_a_positive_timeout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["scan", str(tmp_path), "--timeout", "2.5"]) == EXIT_ERROR
    assert "no HTML files found" in capsys.readouterr().err


@pytest.mark.parametrize("target", ["example.com", "missing-folder"])
def test_rejects_targets_that_are_neither_folders_nor_urls(
    target: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["scan", target]) == EXIT_ERROR
    assert capsys.readouterr().err == (
        f"allymend: {target} is neither a folder nor an http or https URL\n"
    )


@pytest.mark.parametrize(
    "extra", ["https://example.com/", "second-folder"], ids=["folder-and-url", "two-folders"]
)
def test_scans_either_one_folder_or_urls(
    tmp_path: Path, extra: str, capsys: pytest.CaptureFixture[str]
) -> None:
    second = tmp_path / "second-folder"
    second.mkdir()
    target = extra if extra.startswith("https://") else str(second)
    assert main(["scan", str(tmp_path), target]) == EXIT_ERROR
    assert capsys.readouterr().err == (
        "allymend: scan either one folder or one or more URLs, not both\n"
    )


def test_reads_targets_from_a_file_and_skips_comments_and_blank_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    targets = tmp_path / "targets.txt"
    targets.write_text("# public pages\n\n  missing-folder  \n", encoding="utf-8")
    assert main(["scan", f"@{targets}"]) == EXIT_ERROR
    assert capsys.readouterr().err == (
        "allymend: missing-folder is neither a folder nor an http or https URL\n"
    )


def test_reports_a_folder_without_html_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["scan", str(tmp_path)]) == EXIT_ERROR
    assert "no HTML files found" in capsys.readouterr().err


@pytest.mark.parametrize("target", ["https://example.com/", "missing-folder"])
def test_fix_needs_a_folder(target: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fix", target]) == EXIT_ERROR
    assert capsys.readouterr().err == (
        f"allymend: {target} is not a folder; fixes need the site's source files\n"
    )


def test_fix_needs_the_folder_inside_the_current_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    site = tmp_path / "site"
    work = tmp_path / "work"
    site.mkdir()
    work.mkdir()
    monkeypatch.chdir(work)
    assert main(["fix", str(site)]) == EXIT_ERROR
    assert capsys.readouterr().err == (
        f"allymend: {site} is outside the current folder; run allymend fix from a folder that "
        "contains it, so the patch applies from there\n"
    )


@pytest.mark.parametrize("language", ["English", "en_GB", 'en"'])
def test_fix_rejects_a_language_that_is_not_a_tag(
    tmp_path: Path, language: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stop:
        main(["fix", str(tmp_path), "--lang", language])
    assert stop.value.code == EXIT_ERROR
    assert "is not a language tag such as en or en-GB" in capsys.readouterr().err


def test_show_payload_needs_alt_text(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        main(["fix", str(tmp_path), "--show-payload"])
    assert stop.value.code == EXIT_ERROR
    assert "--show-payload needs --alt-text" in capsys.readouterr().err


def test_alt_text_without_credentials_stops_before_scanning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("ANTHROPIC_CONFIG_DIR", raising=False)
    for name in ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "APPDATA"):
        monkeypatch.setenv(name, str(tmp_path))
    monkeypatch.chdir(tmp_path)
    assert main(["fix", ".", "--alt-text", "claude"]) == EXIT_ERROR
    assert capsys.readouterr().err.startswith("allymend: no Anthropic credentials were found; ")


def test_alt_text_without_the_extra_says_how_to_install_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(sys.modules, "allymend.llm.claude", None)
    monkeypatch.chdir(tmp_path)
    assert main(["fix", ".", "--alt-text", "claude"]) == EXIT_ERROR
    assert capsys.readouterr().err == (
        "allymend: Claude support isn't installed; install it with: "
        'pip install "allymend[claude]"\n'
    )


def test_the_documented_default_model_is_the_real_one(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["fix", "--help"])
    assert f"(default:{DEFAULT_MODEL})" in "".join(capsys.readouterr().out.split())


def test_leaves_logging_as_it_was(tmp_path: Path) -> None:
    package = logging.getLogger("allymend")
    before = (package.level, list(package.handlers))
    main(["scan", str(tmp_path)])
    assert (package.level, package.handlers) == before
