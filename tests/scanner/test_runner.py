import socket
from pathlib import Path

import pytest

from pataisa.errors import BrowserNotInstalledError
from pataisa.scanner import scan_directory, scan_url
from pataisa.scanner.site import serve

pytestmark = pytest.mark.browser

PIXEL = "data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=="


def write_page(root: Path, name: str, body: str, *, lang: str = ' lang="en"') -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"<!doctype html><html{lang}><head><meta charset='utf-8'><title>Test page</title></head>"
        f"<body><main><h1>Test page</h1>{body}</main></body></html>",
        encoding="utf-8",
    )


def unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


def test_finds_an_image_without_alt_text(tmp_path: Path) -> None:
    write_page(tmp_path, "index.html", f'<img src="{PIXEL}" width="40" height="40">')

    result = scan_directory(tmp_path)

    assert result.axe_version == "4.13.0"
    [page] = result.pages
    assert page.page == "index.html"
    assert page.error is None
    assert [(o.rule_id, o.target, o.wcag) for o in page.occurrences] == [
        ("image-alt", ("img",), ("1.1.1",))
    ]


def test_finds_a_missing_page_language(tmp_path: Path) -> None:
    write_page(tmp_path, "index.html", "<p>Hello</p>", lang="")
    [page] = scan_directory(tmp_path).pages
    assert [o.rule_id for o in page.occurrences] == ["html-has-lang"]


def test_a_clean_page_has_no_occurrences(tmp_path: Path) -> None:
    write_page(tmp_path, "index.html", f'<img src="{PIXEL}" alt="Company logo">')
    [page] = scan_directory(tmp_path).pages
    assert page.occurrences == ()
    assert page.error is None


def test_scans_every_page_including_subfolders(tmp_path: Path) -> None:
    write_page(tmp_path, "index.html", "<p>Home</p>")
    write_page(tmp_path, "shop/mug.html", f'<img src="{PIXEL}">')

    pages = scan_directory(tmp_path).pages

    assert [page.page for page in pages] == ["index.html", "shop/mug.html"]
    assert [o.rule_id for o in pages[1].occurrences] == ["image-alt"]


def test_scan_url_scans_a_page_over_http(tmp_path: Path) -> None:
    write_page(tmp_path, "index.html", f'<img src="{PIXEL}">')
    with serve(tmp_path) as base_url:
        url = f"{base_url}index.html"
        [page] = scan_url(url).pages
    assert page.page == url
    assert [o.rule_id for o in page.occurrences] == ["image-alt"]


def test_scan_url_reports_http_errors(tmp_path: Path) -> None:
    with serve(tmp_path) as base_url:
        [page] = scan_url(f"{base_url}missing.html").pages
    assert page.error == "HTTP 404"
    assert page.occurrences == ()


def test_scan_url_reports_unreachable_hosts() -> None:
    [page] = scan_url(f"http://127.0.0.1:{unused_port()}/").pages
    assert page.error is not None
    assert "ERR_CONNECTION_REFUSED" in page.error


def test_reports_a_missing_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_page(tmp_path, "index.html", "<p>Home</p>")
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "no-browsers"))
    with pytest.raises(BrowserNotInstalledError):
        scan_directory(tmp_path)
