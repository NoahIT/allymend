from pathlib import Path

import pytest

from allymend.files import SourceText, read_source

TEXT = "<!doctype html>\r\n<p>Caf\xe9 \U0001f642</p>\n"


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (TEXT.encode("utf-8"), SourceText(text=TEXT, encoding="utf-8")),
        (b"\xef\xbb\xbf" + TEXT.encode("utf-8"), SourceText("\ufeff" + TEXT, "utf-8")),
        (b"\xff\xfe" + TEXT.encode("utf-16-le"), SourceText("\ufeff" + TEXT, "utf-16-le")),
        (b"\xfe\xff" + TEXT.encode("utf-16-be"), SourceText("\ufeff" + TEXT, "utf-16-be")),
    ],
    ids=["utf-8", "utf-8-with-mark", "utf-16-le", "utf-16-be"],
)
def test_reads_text_keeping_line_endings_and_the_byte_order_mark(
    tmp_path: Path, data: bytes, expected: SourceText
) -> None:
    (tmp_path / "index.html").write_bytes(data)
    assert read_source(tmp_path, "index.html") == expected


@pytest.mark.parametrize(
    ("relative", "data"),
    [
        ("index.html", TEXT.encode("cp1252", errors="replace")),
        ("index.html", TEXT.encode("utf-16-le")),
        ("index.html", b"\xff\xfe<"),
        ("missing.html", None),
        ("../outside.html", TEXT.encode("utf-8")),
    ],
    ids=["windows-1252", "utf-16-without-a-mark", "odd-utf-16", "missing", "outside-the-folder"],
)
def test_returns_none_for_files_it_cannot_safely_read(
    tmp_path: Path, relative: str, data: bytes | None
) -> None:
    root = tmp_path / "site"
    root.mkdir()
    if data is not None:
        (root / relative).write_bytes(data)
    assert read_source(root, relative) is None
