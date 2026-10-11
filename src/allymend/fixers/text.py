from __future__ import annotations

import unicodedata

from allymend.errors import CannotFixError


def check_text(text: str, max_length: int, what: str) -> str:
    """Return ``text`` with its whitespace collapsed, if it can be put into a page.

    Raises:
        CannotFixError: The text is empty, longer than ``max_length``, or contains control
            characters. The reason calls the text ``what``, for example "alt text".
    """
    cleaned = " ".join(text.split())
    if not cleaned:
        raise CannotFixError(f"the suggested {what} is empty")
    if len(cleaned) > max_length:
        raise CannotFixError(f"the suggested {what} is longer than {max_length} characters")
    if any(unicodedata.category(character) == "Cc" for character in cleaned):
        raise CannotFixError(f"the suggested {what} contains control characters")
    return cleaned
