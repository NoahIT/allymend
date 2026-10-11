import json
from collections.abc import Callable
from pathlib import Path

import pytest

from allymend.cli import EXIT_CLEAN, EXIT_ERROR, EXIT_PROBLEMS, main
from allymend.scanner.site import serve

pytestmark = pytest.mark.browser


def test_reports_problems_and_exits_with_1(
    tmp_path: Path, write_page: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    write_page("index.html", lang=None)
    write_page("about.html")

    assert main(["scan", str(tmp_path)]) == EXIT_PROBLEMS

    lines = capsys.readouterr().out.splitlines()
    assert "index.html: 1 problem from 1 rule" in lines
    assert "  1. Page language is not set (1 element)" in lines
    assert "     axe-core rule html-has-lang, impact serious" in lines
    assert "about.html: no problems found" in lines
    assert "Summary: 1 problem on 1 of 2 pages." in lines


def test_folder_scan_shows_source_lines(
    tmp_path: Path, write_page: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    write_page("index.html", lang=None)
    assert main(["scan", str(tmp_path)]) == EXIT_PROBLEMS
    assert "     Elements: line 1, column 16" in capsys.readouterr().out.splitlines()


def test_clean_folder_exits_with_0(
    tmp_path: Path, write_page: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    write_page("index.html")
    assert main(["scan", str(tmp_path)]) == EXIT_CLEAN
    assert "Summary: 0 problems on 0 of 1 page." in capsys.readouterr().out


def test_writes_json_to_a_file(
    tmp_path: Path, write_page: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    site = tmp_path / "site"
    write_page("site/index.html", lang=None)
    report = tmp_path / "report.json"

    code = main(["scan", str(site), "--format", "json", "--output", str(report)])

    assert code == EXIT_PROBLEMS
    document = json.loads(report.read_text(encoding="utf-8"))
    [page] = document["pages"]
    assert page["page"] == "index.html"
    assert [o["rule_id"] for o in page["occurrences"]] == ["html-has-lang"]
    assert capsys.readouterr().err.splitlines() == [
        "allymend: scanning 1 of 1: index.html",
        f"allymend: wrote {report}",
    ]


def test_writes_markdown(
    tmp_path: Path, write_page: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    write_page("index.html", lang=None)
    assert main(["scan", str(tmp_path), "--format", "markdown"]) == EXIT_PROBLEMS
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "# Accessibility scan"
    assert "| index.html | 1 | html-has-lang (1) |" in lines
    assert "| Page language is not set | html-has-lang | auto | serious | 3.1.1 | 1 | 1 |" in lines


def test_scans_several_urls(
    tmp_path: Path, write_page: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    write_page("index.html")
    write_page("about.html", lang=None)
    with serve(tmp_path) as base_url:
        code = main(["scan", f"{base_url}index.html", f"{base_url}about.html"])
    assert code == EXIT_PROBLEMS
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "Scanned 2 pages with axe-core 4.13.0."
    assert f"{base_url}index.html: no problems found" in lines
    assert f"{base_url}about.html: 1 problem from 1 rule" in lines


def test_scans_urls_listed_in_a_file(
    tmp_path: Path, write_page: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    write_page("index.html")
    write_page("about.html", lang=None)
    targets = tmp_path / "targets.txt"
    with serve(tmp_path) as base_url:
        targets.write_text(
            f"# pages to scan\n{base_url}index.html\n\n{base_url}about.html\n", encoding="utf-8"
        )
        code = main(["scan", f"@{targets}"])
    assert code == EXIT_PROBLEMS
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "Scanned 2 pages with axe-core 4.13.0."
    assert f"{base_url}about.html: 1 problem from 1 rule" in lines


def test_page_that_cannot_be_scanned_exits_with_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with serve(tmp_path) as base_url:
        url = f"{base_url}missing.html"
        code = main(["scan", url])
    assert code == EXIT_ERROR
    captured = capsys.readouterr()
    assert f"{url}: could not be scanned (HTTP 404)" in captured.out
    assert captured.err.splitlines() == [
        f"allymend: scanning 1 of 1: {url}",
        f"allymend: could not scan {url}: HTTP 404",
    ]


def test_quiet_shows_only_warnings(
    tmp_path: Path, write_page: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    write_page("index.html")
    report = tmp_path / "report.md"
    with serve(tmp_path) as base_url:
        missing = f"{base_url}missing.html"
        code = main(["scan", f"{base_url}index.html", missing, "--quiet", "--output", str(report)])
    assert code == EXIT_ERROR
    assert capsys.readouterr().err == f"allymend: could not scan {missing}: HTTP 404\n"
