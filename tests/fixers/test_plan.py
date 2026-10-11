from pathlib import Path

import pytest

from allymend.core.models import (
    Capture,
    Edit,
    Impact,
    Occurrence,
    PageResult,
    ScanResult,
    Slot,
    SourceLocation,
    Unfixed,
    Value,
)
from allymend.errors import CannotFixError
from allymend.fixers import TEXT_RULES, FixOptions, plan_fixes, unified_diff

PAGE = '<!doctype html>\n<html>\n<head><title>Shop</title></head>\n<body><img src="a.png">\n'
FIXED = PAGE.replace("<html>", '<html lang="en">')


def location(file: str = "index.html", text: str = PAGE, tag: str = "<html") -> SourceLocation:
    offset = text.index(tag)
    line = text.count("\n", 0, offset) + 1
    column = offset - text.rfind("\n", 0, offset)
    return SourceLocation(file=file, line=line, column=column, offset=offset)


def problem(
    rule_id: str = "html-has-lang", source: SourceLocation | None = None, target: str = "html"
) -> Occurrence:
    return Occurrence(
        rule_id=rule_id,
        impact=Impact.SERIOUS,
        wcag=(),
        summary="",
        help_url="https://example.com/",
        target=(target,),
        html=f"<{target}>",
        failure_summary="",
        source=source,
    )


def scan(*occurrences: Occurrence, page: str = "index.html") -> ScanResult:
    return ScanResult(axe_version="4.13.0", pages=(PageResult(page=page, occurrences=occurrences),))


def write(root: Path, relative: str, text: str = PAGE) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def unfixed(reason: str, rule_id: str = "html-has-lang", target: str = "html") -> Unfixed:
    return Unfixed(rule_id=rule_id, page="index.html", target=(target,), reason=reason)


def test_plans_a_fix_and_a_patch(tmp_path: Path) -> None:
    write(tmp_path, "index.html")

    plan = plan_fixes(
        tmp_path, scan(problem(source=location())), FixOptions(language="en"), path_prefix="site/"
    )

    [fix] = plan.fixes
    insert_at = PAGE.index("<html") + len("<html")
    assert (fix.rule_id, fix.page, fix.target) == ("html-has-lang", "index.html", ("html",))
    assert fix.edits == (
        Edit(file="index.html", start=insert_at, end=insert_at, text=' lang="en"'),
    )
    assert plan.unfixed == ()
    [change] = plan.changes
    assert (change.file, change.before, change.after) == ("index.html", PAGE, FIXED)
    assert change.diff == plan.patch == unified_diff("site/index.html", PAGE, FIXED)


def test_serialized_plans_leave_out_the_file_texts(tmp_path: Path) -> None:
    write(tmp_path, "index.html")
    plan = plan_fixes(tmp_path, scan(problem(source=location())), FixOptions(language="en"))
    [change] = plan.model_dump(mode="json")["changes"]
    assert set(change) == {"file", "diff"}
    assert "before=" not in repr(plan.changes)
    assert "after=" not in repr(plan.changes)


def test_leaves_a_missing_language_alone_when_none_was_given(tmp_path: Path) -> None:
    write(tmp_path, "index.html")
    plan = plan_fixes(tmp_path, scan(problem(source=location())))
    assert plan.fixes == ()
    assert plan.unfixed == (unfixed("the pages' language wasn't given (--lang)"),)
    assert plan.patch == ""


def test_leaves_rules_without_a_fixer_for_a_person(tmp_path: Path) -> None:
    write(tmp_path, "index.html")
    faint = problem("color-contrast", location(tag="<img"), target="p")
    plan = plan_fixes(tmp_path, scan(faint), FixOptions(language="en"))
    assert plan.unfixed == (
        unfixed("there's no automatic fix for this rule yet", "color-contrast", "p"),
    )


class Writer:
    """A value source that answers every slot with the same text, and remembers the slots."""

    def __init__(self, text: str = "Blue mug", *, decline: str | None = None) -> None:
        self.text = text
        self.decline = decline
        self.slots: list[Slot] = []

    def fill(self, slot: Slot) -> Value:
        self.slots.append(slot)
        if self.decline is not None:
            raise CannotFixError(self.decline)
        return Value(text=self.text, rationale="It shows a mug.", source="writer")


def image_problem(text: str = PAGE) -> Occurrence:
    return problem("image-alt", location(text=text, tag="<img"), target="img").model_copy(
        update={"html": '<img src="a.png">'}
    )


def test_alt_text_needs_someone_to_write_it(tmp_path: Path) -> None:
    write(tmp_path, "index.html")
    plan = plan_fixes(tmp_path, scan(image_problem()))
    assert plan.unfixed == (
        unfixed(
            "needs alt text from a person, or from a model (--text-from claude)", "image-alt", "img"
        ),
    )


def test_alt_text_comes_from_the_value_source(tmp_path: Path) -> None:
    text = PAGE.replace("<html>", '<html lang="lt">')
    write(tmp_path, "index.html", text)
    writer = Writer('Mug "Harbor" & co ')
    capture = Capture(image=b"png bytes", context={"heading": "Shop"})

    plan = plan_fixes(
        tmp_path,
        scan(image_problem(text)),
        FixOptions(language="en", values=writer),
        captures={("index.html", ("img",)): capture},
    )

    [fix] = plan.fixes
    assert fix.value == Value(
        text='Mug "Harbor" & co', rationale="It shows a mug.", source="writer"
    )
    assert fix.edits[0].text == ' alt="Mug &quot;Harbor&quot; &amp; co"'
    [slot] = writer.slots
    assert slot == Slot(
        kind="alt-text",
        rule_id="image-alt",
        page="index.html",
        target=("img",),
        html='<img src="a.png">',
        language="lt",
        context={"heading": "Shop"},
        image=b"png bytes",
    )
    assert "image" not in slot.model_dump()


def test_alt_text_falls_back_to_the_given_language(tmp_path: Path) -> None:
    write(tmp_path, "index.html")
    writer = Writer()
    plan_fixes(tmp_path, scan(image_problem()), FixOptions(language="en", values=writer))
    assert [slot.language for slot in writer.slots] == ["en"]


@pytest.mark.parametrize(
    ("writer", "reason"),
    [
        (
            Writer(decline='the image looks decorative; a person should confirm alt=""'),
            'the image looks decorative; a person should confirm alt=""',
        ),
        (Writer("Image of a mug"), "the suggested alt text starts with words like"),
        (Writer("   "), "the suggested alt text is empty"),
    ],
    ids=["declined", "redundant", "empty"],
)
def test_alt_text_that_cannot_be_used_is_left_with_the_reason(
    tmp_path: Path, writer: Writer, reason: str
) -> None:
    write(tmp_path, "index.html")
    plan = plan_fixes(tmp_path, scan(image_problem()), FixOptions(values=writer))
    [left] = plan.unfixed
    assert left.reason.startswith(reason)
    assert plan.changes == ()


LINKS = (
    '<!doctype html>\n<html lang="en">\n<head><title>Shop</title></head>\n<body>\n'
    '<a href="cart.html"><i class="icon-cart"></i></a>\n'
    '<a href="mugs.html"><img src="mug.png" alt=""></a>\n'
    '<a href="shop.html"><img src="shop.png"></a>\n'
    '<a href="/" title="">Home</a>\n'
    '<button class="search"><svg></svg></button>\n'
    '<button class="close"><img src="close.png"></button>\n'
)


def link_problem(href: str) -> Occurrence:
    tag = f'<a href="{href}"'
    return problem("link-name", location(text=LINKS, tag=tag), target=f'a[href="{href}"]')


def button_problem(name: str) -> Occurrence:
    tag = f'<button class="{name}"'
    return problem("button-name", location(text=LINKS, tag=tag), target=f"button.{name}")


def test_lists_the_rules_whose_fixes_need_written_text() -> None:
    assert frozenset({"image-alt", "link-name", "button-name"}) == TEXT_RULES


def test_button_names_come_from_the_value_source(tmp_path: Path) -> None:
    write(tmp_path, "index.html", LINKS)
    writer = Writer("Search")

    plan = plan_fixes(tmp_path, scan(button_problem("search")), FixOptions(values=writer))

    [fix] = plan.fixes
    position = LINKS.index('<button class="search"') + len("<button")
    assert fix.edits == (
        Edit(file="index.html", start=position, end=position, text=' aria-label="Search"'),
    )
    [slot] = writer.slots
    assert (slot.kind, slot.rule_id, slot.max_length) == ("button-name", "button-name", 100)


@pytest.mark.parametrize(
    ("name", "writer", "reason"),
    [
        (
            "search",
            None,
            "needs a button name from a person, or from a model (--text-from claude)",
        ),
        (
            "close",
            Writer("Close"),
            "the image inside it will name the button once the image has alt text",
        ),
        (
            "search",
            Writer("Button for search"),
            'the suggested button name starts with "button"',
        ),
    ],
    ids=["no-writer", "image-without-alt", "redundant"],
)
def test_buttons_that_cannot_be_named_are_left_with_the_reason(
    tmp_path: Path, name: str, writer: Writer | None, reason: str
) -> None:
    write(tmp_path, "index.html", LINKS)
    plan = plan_fixes(tmp_path, scan(button_problem(name)), FixOptions(values=writer))
    [left] = plan.unfixed
    assert left.reason.startswith(reason)


def test_link_names_need_someone_to_write_them(tmp_path: Path) -> None:
    write(tmp_path, "index.html", LINKS)
    plan = plan_fixes(tmp_path, scan(link_problem("cart.html")))
    [left] = plan.unfixed
    assert left.reason == "needs a link name from a person, or from a model (--text-from claude)"


@pytest.mark.parametrize("href", ["cart.html", "mugs.html"], ids=["icon", "decorative-image"])
def test_link_names_come_from_the_value_source(tmp_path: Path, href: str) -> None:
    write(tmp_path, "index.html", LINKS)
    writer = Writer("Your cart")
    target = f'a[href="{href}"]'
    capture = Capture(image=b"png bytes", context={"link": href})

    plan = plan_fixes(
        tmp_path,
        scan(link_problem(href)),
        FixOptions(values=writer),
        captures={("index.html", (target,)): capture},
    )

    [fix] = plan.fixes
    assert fix.value == Value(text="Your cart", rationale="It shows a mug.", source="writer")
    position = LINKS.index(f'<a href="{href}"') + len("<a")
    assert fix.edits == (
        Edit(file="index.html", start=position, end=position, text=' aria-label="Your cart"'),
    )
    [slot] = writer.slots
    assert (slot.kind, slot.rule_id, slot.target, slot.language) == (
        "link-name",
        "link-name",
        (target,),
        "en",
    )
    assert (slot.max_length, slot.context, slot.image) == (100, {"link": href}, b"png bytes")


@pytest.mark.parametrize(
    ("href", "reason"),
    [
        ("shop.html", "the image inside it will name the link once the image has alt text"),
        ("/", "the <a> tag in index.html already has title; a person should check it"),
    ],
    ids=["image-without-alt", "title"],
)
def test_links_that_cannot_take_a_name_are_not_sent_for_one(
    tmp_path: Path, href: str, reason: str
) -> None:
    write(tmp_path, "index.html", LINKS)
    writer = Writer("Shop")
    plan = plan_fixes(tmp_path, scan(link_problem(href)), FixOptions(values=writer))
    [left] = plan.unfixed
    assert left.reason == reason
    assert writer.slots == []


def test_link_names_that_cannot_be_used_are_left_with_the_reason(tmp_path: Path) -> None:
    write(tmp_path, "index.html", LINKS)
    plan = plan_fixes(
        tmp_path, scan(link_problem("cart.html")), FixOptions(values=Writer("Click here"))
    )
    [left] = plan.unfixed
    assert left.reason == "the suggested link name doesn't say where the link goes"


def test_leaves_problems_without_a_source_location(tmp_path: Path) -> None:
    plan = plan_fixes(tmp_path, scan(problem()), FixOptions(language="en"))
    assert plan.unfixed == (unfixed("the element couldn't be traced to its source"),)


@pytest.mark.parametrize(
    "data",
    [None, PAGE.replace("Shop", "Caf\xe9").encode("cp1252")],
    ids=["missing", "windows-1252"],
)
def test_leaves_problems_in_files_that_cannot_be_read(tmp_path: Path, data: bytes | None) -> None:
    if data is not None:
        (tmp_path / "index.html").write_bytes(data)
    plan = plan_fixes(tmp_path, scan(problem(source=location())), FixOptions(language="en"))
    assert plan.unfixed == (unfixed("index.html couldn't be read from the scanned folder"),)


def test_leaves_problems_in_utf16_files_with_advice(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_bytes(b"\xff\xfe" + PAGE.encode("utf-16-le"))
    source = location(text="\ufeff" + PAGE)
    plan = plan_fixes(tmp_path, scan(problem(source=source)), FixOptions(language="en"))
    assert plan.unfixed == (
        unfixed(
            "index.html is saved as UTF-16, which a patch can't change; save it as UTF-8 to get "
            "fixes"
        ),
    )
    assert plan.changes == ()


def test_passes_on_why_a_fixer_refused(tmp_path: Path) -> None:
    write(tmp_path, "index.html", PAGE.replace("<html>", "<!-- moved -->\n<html>"))
    plan = plan_fixes(tmp_path, scan(problem(source=location())), FixOptions(language="en"))
    [left] = plan.unfixed
    assert (
        left.reason
        == "index.html changed after the scan: there is no <html> tag at line 2, column 1"
    )


def test_a_fix_that_overlaps_an_earlier_one_is_left_out(tmp_path: Path) -> None:
    write(tmp_path, "index.html")
    twice = scan(problem(source=location()), problem(source=location()))

    plan = plan_fixes(tmp_path, twice, FixOptions(language="en"))

    assert len(plan.fixes) == 1
    assert plan.unfixed == (unfixed("it overlaps another fix in the same file"),)
    assert plan.patch == unified_diff("index.html", PAGE, FIXED)


def test_the_patch_covers_each_file_once_in_path_order(tmp_path: Path) -> None:
    for name in ["shop/mug.html", "index.html"]:
        write(tmp_path, name)
    result = ScanResult(
        axe_version="4.13.0",
        pages=tuple(
            PageResult(page=name, occurrences=(problem(source=location(name)),))
            for name in ["shop/mug.html", "index.html"]
        ),
    )

    plan = plan_fixes(tmp_path, result, FixOptions(language="en"))

    assert [fix.page for fix in plan.fixes] == ["shop/mug.html", "index.html"]
    assert plan.patch == unified_diff("index.html", PAGE, FIXED) + unified_diff(
        "shop/mug.html", PAGE, FIXED
    )


def test_options_reject_a_language_that_is_not_a_tag() -> None:
    with pytest.raises(ValueError, match="is not a language tag"):
        FixOptions(language="English")
