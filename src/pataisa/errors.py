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


class MixedTargetsError(PataisaError):
    """More than one folder, or a folder together with URLs, was given to scan."""

    def __init__(self) -> None:
        super().__init__("scan either one folder or one or more URLs, not both")


class NotAFolderError(PataisaError):
    """A command that needs the site's source files was given something other than a folder."""

    def __init__(self, target: str) -> None:
        super().__init__(f"{target} is not a folder; fixes need the site's source files")
        self.target = target


class FolderOutsideError(PataisaError):
    """The folder to fix lies outside the current folder, so a patch can't be applied from here."""

    def __init__(self, folder: Path) -> None:
        super().__init__(
            f"{folder} is outside the current folder; run pataisa fix from a folder that "
            "contains it, so the patch applies from there"
        )
        self.folder = folder


class InvalidURLError(PataisaError):
    """The URL to scan is not an http or https address."""

    def __init__(self, url: str) -> None:
        super().__init__(f"only http and https URLs can be scanned: {url}")
        self.url = url


class AxeResultError(PataisaError):
    """axe-core returned something that is not shaped like its results."""

    def __init__(self) -> None:
        super().__init__("axe-core returned results in an unexpected format")


class CannotFixError(PataisaError):
    """A problem can't be fixed automatically where it was found in the source."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class BrowserNotInstalledError(PataisaError):
    """Playwright's Chromium build is missing."""

    def __init__(self) -> None:
        super().__init__("Chromium is not installed; run: poetry run playwright install chromium")
