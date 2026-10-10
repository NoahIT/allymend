from collections.abc import Iterable
from dataclasses import dataclass

from pataisa.core.models import Impact, Occurrence, SourceLocation

_SEVERITY = {Impact.MINOR: 1, Impact.MODERATE: 2, Impact.SERIOUS: 3, Impact.CRITICAL: 4}


@dataclass(frozen=True, slots=True)
class RuleCount:
    """The elements on a page that fail one rule."""

    rule_id: str
    summary: str
    help_url: str
    impact: Impact | None
    wcag: tuple[str, ...]
    targets: tuple[str, ...]
    sources: tuple[SourceLocation | None, ...]

    @property
    def elements(self) -> int:
        """How many elements fail the rule."""
        return len(self.targets)


def count_by_rule(occurrences: Iterable[Occurrence]) -> tuple[RuleCount, ...]:
    """Group occurrences by rule, most frequent first, with ties ordered by rule id.

    Each group takes the most severe impact among its occurrences.
    """
    groups: dict[str, list[Occurrence]] = {}
    for occurrence in occurrences:
        groups.setdefault(occurrence.rule_id, []).append(occurrence)
    counts = (
        RuleCount(
            rule_id=rule_id,
            summary=members[0].summary,
            help_url=members[0].help_url,
            impact=_most_severe(members),
            wcag=members[0].wcag,
            targets=tuple(" >> ".join(member.target) for member in members),
            sources=tuple(member.source for member in members),
        )
        for rule_id, members in groups.items()
    )
    return tuple(sorted(counts, key=lambda count: (-count.elements, count.rule_id)))


def _most_severe(occurrences: list[Occurrence]) -> Impact | None:
    impacts = [o.impact for o in occurrences if o.impact is not None]
    return max(impacts, key=_SEVERITY.__getitem__, default=None)
