from pathlib import Path


def read_source(root: Path, relative: str) -> str | None:
    """Read a file under ``root`` as UTF-8, keeping its line endings and byte order mark.

    The offsets in ``SourceLocation`` and ``Edit`` index the text this returns. Returns None
    when the file is missing, can't be read, isn't valid UTF-8, or lies outside ``root``.
    """
    base = root.resolve()
    path = (base / relative).resolve()
    if not path.is_relative_to(base):
        return None
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
