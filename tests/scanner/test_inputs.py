from pathlib import Path

import pytest

from pataisa.errors import InvalidURLError, NoPagesError
from pataisa.scanner import scan_directory, scan_url


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "javascript:alert(1)", "example.com", "https://", "ftp://example.com"],
)
def test_scan_url_accepts_only_http_and_https(url: str) -> None:
    with pytest.raises(InvalidURLError):
        scan_url(url)


def test_scan_directory_needs_html_files(tmp_path: Path) -> None:
    (tmp_path / "styles.css").write_text("body {}", encoding="utf-8")
    with pytest.raises(NoPagesError):
        scan_directory(tmp_path)
