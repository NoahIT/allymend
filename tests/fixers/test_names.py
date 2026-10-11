from collections.abc import Callable
from pathlib import Path

import pytest

from allymend.core.models import FileChange, Fix, FixPlan, SourceLocation
from allymend.errors import CannotFixError
from allymend.files import read_source
from allymend.fixers import (
    apply_edits,
    check_name,
    check_name_tag,
    fix_name,
    unified_diff,
)
from allymend.fixers.names import Role
from allymend.mapper import map_sources
from allymend.scanner import scan_directory
from allymend.verifier import verify_fixes


def at(text: str, tag: str) -> SourceLocation:
    offset = text.lower().index(f"<{tag}")
    return SourceLocation(file="index.html", line=1, column=offset + 1, offset=offset)


def fix(text: str, tag: str = "a", name: str = "Shop") -> str:
    return apply_edits(text, [fix_name(text, at(text, tag), tag, name)])


@pytest.mark.parametrize(
    ("html", "tag", "expected"),
    [
        (
            '<a href="/shop"><svg></svg></a>',
            "a",
            '<a aria-label="Shop" href="/shop"><svg></svg></a>',
        ),
        ("<A HREF=/shop></A>", "a", '<A aria-label="Shop" HREF=/shop></A>'),
        ('<a\n  href="/shop"></a>', "a", '<a aria-label="Shop"\n  href="/shop"></a>'),
        ("<a></a>", "a", '<a aria-label="Shop"></a>'),
        (
            '<button class="icon"></button>',
            "button",
            '<button aria-label="Shop" class="icon"></button>',
        ),
        ("<BUTTON/>", "button", '<BUTTON aria-label="Shop"/>'),
        ('<input type="email">', "input", '<input aria-label="Shop" type="email">'),
        (
            "<textarea rows=4></textarea>",
            "textarea",
            '<textarea aria-label="Shop" rows=4></textarea>',
        ),
        ("<select name=size></select>", "select", '<select aria-label="Shop" name=size></select>'),
    ],
    ids=[
        "link",
        "upper-case",
        "attributes-on-the-next-line",
        "no-attributes",
        "button",
        "self-closing-button",
        "input",
        "textarea",
        "select",
    ],
)
def test_adds_aria_label_after_the_tag_name(html: str, tag: str, expected: str) -> None:
    assert fix(f"<p>{html}</p>", tag) == f"<p>{expected}</p>"


def test_escapes_the_name_for_an_attribute() -> None:
    assert fix('<a href="/">', name='Mugs & "cups" <3') == (
        '<a aria-label="Mugs &amp; &quot;cups&quot; &lt;3" href="/">'
    )


@pytest.mark.parametrize(
    ("html", "tag", "attribute"),
    [
        ('<a aria-label="" href="/">', "a", "aria-label"),
        ('<a href="/" ARIA-LABELLEDBY="missing">', "a", "aria-labelledby"),
        ("<a title href=/>", "a", "title"),
        ('<button title="">', "button", "title"),
    ],
)
def test_refuses_an_element_that_already_has_a_name_attribute(
    html: str, tag: str, attribute: str
) -> None:
    reason = f"the <{tag}> tag in index.html already has {attribute}; a person should check it"
    with pytest.raises(CannotFixError, match=f"^{reason}$"):
        check_name_tag(html, at(html, tag), tag)
    with pytest.raises(CannotFixError, match=f"^{reason}$"):
        fix(html, tag)


@pytest.mark.parametrize(
    ("html", "tag"),
    [
        ("<p><abbr>A</abbr></p>", "a"),
        ("<p><area href='/'></p>", "a"),
        ("<p><button-group></button-group></p>", "button"),
    ],
)
def test_refuses_when_the_file_changed_after_the_scan(html: str, tag: str) -> None:
    with pytest.raises(
        CannotFixError, match=rf"^index\.html changed after the scan: there is no <{tag}> tag"
    ):
        check_name_tag(html, at(html, tag), tag)


def test_an_element_that_can_be_named_passes_the_tag_check() -> None:
    html = '<a href="/shop" class="icon"><i class="fa fa-cart"></i></a>'
    check_name_tag(html, at(html, "a"), "a")


@pytest.mark.parametrize(
    ("text", "role", "cleaned"),
    [
        ("Shop", "link", "Shop"),
        ("  Your\n\tcart  ", "link", "Your cart"),
        ("LinkedIn profile", "link", None),
        ("Read more about mugs", "link", None),
        ("Close menu", "button", None),
        ("Buttons and badges", "button", None),
        ("Email address", "field", None),
        ("Field notes", "field", None),
    ],
)
def test_names_are_tidied(text: str, role: Role, cleaned: str | None) -> None:
    assert check_name(text, 100, role) == (cleaned or text)


@pytest.mark.parametrize(
    ("text", "role", "reason"),
    [
        ("", "link", "the suggested link name is empty"),
        ("x" * 101, "link", "the suggested link name is longer than 100 characters"),
        ("Cart\x07", "button", "the suggested button name contains control characters"),
        ("Link to the shop", "link", 'the suggested link name starts with "link"'),
        ("link: shop", "link", 'the suggested link name starts with "link"'),
        ("Button: search", "button", 'the suggested button name starts with "button"'),
        ("Click here", "link", "the suggested link name doesn't say where the link goes"),
        ("Read more.", "link", "the suggested link name doesn't say where the link goes"),
        ("MORE!", "link", "the suggested link name doesn't say where the link goes"),
        ("Click here", "button", "the suggested button name doesn't say what the button does"),
        ("Press", "button", "the suggested button name doesn't say what the button does"),
        ("Input", "field", "the suggested field name doesn't say what the field is for"),
        ("Type here...", "field", "the suggested field name doesn't say what the field is for"),
        ("", "field", "the suggested field name is empty"),
    ],
    ids=[
        "empty",
        "too-long",
        "control-character",
        "link-to",
        "link-colon",
        "button-colon",
        "click-here",
        "read-more",
        "more",
        "button-click-here",
        "press",
        "input",
        "type-here",
        "empty-field",
    ],
)
def test_unusable_names_are_refused(text: str, role: Role, reason: str) -> None:
    with pytest.raises(CannotFixError, match=f"^{reason}"):
        check_name(text, 100, role)


@pytest.mark.browser
@pytest.mark.parametrize(
    ("rule_id", "tag", "element"),
    [
        ("link-name", "a", '<a href="shop.html"><svg width="24" height="24"></svg></a>'),
        (
            "button-name",
            "button",
            '<button type="button"><svg width="24" height="24"></svg></button>',
        ),
        ("label", "input", '<input type="text" name="q">'),
        ("label", "textarea", '<textarea name="note"></textarea>'),
        ("select-name", "select", '<select name="size"><option>S</option></select>'),
    ],
    ids=["link", "button", "input", "textarea", "select"],
)
def test_a_named_element_passes_the_checks(
    tmp_path: Path, write_page: Callable[..., Path], rule_id: str, tag: str, element: str
) -> None:
    write_page("index.html", element)
    result = map_sources(tmp_path, scan_directory(tmp_path))
    [unnamed] = [o for o in result.pages[0].occurrences if o.rule_id == rule_id]
    assert unnamed.source is not None
    source = read_source(tmp_path, "index.html")
    assert source is not None
    edit = fix_name(source.text, unnamed.source, tag, "Shop")
    after = apply_edits(source.text, [edit])
    plan = FixPlan(
        fixes=(Fix(rule_id=rule_id, page="index.html", target=unnamed.target, edits=(edit,)),),
        unfixed=(),
        changes=(
            FileChange(
                file="index.html",
                diff=unified_diff("index.html", source.text, after),
                before=source.text,
                after=after,
            ),
        ),
    )

    verified = verify_fixes(tmp_path, plan)

    [evidence] = verified.verifications
    assert evidence.passed
    assert element.replace(f"<{tag} ", f'<{tag} aria-label="Shop" ', 1) in verified.patch
