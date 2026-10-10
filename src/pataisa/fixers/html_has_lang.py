from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pataisa.core.models import Edit
from pataisa.errors import CannotFixError

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pataisa.core.models import SourceLocation

_LANGUAGE = re.compile(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*")
_HTML_START = re.compile(r"<html(?=[\t\n\f\r />])", re.IGNORECASE)
_SPACE = "\t\n\f\r "


def fix_html_has_lang(text: str, location: SourceLocation, language: str) -> Edit:
    """Give the page's ``html`` element a ``lang`` attribute.

    ``location`` is where the scan traced the ``html`` element in ``text``. The attribute is
    added straight after the tag name, or replaces a ``lang`` attribute that is empty.

    Raises:
        ValueError: ``language`` is not a language tag such as ``en`` or ``en-GB``.
        CannotFixError: There is no ``html`` start tag at ``location``, or it already has a
            language.
    """
    if not _LANGUAGE.fullmatch(language):
        raise ValueError(f"{language!r} is not a language tag such as en or en-GB")
    if not _HTML_START.match(text, location.offset):
        raise CannotFixError(
            f"{location.file} changed after the scan: there is no <html> tag at line "
            f"{location.line}, column {location.column}"
        )
    attribute = f'lang="{language}"'
    name_end = location.offset + len("<html")
    for name, start, end, value in _attributes(text, name_end):
        if name != "lang":
            continue
        if value.strip(_SPACE):
            raise CannotFixError(f"the <html> tag in {location.file} already has a language")
        return Edit(file=location.file, start=start, end=end, text=attribute)
    return Edit(file=location.file, start=name_end, end=name_end, text=f" {attribute}")


def _attributes(text: str, position: int) -> Iterator[tuple[str, int, int, str]]:
    """Yield the name, span and value of each attribute of a start tag, in order.

    ``position`` is just after the tag name. Names are lower-cased. Parsing follows the
    attribute states of the HTML tokenizer, without decoding character references.
    """
    length = len(text)
    while True:
        while position < length and text[position] in _SPACE + "/":
            position += 1
        if position >= length or text[position] == ">":
            return
        start = position
        position += 1
        while position < length and text[position] not in _SPACE + "/>=":
            position += 1
        name = text[start:position].lower()
        name_end = position
        while position < length and text[position] in _SPACE:
            position += 1
        if position >= length or text[position] != "=":
            yield name, start, name_end, ""
            continue
        position += 1
        while position < length and text[position] in _SPACE:
            position += 1
        if position < length and text[position] in "\"'":
            close = text.find(text[position], position + 1)
            if close == -1:
                return
            yield name, start, close + 1, text[position + 1 : close]
            position = close + 1
        else:
            value_start = position
            while position < length and text[position] not in _SPACE + ">":
                position += 1
            yield name, start, position, text[value_start:position]
