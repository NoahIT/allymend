from pathlib import Path

import pytest

from pataisa.core.models import Impact, Occurrence, PageResult, ScanResult, SourceLocation
from pataisa.mapper import HtmlSource, map_sources

PAGE = (
    "<!doctype html>\n"
    '<html lang="en">\n'
    '<head><meta name="viewport" content="width=device-width"><title>Shop</title></head>\n'
    "<body>\n"
    '<main><h1>Shop</h1><img src="mug.jpg"></main>\n'
    "</body>\n"
    "</html>\n"
)


def occurrence(
    target: str | tuple[str, ...] = "img", html: str = '<img src="mug.jpg">'
) -> Occurrence:
    return Occurrence(
        rule_id="image-alt",
        impact=Impact.CRITICAL,
        wcag=("1.1.1",),
        summary="Images must have alternative text",
        help_url="https://dequeuniversity.com/rules/axe/4.13/image-alt",
        target=(target,) if isinstance(target, str) else target,
        html=html,
        failure_summary="",
    )


def locate(
    text: str, target: str | tuple[str, ...] = "img", html: str = "<img>"
) -> SourceLocation | None:
    return HtmlSource(text, "index.html").locate(occurrence(target, html))


def test_finds_the_start_tag_of_the_element() -> None:
    assert locate(PAGE) == SourceLocation(
        file="index.html", line=5, column=20, offset=PAGE.index("<img")
    )


@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_offset_points_at_the_tag_whatever_the_line_endings(newline: str) -> None:
    text = PAGE.replace("\n", newline)
    location = locate(text)
    assert location is not None
    assert location.line == 5
    assert text[location.offset : location.offset + 4] == "<img"


def test_offset_counts_a_byte_order_mark() -> None:
    text = "\ufeff" + PAGE
    location = locate(text)
    assert location is not None
    assert text[location.offset : location.offset + 4] == "<img"


def test_offset_counts_characters_not_bytes() -> None:
    text = PAGE.replace("<h1>Shop</h1>", "<h1>Žąsų parduotuvė 🙂</h1>")
    location = locate(text)
    assert location is not None
    assert text[location.offset : location.offset + 4] == "<img"


def test_finds_elements_in_the_head() -> None:
    location = locate(PAGE, 'meta[name="viewport"]', '<meta name="viewport">')
    assert location is not None
    assert (location.line, PAGE[location.offset : location.offset + 5]) == (3, "<meta")


def test_elements_the_parser_inserts_have_no_location() -> None:
    text = "<table><tr><td>Price</td></tr></table>"
    assert locate(text, "tbody", "<tbody>") is None
    assert locate(text, "td", "<td>") is not None


@pytest.mark.parametrize(
    ("target", "html"),
    [
        ("video", "<video>"),
        ("p", "<p>"),
        (("iframe", "img"), "<img>"),
        ("img", '<input type="image">'),
        ("img", "not markup"),
        ("#\\31 23", "<img>"),
    ],
    ids=["no-match", "several-matches", "inside-a-frame", "different-tag", "no-tag", "unsupported"],
)
def test_no_location_unless_the_match_is_certain(target: str | tuple[str, ...], html: str) -> None:
    text = "<p>One</p><p>Two</p><img src='a.png'>"
    assert locate(text, target, html) is None


def test_falls_back_to_attributes_when_a_script_changed_the_classes() -> None:
    text = '<div class="about">\n  <img src="/qr.png" style="width: 110px">\n</div>'
    rendered = '<img src="/qr.png" style="width: 110px; top: -50px;">'
    assert locate(text, ".fade-in > img", rendered) == SourceLocation(
        file="index.html", line=2, column=3, offset=text.index("<img"), found_by="attributes"
    )


@pytest.mark.parametrize(
    ("text", "target", "html", "found"),
    [
        (
            '<img src="/link.png" id="first"><img src="/link.png" id="second">',
            ".missing",
            '<img src="/link.png" id="second">',
            'id="second"',
        ),
        ('<a href="/a">A</a><a href="/b">B</a>', "a", '<a href="/b">', 'href="/b"'),
        (
            '<a href="/p?a=1&amp;b=2">Shop</a>',
            ".missing",
            '<a href="/p?a=1&amp;b=2" class="active">',
            "href",
        ),
        ('<img id="123" src="a.png">', "#\\31 23", '<img id="123" src="a.png">', 'id="123"'),
    ],
    ids=["id-before-a-shared-src", "one-of-several-selector-matches", "encoded-url", "css-escape"],
)
def test_the_first_attribute_that_singles_out_the_element_wins(
    text: str, target: str, html: str, found: str
) -> None:
    location = locate(text, target, html)
    assert location is not None
    assert location.found_by == "attributes"
    start = text.rindex("<", 0, text.index(found))
    assert location.offset == start


def test_no_location_when_the_attributes_are_shared_too() -> None:
    text = '<img src="/link.png"><img src="/link.png">'
    assert locate(text, ".missing", '<img src="/link.png">') is None


def test_no_fallback_for_markup_that_only_parses_inside_a_parent() -> None:
    text = '<table><tr><td id="price">9</td></tr></table>'
    assert locate(text, ".missing", '<td id="price">') is None


def write(root: Path, relative: str, data: bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def scan(*pages: PageResult) -> ScanResult:
    return ScanResult(axe_version="4.13.0", pages=pages)


def test_map_sources_reads_each_page_from_the_folder(tmp_path: Path) -> None:
    write(tmp_path, "shop/index.html", PAGE.encode("utf-8"))
    result = scan(PageResult(page="shop/index.html", occurrences=(occurrence(),)))

    [page] = map_sources(tmp_path, result).pages

    [mapped] = page.occurrences
    assert mapped.source == SourceLocation(
        file="shop/index.html", line=5, column=20, offset=PAGE.index("<img")
    )


@pytest.mark.parametrize("codec", ["utf-16-le", "utf-16-be"])
def test_map_sources_reads_utf16_pages_with_a_byte_order_mark(tmp_path: Path, codec: str) -> None:
    text = "\ufeff" + PAGE.replace("\n", "\r\n")
    write(tmp_path, "index.html", text.encode(codec))
    result = scan(PageResult(page="index.html", occurrences=(occurrence(),)))

    [page] = map_sources(tmp_path, result).pages

    [mapped] = page.occurrences
    assert mapped.source is not None
    assert (mapped.source.line, mapped.source.column) == (5, 20)
    assert text[mapped.source.offset :].startswith("<img")


def test_map_sources_leaves_pages_without_problems_alone(tmp_path: Path) -> None:
    clean = PageResult(page="about.html")
    failed = PageResult(page="missing.html", error="HTTP 404")
    assert map_sources(tmp_path, scan(clean, failed)).pages == (clean, failed)


@pytest.mark.parametrize(
    ("relative", "data"),
    [
        ("index.html", "<img src='caf\xe9.png'>".encode("cp1252")),
        ("missing.html", None),
        ("../outside.html", b"<img src='a.png'>"),
    ],
    ids=["windows-1252", "missing-file", "outside-the-folder"],
)
def test_map_sources_skips_files_it_cannot_safely_read(
    tmp_path: Path, relative: str, data: bytes | None
) -> None:
    root = tmp_path / "site"
    root.mkdir()
    if data is not None:
        write(root, relative, data)
    result = scan(PageResult(page=relative, occurrences=(occurrence(),)))

    [page] = map_sources(root, result).pages

    assert page.occurrences[0].source is None
