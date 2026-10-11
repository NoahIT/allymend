from __future__ import annotations

import html
import re
from typing import TYPE_CHECKING

from allymend.core.models import Edit
from allymend.errors import CannotFixError
from allymend.fixers.tags import start_tag_attributes
from allymend.fixers.text import check_text

if TYPE_CHECKING:
    from allymend.core.models import SourceLocation

_A_START = re.compile(r"<a(?=[\t\n\f\r />])", re.IGNORECASE)
_NAMING_ATTRIBUTES = ("aria-label", "aria-labelledby", "title")
_REDUNDANT = re.compile(r"link\b", re.IGNORECASE)
_VAGUE = frozenset(
    {"click", "click here", "go", "here", "learn more", "more", "read more", "this link"}
)


def check_link_name(text: str, max_length: int) -> str:
    """Return ``text`` with its whitespace collapsed, if it can be used as a link's name.

    Raises:
        CannotFixError: The text is empty, longer than ``max_length``, contains control
            characters, starts with the word "link" that screen readers already say, or
            doesn't say where the link goes, like "click here".
    """
    cleaned = check_text(text, max_length, "link name")
    if _REDUNDANT.match(cleaned):
        raise CannotFixError(
            'the suggested link name starts with "link", which screen readers already say'
        )
    if cleaned.lower().rstrip(".!:") in _VAGUE:
        raise CannotFixError("the suggested link name doesn't say where the link goes")
    return cleaned


def check_link_tag(text: str, location: SourceLocation) -> None:
    """Make sure the link at ``location`` can be given a name, before anyone writes one.

    Raises:
        CannotFixError: There is no ``a`` start tag at ``location``, or it already has an
            ``aria-label``, ``aria-labelledby`` or ``title``, which a person should look at.
    """
    _label_position(text, location)


def fix_link_name(text: str, location: SourceLocation, name: str) -> Edit:
    """Give an ``a`` element a name with ``aria-label``.

    ``location`` is where the scan traced the ``a`` element in ``text``. The attribute is
    added straight after the tag name, with ``name`` escaped for an attribute value.

    Raises:
        CannotFixError: For the reasons ``check_link_tag`` gives.
    """
    position = _label_position(text, location)
    attribute = f' aria-label="{html.escape(name, quote=True)}"'
    return Edit(file=location.file, start=position, end=position, text=attribute)


def _label_position(text: str, location: SourceLocation) -> int:
    if not _A_START.match(text, location.offset):
        raise CannotFixError(
            f"{location.file} changed after the scan: there is no <a> tag at line "
            f"{location.line}, column {location.column}"
        )
    name_end = location.offset + len("<a")
    for name, *_ in start_tag_attributes(text, name_end):
        if name in _NAMING_ATTRIBUTES:
            raise CannotFixError(
                f"the <a> tag in {location.file} already has {name}; a person should check it"
            )
    return name_end
