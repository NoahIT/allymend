from __future__ import annotations

import html
import re
import unicodedata
from typing import TYPE_CHECKING

from allymend.core.models import Edit
from allymend.errors import CannotFixError
from allymend.fixers.tags import start_tag_attributes

if TYPE_CHECKING:
    from allymend.core.models import SourceLocation

_IMG_START = re.compile(r"<img(?=[\t\n\f\r />])", re.IGNORECASE)
_REDUNDANT = re.compile(r"(image|picture|photo|photograph|graphic|icon) of\b", re.IGNORECASE)


def check_alt_text(text: str, max_length: int) -> str:
    """Return ``text`` with its whitespace collapsed, if it can be used as alt text.

    Raises:
        CannotFixError: The text is empty, longer than ``max_length``, starts with words like
            "image of" that screen readers already say, or contains control characters.
    """
    cleaned = " ".join(text.split())
    if not cleaned:
        raise CannotFixError("the suggested alt text is empty")
    if len(cleaned) > max_length:
        raise CannotFixError(f"the suggested alt text is longer than {max_length} characters")
    if _REDUNDANT.match(cleaned):
        raise CannotFixError(
            'the suggested alt text starts with words like "image of", which screen readers '
            "already say"
        )
    if any(unicodedata.category(character) == "Cc" for character in cleaned):
        raise CannotFixError("the suggested alt text contains control characters")
    return cleaned


def fix_image_alt(text: str, location: SourceLocation, alt: str) -> Edit:
    """Give an ``img`` element alt text.

    ``location`` is where the scan traced the ``img`` element in ``text``. The attribute is
    added straight after the tag name, with ``alt`` escaped for an attribute value.

    Raises:
        CannotFixError: There is no ``img`` start tag at ``location``, or it already has an
            ``alt`` attribute.
    """
    if not _IMG_START.match(text, location.offset):
        raise CannotFixError(
            f"{location.file} changed after the scan: there is no <img> tag at line "
            f"{location.line}, column {location.column}"
        )
    name_end = location.offset + len("<img")
    if any(name == "alt" for name, *_ in start_tag_attributes(text, name_end)):
        raise CannotFixError(f"the <img> tag in {location.file} already has an alt attribute")
    attribute = f' alt="{html.escape(alt, quote=True)}"'
    return Edit(file=location.file, start=name_end, end=name_end, text=attribute)
