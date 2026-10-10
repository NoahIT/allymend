from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Impact(StrEnum):
    """How severely axe-core rates a problem for the people it affects."""

    MINOR = "minor"
    MODERATE = "moderate"
    SERIOUS = "serious"
    CRITICAL = "critical"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceLocation(_Model):
    """Where an element's start tag is in a source file.

    Attributes:
        file: The file's path relative to the scanned folder, with forward slashes.
        line: The 1-based line of the start tag.
        column: The 1-based column of the start tag.
        offset: The 0-based character offset of the start tag's ``<`` in the file's bytes
            decoded as UTF-8, without newline translation and counting a byte order mark.
    """

    file: str
    line: int
    column: int
    offset: int


class Occurrence(_Model):
    """One element on one page that fails one rule.

    Attributes:
        rule_id: The axe-core rule, for example ``image-alt``.
        impact: The severity axe-core gives this element, if any.
        wcag: WCAG success criteria the rule relates to, for example ``("1.1.1",)``.
        summary: axe-core's one-line description of the rule.
        help_url: A page explaining the rule.
        target: CSS selectors locating the element; one per frame or shadow root.
        html: The element's opening markup as rendered in the browser.
        failure_summary: What axe-core found wrong with this element.
        source: Where the element is written in the source, when that could be determined.
    """

    rule_id: str
    impact: Impact | None
    wcag: tuple[str, ...]
    summary: str
    help_url: str
    target: tuple[str, ...]
    html: str
    failure_summary: str
    source: SourceLocation | None = None


class PageResult(_Model):
    """The outcome of scanning one page.

    Attributes:
        page: A relative file path when scanning a folder, otherwise the URL.
        occurrences: Problems found on the page.
        error: Why the page could not be scanned, if it could not.
    """

    page: str
    occurrences: tuple[Occurrence, ...] = ()
    error: str | None = None


class ScanResult(_Model):
    """Everything found in one scan."""

    axe_version: str
    pages: tuple[PageResult, ...]
