from __future__ import annotations

import re
from typing import TYPE_CHECKING

from allymend.core.models import Edit
from allymend.errors import CannotFixError
from allymend.fixers.tags import HTML_SPACE, start_tag_attributes

if TYPE_CHECKING:
    from allymend.core.models import SourceLocation

_LANGUAGE = re.compile(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*")
_HTML_START = re.compile(r"<html(?=[\t\n\f\r />])", re.IGNORECASE)


def check_language_tag(value: str) -> str:
    """Return ``value`` if it has the form of a language tag such as ``en`` or ``en-GB``.

    Only the form is checked, which is enough to keep the value safe inside an attribute.

    Raises:
        ValueError: ``value`` doesn't have that form.
    """
    if not _LANGUAGE.fullmatch(value):
        raise ValueError(f"{value!r} is not a language tag such as en or en-GB")
    return value


def fix_html_has_lang(text: str, location: SourceLocation, language: str) -> Edit:
    """Give the page's ``html`` element a ``lang`` attribute.

    ``location`` is where the scan traced the ``html`` element in ``text``. The attribute is
    added straight after the tag name, or replaces a ``lang`` attribute that is empty.

    Raises:
        ValueError: ``language`` is not a language tag such as ``en`` or ``en-GB``.
        CannotFixError: There is no ``html`` start tag at ``location``, or it already has a
            language.
    """
    check_language_tag(language)
    if not _HTML_START.match(text, location.offset):
        raise CannotFixError(
            f"{location.file} changed after the scan: there is no <html> tag at line "
            f"{location.line}, column {location.column}"
        )
    attribute = f'lang="{language}"'
    name_end = location.offset + len("<html")
    for name, start, end, value in start_tag_attributes(text, name_end):
        if name != "lang":
            continue
        if value.strip(HTML_SPACE):
            raise CannotFixError(f"the <html> tag in {location.file} already has a language")
        return Edit(file=location.file, start=start, end=end, text=attribute)
    return Edit(file=location.file, start=name_end, end=name_end, text=f" {attribute}")
