from pathlib import Path

from pataisa.cli.output import render_fix_summary
from pataisa.core.models import Edit, Fix, FixPlan, PageResult, ScanResult, Unfixed

PATCH = Path("pataisa.patch")


def result(*pages: PageResult) -> ScanResult:
    return ScanResult(axe_version="4.13.0", pages=pages)


def fix(page: str) -> Fix:
    edit = Edit(file=page, start=5, end=5, text=' lang="en"')
    return Fix(rule_id="html-has-lang", page=page, target=("html",), edits=(edit,))


def left(page: str, rule_id: str, target: str, reason: str) -> Unfixed:
    return Unfixed(rule_id=rule_id, page=page, target=(target,), reason=reason)


def test_lists_what_was_fixed_and_what_was_left() -> None:
    plan = FixPlan(
        fixes=(fix("index.html"), fix("about.html")),
        unfixed=(
            left(
                "index.html", "image-alt", "img.logo", "there's no automatic fix for this rule yet"
            ),
            left(
                "index.html", "image-alt", "img.mug", "there's no automatic fix for this rule yet"
            ),
            left("index.html", "duplicate-id", "#a", "there's no automatic fix for this rule yet"),
        ),
        changes=(),
    )
    scanned = result(PageResult(page="shop.html", error="HTTP 404"))

    assert render_fix_summary(scanned, plan, PATCH).splitlines() == [
        "Wrote fixes for 2 problems in 2 files to pataisa.patch.",
        "Review it, apply it from this folder with: git apply pataisa.patch",
        "Then scan again to confirm the problems are gone.",
        "",
        "Not fixed (3 problems):",
        "  index.html: Image has no text alternative (image-alt), 2 elements: "
        "there's no automatic fix for this rule yet",
        "  index.html: duplicate-id, 1 element: there's no automatic fix for this rule yet",
        "",
        "Not scanned:",
        "  shop.html: HTTP 404",
    ]


def test_says_when_nothing_could_be_fixed() -> None:
    plan = FixPlan(
        fixes=(),
        unfixed=(left("index.html", "html-has-lang", "html", "the pages' language wasn't given"),),
        changes=(),
    )
    assert render_fix_summary(result(), plan, PATCH).splitlines()[0] == (
        "Nothing could be fixed automatically, so pataisa.patch is empty."
    )


def test_says_when_there_was_nothing_to_fix() -> None:
    plan = FixPlan(fixes=(), unfixed=(), changes=())
    assert render_fix_summary(result(), plan, PATCH) == (
        "No problems found, so pataisa.patch is empty.\n"
    )
