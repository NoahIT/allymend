import json

from pataisa import __version__
from pataisa.cli.output import LIMITS_NOTE, render_json, render_markdown, render_text
from pataisa.core.models import Impact, Occurrence, PageResult, ScanResult

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
RESULT = ScanResult(
    axe_version="4.13.0",
    pages=(
        PageResult(page="index.html", occurrences=(MISSING_ALT, MISSING_LANG)),
        PageResult(page="about.html"),
        PageResult(page="missing.html", error="HTTP 404"),
    ),
)


def test_text_lists_each_problem_with_its_rule_and_criterion() -> None:
    lines = render_text(RESULT).splitlines()
    start = lines.index("index.html: 2 problems")
    assert lines[start + 1 : start + 4] == [
        "  1. Images must have alternative text",
        "     rule image-alt; impact critical; WCAG 1.1.1",
        "     element: main > img",
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
    result = ScanResult(
        axe_version="4.13.0", pages=(PageResult(page="index.html", occurrences=(MISSING_ALT,)),)
    )
    lines = render_text(result).splitlines()
    assert lines[0] == "Scanned 1 page with axe-core 4.13.0."
    assert "index.html: 1 problem" in lines
    assert lines[-2] == "Summary: 1 problem on 1 of 1 page."


def test_text_leaves_out_missing_impact_and_criteria() -> None:
    bare = MISSING_ALT.model_copy(update={"impact": None, "wcag": ()})
    result = ScanResult(
        axe_version="4.13.0", pages=(PageResult(page="a.html", occurrences=(bare,)),)
    )
    assert "     rule image-alt" in render_text(result).splitlines()


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
    assert "| image-alt | critical | 1.1.1 | 1 | Images must have alternative text |" in lines
    assert (
        "| html-has-lang | serious | 3.1.1 | 1 | &lt;html&gt; element must have a lang attribute |"
        in lines
    )


def test_markdown_counts_repeated_rules_and_lists_three_in_the_overview() -> None:
    occurrences = (
        MISSING_ALT,
        MISSING_ALT,
        MISSING_ALT,
        MISSING_LANG,
        MISSING_ALT.model_copy(update={"rule_id": "link-name"}),
        MISSING_ALT.model_copy(update={"rule_id": "label"}),
    )
    result = ScanResult(
        axe_version="4.13.0", pages=(PageResult(page="index.html", occurrences=occurrences),)
    )
    lines = render_markdown(result).splitlines()
    assert "| index.html | 6 | image-alt (3), html-has-lang (1), label (1) |" in lines
    assert "| image-alt | critical | 1.1.1 | 3 | Images must have alternative text |" in lines


def test_markdown_escapes_text_from_pages() -> None:
    result = ScanResult(
        axe_version="4.13.0",
        pages=(PageResult(page="shop|<b>.html", occurrences=(MISSING_ALT,)),),
    )
    lines = render_markdown(result).splitlines()
    assert "## shop\\|&lt;b&gt;.html" in lines
    assert "| shop\\|&lt;b&gt;.html | 1 | image-alt (1) |" in lines


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
