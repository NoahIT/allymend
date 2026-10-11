from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Impact(StrEnum):
    """How severely axe-core rates a problem for the people it affects."""

    MINOR = "minor"
    MODERATE = "moderate"
    SERIOUS = "serious"
    CRITICAL = "critical"


type TextKind = Literal["alt-text", "link-name", "button-name", "field-name"]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceLocation(_Model):
    """Where an element's start tag is in a source file.

    Attributes:
        file: The file's path relative to the scanned folder, with forward slashes.
        line: The 1-based line of the start tag.
        column: The 1-based column of the start tag.
        offset: The 0-based character offset of the start tag's ``<`` in the file's text as
            ``allymend.files.read_source`` returns it: decoded without newline translation, and
            counting a byte order mark.
        found_by: ``selector`` when axe-core's selector matched the element in the source.
            ``attributes`` when the selector didn't, and the element was found by an ``id``,
            ``src``, ``href`` or ``name`` it shares with the element in the browser instead;
            that is less certain.
    """

    file: str
    line: int
    column: int
    offset: int
    found_by: Literal["selector", "attributes"] = "selector"


class Edit(_Model):
    """A change to one span of a source file.

    Attributes:
        file: The file's path relative to the scanned folder, with forward slashes.
        start: Where the replaced span starts, counted like ``SourceLocation.offset``.
        end: Where the replaced span ends. Equal to ``start`` for an insertion.
        text: The text that replaces the span.
    """

    file: str
    start: int
    end: int
    text: str


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


class Capture(_Model):
    """What an element shows in the browser, and the text around it.

    Attributes:
        image: For an image element, the image as the browser decoded it, scaled to fit 1568
            pixels; otherwise a screenshot of the element. Left out of serialized output.
        media_type: The image's format, ``image/jpeg`` or ``image/png``.
        context: Nearby text that helps describe the element, by kind, for example ``link`` for
            the address of a link the element is in.
    """

    image: bytes | None = Field(default=None, exclude=True, repr=False)
    media_type: str = "image/png"
    context: dict[str, str] = Field(default_factory=dict)


class Slot(_Model):
    """Text a fix needs that a person or a model has to write.

    Attributes:
        kind: What the text is for: ``alt-text`` for an image, ``link-name`` for a link,
            ``button-name`` for a button, or ``field-name`` for a form field.
        rule_id: The axe-core rule the occurrence fails.
        page: The page it was found on.
        target: The occurrence's CSS selectors.
        html: The element's opening markup as rendered in the browser.
        language: The page's language tag, if known.
        context: Nearby text that helps describe the element, as in ``Capture``.
        image: What the element shows, as in ``Capture``, if it was captured. Left out of
            serialized output.
        media_type: The image's format, as in ``Capture``.
        max_length: The longest acceptable text.
    """

    kind: TextKind
    rule_id: str
    page: str
    target: tuple[str, ...]
    html: str
    language: str | None = None
    context: dict[str, str] = Field(default_factory=dict)
    image: bytes | None = Field(default=None, exclude=True, repr=False)
    media_type: str = "image/png"
    max_length: int = 150


class Value(_Model):
    """Text written for a slot.

    Attributes:
        text: The text.
        rationale: Why it fits, in a sentence.
        source: Who wrote it, for example the model's name.
    """

    text: str
    rationale: str = ""
    source: str


class Fix(_Model):
    """Source changes that fix one occurrence.

    Attributes:
        rule_id: The axe-core rule the occurrence fails.
        page: The page it was found on.
        target: The occurrence's CSS selectors.
        edits: The changes to make.
        value: The text the fix inserts, when someone had to write it.
    """

    rule_id: str
    page: str
    target: tuple[str, ...]
    edits: tuple[Edit, ...]
    value: Value | None = None


class Unfixed(_Model):
    """An occurrence that was left for a person, and why.

    Attributes:
        rule_id: The axe-core rule the occurrence fails.
        page: The page it was found on.
        target: The occurrence's CSS selectors.
        reason: Why it wasn't fixed.
    """

    rule_id: str
    page: str
    target: tuple[str, ...]
    reason: str


class Resolved(_Model):
    """An occurrence no fix was aimed at, which was gone once its page's fixes were applied.

    For example, a link whose only content is an image gets its name from the alt text a fix
    gives the image.

    Attributes:
        rule_id: The axe-core rule the occurrence failed.
        page: The page it was found on.
        target: The occurrence's CSS selectors.
    """

    rule_id: str
    page: str
    target: tuple[str, ...]


class FileChange(_Model):
    """What the fixes do to one source file.

    Attributes:
        file: The file's path relative to the scanned folder, with forward slashes.
        diff: The change as a unified diff.
        before: The file's text when the fixes were planned. Left out of serialized output.
        after: The text with every fix for the file applied. Left out of serialized output.
    """

    file: str
    diff: str
    before: str = Field(exclude=True, repr=False)
    after: str = Field(exclude=True, repr=False)


class Check(_Model):
    """One check of a file's fixes.

    Attributes:
        name: What was checked: ``edits``, ``scanned``, ``fixed``, ``no-new-problems`` or
            ``tree``.
        passed: Whether it held.
        detail: What was wrong, when it didn't hold.
    """

    name: str
    passed: bool
    detail: str = ""


class Verification(_Model):
    """The evidence for one file's fixes.

    Attributes:
        file: The file's path relative to the scanned folder, with forward slashes.
        checks: The checks that were run, in order. The pages are loaded only when the edits
            pass, and the rest is checked only when both pages loaded.
    """

    file: str
    checks: tuple[Check, ...]

    @property
    def passed(self) -> bool:
        """Whether every check held."""
        return all(check.passed for check in self.checks)


class FixPlan(_Model):
    """The fixes for one scan, and the occurrences they leave.

    Attributes:
        fixes: Fixes that were planned, in scan order.
        unfixed: Occurrences without a fix, in scan order.
        changes: What the fixes do to each file, in path order.
        verifications: Evidence from checking the changes, once they have been checked.
        resolved: Occurrences without a fix that the checked changes made go away, in scan
            order.
    """

    fixes: tuple[Fix, ...]
    unfixed: tuple[Unfixed, ...]
    changes: tuple[FileChange, ...]
    verifications: tuple[Verification, ...] = ()
    resolved: tuple[Resolved, ...] = ()

    @property
    def patch(self) -> str:
        """All the changes as one unified diff, or an empty string when there are none."""
        return "".join(change.diff for change in self.changes)
