from pathlib import Path


class PataisaError(Exception):
    """Base class for errors that pataisa reports to its user."""


class NoPagesError(PataisaError):
    """The folder to scan contains no HTML files."""

    def __init__(self, root: Path) -> None:
        super().__init__(f"no HTML files found in {root}")
        self.root = root


class UnknownTargetError(PataisaError):
    """The scan target is neither a folder nor an http or https URL."""

    def __init__(self, target: str) -> None:
        super().__init__(f"{target} is neither a folder nor an http or https URL")
        self.target = target


class InvalidURLError(PataisaError):
    """The URL to scan is not an http or https address."""

    def __init__(self, url: str) -> None:
        super().__init__(f"only http and https URLs can be scanned: {url}")
        self.url = url


class AxeResultError(PataisaError):
    """axe-core returned something that is not shaped like its results."""

    def __init__(self) -> None:
        super().__init__("axe-core returned results in an unexpected format")


class BrowserNotInstalledError(PataisaError):
    """Playwright's Chromium build is missing."""

    def __init__(self) -> None:
        super().__init__("Chromium is not installed; run: poetry run playwright install chromium")
