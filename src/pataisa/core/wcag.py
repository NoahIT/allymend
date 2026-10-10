import re
from collections.abc import Iterable

_CRITERION_TAG = re.compile(r"wcag(\d)(\d)(\d+)")


def success_criteria(tags: Iterable[str]) -> tuple[str, ...]:
    """Turn axe-core tags such as ``wcag1410`` into success criteria such as ``1.4.10``."""
    return tuple(
        ".".join(match.groups())
        for tag in tags
        if (match := _CRITERION_TAG.fullmatch(tag)) is not None
    )
