from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from allymend.scanner.site import find_pages, serve


def touch(root: Path, relative: str, content: str = "") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_find_pages_returns_sorted_relative_paths(tmp_path: Path) -> None:
    for page in ["shop/mug.html", "index.html", "about.html", "styles.css"]:
        touch(tmp_path, page)
    assert find_pages(tmp_path) == ("about.html", "index.html", "shop/mug.html")


def test_find_pages_skips_hidden_folders_and_node_modules(tmp_path: Path) -> None:
    for page in ["index.html", ".git/index.html", "node_modules/pkg/readme.html"]:
        touch(tmp_path, page)
    assert find_pages(tmp_path) == ("index.html",)


def test_find_pages_in_an_empty_folder(tmp_path: Path) -> None:
    assert find_pages(tmp_path) == ()


def test_serve_returns_files_from_the_root(tmp_path: Path) -> None:
    touch(tmp_path, "index.html", "<h1>Shop</h1>")
    with serve(tmp_path) as base_url, urlopen(f"{base_url}index.html") as response:  # noqa: S310  local test server
        assert response.read() == b"<h1>Shop</h1>"


def test_serve_does_not_reach_outside_the_root(tmp_path: Path) -> None:
    root = tmp_path / "site"
    touch(root, "index.html")
    touch(tmp_path, "secret.txt", "do not serve")
    with serve(root) as base_url, pytest.raises(HTTPError) as error:
        urlopen(f"{base_url}../secret.txt")  # noqa: S310  local test server
    error.value.close()
    assert error.value.code == 404
