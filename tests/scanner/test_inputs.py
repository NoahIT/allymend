from pathlib import Path

import pytest

from pataisa.errors import InvalidURLError, NoPagesError
from pataisa.scanner import scan_directory, scan_url, scan_urls


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "javascript:alert(1)", "example.com", "https://", "ftp://example.com"],
)
def test_scan_url_accepts_only_http_and_https(url: str) -> None:
    with pytest.raises(InvalidURLError):
        scan_url(url)


def test_scan_urls_checks_every_url_before_scanning() -> None:
    with pytest.raises(InvalidURLError) as error:
        scan_urls(["https://example.com/", "file:///etc/passwd"])
    assert error.value.url == "file:///etc/passwd"


def test_scan_urls_with_no_urls_scans_nothing() -> None:
    assert scan_urls([]).pages == ()


def test_scan_directory_needs_html_files(tmp_path: Path) -> None:
    (tmp_path / "styles.css").write_text("body {}", encoding="utf-8")
    with pytest.raises(NoPagesError):
        scan_directory(tmp_path)
