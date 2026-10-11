import re

import pytest

from allymend.core.rules import CRITERIA, RULES, Criterion, Remediability, Rule

WEBAIM_TOP_SIX = {
    "color-contrast",
    "image-alt",
    "label",
    "link-name",
    "button-name",
    "html-has-lang",
}


def test_covers_the_most_common_failures_on_the_web() -> None:
    assert RULES.keys() >= WEBAIM_TOP_SIX


@pytest.mark.parametrize("rule", RULES.values(), ids=lambda rule: rule.rule_id)
def test_every_rule_is_written_out_in_full_sentences(rule: Rule) -> None:
    for text in (rule.affects, rule.why, rule.fix):
        assert text[0].isupper()
        assert text.endswith(".")
    assert not rule.title.endswith(".")


@pytest.mark.parametrize("criterion", CRITERIA.values(), ids=lambda criterion: criterion.number)
def test_every_criterion_links_to_its_w3c_explanation(criterion: Criterion) -> None:
    assert re.fullmatch(r"\d\.\d\.\d+", criterion.number)
    assert criterion.level in {"A", "AA"}
    assert criterion.url == (f"https://www.w3.org/WAI/WCAG22/Understanding/{criterion.slug}")
    assert re.fullmatch(r"[a-z]+(-[a-z]+)*", criterion.slug)


def test_page_language_and_zoom_are_the_automatic_fixes() -> None:
    automatic = {
        rule.rule_id for rule in RULES.values() if rule.remediability is Remediability.AUTO
    }
    assert automatic == {"html-has-lang", "meta-viewport"}


def test_the_catalog_cannot_be_changed_at_runtime() -> None:
    with pytest.raises(TypeError):
        RULES["image-alt"] = RULES["label"]  # type: ignore[index]
    with pytest.raises(TypeError):
        CRITERIA["1.1.1"] = CRITERIA["4.1.2"]  # type: ignore[index]
