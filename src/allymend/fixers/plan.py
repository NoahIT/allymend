from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from allymend.core.models import FileChange, Fix, FixPlan, Unfixed
from allymend.errors import CannotFixError
from allymend.files import read_source
from allymend.fixers.edits import apply_edits, unified_diff
from allymend.fixers.html_has_lang import check_language_tag, fix_html_has_lang

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from allymend.core.models import Edit, Occurrence, ScanResult, SourceLocation
    from allymend.files import SourceText


@dataclass(frozen=True, slots=True)
class FixOptions:
    """Settings for planning fixes.

    Attributes:
        language: The pages' language as a tag such as ``en`` or ``en-GB``. Fixing a missing
            page language needs it.

    Raises:
        ValueError: ``language`` is not a language tag.
    """

    language: str | None = None

    def __post_init__(self) -> None:
        if self.language is not None:
            check_language_tag(self.language)


def plan_fixes(
    root: Path, result: ScanResult, options: FixOptions | None = None, *, path_prefix: str = ""
) -> FixPlan:
    """Work out fixes for the occurrences in a scan of the folder ``root``.

    The scan must have been through ``map_sources``, so occurrences carry source locations.
    Each source file is read once, and each fix is checked against the others planned for the
    same file. Nothing is written. The diffs' paths are relative to ``root``, with
    ``path_prefix`` in front so that the patch can be applied from another folder.
    """
    planner = _Planner(root, options or FixOptions())
    fixes: list[Fix] = []
    unfixed: list[Unfixed] = []
    for page in result.pages:
        for occurrence in page.occurrences:
            try:
                fixes.append(planner.fix(page.page, occurrence))
            except CannotFixError as error:
                unfixed.append(
                    Unfixed(
                        rule_id=occurrence.rule_id,
                        page=page.page,
                        target=occurrence.target,
                        reason=error.reason,
                    )
                )
    return FixPlan(fixes=tuple(fixes), unfixed=tuple(unfixed), changes=planner.changes(path_prefix))


def _page_language(text: str, location: SourceLocation, options: FixOptions) -> Edit:
    if options.language is None:
        raise CannotFixError("the pages' language wasn't given (--lang)")
    return fix_html_has_lang(text, location, options.language)


_FIXERS: Mapping[str, Callable[[str, SourceLocation, FixOptions], Edit]] = MappingProxyType(
    {"html-has-lang": _page_language}
)


class _Planner:
    def __init__(self, root: Path, options: FixOptions) -> None:
        self._root = root
        self._options = options
        self._sources: dict[str, SourceText | None] = {}
        self._edits: dict[str, list[Edit]] = {}

    def fix(self, page: str, occurrence: Occurrence) -> Fix:
        fixer = _FIXERS.get(occurrence.rule_id)
        if fixer is None:
            raise CannotFixError("there's no automatic fix for this rule yet")
        location = occurrence.source
        if location is None:
            raise CannotFixError("the element couldn't be traced to its source")
        text = self._text(location.file)
        edit = fixer(text, location, self._options)
        planned = self._edits.get(location.file, [])
        try:
            apply_edits(text, [*planned, edit])
        except ValueError:
            raise CannotFixError("it overlaps another fix in the same file") from None
        self._edits[location.file] = [*planned, edit]
        return Fix(rule_id=occurrence.rule_id, page=page, target=occurrence.target, edits=(edit,))

    def changes(self, path_prefix: str) -> tuple[FileChange, ...]:
        changes = []
        for file in sorted(self._edits):
            before = self._text(file)
            after = apply_edits(before, self._edits[file])
            diff = unified_diff(path_prefix + file, before, after)
            changes.append(FileChange(file=file, diff=diff, before=before, after=after))
        return tuple(changes)

    def _text(self, file: str) -> str:
        if file not in self._sources:
            self._sources[file] = read_source(self._root, file)
        source = self._sources[file]
        if source is None:
            raise CannotFixError(f"{file} couldn't be read from the scanned folder")
        if source.encoding != "utf-8":
            raise CannotFixError(
                f"{file} is saved as UTF-16, which a patch can't change; save it as UTF-8 to get "
                "fixes"
            )
        return source.text
