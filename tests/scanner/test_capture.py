import socket
import struct
import zlib
from collections.abc import Callable
from pathlib import Path

import pytest

from allymend.core.models import Impact, Occurrence, PageResult, ScanResult
from allymend.scanner import ScanOptions, capture_elements, open_browser
from allymend.scanner.runner import _bounded
from allymend.scanner.site import serve

pytestmark = pytest.mark.browser

PIXEL = "data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=="
FIGURE = (
    "<h2>Mugs</h2><p>Our range.</p>"
    '<figure><a href="/shop/mug.html"><img class="mug" src="/images/mug.png?v=2" '
    'width="40" height="30" style="background: #36c">Blue mug</a>'
    "<figcaption>Handmade in Vilnius</figcaption></figure>"
)


def screenshot_size(png: bytes, width: int, height: int) -> bool:
    """Whether a PNG screenshot has about this size.

    Layout at fractional positions rounds the screenshot box out by up to a pixel.
    """
    actual = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    return all(0 <= got - want <= 1 for got, want in zip(actual, (width, height), strict=True))


def solid_png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

    rows = b"".join(b"\x00" + b"\x33\x66\xcc" * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def jpeg_size(jpeg: bytes) -> tuple[int, int]:
    position = 2
    while position < len(jpeg):
        marker = jpeg[position + 1]
        length = int.from_bytes(jpeg[position + 2 : position + 4], "big")
        if marker in {0xC0, 0xC1, 0xC2}:
            height = int.from_bytes(jpeg[position + 5 : position + 7], "big")
            width = int.from_bytes(jpeg[position + 7 : position + 9], "big")
            return width, height
        position += 2 + length
    message = "no frame header"
    raise ValueError(message)


def occurrence(target: tuple[str, ...], rule_id: str = "image-alt") -> Occurrence:
    return Occurrence(
        rule_id=rule_id,
        impact=Impact.CRITICAL,
        wcag=("1.1.1",),
        summary="",
        help_url="https://example.com/",
        target=target,
        html="<img>",
        failure_summary="",
    )


def test_captures_a_screenshot_and_the_text_around_an_image(
    tmp_path: Path, write_page: Callable[..., Path]
) -> None:
    write_page("index.html", FIGURE)
    with serve(tmp_path) as base_url, open_browser() as browser:
        captures = browser.capture(f"{base_url}index.html", [("img.mug",)])

    capture = captures[("img.mug",)]
    assert capture.image is not None
    assert capture.image.startswith(b"\x89PNG")
    assert screenshot_size(capture.image, 40, 30)
    assert capture.context == {
        "page title": "Test page",
        "heading": "Mugs",
        "caption": "Handmade in Vilnius",
        "link": "/shop/mug.html",
        "link text": "Blue mug",
        "file name": "mug.png",
        "nearby text": "Blue mug",
    }


@pytest.mark.parametrize(
    ("natural", "expected"),
    [((200, 100), (200, 100)), ((3200, 800), (1568, 392))],
    ids=["as-is", "scaled-down"],
)
def test_captures_the_decoded_image_whatever_the_page_does_to_it(
    tmp_path: Path,
    write_page: Callable[..., Path],
    natural: tuple[int, int],
    expected: tuple[int, int],
) -> None:
    (tmp_path / "photo.png").write_bytes(solid_png(*natural))
    write_page("index.html", '<img src="photo.png" style="width: 50px; opacity: 0">')
    with serve(tmp_path) as base_url, open_browser() as browser:
        [capture] = browser.capture(f"{base_url}index.html", [("img",)]).values()
    assert capture.media_type == "image/jpeg"
    assert capture.image is not None
    assert jpeg_size(capture.image) == expected


def test_falls_back_to_a_screenshot_for_images_from_other_sites(
    tmp_path: Path, write_page: Callable[..., Path]
) -> None:
    other = tmp_path / "other"
    other.mkdir()
    (other / "photo.png").write_bytes(solid_png(20, 10))
    with serve(other) as other_url, serve(tmp_path) as base_url, open_browser() as browser:
        write_page("index.html", f'<img src="{other_url}photo.png">')
        [capture] = browser.capture(f"{base_url}index.html", [("img",)]).values()
    assert capture.media_type == "image/png"
    assert capture.image is not None
    assert screenshot_size(capture.image, 20, 10)


def test_leaves_out_elements_it_cannot_capture(
    tmp_path: Path, write_page: Callable[..., Path]
) -> None:
    write_page("index.html", f'<img class="shown" src="{PIXEL}"><img class="gone" hidden>')
    with serve(tmp_path) as base_url, open_browser(ScanOptions(timeout_ms=2000)) as browser:
        captures = browser.capture(
            f"{base_url}index.html",
            [("img.shown",), ("img.gone",), (".missing",), ("iframe", "img")],
        )
    assert list(captures) == [("img.shown",)]
    assert "file name" not in captures[("img.shown",)].context


def test_bounds_long_text(tmp_path: Path, write_page: Callable[..., Path]) -> None:
    write_page("index.html", f'<p>{"word " * 100}<img src="{PIXEL}"></p>')
    with serve(tmp_path) as base_url, open_browser() as browser:
        [capture] = browser.capture(f"{base_url}index.html", [("img",)]).values()
    nearby = capture.context["nearby text"]
    assert len(nearby) <= 200
    assert nearby.endswith(" word...")


def test_a_page_that_does_not_load_gives_no_captures(tmp_path: Path) -> None:
    with serve(tmp_path) as base_url, open_browser(ScanOptions(timeout_ms=2000)) as browser:
        assert browser.capture(f"{base_url}missing.html", [("img",)]) == {}


def test_a_page_that_cannot_be_reached_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}/index.html"
    with open_browser() as browser:
        assert browser.capture(url, [("img",)]) == {}
    [record] = caplog.records
    assert record.getMessage().startswith(f"could not capture elements on {url}: ")


def test_a_target_the_browser_rejects_is_left_out(
    tmp_path: Path, write_page: Callable[..., Path]
) -> None:
    write_page("index.html", f'<img src="{PIXEL}">')
    with serve(tmp_path) as base_url, open_browser() as browser:
        captures = browser.capture(f"{base_url}index.html", [("img[",), ("img",)])
    assert list(captures) == [("img",)]


def test_context_from_the_page_is_checked_and_bounded() -> None:
    assert _bounded("not a mapping") == {}
    assert _bounded({"heading": " Shop ", "count": 3, "empty": "  ", 4: "x"}) == {"heading": "Shop"}
    assert _bounded({"nearby text": "x" * 300}) == {"nearby text": "x" * 197 + "..."}


def test_captures_only_the_rules_asked_for_keyed_by_page_and_target(
    tmp_path: Path, write_page: Callable[..., Path]
) -> None:
    write_page("index.html", FIGURE)
    write_page("about.html", f'<img src="{PIXEL}">')
    result = ScanResult(
        axe_version="4.13.0",
        pages=(
            PageResult(page="index.html", occurrences=(occurrence(("img.mug",)),)),
            PageResult(page="about.html", occurrences=(occurrence(("img",), "link-name"),)),
            PageResult(page="missing.html", error="HTTP 404"),
        ),
    )

    captures = capture_elements(tmp_path, result, {"image-alt"})

    assert list(captures) == [("index.html", ("img.mug",))]
