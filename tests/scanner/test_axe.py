import pytest

from allymend.core.models import Impact
from allymend.errors import AxeResultError
from allymend.scanner.axe import AXE_VERSION, axe_source, parse_violations

IMAGE_ALT = {
    "id": "image-alt",
    "impact": "critical",
    "tags": ["cat.text-alternatives", "wcag2a", "wcag111"],
    "help": "Images must have alternative text",
    "helpUrl": "https://dequeuniversity.com/rules/axe/4.13/image-alt",
    "nodes": [
        {
            "target": ["main > img"],
            "html": '<img src="mug.jpg">',
            "impact": "critical",
            "failureSummary": "Fix any of the following: Element does not have an alt attribute",
        },
        {
            "target": [["product-card", "img"]],
            "html": '<img src="towel.jpg">',
            "failureSummary": "Fix any of the following: Element does not have an alt attribute",
        },
    ],
}


def test_returns_one_occurrence_per_failing_element() -> None:
    first, second = parse_violations({"violations": [IMAGE_ALT], "passes": []})

    assert first.rule_id == "image-alt"
    assert first.impact is Impact.CRITICAL
    assert first.wcag == ("1.1.1",)
    assert first.summary == "Images must have alternative text"
    assert first.target == ("main > img",)
    assert first.html == '<img src="mug.jpg">'
    assert second.target == ("product-card >>> img",)


def test_element_without_its_own_impact_takes_the_rule_impact() -> None:
    occurrences = parse_violations({"violations": [IMAGE_ALT]})
    assert occurrences[1].impact is Impact.CRITICAL


def test_no_violations() -> None:
    assert parse_violations({"violations": []}) == ()


@pytest.mark.parametrize(
    "raw", [None, "not results", {}, {"violations": "none"}, {"violations": [{"id": "x"}]}]
)
def test_rejects_anything_not_shaped_like_axe_results(raw: object) -> None:
    with pytest.raises(AxeResultError):
        parse_violations(raw)


def test_axe_source_is_the_vendored_build() -> None:
    assert axe_source().startswith(f"/*! axe v{AXE_VERSION}")
