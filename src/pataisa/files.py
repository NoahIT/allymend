from dataclasses import dataclass
from pathlib import Path

_BYTE_ORDER_MARKS = (
    (b"\xef\xbb\xbf", "utf-8"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
)


@dataclass(frozen=True, slots=True)
class SourceText:
    """A source file's text and the encoding it was read with.

    Attributes:
        text: The decoded file, without newline translation. A byte order mark stays as the
            first character, so offsets count it.
        encoding: ``utf-8``, ``utf-16-le`` or ``utf-16-be``.
    """

    text: str
    encoding: str


def read_source(root: Path, relative: str) -> SourceText | None:
    """Read a file under ``root``, keeping its line endings and byte order mark.

    As in browsers, a UTF-16 byte order mark makes the file UTF-16; otherwise it is read as
    UTF-8. The offsets in ``SourceLocation`` and ``Edit`` index the text this returns. Returns
    None when the file is missing, can't be read or decoded, or lies outside ``root``.
    """
    base = root.resolve()
    path = (base / relative).resolve()
    if not path.is_relative_to(base):
        return None
    try:
        data = path.read_bytes()
        encoding = next(
            (name for mark, name in _BYTE_ORDER_MARKS if data.startswith(mark)), "utf-8"
        )
        return SourceText(text=data.decode(encoding), encoding=encoding)
    except (OSError, UnicodeDecodeError):
        return None
