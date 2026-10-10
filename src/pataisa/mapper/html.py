from __future__ import annotations

import re
from typing import TYPE_CHECKING

from justhtml import JustHTML, SelectorError

from pataisa.core.models import Occurrence, PageResult, ScanResult, SourceLocation
from pataisa.files import read_source

if TYPE_CHECKING:
    from pathlib import Path

_BYTE_ORDER_MARK = "\ufeff"
_TAG_NAME = re.compile(r"<([A-Za-z][A-Za-z0-9-]*)")


class HtmlSource:
    """An HTML file parsed with the position of every element's start tag."""

    def __init__(self, text: str, file: str) -> None:
        self.file = file
        # justhtml counts offsets after the byte order mark; the file text still contains it.
        self._shift = 1 if text.startswith(_BYTE_ORDER_MARK) else 0
        self._document = JustHTML(text, track_node_locations=True, sanitize=False)

    def locate(self, occurrence: Occurrence) -> SourceLocation | None:
        """Find where the element an occurrence points to is written.

        Returns None unless exactly one element matches the occurrence's selector, it has the
        same tag name as the element in the browser, and the parser read it from the file
        rather than inserting it.
        """
        if len(occurrence.target) != 1:
            return None
        try:
            matches = list(self._document.root.query(occurrence.target[0]))
        except SelectorError:
            return None
        if len(matches) != 1:
            return None
        [element] = matches
        line, column, offset = element.origin_line, element.origin_col, element.origin_offset
        if line is None or column is None or offset is None:
            return None
        if element.name != _tag_name(occurrence.html):
            return None
        return SourceLocation(file=self.file, line=line, column=column, offset=offset + self._shift)


def map_sources(root: Path, result: ScanResult) -> ScanResult:
    """Add source locations to the occurrences of a scan of the folder ``root``.

    Each page is read from ``root`` by its relative path. Pages that cannot be read, are not
    valid UTF-8 or lie outside ``root`` keep their occurrences without locations.
    """
    return result.model_copy(update={"pages": tuple(_map_page(root, p) for p in result.pages)})


def _map_page(root: Path, page: PageResult) -> PageResult:
    if not page.occurrences:
        return page
    text = read_source(root, page.page)
    if text is None:
        return page
    source = HtmlSource(text, page.page)
    located = tuple(o.model_copy(update={"source": source.locate(o)}) for o in page.occurrences)
    return page.model_copy(update={"occurrences": located})


def _tag_name(html: str) -> str | None:
    match = _TAG_NAME.match(html)
    return match.group(1).lower() if match else None
