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
    """

    rule_id: str
    impact: Impact | None
    wcag: tuple[str, ...]
    summary: str
    help_url: str
    target: tuple[str, ...]
    html: str
    failure_summary: str


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
