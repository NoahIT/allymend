from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from justhtml import JustHTML, SelectorError

from allymend.core.models import Occurrence, PageResult, ScanResult, SourceLocation
from allymend.files import read_source

if TYPE_CHECKING:
    from pathlib import Path

    from justhtml import QueryMatch

_BYTE_ORDER_MARK = "\ufeff"
_TAG_NAME = re.compile(r"<([A-Za-z][A-Za-z0-9-]*)")
_IDENTIFYING_ATTRIBUTES = ("id", "src", "href", "name")


class HtmlSource:
    """An HTML file parsed with the position of every element's start tag."""

    def __init__(self, text: str, file: str) -> None:
        self.file = file
        # justhtml counts offsets after the byte order mark; the file text still contains it.
        self._shift = 1 if text.startswith(_BYTE_ORDER_MARK) else 0
        self._document = JustHTML(text, track_node_locations=True, sanitize=False)

    def locate(self, occurrence: Occurrence) -> SourceLocation | None:
        """Find where the element an occurrence points to is written.

        The occurrence's selector is tried first: it must match exactly one element with the
        same tag name as the element in the browser. When it doesn't, for example because a
        script changed the element's classes, exactly one element with that tag must share the
        browser element's ``id``, ``src``, ``href`` or ``name``, tried in that order. Returns
        None when neither finds an element, or the element was inserted by the parser rather
        than read from the file.
        """
        tag = _tag_name(occurrence.html)
        if len(occurrence.target) != 1 or tag is None:
            return None
        found_by: Literal["selector", "attributes"] = "selector"
        element = self._by_selector(occurrence.target[0], tag)
        if element is None:
            found_by = "attributes"
            element = self._by_attributes(occurrence.html, tag)
        if element is None:
            return None
        line, column, offset = element.origin_line, element.origin_col, element.origin_offset
        if line is None or column is None or offset is None:
            return None
        return SourceLocation(
            file=self.file, line=line, column=column, offset=offset + self._shift, found_by=found_by
        )

    def _by_selector(self, selector: str, tag: str) -> QueryMatch | None:
        try:
            matches = self._document.root.query(selector)
        except SelectorError:
            return None
        return matches[0] if len(matches) == 1 and matches[0].name == tag else None

    def _by_attributes(self, html: str, tag: str) -> QueryMatch | None:
        rendered = next(iter(JustHTML(html, sanitize=False).root.query(tag)), None)
        if rendered is None:
            return None
        candidates = self._document.root.query(tag)
        for name in _IDENTIFYING_ATTRIBUTES:
            value = _attribute(rendered, name)
            if not value:
                continue
            same = [element for element in candidates if _attribute(element, name) == value]
            if len(same) == 1:
                return same[0]
        return None


def map_sources(root: Path, result: ScanResult) -> ScanResult:
    """Add source locations to the occurrences of a scan of the folder ``root``.

    Each page is read from ``root`` by its relative path with ``read_source``, so UTF-8 and
    UTF-16 with a byte order mark both work. Pages that can't be read or decoded, or lie
    outside ``root``, keep their occurrences without locations.
    """
    return result.model_copy(update={"pages": tuple(_map_page(root, p) for p in result.pages)})


def _map_page(root: Path, page: PageResult) -> PageResult:
    if not page.occurrences:
        return page
    read = read_source(root, page.page)
    if read is None:
        return page
    source = HtmlSource(read.text, page.page)
    located = tuple(o.model_copy(update={"source": source.locate(o)}) for o in page.occurrences)
    return page.model_copy(update={"occurrences": located})


def _attribute(element: QueryMatch, name: str) -> str | None:
    return (element.attrs or {}).get(name)


def _tag_name(html: str) -> str | None:
    match = _TAG_NAME.match(html)
    return match.group(1).lower() if match else None
