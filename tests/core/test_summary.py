from pataisa.core.models import Impact, Occurrence
from pataisa.core.summary import RuleCount, count_by_rule


def occurrence(rule_id: str, impact: Impact | None = Impact.SERIOUS) -> Occurrence:
    return Occurrence(
        rule_id=rule_id,
        impact=impact,
        wcag=("1.1.1",),
        summary=f"{rule_id} summary",
        help_url=f"https://dequeuniversity.com/rules/axe/4.13/{rule_id}",
        target=("main",),
        html="<main>",
        failure_summary="",
    )


def test_counts_elements_per_rule_with_the_most_frequent_first() -> None:
    counts = count_by_rule(
        [
            occurrence("link-name"),
            occurrence("image-alt"),
            occurrence("image-alt"),
            occurrence("color-contrast"),
            occurrence("image-alt"),
        ]
    )
    assert [(count.rule_id, count.elements) for count in counts] == [
        ("image-alt", 3),
        ("color-contrast", 1),
        ("link-name", 1),
    ]


def test_keeps_the_rule_summary_and_criteria() -> None:
    assert count_by_rule([occurrence("image-alt")]) == (
        RuleCount(
            rule_id="image-alt",
            summary="image-alt summary",
            impact=Impact.SERIOUS,
            wcag=("1.1.1",),
            elements=1,
        ),
    )


def test_takes_the_most_severe_impact() -> None:
    [count] = count_by_rule(
        [
            occurrence("label", Impact.MODERATE),
            occurrence("label", Impact.CRITICAL),
            occurrence("label", None),
        ]
    )
    assert count.impact is Impact.CRITICAL


def test_impact_is_none_when_no_occurrence_has_one() -> None:
    [count] = count_by_rule([occurrence("label", None)])
    assert count.impact is None


def test_no_occurrences() -> None:
    assert count_by_rule([]) == ()
