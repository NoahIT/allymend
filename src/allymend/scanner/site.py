from __future__ import annotations

from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import TYPE_CHECKING, override

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_SKIPPED_DIRS = frozenset({"node_modules"})


def find_pages(root: Path) -> tuple[str, ...]:
    """Return the HTML files under ``root`` as sorted, slash-separated relative paths.

    Hidden folders and ``node_modules`` are skipped.
    """
    pages = (path.relative_to(root) for path in root.rglob("*.html") if path.is_file())
    return tuple(sorted(page.as_posix() for page in pages if not _is_skipped(page)))


def _is_skipped(page: Path) -> bool:
    return any(part.startswith(".") or part in _SKIPPED_DIRS for part in page.parts[:-1])


class _QuietHandler(SimpleHTTPRequestHandler):
    @override
    def log_message(self, format: str, *args: object) -> None:
        pass


@contextmanager
def serve(root: Path) -> Iterator[str]:
    """Serve ``root`` over HTTP on 127.0.0.1 and yield the base URL, which ends in ``/``."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_QuietHandler, directory=str(root)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
