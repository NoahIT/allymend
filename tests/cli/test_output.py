import json

from pataisa import __version__
from pataisa.cli.output import LIMITS_NOTE, render_json, render_markdown, render_text
from pataisa.core.models import Impact, Occurrence, PageResult, ScanResult, SourceLocation
from pataisa.core.rules import RULES

MISSING_ALT = Occurrence(
    rule_id="image-alt",
    impact=Impact.CRITICAL,
    wcag=("1.1.1",),
    summary="Images must have alternative text",
    help_url="https://dequeuniversity.com/rules/axe/4.13/image-alt",
    target=("main > img",),
    html='<img src="mug.jpg">',
    failure_summary="Fix any of the following: Element does not have an alt attribute",
)
MISSING_LANG = Occurrence(
    rule_id="html-has-lang",
    impact=Impact.SERIOUS,
    wcag=("3.1.1",),
    summary="<html> element must have a lang attribute",
    help_url="https://dequeuniversity.com/rules/axe/4.13/html-has-lang",
    target=("html",),
    html="<html>",
    failure_summary="Fix any of the following: The <html> element does not have a lang attribute",
)
MARQUEE = Occurrence(
    rule_id="marquee",
    impact=None,
    wcag=("2.2.2",),
    summary="<marquee> elements are deprecated and must not be used",
    help_url="https://dequeuniversity.com/rules/axe/4.13/marquee",
    target=("marquee",),
    html="<marquee>",
    failure_summary="Fix all of the following: Element is a marquee",
)
RESULT = ScanResult(
    axe_version="4.13.0",
    pages=(
        PageResult(page="index.html", occurrences=(MISSING_ALT, MISSING_LANG)),
        PageResult(page="about.html"),
        PageResult(page="missing.html", error="HTTP 404"),
    ),
)


def single_page(*occurrences: Occurrence) -> ScanResult:
    return ScanResult(
        axe_version="4.13.0", pages=(PageResult(page="index.html", occurrences=occurrences),)
    )


def test_text_counts_problems_and_rules_on_each_page() -> None:
    lines = render_text(RESULT).splitlines()
    assert "index.html: 2 problems from 2 rules" in lines
    assert lines.index("  1. Page language is not set (1 element)") < lines.index(
        "  2. Image has no text alternative (1 element)"
    )


def test_text_explains_each_rule_once() -> None:
    lines = render_text(RESULT).splitlines()
    start = lines.index("  2. Image has no text alternative (1 element)")
    rule = RULES["image-alt"]
    assert lines[start + 1 : start + 8] == [
        f"     Who it affects: {rule.affects}",
        f"     Why it matters: {rule.why}",
        f"     How to fix: {rule.fix}",
        "     Fix type: needs a person to decide",
        "     WCAG 1.1.1 Non-text Content (level A): "
        "https://www.w3.org/WAI/WCAG22/Understanding/non-text-content",
        "     axe-core rule image-alt, impact critical",
        "     Elements: main > img",
    ]


def test_text_lists_five_elements_then_how_many_more() -> None:
    images = (
        MISSING_ALT.model_copy(update={"target": (f"li:nth-child({n}) > img",)})
        for n in range(1, 8)
    )
    lines = render_text(single_page(*images)).splitlines()
    assert "  1. Image has no text alternative (7 elements)" in lines
    assert (
        "     Elements: li:nth-child(1) > img; li:nth-child(2) > img; li:nth-child(3) > img; "
        "li:nth-child(4) > img; li:nth-child(5) > img; and 2 more"
    ) in lines


def test_text_shows_source_lines_for_elements_traced_to_the_source() -> None:
    traced = MISSING_ALT.model_copy(
        update={"source": SourceLocation(file="index.html", line=12, column=5, offset=301)}
    )
    lines = render_text(single_page(traced, MISSING_ALT)).splitlines()
    assert "     Elements: line 12, column 5; main > img" in lines


def test_markdown_adds_a_lines_column_only_when_elements_were_traced() -> None:
    traced = MISSING_ALT.model_copy(
        update={"source": SourceLocation(file="index.html", line=12, column=5, offset=301)}
    )
    with_lines = render_markdown(single_page(traced, MISSING_ALT)).splitlines()
    assert "| Problem | Rule | Fix type | Impact | WCAG | Elements | Lines |" in with_lines
    assert (
        "| Image has no text alternative | image-alt | human | critical | 1.1.1 | 2 | 12 |"
        in with_lines
    )
    without_lines = render_markdown(single_page(MISSING_ALT)).splitlines()
    assert "| Problem | Rule | Fix type | Impact | WCAG | Elements |" in without_lines


def test_text_falls_back_to_axe_for_rules_outside_the_catalog() -> None:
    lines = render_text(single_page(MARQUEE)).splitlines()
    start = lines.index("  1. <marquee> elements are deprecated and must not be used (1 element)")
    assert lines[start + 1 : start + 5] == [
        "     More information: https://dequeuniversity.com/rules/axe/4.13/marquee",
        "     WCAG 2.2.2",
        "     axe-core rule marquee",
        "     Elements: marquee",
    ]


def test_text_marks_clean_pages_and_pages_that_failed() -> None:
    lines = render_text(RESULT).splitlines()
    assert "about.html: no problems found" in lines
    assert "missing.html: could not be scanned (HTTP 404)" in lines


def test_text_ends_with_a_summary_and_the_limits_of_automated_checks() -> None:
    lines = render_text(RESULT).splitlines()
    assert lines[0] == "Scanned 3 pages with axe-core 4.13.0."
    assert lines[-2:] == [
        "Summary: 2 problems on 1 of 3 pages. 1 page could not be scanned.",
        LIMITS_NOTE,
    ]


def test_text_uses_singular_nouns_for_one() -> None:
    lines = render_text(single_page(MISSING_ALT)).splitlines()
    assert lines[0] == "Scanned 1 page with axe-core 4.13.0."
    assert "index.html: 1 problem from 1 rule" in lines
    assert lines[-2] == "Summary: 1 problem on 1 of 1 page."


def test_text_has_no_colour_codes() -> None:
    assert "\x1b" not in render_text(RESULT)


def test_markdown_starts_with_an_overview_row_per_page() -> None:
    lines = render_markdown(RESULT).splitlines()
    assert lines[:9] == [
        "# Accessibility scan",
        "",
        "Scanned 3 pages with axe-core 4.13.0.",
        "",
        "| Page | Problems | Most frequent rules |",
        "| --- | ---: | --- |",
        "| index.html | 2 | html-has-lang (1), image-alt (1) |",
        "| about.html | 0 |  |",
        "| missing.html | not scanned | HTTP 404 |",
    ]


def test_markdown_groups_problems_by_rule_on_pages_with_problems() -> None:
    lines = render_markdown(RESULT).splitlines()
    assert "## index.html" in lines
    assert "## about.html" not in lines
    assert "## missing.html" not in lines
    assert "| Problem | Rule | Fix type | Impact | WCAG | Elements |" in lines
    assert "| Page language is not set | html-has-lang | auto | serious | 3.1.1 | 1 |" in lines
    assert "| Image has no text alternative | image-alt | human | critical | 1.1.1 | 1 |" in lines


def test_markdown_counts_repeated_rules_and_lists_three_in_the_overview() -> None:
    result = single_page(
        MISSING_ALT,
        MISSING_ALT,
        MISSING_ALT,
        MISSING_LANG,
        MISSING_ALT.model_copy(update={"rule_id": "link-name"}),
        MISSING_ALT.model_copy(update={"rule_id": "label"}),
    )
    lines = render_markdown(result).splitlines()
    assert "| index.html | 6 | image-alt (3), html-has-lang (1), label (1) |" in lines
    assert "| Image has no text alternative | image-alt | human | critical | 1.1.1 | 3 |" in lines


def test_markdown_escapes_text_from_pages_and_axe() -> None:
    result = ScanResult(
        axe_version="4.13.0",
        pages=(PageResult(page="shop|<b>.html", occurrences=(MARQUEE,)),),
    )
    lines = render_markdown(result).splitlines()
    assert "## shop\\|&lt;b&gt;.html" in lines
    assert "| shop\\|&lt;b&gt;.html | 1 | marquee (1) |" in lines
    assert (
        "| &lt;marquee&gt; elements are deprecated and must not be used "
        "| marquee |  |  | 2.2.2 | 1 |"
    ) in lines


def test_markdown_ends_with_the_summary_and_the_limits_of_automated_checks() -> None:
    lines = render_markdown(RESULT).splitlines()
    assert lines[-3:] == [
        "Summary: 2 problems on 1 of 3 pages. 1 page could not be scanned.",
        "",
        LIMITS_NOTE,
    ]


def test_json_is_versioned_and_leaves_out_markup() -> None:
    document = json.loads(render_json(RESULT))

    assert document["schema_version"] == 1
    assert document["pataisa_version"] == __version__
    assert document["axe_version"] == "4.13.0"
    occurrence = document["pages"][0]["occurrences"][0]
    assert occurrence["rule_id"] == "image-alt"
    assert occurrence["impact"] == "critical"
    assert occurrence["target"] == ["main > img"]
    assert "html" not in occurrence
    assert document["pages"][2]["error"] == "HTTP 404"


def test_json_includes_markup_when_asked() -> None:
    document = json.loads(render_json(RESULT, include_markup=True))
    assert document["pages"][0]["occurrences"][0]["html"] == '<img src="mug.jpg">'
