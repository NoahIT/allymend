import pytest

from pataisa.core.wcag import success_criteria


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        (["cat.text-alternatives", "wcag2a", "wcag111"], ("1.1.1",)),
        (["wcag2aa", "wcag1410"], ("1.4.10",)),
        (["wcag22aa", "wcag2411"], ("2.4.11",)),
        (["wcag2a", "wcag244", "wcag412"], ("2.4.4", "4.1.2")),
        (["best-practice", "wcag21aa", "wcag2a"], ()),
    ],
)
def test_success_criteria(tags: list[str], expected: tuple[str, ...]) -> None:
    assert success_criteria(tags) == expected
