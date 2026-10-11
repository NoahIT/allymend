from __future__ import annotations

import base64
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import quote, urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from allymend import __version__
from allymend.core.models import Capture, PageResult, ScanResult
from allymend.errors import AxeResultError, BrowserNotInstalledError, InvalidURLError, NoPagesError
from allymend.scanner.axe import AXE_VERSION, WCAG_TAGS, axe_source, parse_violations
from allymend.scanner.site import find_pages, serve

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence
    from pathlib import Path

    from playwright.sync_api import Browser, BrowserContext, Page, Playwright, Route

logger = logging.getLogger(__name__)

_FIRST_HTTP_ERROR = 400
_POLL_MS = 100
_MAX_IMAGE_BYTES = 3_500_000
_MAX_CONTEXT_CHARACTERS = 200
_JPEG_DATA_URL = "data:image/jpeg;base64,"

_DECODED_IMAGE = """
async element => {
  if (!(element instanceof HTMLImageElement)) return null;
  element.scrollIntoView({ block: "center" });
  if (!element.complete) {
    await new Promise(resolve => {
      element.addEventListener("load", resolve, { once: true });
      element.addEventListener("error", resolve, { once: true });
      setTimeout(resolve, 5000);
    });
  }
  const width = element.naturalWidth;
  const height = element.naturalHeight;
  if (!width || !height) return null;
  const scale = Math.min(1, 1568 / Math.max(width, height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  const context = canvas.getContext("2d");
  context.fillStyle = "#fff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(element, 0, 0, canvas.width, canvas.height);
  try {
    return canvas.toDataURL("image/jpeg", 0.9);
  } catch {
    return null;
  }
}
"""

_CONTEXT = """
element => {
  const text = node =>
    (node ? node.innerText || node.textContent || "" : "").replace(/\\s+/g, " ").trim();
  const link = element.closest("a[href]");
  const figure = element.closest("figure");
  let heading = null;
  for (const candidate of document.querySelectorAll("h1, h2, h3, h4, h5, h6")) {
    if (candidate.compareDocumentPosition(element) & Node.DOCUMENT_POSITION_FOLLOWING) {
      heading = candidate;
    }
  }
  const source = element.getAttribute("src") || "";
  return {
    "page title": document.title,
    "heading": text(heading),
    "caption": text(figure && figure.querySelector("figcaption")),
    "link": link ? link.getAttribute("href") : "",
    "link text": text(link),
    "file name": source.startsWith("data:") ? "" : source.split(/[?#]/)[0].split("/").pop(),
    "nearby text": text(element.parentElement),
  };
}
"""

_RUN_AXE = """
options => {
  if (window.__allymendRun === undefined) {
    window.__allymendRun = null;
    axe.run(document, options).then(
      results => { window.__allymendRun = { results }; },
      error => { window.__allymendRun = { error: String(error) }; },
    );
  }
  return window.__allymendRun;
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


@dataclass(frozen=True, slots=True)
class PageScan:
    """What a browser session found on one page.

    Attributes:
        result: The page's occurrences, or why it couldn't be scanned.
        tree: The page's accessibility tree as a Playwright ARIA snapshot, if it was asked for
            and the page could be scanned.
    """

    result: PageResult
    tree: str | None = None


class BrowserSession:
    """A running browser that checks one page at a time with axe-core.

    Open one with ``open_browser``.
    """

    def __init__(self, context: BrowserContext, options: ScanOptions) -> None:
        self._context = context
        self._options = options

    def scan(self, name: str, url: str, *, html: str | None = None, tree: bool = False) -> PageScan:
        """Load the page at ``url`` and check it.

        Args:
            name: What to call the page in the result.
            url: The page's address.
            html: A document to load in place of the one at ``url``. Everything the document
                refers to, such as styles and images, still comes from where it normally does.
            tree: Also capture the page's accessibility tree.
        """
        page = self._context.new_page()
        served: list[str] = []
        if html is not None:
            replacement = html

            def fulfill(route: Route) -> None:
                served.append(route.request.url)
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=replacement)

            page.route(lambda requested: requested == url, fulfill)
        try:
            response = page.goto(url, wait_until="load", timeout=self._options.timeout_ms)
            if response is not None and response.status >= _FIRST_HTTP_ERROR:
                error = f"HTTP {response.status}"
            elif html is not None and not served:
                error = "the replacement content wasn't loaded"
            else:
                return self._check(page, name, tree=tree)
        except PlaywrightTimeoutError:
            error = f"did not finish within {self._options.timeout_ms / 1000:g} s"
        except PlaywrightError as caught:
            error = _first_line(caught.message)
        except AxeResultError as caught:
            error = str(caught)
        finally:
            page.close()
        return PageScan(PageResult(page=name, error=error))

    def capture(
        self, url: str, targets: Iterable[tuple[str, ...]]
    ) -> dict[tuple[str, ...], Capture]:
        """Load the page at ``url`` and capture the elements that ``targets`` point to.

        Each capture holds what the element shows and the text around it, such as the link it
        is in or the nearest heading. For an image element that is the image as the browser
        decoded it, so styles and animations don't change it; images the page can't read back,
        such as ones from other sites, and other elements get a screenshot instead. Elements in
        frames or shadow roots, and elements that can't be found or shown, are left out.
        """
        page = self._context.new_page()
        page.set_default_timeout(self._options.timeout_ms)
        captures: dict[tuple[str, ...], Capture] = {}
        try:
            page.goto(url, wait_until="load")
            for target in targets:
                if len(target) != 1:
                    continue
                element = page.locator(target[0]).first
                try:
                    if not element.is_visible():
                        continue
                    context = element.evaluate(_CONTEXT)
                    decoded = element.evaluate(_DECODED_IMAGE)
                    if isinstance(decoded, str) and decoded.startswith(_JPEG_DATA_URL):
                        image = base64.b64decode(decoded.removeprefix(_JPEG_DATA_URL))
                        media_type = "image/jpeg"
                    else:
                        image = element.screenshot(type="png", animations="disabled")
                        media_type = "image/png"
                except PlaywrightError:
                    continue
                captures[target] = Capture(
                    image=image if len(image) <= _MAX_IMAGE_BYTES else None,
                    media_type=media_type,
                    context=_bounded(context),
                )
        except PlaywrightError as error:
            logger.warning("could not capture elements on %s: %s", url, _first_line(error.message))
        finally:
            page.close()
        return captures

    def _check(self, page: Page, name: str, *, tree: bool) -> PageScan:
        timeout = self._options.timeout_ms
        snapshot = page.locator(":root").aria_snapshot(timeout=timeout) if tree else None
        outcome = page.wait_for_function(
            _RUN_AXE,
            arg={
                "runOnly": {"type": "tag", "values": list(self._options.tags)},
                "resultTypes": ["violations"],
            },
            polling=_POLL_MS,
            timeout=timeout,
        ).json_value()
        if isinstance(outcome, dict) and "error" in outcome:
            return PageScan(PageResult(page=name, error=f"axe-core failed: {outcome['error']}"))
        results = outcome.get("results") if isinstance(outcome, dict) else None
        return PageScan(PageResult(page=name, occurrences=parse_violations(results)), snapshot)


@contextmanager
def open_browser(options: ScanOptions | None = None) -> Iterator[BrowserSession]:
    """Start Chromium with axe-core loaded into every page and frame.

    Raises:
        BrowserNotInstalledError: Playwright's Chromium build is missing.
    """
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        try:
            context = browser.new_context(user_agent=_user_agent(browser), accept_downloads=False)
            context.add_init_script(script=axe_source())
            yield BrowserSession(context, options or ScanOptions())
        finally:
            browser.close()


def _scan(pages: Sequence[tuple[str, str]], options: ScanOptions) -> ScanResult:
    results: list[PageResult] = []
    with open_browser(options) as browser:
        for number, (name, url) in enumerate(pages, start=1):
            logger.info("scanning %d of %d: %s", number, len(pages), name)
            result = browser.scan(name, url).result
            if result.error is not None:
                logger.warning("could not scan %s: %s", name, result.error)
            results.append(result)
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
    return f"{default} allymend/{__version__}"


def _bounded(context: object) -> dict[str, str]:
    if not isinstance(context, dict):
        return {}
    bounded = {}
    for name, value in context.items():
        if isinstance(name, str) and isinstance(value, str) and value.strip():
            text = value.strip()
            if len(text) > _MAX_CONTEXT_CHARACTERS:
                cut = text[: _MAX_CONTEXT_CHARACTERS - 3]
                text = (cut.rsplit(" ", 1)[0] if " " in cut else cut).rstrip() + "..."
            bounded[name] = text
    return bounded


def _first_line(message: str) -> str:
    return next(iter(message.splitlines()), "the browser reported an error")
