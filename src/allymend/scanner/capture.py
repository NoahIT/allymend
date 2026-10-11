from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import quote

from allymend.scanner.runner import open_browser
from allymend.scanner.site import serve

if TYPE_CHECKING:
    from collections.abc import Collection
    from pathlib import Path

    from allymend.core.models import Capture, ScanResult
    from allymend.scanner.runner import ScanOptions

logger = logging.getLogger(__name__)


def capture_elements(
    root: Path, result: ScanResult, rule_ids: Collection[str], options: ScanOptions | None = None
) -> dict[tuple[str, tuple[str, ...]], Capture]:
    """Capture the elements behind the occurrences of some rules in a scan of the folder ``root``.

    Pages are served from ``root`` again and each is loaded once. The captures are keyed by
    page and target, as ``plan_fixes`` expects them.
    """
    wanted = {
        page.page: [o.target for o in page.occurrences if o.rule_id in rule_ids]
        for page in result.pages
    }
    captures: dict[tuple[str, tuple[str, ...]], Capture] = {}
    with serve(root) as base_url, open_browser(options) as browser:
        for page, targets in wanted.items():
            if not targets:
                continue
            logger.info("capturing %d element(s) on %s", len(targets), page)
            for target, capture in browser.capture(base_url + quote(page), targets).items():
                captures[(page, target)] = capture
    return captures
