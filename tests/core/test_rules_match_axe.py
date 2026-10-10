from typing import Any

import pytest
from playwright.sync_api import sync_playwright

from pataisa.core.rules import CRITERIA, RULES
from pataisa.core.wcag import success_criteria
from pataisa.scanner.axe import WCAG_TAGS, axe_source

pytestmark = pytest.mark.browser


@pytest.fixture(scope="module")
def axe_rules() -> dict[str, list[str]]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.evaluate(axe_source())
            rules: list[dict[str, Any]] = page.evaluate(
                "tags => axe.getRules(tags)", list(WCAG_TAGS)
            )
        finally:
            browser.close()
    return {rule["ruleId"]: rule["tags"] for rule in rules}


def test_every_catalog_rule_exists_in_axe_core(axe_rules: dict[str, list[str]]) -> None:
    assert RULES.keys() <= axe_rules.keys()


def test_every_criterion_of_a_catalog_rule_is_described(axe_rules: dict[str, list[str]]) -> None:
    for rule_id in RULES:
        assert set(success_criteria(axe_rules[rule_id])) <= CRITERIA.keys(), rule_id
