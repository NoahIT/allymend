from collections.abc import Callable
from pathlib import Path

import pytest

from allymend.core.models import Slot, SourceLocation, Value
from allymend.errors import CannotFixError
from allymend.fixers import FixOptions, apply_edits, check_alt_text, fix_image_alt, plan_fixes
from allymend.mapper import map_sources
from allymend.scanner import scan_directory
from allymend.verifier import verify_fixes


def fix(text: str, alt: str = "Blue mug", tag: str = "<img") -> str:
    offset = text.lower().index(tag)
    location = SourceLocation(file="index.html", line=1, column=offset + 1, offset=offset)
    return apply_edits(text, [fix_image_alt(text, location, alt)])


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ('<img src="mug.png">', '<img alt="Blue mug" src="mug.png">'),
        ('<IMG src="mug.png">', '<IMG alt="Blue mug" src="mug.png">'),
        ('<img\n  src="mug.png">', '<img alt="Blue mug"\n  src="mug.png">'),
        ('<img src="mug.png"/>', '<img alt="Blue mug" src="mug.png"/>'),
    ],
    ids=["plain", "upper-case", "attributes-on-the-next-line", "self-closing"],
)
def test_adds_alt_after_the_tag_name(html: str, expected: str) -> None:
    assert fix(f"<p>{html}</p>") == f"<p>{expected}</p>"


def test_escapes_the_text_for_an_attribute() -> None:
    assert fix('<img src="a.png">', alt='Mugs & "cups" <3') == (
        '<img alt="Mugs &amp; &quot;cups&quot; &lt;3" src="a.png">'
    )


@pytest.mark.parametrize("html", ['<img alt="" src="a.png">', "<img ALT=logo>", "<img alt>"])
def test_refuses_an_image_that_already_has_alt(html: str) -> None:
    with pytest.raises(CannotFixError, match="already has an alt attribute"):
        fix(html)


def test_refuses_when_the_file_changed_after_the_scan() -> None:
    with pytest.raises(CannotFixError, match=r"^index\.html changed after the scan"):
        fix("<p><imgs src='a.png'></p>", tag="<imgs")


@pytest.mark.parametrize(
    ("text", "cleaned"),
    [("Blue mug", "Blue mug"), ("  Blue\n\tmug  ", "Blue mug"), ("Logo of Harbor Goods", None)],
)
def test_alt_text_is_tidied(text: str, cleaned: str | None) -> None:
    assert check_alt_text(text, 150) == (cleaned or text)


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "the suggested alt text is empty"),
        ("x" * 151, "the suggested alt text is longer than 150 characters"),
        ("Image of a blue mug", 'the suggested alt text starts with words like "image of"'),
        ("photo of the team", 'the suggested alt text starts with words like "image of"'),
        ("Blue\x07mug", "the suggested alt text contains control characters"),
    ],
    ids=["empty", "too-long", "image-of", "photo-of", "control-character"],
)
def test_unusable_alt_text_is_refused(text: str, reason: str) -> None:
    with pytest.raises(CannotFixError, match=f"^{reason}"):
        check_alt_text(text, 150)


class Writer:
    def fill(self, slot: Slot) -> Value:
        return Value(text="Blue mug", rationale=f"A mug on {slot.page}.", source="writer")


@pytest.mark.browser
def test_written_alt_text_passes_the_checks(
    tmp_path: Path, write_page: Callable[..., Path]
) -> None:
    write_page("index.html", '<img src="mug.png">')
    result = map_sources(tmp_path, scan_directory(tmp_path))

    verified = verify_fixes(tmp_path, plan_fixes(tmp_path, result, FixOptions(values=Writer())))

    [fixed] = verified.fixes
    assert fixed.value == Value(text="Blue mug", rationale="A mug on index.html.", source="writer")
    [evidence] = verified.verifications
    assert evidence.passed
    assert 'alt="Blue mug"' in verified.patch
