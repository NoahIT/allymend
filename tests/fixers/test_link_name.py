from collections.abc import Callable
from pathlib import Path

import pytest

from allymend.core.models import FileChange, Fix, FixPlan, SourceLocation
from allymend.errors import CannotFixError
from allymend.files import read_source
from allymend.fixers import (
    apply_edits,
    check_link_name,
    check_link_tag,
    fix_link_name,
    unified_diff,
)
from allymend.mapper import map_sources
from allymend.scanner import scan_directory
from allymend.verifier import verify_fixes


def at(text: str, tag: str) -> SourceLocation:
    offset = text.lower().index(tag)
    return SourceLocation(file="index.html", line=1, column=offset + 1, offset=offset)


def fix(text: str, name: str = "Shop", tag: str = "<a") -> str:
    return apply_edits(text, [fix_link_name(text, at(text, tag), name)])


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ('<a href="/shop"><svg></svg></a>', '<a aria-label="Shop" href="/shop"><svg></svg></a>'),
        ("<A HREF=/shop></A>", '<A aria-label="Shop" HREF=/shop></A>'),
        ('<a\n  href="/shop"></a>', '<a aria-label="Shop"\n  href="/shop"></a>'),
        ("<a></a>", '<a aria-label="Shop"></a>'),
    ],
    ids=["plain", "upper-case", "attributes-on-the-next-line", "no-attributes"],
)
def test_adds_aria_label_after_the_tag_name(html: str, expected: str) -> None:
    assert fix(f"<p>{html}</p>") == f"<p>{expected}</p>"


def test_escapes_the_name_for_an_attribute() -> None:
    assert fix('<a href="/">', name='Mugs & "cups" <3') == (
        '<a aria-label="Mugs &amp; &quot;cups&quot; &lt;3" href="/">'
    )


@pytest.mark.parametrize(
    ("html", "attribute"),
    [
        ('<a aria-label="" href="/">', "aria-label"),
        ('<a href="/" ARIA-LABELLEDBY="missing">', "aria-labelledby"),
        ("<a title href=/>", "title"),
    ],
)
def test_refuses_a_link_that_already_has_a_name_attribute(html: str, attribute: str) -> None:
    reason = f"the <a> tag in index.html already has {attribute}; a person should check it"
    with pytest.raises(CannotFixError, match=f"^{reason}$"):
        check_link_tag(html, at(html, "<a"))
    with pytest.raises(CannotFixError, match=f"^{reason}$"):
        fix(html)


@pytest.mark.parametrize("html", ["<p><abbr>A</abbr></p>", "<p><area href='/'></p>"])
def test_refuses_when_the_file_changed_after_the_scan(html: str) -> None:
    with pytest.raises(CannotFixError, match=r"^index\.html changed after the scan"):
        check_link_tag(html, at(html, "<a"))


def test_a_link_that_can_be_named_passes_the_tag_check() -> None:
    html = '<a href="/shop" class="icon"><i class="fa fa-cart"></i></a>'
    check_link_tag(html, at(html, "<a"))


@pytest.mark.parametrize(
    ("text", "cleaned"),
    [
        ("Shop", "Shop"),
        ("  Your\n\tcart  ", "Your cart"),
        ("LinkedIn profile", None),
        ("Read more about mugs", None),
    ],
)
def test_link_names_are_tidied(text: str, cleaned: str | None) -> None:
    assert check_link_name(text, 100) == (cleaned or text)


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "the suggested link name is empty"),
        ("x" * 101, "the suggested link name is longer than 100 characters"),
        ("Cart\x07", "the suggested link name contains control characters"),
        ("Link to the shop", 'the suggested link name starts with "link"'),
        ("link: shop", 'the suggested link name starts with "link"'),
        ("Click here", "the suggested link name doesn't say where the link goes"),
        ("Read more.", "the suggested link name doesn't say where the link goes"),
        ("MORE!", "the suggested link name doesn't say where the link goes"),
    ],
    ids=[
        "empty",
        "too-long",
        "control-character",
        "link-to",
        "link-colon",
        "click-here",
        "read-more",
        "more",
    ],
)
def test_unusable_link_names_are_refused(text: str, reason: str) -> None:
    with pytest.raises(CannotFixError, match=f"^{reason}"):
        check_link_name(text, 100)


@pytest.mark.browser
def test_a_named_link_passes_the_checks(tmp_path: Path, write_page: Callable[..., Path]) -> None:
    write_page("index.html", '<a href="shop.html"><svg width="24" height="24"></svg></a>')
    result = map_sources(tmp_path, scan_directory(tmp_path))
    [link] = [o for o in result.pages[0].occurrences if o.rule_id == "link-name"]
    assert link.source is not None
    source = read_source(tmp_path, "index.html")
    assert source is not None
    edit = fix_link_name(source.text, link.source, "Shop")
    after = apply_edits(source.text, [edit])
    plan = FixPlan(
        fixes=(Fix(rule_id="link-name", page="index.html", target=link.target, edits=(edit,)),),
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
    assert '<a aria-label="Shop" href="shop.html">' in verified.patch
