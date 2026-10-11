from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from justhtml import JustHTML

from allymend.core.models import Capture, FileChange, Fix, FixPlan, Slot, Unfixed
from allymend.errors import CannotFixError
from allymend.files import read_source
from allymend.fixers.alt_text import check_alt_text, fix_image_alt
from allymend.fixers.edits import apply_edits, unified_diff
from allymend.fixers.html_has_lang import check_language_tag, fix_html_has_lang

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from allymend.core.models import Edit, Occurrence, ScanResult, SourceLocation, Value
    from allymend.files import SourceText
    from allymend.fixers.values import ValueSource


@dataclass(frozen=True, slots=True)
class FixOptions:
    """Settings for planning fixes.

    Attributes:
        language: The pages' language as a tag such as ``en`` or ``en-GB``. Fixing a missing
            page language needs it.
        values: Where text that fixes need comes from, such as alt text. Without it, those
            fixes are left for a person.

    Raises:
        ValueError: ``language`` is not a language tag.
    """

    language: str | None = None
    values: ValueSource | None = None

    def __post_init__(self) -> None:
        if self.language is not None:
            check_language_tag(self.language)


def plan_fixes(
    root: Path,
    result: ScanResult,
    options: FixOptions | None = None,
    *,
    path_prefix: str = "",
    captures: Mapping[tuple[str, tuple[str, ...]], Capture] | None = None,
) -> FixPlan:
    """Work out fixes for the occurrences in a scan of the folder ``root``.

    The scan must have been through ``map_sources``, so occurrences carry source locations.
    Each source file is read once, and each fix is checked against the others planned for the
    same file. Nothing is written. The diffs' paths are relative to ``root``, with
    ``path_prefix`` in front so that the patch can be applied from another folder.

    Fixes that need text someone has to write, such as alt text, ask ``options.values`` for it.
    ``captures`` holds how elements looked in the browser, keyed by page and target, to help
    whoever writes the text.
    """
    planner = _Planner(root, options or FixOptions(), captures or {})
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


@dataclass(frozen=True, slots=True)
class _Request:
    text: str
    page: str
    occurrence: Occurrence
    location: SourceLocation
    language: str | None
    options: FixOptions
    capture: Capture | None


def _page_language(request: _Request) -> tuple[Edit, Value | None]:
    if request.options.language is None:
        raise CannotFixError("the pages' language wasn't given (--lang)")
    return fix_html_has_lang(request.text, request.location, request.options.language), None


def _image_alt(request: _Request) -> tuple[Edit, Value | None]:
    if request.options.values is None:
        raise CannotFixError("needs alt text from a person, or from a model (--text-from claude)")
    capture = request.capture or Capture()
    slot = Slot(
        kind="alt-text",
        rule_id=request.occurrence.rule_id,
        page=request.page,
        target=request.occurrence.target,
        html=request.occurrence.html,
        language=request.language or request.options.language,
        context=capture.context,
        image=capture.image,
        media_type=capture.media_type,
    )
    value = request.options.values.fill(slot)
    alt = check_alt_text(value.text, slot.max_length)
    edit = fix_image_alt(request.text, request.location, alt)
    return edit, value.model_copy(update={"text": alt})


_FIXERS: Mapping[str, Callable[[_Request], tuple[Edit, Value | None]]] = MappingProxyType(
    {"html-has-lang": _page_language, "image-alt": _image_alt}
)


class _Planner:
    def __init__(
        self,
        root: Path,
        options: FixOptions,
        captures: Mapping[tuple[str, tuple[str, ...]], Capture],
    ) -> None:
        self._root = root
        self._options = options
        self._captures = captures
        self._sources: dict[str, SourceText | None] = {}
        self._languages: dict[str, str | None] = {}
        self._edits: dict[str, list[Edit]] = {}

    def fix(self, page: str, occurrence: Occurrence) -> Fix:
        fixer = _FIXERS.get(occurrence.rule_id)
        if fixer is None:
            raise CannotFixError("there's no automatic fix for this rule yet")
        location = occurrence.source
        if location is None:
            raise CannotFixError("the element couldn't be traced to its source")
        text = self._text(location.file)
        edit, value = fixer(
            _Request(
                text=text,
                page=page,
                occurrence=occurrence,
                location=location,
                language=self._language(location.file, text),
                options=self._options,
                capture=self._captures.get((page, occurrence.target)),
            )
        )
        planned = self._edits.get(location.file, [])
        try:
            apply_edits(text, [*planned, edit])
        except ValueError:
            raise CannotFixError("it overlaps another fix in the same file") from None
        self._edits[location.file] = [*planned, edit]
        return Fix(
            rule_id=occurrence.rule_id,
            page=page,
            target=occurrence.target,
            edits=(edit,),
            value=value,
        )

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

    def _language(self, file: str, text: str) -> str | None:
        if file not in self._languages:
            self._languages[file] = _document_language(text)
        return self._languages[file]


def _document_language(text: str) -> str | None:
    elements = JustHTML(text, sanitize=False).root.query("html")
    language = next((((e.attrs or {}).get("lang") or "").strip() for e in elements), "")
    try:
        return check_language_tag(language)
    except ValueError:
        return None
