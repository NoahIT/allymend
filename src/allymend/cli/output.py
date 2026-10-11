from __future__ import annotations

import base64
import json
from collections import Counter
from typing import TYPE_CHECKING, Any

from allymend import __version__
from allymend.core.rules import CRITERIA, RULES, Remediability
from allymend.core.summary import count_by_rule

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from pydantic.main import IncEx

    from allymend.core.models import FixPlan, PageResult, ScanResult, Slot
    from allymend.core.summary import RuleCount

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
_WRITTEN = {"image-alt": "alt text", "link-name": "link name"}


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
        "allymend_version": __version__,
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


def render_evidence(result: ScanResult, plan: FixPlan) -> str:
    """Render a checked fix plan as versioned JSON: the fixes, what was left, and the checks."""
    document = {
        "schema_version": SCHEMA_VERSION,
        "allymend_version": __version__,
        "axe_version": result.axe_version,
        **plan.model_dump(mode="json"),
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def render_payloads(requests: Sequence[tuple[Slot, Mapping[str, Any]]]) -> str:
    """Show what would be sent to a model for each slot, with images summarised."""
    if not requests:
        return "Nothing would be sent: no element needs text that allymend can fix.\n"
    lines = [
        f"Would send {_count(len(requests), 'request')} to {requests[0][1]['model']}. "
        "Nothing has been sent."
    ]
    instructions: dict[str, str] = {}
    for slot, request in requests:
        instructions.setdefault(slot.kind, str(request["system"]))
    for kind, system in instructions.items():
        lines += ["", f"Instructions sent with every {kind} request:"]
        lines += [f"  {line}" if line else "" for line in system.splitlines()]
    for number, (slot, request) in enumerate(requests, start=1):
        lines += ["", f"{number}. {slot.page}: {' >>> '.join(slot.target)}"]
        for block in request["messages"][0]["content"]:
            if block["type"] == "image":
                size = len(base64.b64decode(block["source"]["data"]))
                lines.append(f"   image: {block['source']['media_type']}, {size:,} bytes")
            else:
                lines += [f"   {line}" if line else "" for line in block["text"].splitlines()]
    return "\n".join(lines) + "\n"


def render_fix_summary(
    result: ScanResult, plan: FixPlan, patch_file: Path, evidence_file: Path | None = None
) -> str:
    """Summarise what a fix run wrote to ``patch_file`` and what it left for a person."""
    files = {edit.file for fix in plan.fixes for edit in fix.edits}
    if plan.fixes:
        lines = [
            f"Wrote fixes for {_count(len(plan.fixes), 'problem')} in "
            f"{_count(len(files), 'file')} to {patch_file}. Each was checked in a browser first.",
            f"Review it, then apply it from this folder with: git apply {patch_file}",
        ]
    elif plan.unfixed:
        lines = [f"Nothing could be fixed automatically, so {patch_file} is empty."]
    else:
        lines = [f"No problems found, so {patch_file} is empty."]
    if evidence_file is not None:
        lines.append(f"The checks behind every fix are in {evidence_file}.")
    written = [fix for fix in plan.fixes if fix.value is not None]
    if written:
        lines += ["", "Text written by a model; read each one before applying the patch:"]
        lines += [
            f'  {fix.page}: {_WRITTEN.get(fix.rule_id, fix.rule_id)} "{fix.value.text}" '
            f"({fix.value.source})"
            for fix in written
            if fix.value is not None
        ]
    solved = Counter((item.page, item.rule_id) for item in plan.resolved)
    if solved:
        lines += [
            "",
            f"Also gone once these fixes were applied ({_count(len(plan.resolved), 'problem')}):",
        ]
        lines += [
            f"  {page}: {_rule_name(rule_id)}, {_count(elements, 'element')}"
            for (page, rule_id), elements in solved.items()
        ]
    left = Counter((item.page, item.rule_id, item.reason) for item in plan.unfixed)
    if left:
        lines += ["", f"Not fixed ({_count(len(plan.unfixed), 'problem')}):"]
        lines += [
            f"  {page}: {_rule_name(rule_id)}, {_count(elements, 'element')}: {reason}"
            for (page, rule_id, reason), elements in left.items()
        ]
    failed = [page for page in result.pages if page.error is not None]
    if failed:
        lines += ["", "Not scanned:"]
        lines += [f"  {page.page}: {page.error}" for page in failed]
    return "\n".join(lines) + "\n"


def _rule_name(rule_id: str) -> str:
    rule = RULES.get(rule_id)
    return f"{rule.title} ({rule_id})" if rule is not None else rule_id


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
