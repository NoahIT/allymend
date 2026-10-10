from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pataisa import __version__

if TYPE_CHECKING:
    from pydantic.main import IncEx

    from pataisa.core.models import PageResult, ScanResult

SCHEMA_VERSION = 1
LIMITS_NOTE = (
    "Automated checks find only some accessibility problems. "
    "Test with people who use assistive technology too."
)


def render_text(result: ScanResult) -> str:
    """Render a scan as plain text that reads the same in a terminal and a screen reader."""
    lines = [f"Scanned {_count(len(result.pages), 'page')} with axe-core {result.axe_version}.", ""]
    for page in result.pages:
        lines.extend(_page_lines(page))
        lines.append("")
    lines.extend([_summary(result), LIMITS_NOTE])
    return "\n".join(lines) + "\n"


def render_json(result: ScanResult, *, include_markup: bool = False) -> str:
    """Render a scan as versioned JSON. Element markup is left out unless asked for."""
    exclude: IncEx | None = (
        None if include_markup else {"pages": {"__all__": {"occurrences": {"__all__": {"html"}}}}}
    )
    document = {
        "schema_version": SCHEMA_VERSION,
        "pataisa_version": __version__,
        **result.model_dump(mode="json", exclude=exclude),
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def _page_lines(page: PageResult) -> list[str]:
    if page.error is not None:
        return [f"{page.page}: could not be scanned ({page.error})"]
    if not page.occurrences:
        return [f"{page.page}: no problems found"]
    lines = [f"{page.page}: {_count(len(page.occurrences), 'problem')}"]
    for number, occurrence in enumerate(page.occurrences, start=1):
        details = [f"rule {occurrence.rule_id}"]
        if occurrence.impact is not None:
            details.append(f"impact {occurrence.impact}")
        if occurrence.wcag:
            details.append(f"WCAG {', '.join(occurrence.wcag)}")
        lines.extend(
            [
                f"  {number}. {occurrence.summary}",
                f"     {'; '.join(details)}",
                f"     element: {' >> '.join(occurrence.target)}",
            ]
        )
    return lines


def _summary(result: ScanResult) -> str:
    problems = sum(len(page.occurrences) for page in result.pages)
    affected = sum(1 for page in result.pages if page.occurrences)
    failed = sum(1 for page in result.pages if page.error is not None)
    summary = (
        f"Summary: {_count(problems, 'problem')} on {affected} of "
        f"{_count(len(result.pages), 'page')}."
    )
    if failed:
        summary += f" {_count(failed, 'page')} could not be scanned."
    return summary


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"
