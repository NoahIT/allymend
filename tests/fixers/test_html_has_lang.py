from collections.abc import Callable
from pathlib import Path

import pytest

from pataisa.core.models import SourceLocation
from pataisa.errors import CannotFixError
from pataisa.fixers import apply_edits, fix_html_has_lang
from pataisa.mapper import map_sources
from pataisa.scanner import scan_directory

REST = "<head><title>Shop</title></head><body><h1>Shop</h1></body></html>"


def fix(text: str, language: str = "en", tag: str = "<html") -> str:
    offset = text.lower().index(tag)
    location = SourceLocation(file="index.html", line=1, column=offset + 1, offset=offset)
    return apply_edits(text, [fix_html_has_lang(text, location, language)])


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<html>", '<html lang="en">'),
        ('<html class="no-js">', '<html lang="en" class="no-js">'),
        ('<html\n  class="no-js">', '<html lang="en"\n  class="no-js">'),
        ("<HTML>", '<HTML lang="en">'),
        ('<html xml:lang="">', '<html lang="en" xml:lang="">'),
        ("<html hidden>", '<html lang="en" hidden>'),
    ],
    ids=[
        "bare",
        "other-attributes",
        "attributes-on-the-next-line",
        "upper-case",
        "empty-xml-lang",
        "attribute-without-a-value",
    ],
)
def test_adds_the_attribute_after_the_tag_name(html: str, expected: str) -> None:
    assert fix(f"<!doctype html>{html}{REST}") == f"<!doctype html>{expected}{REST}"


def test_stops_reading_attributes_at_a_value_that_never_closes() -> None:
    assert fix('<html class="no-js') == '<html lang="en" class="no-js'


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<html lang>", '<html lang="en">'),
        ('<html lang="">', '<html lang="en">'),
        ("<html lang=''>", '<html lang="en">'),
        ('<html lang=" ">', '<html lang="en">'),
        ('<html LANG="">', '<html lang="en">'),
        ('<html lang = "" >', '<html lang="en" >'),
        ("<html lang=>", '<html lang="en">'),
        ('<html class="a" / lang="">', '<html class="a" / lang="en">'),
        ('<html class=a lang="">', '<html class=a lang="en">'),
        ('<html class="a"lang="">', '<html class="a"lang="en">'),
        ('<html data-x="lang=en" lang="">', '<html data-x="lang=en" lang="en">'),
    ],
    ids=[
        "no-value",
        "double-quoted",
        "single-quoted",
        "only-space",
        "upper-case",
        "spaced",
        "unquoted-empty",
        "after-a-slash",
        "after-an-unquoted-value",
        "no-space-between-attributes",
        "lang-inside-another-value",
    ],
)
def test_replaces_an_empty_lang_attribute(html: str, expected: str) -> None:
    assert fix(f"<!doctype html>{html}{REST}") == f"<!doctype html>{expected}{REST}"


def test_replaces_only_the_first_of_two_lang_attributes() -> None:
    text = f'<html lang="" lang="lt">{REST}'
    assert fix(text) == f'<html lang="en" lang="lt">{REST}'


@pytest.mark.parametrize("language", ["lt", "en-GB", "zh-Hant-TW", "sr-Latn"])
def test_accepts_language_tags(language: str) -> None:
    assert fix(f"<html>{REST}", language).startswith(f'<html lang="{language}">')


@pytest.mark.parametrize("language", ["", "e", "english", "en_GB", 'en" onload="x', "en-"])
def test_rejects_values_that_are_not_language_tags(language: str) -> None:
    with pytest.raises(ValueError, match="is not a language tag such as en or en-GB"):
        fix(f"<html>{REST}", language)


def test_refuses_a_page_that_already_has_a_language() -> None:
    with pytest.raises(CannotFixError, match=r"^the <html> tag in index\.html already has"):
        fix(f'<html lang="lt">{REST}')


@pytest.mark.parametrize("tag", ["<head>", "<h1>"], ids=["another-tag", "shifted"])
def test_refuses_when_the_file_changed_after_the_scan(tag: str) -> None:
    with pytest.raises(CannotFixError, match=r"^index\.html changed after the scan"):
        fix(f"<html>{REST}", tag=tag)


def test_refuses_a_tag_that_only_starts_like_html() -> None:
    with pytest.raises(CannotFixError, match="changed after the scan"):
        fix(f"<htmlx><html>{REST}", tag="<htmlx")


@pytest.mark.browser
def test_the_fixed_page_passes_the_check(tmp_path: Path, write_page: Callable[..., Path]) -> None:
    path = write_page("index.html", lang=None)
    text = path.read_bytes().decode("utf-8")
    [page] = map_sources(tmp_path, scan_directory(tmp_path)).pages
    [occurrence] = page.occurrences
    assert occurrence.rule_id == "html-has-lang"
    assert occurrence.source is not None

    path.write_bytes(
        apply_edits(text, [fix_html_has_lang(text, occurrence.source, "en")]).encode("utf-8")
    )

    [page] = scan_directory(tmp_path).pages
    assert page.error is None
    assert page.occurrences == ()
