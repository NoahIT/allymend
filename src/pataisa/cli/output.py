from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pataisa import __version__
from pataisa.core.rules import CRITERIA, RULES, Remediability
from pataisa.core.summary import count_by_rule

if TYPE_CHECKING:
    from pydantic.main import IncEx

    from pataisa.core.models import PageResult, ScanResult
    from pataisa.core.summary import RuleCount

SCHEMA_VERSION = 1
LIMITS_NOTE = (
    "Automated checks find only some accessibility problems. "
    "Test with people who use assistive technology too."
)
_SHOWN_ELEMENTS = 5
_FIX_TYPES = {
    Remediability.AUTO: "can be automated",
    Remediability.SUGGESTED: "a fix can be suggested, but a person should review it",
    Remediability.HUMAN: "needs a person to decide",
}


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


def render_markdown(result: ScanResult) -> str:
    """Render a scan as Markdown, with the problems on each page grouped by rule."""
    lines = [
        "# Accessibility scan",
        "",
        f"Scanned {_count(len(result.pages), 'page')} with axe-core {result.axe_version}.",
        "",
        "| Page | Problems | Most frequent rules |",
        "| --- | ---: | --- |",
    ]
    lines.extend(_overview_row(page) for page in result.pages)
    for page in result.pages:
        if not page.occurrences:
            continue
        mapped = any(occurrence.source is not None for occurrence in page.occurrences)
        header = "| Problem | Rule | Fix type | Impact | WCAG | Elements |"
        divider = "| --- | --- | --- | --- | --- | ---: |"
        if mapped:
            header += " Lines |"
            divider += " --- |"
        lines.extend(["", f"## {_escape(page.page)}", "", header, divider])
        lines.extend(
            _markdown_rule_row(count, with_lines=mapped)
            for count in count_by_rule(page.occurrences)
        )
    lines.extend(["", _summary(result), "", LIMITS_NOTE])
    return "\n".join(lines) + "\n"


def _overview_row(page: PageResult) -> str:
    if page.error is not None:
        return f"| {_escape(page.page)} | not scanned | {_escape(page.error)} |"
    top = count_by_rule(page.occurrences)[:3]
    rules = ", ".join(f"{count.rule_id} ({count.elements})" for count in top)
    return f"| {_escape(page.page)} | {len(page.occurrences)} | {rules} |"


def _markdown_rule_row(count: RuleCount, *, with_lines: bool) -> str:
    rule = RULES.get(count.rule_id)
    title = rule.title if rule is not None else count.summary
    fix_type = rule.remediability if rule is not None else ""
    row = (
        f"| {_escape(title)} | {count.rule_id} | {fix_type} | {count.impact or ''} | "
        f"{', '.join(count.wcag)} | {count.elements} |"
    )
    if with_lines:
        row += f" {_shortened([str(s.line) for s in count.sources if s is not None])} |"
    return row


def _shortened(items: list[str], separator: str = ", ") -> str:
    hidden = len(items) - _SHOWN_ELEMENTS
    shown = separator.join(items[:_SHOWN_ELEMENTS])
    return shown + (f"{separator}and {hidden} more" if hidden > 0 else "")


def _escape(text: str) -> str:
    replacements = {"&": "&amp;", "<": "&lt;", ">": "&gt;", "|": "\\|", "\n": " "}
    return "".join(replacements.get(character, character) for character in text)


def _page_lines(page: PageResult) -> list[str]:
    if page.error is not None:
        return [f"{page.page}: could not be scanned ({page.error})"]
    if not page.occurrences:
        return [f"{page.page}: no problems found"]
    counts = count_by_rule(page.occurrences)
    lines = [
        f"{page.page}: {_count(len(page.occurrences), 'problem')} from "
        f"{_count(len(counts), 'rule')}"
    ]
    for number, count in enumerate(counts, start=1):
        lines.append("")
        lines.extend(_rule_lines(number, count))
    return lines


def _rule_lines(number: int, count: RuleCount) -> list[str]:
    rule = RULES.get(count.rule_id)
    title = rule.title if rule is not None else count.summary
    lines = [f"  {number}. {title} ({_count(count.elements, 'element')})"]
    if rule is not None:
        lines.extend(
            [
                f"     Who it affects: {rule.affects}",
                f"     Why it matters: {rule.why}",
                f"     How to fix: {rule.fix}",
                f"     Fix type: {_FIX_TYPES[rule.remediability]}",
            ]
        )
    else:
        lines.append(f"     More information: {count.help_url}")
    lines.extend(f"     {_criterion(criterion)}" for criterion in count.wcag)
    impact = f", impact {count.impact}" if count.impact is not None else ""
    lines.append(f"     axe-core rule {count.rule_id}{impact}")
    elements = [
        target if source is None else f"line {source.line}, column {source.column}"
        for target, source in zip(count.targets, count.sources, strict=True)
    ]
    lines.append(f"     Elements: {_shortened(elements, '; ')}")
    return lines


def _criterion(number: str) -> str:
    criterion = CRITERIA.get(number)
    if criterion is None:
        return f"WCAG {number}"
    return f"WCAG {number} {criterion.name} (level {criterion.level}): {criterion.url}"


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
