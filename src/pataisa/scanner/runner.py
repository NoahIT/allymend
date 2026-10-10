from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import quote, urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
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

logger = logging.getLogger(__name__)

_FIRST_HTTP_ERROR = 400
_POLL_MS = 100

_RUN_AXE = """
options => {
  if (window.__pataisaRun === undefined) {
    window.__pataisaRun = null;
    axe.run(document, options).then(
      results => { window.__pataisaRun = { results }; },
      error => { window.__pataisaRun = { error: String(error) }; },
    );
  }
  return window.__pataisaRun;
}
"""


@dataclass(frozen=True, slots=True)
class ScanOptions:
    """Settings for a scan.

    Attributes:
        tags: axe-core rule tags to run. Defaults to WCAG 2.0, 2.1 and 2.2 level A and AA.
        timeout_ms: How long to wait for each page to load, and again for axe-core to check it.
    """

    tags: tuple[str, ...] = WCAG_TAGS
    timeout_ms: int = 30_000


def scan_directory(root: Path, options: ScanOptions | None = None) -> ScanResult:
    """Scan every HTML file under ``root``, served from a local web server.

    Each page is logged at INFO before it is scanned, and each page that fails at WARNING.

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

    A URL that appears more than once is scanned once. Each page is logged at INFO before it
    is scanned, and each page that fails at WARNING.

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
    results: list[PageResult] = []
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        try:
            context = browser.new_context(user_agent=_user_agent(browser), accept_downloads=False)
            context.add_init_script(script=axe_source())
            for number, (name, url) in enumerate(pages, start=1):
                logger.info("scanning %d of %d: %s", number, len(pages), name)
                result = _scan_page(context, name, url, options)
                if result.error is not None:
                    logger.warning("could not scan %s: %s", name, result.error)
                results.append(result)
        finally:
            browser.close()
    return ScanResult(axe_version=AXE_VERSION, pages=tuple(results))


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


def _scan_page(context: BrowserContext, name: str, url: str, options: ScanOptions) -> PageResult:
    page = context.new_page()
    try:
        response = page.goto(url, wait_until="load", timeout=options.timeout_ms)
        if response is not None and response.status >= _FIRST_HTTP_ERROR:
            return PageResult(page=name, error=f"HTTP {response.status}")
        outcome = page.wait_for_function(
            _RUN_AXE,
            arg={
                "runOnly": {"type": "tag", "values": list(options.tags)},
                "resultTypes": ["violations"],
            },
            polling=_POLL_MS,
            timeout=options.timeout_ms,
        ).json_value()
        if isinstance(outcome, dict) and "error" in outcome:
            return PageResult(page=name, error=f"axe-core failed: {outcome['error']}")
        occurrences = parse_violations(
            outcome.get("results") if isinstance(outcome, dict) else None
        )
    except PlaywrightTimeoutError:
        return PageResult(page=name, error=f"did not finish within {options.timeout_ms / 1000:g} s")
    except PlaywrightError as error:
        return PageResult(page=name, error=_first_line(error.message))
    except AxeResultError as error:
        return PageResult(page=name, error=str(error))
    finally:
        page.close()
    return PageResult(page=name, occurrences=occurrences)


def _first_line(message: str) -> str:
    return next(iter(message.splitlines()), "the browser reported an error")
