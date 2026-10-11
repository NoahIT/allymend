from __future__ import annotations

import html
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

from allymend.core.models import Edit
from allymend.errors import CannotFixError
from allymend.fixers.tags import start_tag_attributes
from allymend.fixers.text import check_text

if TYPE_CHECKING:
    from collections.abc import Mapping

    from allymend.core.models import SourceLocation

type Role = Literal["link", "button", "field"]

_NAMING_ATTRIBUTES = ("aria-label", "aria-labelledby", "title")


@dataclass(frozen=True, slots=True)
class _Rules:
    redundant: re.Pattern[str] | None
    vague: frozenset[str]
    purpose: str


_ROLES: Mapping[str, _Rules] = MappingProxyType(
    {
        "link": _Rules(
            redundant=re.compile(r"link\b", re.IGNORECASE),
            vague=frozenset(
                {
                    "click",
                    "click here",
                    "go",
                    "here",
                    "learn more",
                    "more",
                    "read more",
                    "this link",
                }
            ),
            purpose="where the link goes",
        ),
        "button": _Rules(
            redundant=re.compile(r"button\b", re.IGNORECASE),
            vague=frozenset({"click", "click here", "go", "here", "press", "tap"}),
            purpose="what the button does",
        ),
        "field": _Rules(
            redundant=None,
            vague=frozenset(
                {"choose", "enter", "enter text", "field", "input", "select", "text", "type here"}
            ),
            purpose="what the field is for",
        ),
    }
)


def check_name(text: str, max_length: int, role: Role) -> str:
    """Return ``text`` with its whitespace collapsed, if it can name an element with ``role``.

    Raises:
        CannotFixError: The text is empty, longer than ``max_length``, contains control
            characters, starts with the role of a link or button, which screen readers already
            say, or is too vague to tell people what the element is for, like "click here".
    """
    rules = _ROLES[role]
    cleaned = check_text(text, max_length, f"{role} name")
    if rules.redundant is not None and rules.redundant.match(cleaned):
        raise CannotFixError(
            f'the suggested {role} name starts with "{role}", which screen readers already say'
        )
    if cleaned.lower().rstrip(".!:") in rules.vague:
        raise CannotFixError(f"the suggested {role} name doesn't say {rules.purpose}")
    return cleaned


def check_name_tag(text: str, location: SourceLocation, tag: str) -> None:
    """Make sure the ``tag`` element at ``location`` can be named, before anyone writes a name.

    Raises:
        CannotFixError: There is no ``tag`` start tag at ``location``, or it already has an
            ``aria-label``, ``aria-labelledby`` or ``title``, which a person should look at.
    """
    _label_position(text, location, tag)


def fix_name(text: str, location: SourceLocation, tag: str, name: str) -> Edit:
    """Give the ``tag`` element at ``location`` a name with ``aria-label``.

    The attribute is added straight after the tag name, with ``name`` escaped for an attribute
    value.

    Raises:
        CannotFixError: For the reasons ``check_name_tag`` gives.
    """
    position = _label_position(text, location, tag)
    attribute = f' aria-label="{html.escape(name, quote=True)}"'
    return Edit(file=location.file, start=position, end=position, text=attribute)


def _label_position(text: str, location: SourceLocation, tag: str) -> int:
    start = re.compile(rf"<{re.escape(tag)}(?=[\t\n\f\r />])", re.IGNORECASE)
    if not start.match(text, location.offset):
        raise CannotFixError(
            f"{location.file} changed after the scan: there is no <{tag}> tag at line "
            f"{location.line}, column {location.column}"
        )
    name_end = location.offset + 1 + len(tag)
    for name, *_ in start_tag_attributes(text, name_end):
        if name in _NAMING_ATTRIBUTES:
            raise CannotFixError(
                f"the <{tag}> tag in {location.file} already has {name}; a person should check it"
            )
    return name_end
