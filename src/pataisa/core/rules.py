from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class Remediability(StrEnum):
    """How a problem can be fixed."""

    AUTO = "auto"
    SUGGESTED = "suggested"
    HUMAN = "human"


@dataclass(frozen=True, slots=True)
class Criterion:
    """A WCAG 2.2 success criterion."""

    number: str
    name: str
    level: str
    slug: str

    @property
    def url(self) -> str:
        """The W3C page that explains this criterion."""
        return f"https://www.w3.org/WAI/WCAG22/Understanding/{self.slug}"


@dataclass(frozen=True, slots=True)
class Rule:
    """A plain-language explanation of one axe-core rule."""

    rule_id: str
    title: str
    affects: str
    why: str
    fix: str
    remediability: Remediability


_CRITERIA = (
    Criterion("1.1.1", "Non-text Content", "A", "non-text-content"),
    Criterion("1.4.3", "Contrast (Minimum)", "AA", "contrast-minimum"),
    Criterion("1.4.4", "Resize Text", "AA", "resize-text"),
    Criterion("2.4.2", "Page Titled", "A", "page-titled"),
    Criterion("2.4.4", "Link Purpose (In Context)", "A", "link-purpose-in-context"),
    Criterion("2.5.8", "Target Size (Minimum)", "AA", "target-size-minimum"),
    Criterion("3.1.1", "Language of Page", "A", "language-of-page"),
    Criterion("4.1.2", "Name, Role, Value", "A", "name-role-value"),
)

_RULES = (
    Rule(
        "image-alt",
        "Image has no text alternative",
        "Blind people using screen readers, and anyone whose images don't load.",
        "A screen reader reads out the file name or skips the image, so its information is lost.",
        'Describe what the image shows or does in an alt attribute. Use alt="" if it is only '
        "decoration.",
        Remediability.HUMAN,
    ),
    Rule(
        "link-name",
        "Link has no name",
        "Screen reader users and people who control their computer by voice.",
        'The link is announced only as "link", so nobody can tell where it goes, and voice users '
        "have no word to say to click it.",
        "Put text inside the link, or give an icon-only link an aria-label that says where it "
        "goes.",
        Remediability.SUGGESTED,
    ),
    Rule(
        "button-name",
        "Button has no name",
        "Screen reader users and people who control their computer by voice.",
        'The button is announced only as "button", so its action is a guess.',
        "Give the button visible text, or an aria-label that names the action if it shows only "
        "an icon.",
        Remediability.SUGGESTED,
    ),
    Rule(
        "label",
        "Form field has no label",
        "Screen reader users, voice control users and people with cognitive disabilities.",
        "A screen reader can't say what to type, and clicking the field's text doesn't move to "
        "the field.",
        "Connect a visible label to the field with matching for and id attributes.",
        Remediability.SUGGESTED,
    ),
    Rule(
        "select-name",
        "Drop-down has no label",
        "Screen reader users and people who control their computer by voice.",
        "The drop-down is announced without saying what it chooses.",
        "Connect a visible label to the select element with matching for and id attributes.",
        Remediability.SUGGESTED,
    ),
    Rule(
        "html-has-lang",
        "Page language is not set",
        "Screen reader users, and people who rely on translation or reading tools.",
        "A screen reader may read the whole page with the wrong pronunciation.",
        'Add a lang attribute to the html element, for example lang="en".',
        Remediability.AUTO,
    ),
    Rule(
        "document-title",
        "Page has no title",
        "Screen reader users, and anyone with several tabs open.",
        "The title is the first thing a screen reader announces and what names the browser tab.",
        "Add a title element that says what the page is.",
        Remediability.SUGGESTED,
    ),
    Rule(
        "color-contrast",
        "Text has too little contrast",
        "People with low vision or colour vision deficiency, and anyone reading in bright light.",
        "Text too close in colour to its background is hard or impossible to read.",
        "Darken the text or lighten the background until the contrast ratio is at least 4.5:1, "
        "or 3:1 for large text.",
        Remediability.SUGGESTED,
    ),
    Rule(
        "meta-viewport",
        "Zooming is turned off",
        "People with low vision who zoom in on phones and tablets.",
        "The page stops people from enlarging text they can't read at normal size.",
        "Remove user-scalable=no and any maximum-scale from the viewport meta tag.",
        Remediability.AUTO,
    ),
    Rule(
        "target-size",
        "Touch target is too small",
        "People with tremors or limited movement, and anyone using a touch screen.",
        "Small or crowded targets are easy to miss, or to hit the wrong one.",
        "Make the target at least 24 by 24 CSS pixels, or leave enough space around it.",
        Remediability.SUGGESTED,
    ),
)

CRITERIA: Mapping[str, Criterion] = MappingProxyType({c.number: c for c in _CRITERIA})
RULES: Mapping[str, Rule] = MappingProxyType({rule.rule_id: rule for rule in _RULES})
