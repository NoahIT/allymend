from pathlib import Path

import pytest

from pataisa import __version__
from pataisa.cli import EXIT_ERROR, main


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        main(["--version"])
    assert stop.value.code == 0
    assert capsys.readouterr().out == f"pataisa {__version__}\n"


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
        f"pataisa: {target} is neither a folder nor an http or https URL\n"
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
        "pataisa: scan either one folder or one or more URLs, not both\n"
    )


def test_reads_targets_from_a_file_and_skips_comments_and_blank_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    targets = tmp_path / "targets.txt"
    targets.write_text("# public pages\n\n  missing-folder  \n", encoding="utf-8")
    assert main(["scan", f"@{targets}"]) == EXIT_ERROR
    assert capsys.readouterr().err == (
        "pataisa: missing-folder is neither a folder nor an http or https URL\n"
    )


def test_reports_a_folder_without_html_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["scan", str(tmp_path)]) == EXIT_ERROR
    assert "no HTML files found" in capsys.readouterr().err
