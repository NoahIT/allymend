from importlib.resources import files

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from allymend.core.models import Impact, Occurrence
from allymend.core.wcag import success_criteria
from allymend.errors import AxeResultError

AXE_VERSION = "4.13.0"
WCAG_TAGS = ("wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa")


def axe_source() -> str:
    """Return the vendored axe-core script."""
    script = files("allymend").joinpath("_vendor", "axe-core", "axe.min.js")
    return script.read_text(encoding="utf-8")


class _AxeNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    target: list[str | list[str]]
    html: str
    impact: Impact | None = None
    failure_summary: str = Field(default="", alias="failureSummary")


class _AxeRule(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rule_id: str = Field(alias="id")
    impact: Impact | None = None
    tags: list[str]
    summary: str = Field(alias="help")
    help_url: str = Field(alias="helpUrl")
    nodes: list[_AxeNode]


class _AxeResults(BaseModel):
    model_config = ConfigDict(extra="ignore")

    violations: list[_AxeRule]


def parse_violations(raw: object) -> tuple[Occurrence, ...]:
    """Turn the result of ``axe.run`` into one occurrence per failing element.

    Raises:
        AxeResultError: ``raw`` is not shaped like axe-core results.
    """
    try:
        results = _AxeResults.model_validate(raw)
    except ValidationError as error:
        raise AxeResultError from error
    return tuple(
        Occurrence(
            rule_id=rule.rule_id,
            impact=node.impact or rule.impact,
            wcag=success_criteria(rule.tags),
            summary=rule.summary,
            help_url=rule.help_url,
            target=tuple(_selector(part) for part in node.target),
            html=node.html,
            failure_summary=node.failure_summary,
        )
        for rule in results.violations
        for node in rule.nodes
    )


def _selector(part: str | list[str]) -> str:
    # axe-core nests the selectors of an element inside shadow roots.
    return part if isinstance(part, str) else " >>> ".join(part)
