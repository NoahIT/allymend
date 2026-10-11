from collections.abc import Callable
from pathlib import Path

import pytest

from allymend.mapper import map_sources
from allymend.scanner import scan_directory

pytestmark = pytest.mark.browser

PIXEL = "data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=="


def test_traces_problems_found_in_the_browser_to_their_source_lines(
    tmp_path: Path, write_page: Callable[..., Path]
) -> None:
    body = (
        f'\n<ul>\n  <li><img src="{PIXEL}" alt="Mug"></li>\n  <li><img src="{PIXEL}"></li>\n</ul>\n'
    )
    path = write_page("index.html", body, lang=None)
    text = path.read_bytes().decode("utf-8")

    [page] = map_sources(tmp_path, scan_directory(tmp_path)).pages

    sources = {o.rule_id: o.source for o in page.occurrences}
    assert sources["html-has-lang"] is not None
    assert sources["html-has-lang"].line == 1
    image = sources["image-alt"]
    assert image is not None
    assert image.line == 4
    assert text[image.offset :].startswith(f'<img src="{PIXEL}">')
