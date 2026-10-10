from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def write_page(tmp_path: Path) -> Callable[..., Path]:
    """Write a minimal, otherwise valid HTML page under ``tmp_path``."""

    def write(name: str, body: str = "<p>Hello</p>", *, lang: str | None = "en") -> Path:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        lang_attribute = f' lang="{lang}"' if lang else ""
        path.write_text(
            f"<!doctype html><html{lang_attribute}><head><meta charset='utf-8'>"
            f"<title>Test page</title></head><body><main><h1>Test page</h1>{body}</main>"
            "</body></html>",
            encoding="utf-8",
        )
        return path

    return write
