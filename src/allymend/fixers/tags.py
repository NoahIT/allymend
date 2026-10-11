from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

HTML_SPACE = "\t\n\f\r "


def start_tag_attributes(text: str, position: int) -> Iterator[tuple[str, int, int, str]]:
    """Yield the name, span and value of each attribute of a start tag, in order.

    ``position`` is just after the tag name. Names are lower-cased. Parsing follows the
    attribute states of the HTML tokenizer, without decoding character references.
    """
    length = len(text)
    while True:
        while position < length and text[position] in HTML_SPACE + "/":
            position += 1
        if position >= length or text[position] == ">":
            return
        start = position
        position += 1
        while position < length and text[position] not in HTML_SPACE + "/>=":
            position += 1
        name = text[start:position].lower()
        name_end = position
        while position < length and text[position] in HTML_SPACE:
            position += 1
        if position >= length or text[position] != "=":
            yield name, start, name_end, ""
            continue
        position += 1
        while position < length and text[position] in HTML_SPACE:
            position += 1
        if position < length and text[position] in "\"'":
            close = text.find(text[position], position + 1)
            if close == -1:
                return
            yield name, start, close + 1, text[position + 1 : close]
            position = close + 1
        else:
            value_start = position
            while position < length and text[position] not in HTML_SPACE + ">":
                position += 1
            yield name, start, position, text[value_start:position]
