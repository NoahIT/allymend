from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from allymend.core.models import Slot, Value


class ValueSource(Protocol):
    """Writes the text that slots need, for example with a language model."""

    def fill(self, slot: Slot) -> Value:
        """Write the text a slot needs.

        Raises:
            CannotFixError: The text can't or shouldn't be written without a person, for
                example because an image looks decorative.
        """
        ...
