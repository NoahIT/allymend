from __future__ import annotations

import difflib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pataisa.core.models import Edit

_NO_NEWLINE = "\\ No newline at end of file\n"


def apply_edits(text: str, edits: Iterable[Edit]) -> str:
    """Apply edits to the text of one file.

    Every offset refers to the original text, so the order the edits are given in doesn't
    matter.

    Raises:
        ValueError: The edits are for more than one file, an edit lies outside the text, or two
            edits overlap or insert at the same place.
    """
    ordered = sorted(edits, key=lambda edit: (edit.start, edit.end))
    if len({edit.file for edit in ordered}) > 1:
        raise ValueError("edits for more than one file can't be applied to one text")
    parts: list[str] = []
    position = 0
    previous: Edit | None = None
    for edit in ordered:
        if not 0 <= edit.start <= edit.end <= len(text):
            raise ValueError(
                f"edit {edit.start}-{edit.end} lies outside the {len(text)} characters "
                f"of {edit.file}"
            )
        if previous is not None and (edit.start < previous.end or edit.start == previous.start):
            raise ValueError(
                f"edits at {previous.start}-{previous.end} and {edit.start}-{edit.end} "
                f"in {edit.file} overlap"
            )
        parts += (text[position : edit.start], edit.text)
        position = edit.end
        previous = edit
    parts.append(text[position:])
    return "".join(parts)


def unified_diff(file: str, before: str, after: str) -> str:
    """Return the change from ``before`` to ``after`` as a unified diff.

    The diff applies with ``git apply`` or ``patch -p1`` from the folder ``file`` is relative
    to. Line endings are kept exactly as they are in the file. Returns an empty string when
    nothing changed.
    """
    lines = difflib.unified_diff(
        _lines(before), _lines(after), fromfile=f"a/{file}", tofile=f"b/{file}"
    )
    return "".join(line if line.endswith("\n") else f"{line}\n{_NO_NEWLINE}" for line in lines)


def _lines(text: str) -> list[str]:
    *complete, last = text.split("\n")
    return [f"{line}\n" for line in complete] + ([last] if last else [])
