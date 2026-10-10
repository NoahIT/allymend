from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import quote, urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from pataisa import __version__
from pataisa.core.models import PageResult, ScanResult
from pataisa.errors import AxeResultError, BrowserNotInstalledError, InvalidURLError, NoPagesError
from pataisa.scanner.axe import AXE_VERSION, WCAG_TAGS, axe_source, parse_violations
from pataisa.scanner.site import find_pages, serve

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from playwright.sync_api import Browser, BrowserContext, Playwright

_FIRST_HTTP_ERROR = 400


@dataclass(frozen=True, slots=True)
class ScanOptions:
    """Settings for a scan.

    Attributes:
        tags: axe-core rule tags to run. Defaults to WCAG 2.0, 2.1 and 2.2 level A and AA.
        timeout_ms: How long to wait for each page to load.
    """

    tags: tuple[str, ...] = WCAG_TAGS
    timeout_ms: int = 30_000


def scan_directory(root: Path, options: ScanOptions | None = None) -> ScanResult:
    """Scan every HTML file under ``root``, served from a local web server.

    Raises:
        NoPagesError: ``root`` contains no HTML files.
        BrowserNotInstalledError: Playwright's Chromium build is missing.
    """
    pages = find_pages(root)
    if not pages:
        raise NoPagesError(root)
    with serve(root) as base_url:
        return _scan([(page, base_url + quote(page)) for page in pages], options or ScanOptions())


def scan_urls(urls: Sequence[str], options: ScanOptions | None = None) -> ScanResult:
    """Scan pages by their URLs, in the order given, with one browser.

    A URL that appears more than once is scanned once.

    Raises:
        InvalidURLError: A URL is not an http or https URL. Nothing is scanned.
        BrowserNotInstalledError: Playwright's Chromium build is missing.
    """
    for url in urls:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise InvalidURLError(url)
    unique = list(dict.fromkeys(urls))
    if not unique:
        return ScanResult(axe_version=AXE_VERSION, pages=())
    return _scan([(url, url) for url in unique], options or ScanOptions())


def scan_url(url: str, options: ScanOptions | None = None) -> ScanResult:
    """Scan one page by its URL.

    Raises:
        InvalidURLError: ``url`` is not an http or https URL.
        BrowserNotInstalledError: Playwright's Chromium build is missing.
    """
    return scan_urls([url], options)


def _scan(pages: Sequence[tuple[str, str]], options: ScanOptions) -> ScanResult:
    source = axe_source()
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        try:
            context = browser.new_context(user_agent=_user_agent(browser), accept_downloads=False)
            results = tuple(_scan_page(context, name, url, source, options) for name, url in pages)
        finally:
            browser.close()
    return ScanResult(axe_version=AXE_VERSION, pages=results)


def _launch(playwright: Playwright) -> Browser:
    try:
        return playwright.chromium.launch()
    except PlaywrightError as error:
        if "Executable doesn't exist" in error.message:
            raise BrowserNotInstalledError from error
        raise


def _user_agent(browser: Browser) -> str:
    page = browser.new_page()
    try:
        default = str(page.evaluate("navigator.userAgent"))
    finally:
        page.close()
    return f"{default} pataisa/{__version__}"


def _scan_page(
    context: BrowserContext, name: str, url: str, source: str, options: ScanOptions
) -> PageResult:
    page = context.new_page()
    try:
        response = page.goto(url, wait_until="load", timeout=options.timeout_ms)
        if response is not None and response.status >= _FIRST_HTTP_ERROR:
            return PageResult(page=name, error=f"HTTP {response.status}")
        page.evaluate(source)
        raw = page.evaluate(
            "options => axe.run(document, options)",
            {
                "runOnly": {"type": "tag", "values": list(options.tags)},
                "resultTypes": ["violations"],
            },
        )
        occurrences = parse_violations(raw)
    except PlaywrightError as error:
        return PageResult(page=name, error=_first_line(error.message))
    except AxeResultError as error:
        return PageResult(page=name, error=str(error))
    finally:
        page.close()
    return PageResult(page=name, occurrences=occurrences)


def _first_line(message: str) -> str:
    return next(iter(message.splitlines()), "the browser reported an error")
