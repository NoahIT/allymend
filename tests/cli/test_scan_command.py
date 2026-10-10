import json
from collections.abc import Callable
from pathlib import Path

import pytest

from pataisa.cli import EXIT_CLEAN, EXIT_ERROR, EXIT_PROBLEMS, main
from pataisa.scanner.site import serve

pytestmark = pytest.mark.browser


def test_reports_problems_and_exits_with_1(
    tmp_path: Path, write_page: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    write_page("index.html", lang=None)
    write_page("about.html")

    assert main(["scan", str(tmp_path)]) == EXIT_PROBLEMS

    lines = capsys.readouterr().out.splitlines()
    assert "index.html: 1 problem" in lines
    assert "     rule html-has-lang; impact serious; WCAG 3.1.1" in lines
    assert "about.html: no problems found" in lines
    assert "Summary: 1 problem on 1 of 2 pages." in lines


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
    assert capsys.readouterr().err == f"pataisa: wrote {report}\n"


def test_page_that_cannot_be_scanned_exits_with_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with serve(tmp_path) as base_url:
        code = main(["scan", f"{base_url}missing.html"])
    assert code == EXIT_ERROR
    assert f"{base_url}missing.html: could not be scanned (HTTP 404)" in capsys.readouterr().out
