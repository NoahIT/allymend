from __future__ import annotations

import logging
import re
from collections import Counter
from typing import TYPE_CHECKING
from urllib.parse import quote

from justhtml import JustHTML

from allymend.core.models import Check, Unfixed, Verification
from allymend.scanner import open_browser
from allymend.scanner.site import serve

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from pathlib import Path

    from allymend.core.models import FileChange, Fix, FixPlan, PageResult
    from allymend.scanner import BrowserSession, ScanOptions

logger = logging.getLogger(__name__)

_ROLE = re.compile(r"^\s*- ([^\s:\"]+)")
_SPACE = re.compile(r"\s+")


def verify_fixes(root: Path, plan: FixPlan, options: ScanOptions | None = None) -> FixPlan:
    """Check every planned change in a browser before trusting it.

    Each changed file is served from ``root`` and loaded twice in one browser session: as it is,
    and with its fixes. The fixes must not hide anything, must make their occurrences go away,
    must not bring in new ones, and must not take anything out of the accessibility tree. A
    file's fixes pass or fail together.

    Returns the plan with only the changes that passed. The fixes in files that failed move to
    ``unfixed`` with the reason, and the evidence for every file is in ``verifications``.
    """
    if not plan.changes:
        return plan
    verifications = []
    with serve(root) as base_url, open_browser(options) as browser:
        for change in plan.changes:
            logger.info("checking the fixes in %s", change.file)
            fixes = [fix for fix in plan.fixes if _touches(fix, change.file)]
            verification = _verify(browser, base_url + quote(change.file), change, fixes)
            if not verification.passed:
                logger.warning("rejected the fixes in %s", change.file)
            verifications.append(verification)
    failed = {v.file: _reason(v) for v in verifications if not v.passed}
    rejected = [fix for fix in plan.fixes if any(_touches(fix, file) for file in failed)]
    return plan.model_copy(
        update={
            "fixes": tuple(fix for fix in plan.fixes if fix not in rejected),
            "unfixed": plan.unfixed
            + tuple(
                Unfixed(
                    rule_id=fix.rule_id,
                    page=fix.page,
                    target=fix.target,
                    reason=next(failed[edit.file] for edit in fix.edits if edit.file in failed),
                )
                for fix in rejected
            ),
            "changes": tuple(change for change in plan.changes if change.file not in failed),
            "verifications": tuple(verifications),
        }
    )


def _verify(
    browser: BrowserSession, url: str, change: FileChange, fixes: Sequence[Fix]
) -> Verification:
    checks = [_check_edits(change)]
    if checks[-1].passed:
        before = browser.scan(change.file, url, tree=True)
        after = browser.scan(change.file, url, html=change.after, tree=True)
        checks.append(_check_scanned(before.result, after.result))
        if checks[-1].passed:
            checks += [
                _check_fixed(after.result, fixes),
                _check_no_new_problems(before.result, after.result),
                _check_tree(before.tree or "", after.tree or ""),
            ]
    return Verification(file=change.file, checks=tuple(checks))


def _check_edits(change: FileChange) -> Check:
    hiding_before, elements_before = _inventory(change.before)
    hiding_after, elements_after = _inventory(change.after)
    added = hiding_after - hiding_before
    problems = []
    if added:
        problems.append("an edit adds " + ", ".join(name for name, _ in _HIDING if added[name]))
    if elements_after < elements_before:
        problems.append("an edit removes an element")
    if problems:
        return Check(name="edits", passed=False, detail="; ".join(problems))
    return Check(name="edits", passed=True)


def _inventory(text: str) -> tuple[Counter[str], int]:
    """Count the ways a page's elements are hidden from assistive technology, and its elements."""
    hiding: Counter[str] = Counter()
    elements = 0
    for element in JustHTML(text, sanitize=False).root.query("*"):
        if element.name.startswith("!"):
            continue
        elements += 1
        attributes = element.attrs or {}
        hiding.update(name for name, hides in _HIDING if hides(attributes))
    return hiding, elements


def _value(attributes: Mapping[str, str | None], name: str) -> str:
    return _SPACE.sub("", (attributes.get(name) or "").lower())


_HIDING: tuple[tuple[str, Callable[[Mapping[str, str | None]], bool]], ...] = (
    ("aria-hidden", lambda a: _value(a, "aria-hidden") == "true"),
    (
        "an ARIA role of none or presentation",
        lambda a: (a.get("role") or "").lower().split()[:1] in (["none"], ["presentation"]),
    ),
    ("display: none", lambda a: "display:none" in _value(a, "style")),
    ("visibility: hidden", lambda a: "visibility:hidden" in _value(a, "style")),
    ('tabindex="-1"', lambda a: _value(a, "tabindex") == "-1"),
    ("the hidden attribute", lambda a: "hidden" in a),
    ("the inert attribute", lambda a: "inert" in a),
)


def _check_scanned(before: PageResult, after: PageResult) -> Check:
    if before.error is not None:
        return Check(name="scanned", passed=False, detail=f"the page as it is: {before.error}")
    if after.error is not None:
        return Check(name="scanned", passed=False, detail=f"the fixed page: {after.error}")
    return Check(name="scanned", passed=True)


def _check_fixed(after: PageResult, fixes: Sequence[Fix]) -> Check:
    remaining = {(o.rule_id, o.target) for o in after.occurrences}
    still = [
        f"{fix.rule_id} on {_selector(fix.target)}"
        for fix in fixes
        if (fix.rule_id, fix.target) in remaining
    ]
    if still:
        return Check(name="fixed", passed=False, detail="still found: " + "; ".join(still))
    return Check(name="fixed", passed=True)


def _check_no_new_problems(before: PageResult, after: PageResult) -> Check:
    known = {(o.rule_id, o.target) for o in before.occurrences}
    new = [
        f"{o.rule_id} on {_selector(o.target)}"
        for o in after.occurrences
        if (o.rule_id, o.target) not in known
    ]
    if new:
        return Check(name="no-new-problems", passed=False, detail="new: " + "; ".join(new))
    return Check(name="no-new-problems", passed=True)


def _check_tree(before: str, after: str) -> Check:
    lost = _roles(before) - _roles(after)
    if lost:
        names = ", ".join(sorted(lost.elements()))
        return Check(name="tree", passed=False, detail=f"gone from the accessibility tree: {names}")
    return Check(name="tree", passed=True)


def _roles(tree: str) -> Counter[str]:
    return Counter(match.group(1) for line in tree.splitlines() if (match := _ROLE.match(line)))


def _touches(fix: Fix, file: str) -> bool:
    return any(edit.file == file for edit in fix.edits)


def _reason(verification: Verification) -> str:
    failed = next(check for check in verification.checks if not check.passed)
    return f"rejected by the check after fixing: {failed.detail}"


def _selector(target: tuple[str, ...]) -> str:
    return " >>> ".join(target)
