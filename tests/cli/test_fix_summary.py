from pathlib import Path

from allymend.cli.output import render_fix_summary, render_payloads
from allymend.core.models import (
    Edit,
    Fix,
    FixPlan,
    PageResult,
    Resolved,
    ScanResult,
    Slot,
    Unfixed,
    Value,
)

PATCH = Path("allymend.patch")


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

    assert render_fix_summary(scanned, plan, PATCH, Path("checks.json")).splitlines() == [
        "Wrote fixes for 2 problems in 2 files to allymend.patch. Each was checked in a browser "
        "first.",
        "Review it, then apply it from this folder with: git apply allymend.patch",
        "The checks behind every fix are in checks.json.",
        "",
        "Not fixed (3 problems):",
        "  index.html: Image has no text alternative (image-alt), 2 elements: "
        "there's no automatic fix for this rule yet",
        "  index.html: duplicate-id, 1 element: there's no automatic fix for this rule yet",
        "",
        "Not scanned:",
        "  shop.html: HTTP 404",
    ]


def test_lists_text_written_by_a_model() -> None:
    value = Value(text="A blue mug", rationale="It shows a mug.", source="claude-opus-5-5")
    written = fix("shop.html").model_copy(update={"rule_id": "image-alt", "value": value})
    plan = FixPlan(fixes=(fix("index.html"), written), unfixed=(), changes=())
    assert render_fix_summary(result(), plan, PATCH).splitlines()[2:] == [
        "",
        "Text written by a model; read each one before applying the patch:",
        '  shop.html: "A blue mug" (claude-opus-5-5)',
    ]


def test_lists_problems_the_fixes_also_solved() -> None:
    plan = FixPlan(
        fixes=(fix("shop.html"),),
        unfixed=(left("shop.html", "button-name", "button", "there's no automatic fix"),),
        changes=(),
        resolved=(
            Resolved(rule_id="link-name", page="shop.html", target=("a.home",)),
            Resolved(rule_id="link-name", page="shop.html", target=("a.cart",)),
            Resolved(rule_id="region", page="shop.html", target=("p",)),
        ),
    )
    assert render_fix_summary(result(), plan, PATCH).splitlines()[2:] == [
        "",
        "Also gone once these fixes were applied (3 problems):",
        "  shop.html: Link has no name (link-name), 2 elements",
        "  shop.html: region, 1 element",
        "",
        "Not fixed (1 problem):",
        "  shop.html: Button has no name (button-name), 1 element: there's no automatic fix",
    ]


def test_payloads_show_images_by_size_and_text_in_full() -> None:
    request = {
        "model": "claude-opus-5-5",
        "system": "Write alt text.\n\nBe brief.",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAAA"},
                    },
                    {"type": "text", "text": "Alt text, please.\n\n<page_details>"},
                ],
            }
        ],
    }
    target = Slot(kind="alt-text", rule_id="image-alt", page="a.html", target=("img",), html="")
    assert render_payloads([(target, request)]).splitlines() == [
        "Would send 1 request to claude-opus-5-5. Nothing has been sent.",
        "",
        "Instructions sent with every request:",
        "  Write alt text.",
        "",
        "  Be brief.",
        "",
        "1. a.html: img",
        "   image: image/jpeg, 3 bytes",
        "   Alt text, please.",
        "",
        "   <page_details>",
    ]
    assert render_payloads([]) == (
        "Nothing would be sent: no image needs alt text that allymend can fix.\n"
    )


def test_says_when_nothing_could_be_fixed() -> None:
    plan = FixPlan(
        fixes=(),
        unfixed=(left("index.html", "html-has-lang", "html", "the pages' language wasn't given"),),
        changes=(),
    )
    assert render_fix_summary(result(), plan, PATCH).splitlines()[0] == (
        "Nothing could be fixed automatically, so allymend.patch is empty."
    )


def test_says_when_there_was_nothing_to_fix() -> None:
    plan = FixPlan(fixes=(), unfixed=(), changes=())
    assert render_fix_summary(result(), plan, PATCH) == (
        "No problems found, so allymend.patch is empty.\n"
    )
