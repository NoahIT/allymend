from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from allymend.core.models import (
    Edit,
    FileChange,
    Fix,
    FixPlan,
    Resolved,
    Slot,
    Unfixed,
    Value,
)
from allymend.fixers import FixOptions, apply_edits, plan_fixes, unified_diff
from allymend.mapper import map_sources
from allymend.scanner import ScanOptions, scan_directory
from allymend.verifier import verify_fixes
from allymend.verifier.verify import _check_edits, _check_tree

IMAGE = '<img src="mug.png" alt="Mug">'
PAGE = (
    "<!doctype html><html><head><meta charset='utf-8'><title>Shop</title></head>"
    f"<body><main><h1>Shop</h1>{IMAGE}</main></body></html>"
)
NO_LANGUAGE = Unfixed(rule_id="html-has-lang", page="index.html", target=("html",), reason="no")


class Writer:
    def fill(self, slot: Slot) -> Value:  # noqa: ARG002  every slot gets the same text
        return Value(text="Mug shop", source="writer")


def plan_for(replacements: Sequence[tuple[str, str]], file: str = "index.html") -> FixPlan:
    """A one-fix html-has-lang plan whose edits each replace the first match of a string."""
    edits = []
    for old, new in replacements:
        start = PAGE.index(old)
        edits.append(Edit(file=file, start=start, end=start + len(old), text=new))
    after = apply_edits(PAGE, edits)
    change = FileChange(file=file, diff=unified_diff(file, PAGE, after), before=PAGE, after=after)
    fix = Fix(rule_id="html-has-lang", page=file, target=("html",), edits=tuple(edits))
    return FixPlan(fixes=(fix,), unfixed=(), changes=(change,))


def check_edits(replacements: Sequence[tuple[str, str]]) -> tuple[bool, str]:
    plan = plan_for(replacements)
    check = _check_edits(plan.changes[0])
    return check.passed, check.detail


@pytest.mark.parametrize(
    ("inserted", "found"),
    [
        (' aria-hidden="true"', "aria-hidden"),
        (' ARIA-HIDDEN="True"', "aria-hidden"),
        (' role="presentation"', "an ARIA role of none or presentation"),
        (" role=none", "an ARIA role of none or presentation"),
        (' style="display:none"', "display: none"),
        (' style="color: red; Display : None"', "display: none"),
        (' style="visibility: hidden"', "visibility: hidden"),
        (' tabindex="-1"', 'tabindex="-1"'),
        (" hidden", "the hidden attribute"),
        (" inert", "the inert attribute"),
    ],
)
def test_edits_that_hide_content_are_caught(inserted: str, found: str) -> None:
    assert check_edits([("<img", f"<img{inserted}")]) == (False, f"an edit adds {found}")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("<html", '<html lang="en"'),
        ("<html", '<html role="navigation"'),
        ("<html", '<html class="hidden"'),
        ("<html", '<html data-hidden="1"'),
        ("<html", '<html title="inert"'),
        ("<img", '<img aria-hidden="false"'),
        ("<img", '<img title="Hidden treasure, display: none"'),
        ("</main>", "<p>A hidden gem, inert no more.</p></main>"),
    ],
    ids=[
        "lang",
        "landmark-role",
        "class-named-hidden",
        "data-attribute",
        "word-in-a-title",
        "aria-hidden-false",
        "words-in-a-value",
        "words-in-text",
    ],
)
def test_ordinary_edits_pass(old: str, new: str) -> None:
    assert check_edits([(old, new)]) == (True, "")


def test_hiding_that_was_already_there_is_not_blamed_on_the_edit() -> None:
    assert check_edits([("<main>", '<main aria-hidden="true">')]) == (
        False,
        "an edit adds aria-hidden",
    )
    plan = plan_for([("<html", '<html lang="en"')])
    hidden = plan.changes[0].model_copy(
        update={
            "before": plan.changes[0].before.replace("<main>", '<main aria-hidden="true">'),
            "after": plan.changes[0].after.replace("<main>", '<main aria-hidden="true">'),
        }
    )
    assert _check_edits(hidden).passed


def test_removing_an_element_is_caught() -> None:
    assert check_edits([(IMAGE, "")]) == (False, "an edit removes an element")
    assert check_edits([(IMAGE, '<b aria-hidden="true">Mug</b>'), ("<h1>Shop</h1>", "")]) == (
        False,
        "an edit adds aria-hidden; an edit removes an element",
    )


def test_replacing_an_element_with_another_is_left_to_the_tree_check() -> None:
    assert check_edits([(IMAGE, "<span>Mug</span>")]) == (True, "")


def test_the_tree_may_gain_entries_and_names_but_not_lose_roles() -> None:
    before = '- document:\n  - heading "Shop" [level=1]\n  - img\n  - textbox'
    named = "\n".join(
        [
            "- document:",
            '  - heading "Shop" [level=1]',
            '  - img "Mug"',
            "  - text: Email",
            '  - textbox "Email"',
        ]
    )
    assert _check_tree(before, named).passed
    check = _check_tree(before, '- document:\n  - heading "Shop" [level=1]\n  - textbox')
    assert (check.passed, check.detail) == (False, "gone from the accessibility tree: img")


def test_a_plan_without_changes_is_returned_as_it_is(tmp_path: Path) -> None:
    plan = FixPlan(fixes=(), unfixed=(), changes=())
    assert verify_fixes(tmp_path, plan) is plan


@pytest.mark.browser
def test_a_fix_that_works_is_kept_with_its_evidence(
    tmp_path: Path, write_page: Callable[..., Path]
) -> None:
    write_page("index.html", IMAGE, lang=None)
    planned = plan_fixes(
        tmp_path, map_sources(tmp_path, scan_directory(tmp_path)), FixOptions(language="en")
    )

    verified = verify_fixes(tmp_path, planned)

    assert verified.fixes == planned.fixes
    assert verified.changes == planned.changes
    assert verified.unfixed == ()
    [evidence] = verified.verifications
    assert evidence.passed
    assert [check.name for check in evidence.checks] == [
        "edits",
        "scanned",
        "fixed",
        "no-new-problems",
        "tree",
    ]


@pytest.mark.browser
@pytest.mark.parametrize(
    ("replacements", "check", "reason"),
    [
        (
            [("<html", '<html lang="en"'), ("<img", '<img aria-hidden="true"')],
            "edits",
            "an edit adds aria-hidden",
        ),
        ([("<html", '<html data-lang="en"')], "fixed", "still found: html-has-lang on html"),
        (
            [("<html", '<html lang="en"'), ("</main>", '<img src="new.png"></main>')],
            "no-new-problems",
            'new: image-alt on img[src$="new.png"]',
        ),
        (
            [("<html", '<html lang="en"'), (IMAGE, "<span>Mug</span>")],
            "tree",
            "gone from the accessibility tree: img",
        ),
    ],
    ids=["hides-content", "does-not-fix", "new-problem", "empties-the-tree"],
)
def test_a_fix_that_fails_a_check_is_rejected(
    tmp_path: Path, replacements: list[tuple[str, str]], check: str, reason: str
) -> None:
    (tmp_path / "index.html").write_bytes(PAGE.encode("utf-8"))

    verified = verify_fixes(tmp_path, plan_for(replacements))

    assert verified.fixes == ()
    assert verified.changes == ()
    assert verified.patch == ""
    [left] = verified.unfixed
    assert (left.rule_id, left.page, left.target) == ("html-has-lang", "index.html", ("html",))
    assert left.reason == f"rejected by the check after fixing: {reason}"
    [evidence] = verified.verifications
    assert [(c.name, c.detail) for c in evidence.checks if not c.passed] == [(check, reason)]


@pytest.mark.browser
def test_problems_that_go_away_with_the_fixes_are_resolved(
    tmp_path: Path, write_page: Callable[..., Path]
) -> None:
    write_page(
        "index.html", '<a href="shop.html"><img src="mug.png"></a><p style="color:#eee">Faint</p>'
    )
    planned = plan_fixes(
        tmp_path, map_sources(tmp_path, scan_directory(tmp_path)), FixOptions(values=Writer())
    )
    left = {item.rule_id: item for item in planned.unfixed}
    assert sorted(left) == ["color-contrast", "link-name"]

    verified = verify_fixes(tmp_path, planned)

    assert verified.fixes == planned.fixes
    assert verified.unfixed == (left["color-contrast"],)
    link = left["link-name"]
    assert verified.resolved == (
        Resolved(rule_id=link.rule_id, page=link.page, target=link.target),
    )


@pytest.mark.browser
@pytest.mark.parametrize(
    ("replacements", "unfixed", "resolved"),
    [
        (
            [("<html", '<html lang="en"')],
            (),
            (Resolved(rule_id="html-has-lang", page="index.html", target=("html",)),),
        ),
        (
            [("<html", '<html lang="en"'), ("</main>", '<img src="new.png"></main>')],
            (NO_LANGUAGE,),
            (),
        ),
    ],
    ids=["passed", "rejected"],
)
def test_only_changes_that_pass_their_checks_resolve_problems(
    tmp_path: Path,
    replacements: list[tuple[str, str]],
    unfixed: tuple[Unfixed, ...],
    resolved: tuple[Resolved, ...],
) -> None:
    (tmp_path / "index.html").write_bytes(PAGE.encode("utf-8"))
    plan = plan_for(replacements).model_copy(update={"fixes": (), "unfixed": (NO_LANGUAGE,)})

    verified = verify_fixes(tmp_path, plan)

    assert (verified.unfixed, verified.resolved) == (unfixed, resolved)


@pytest.mark.browser
def test_a_fix_that_breaks_the_page_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_bytes(PAGE.encode("utf-8"))
    plan = plan_for(
        [("<html", '<html lang="en"'), ("</main>", "<script>for(;;){}</script></main>")]
    )
    [left] = verify_fixes(tmp_path, plan, ScanOptions(timeout_ms=2000)).unfixed
    assert left.reason == (
        "rejected by the check after fixing: the fixed page: did not finish within 2 s"
    )


@pytest.mark.browser
def test_a_page_that_cannot_be_loaded_is_rejected(tmp_path: Path) -> None:
    plan = plan_for([("<html", '<html lang="en"')], file="gone.html")
    [left] = verify_fixes(tmp_path, plan).unfixed
    assert left.reason == "rejected by the check after fixing: the page as it is: HTTP 404"
