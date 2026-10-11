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
from allymend.fixers.names import check_name, check_name_tag, fix_name

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from justhtml import QueryMatch

    from allymend.core.models import (
        Edit,
        Occurrence,
        ScanResult,
        SourceLocation,
        TextKind,
        Value,
    )
    from allymend.files import SourceText
    from allymend.fixers.names import Role
    from allymend.fixers.values import ValueSource

_ALT_TEXT_LENGTH = 150
_NAME_LENGTH = 100


@dataclass(frozen=True, slots=True)
class FixOptions:
    """Settings for planning fixes.

    Attributes:
        language: The pages' language as a tag such as ``en`` or ``en-GB``. Fixing a missing
            page language needs it.
        values: Where text that fixes need comes from, such as alt text or link names. Without
            it, those fixes are left for a person.

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

    Fixes that need text someone has to write, such as alt text or a link's name, ask
    ``options.values`` for it.
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
    element: QueryMatch | None
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
    slot = _slot(request, "alt-text", _ALT_TEXT_LENGTH)
    value = request.options.values.fill(slot)
    alt = check_alt_text(value.text, slot.max_length)
    edit = fix_image_alt(request.text, request.location, alt)
    return edit, value.model_copy(update={"text": alt})


@dataclass(frozen=True, slots=True)
class _Control:
    tags: tuple[str, ...]
    role: Role
    kind: TextKind


_CONTROLS: Mapping[str, _Control] = MappingProxyType(
    {
        "link-name": _Control(tags=("a",), role="link", kind="link-name"),
        "button-name": _Control(tags=("button",), role="button", kind="button-name"),
        "label": _Control(tags=("input", "textarea"), role="field", kind="field-name"),
        "select-name": _Control(tags=("select",), role="field", kind="field-name"),
    }
)


def _control_name(request: _Request) -> tuple[Edit, Value | None]:
    control = _CONTROLS[request.occurrence.rule_id]
    element = request.element
    tag = element.name if element is not None and element.name in control.tags else control.tags[0]
    images = element.query("img") if element is not None else []
    if any("alt" not in (image.attrs or {}) for image in images):
        raise CannotFixError(
            f"the image inside it will name the {control.role} once the image has alt text"
        )
    check_name_tag(request.text, request.location, tag)
    if request.options.values is None:
        raise CannotFixError(
            f"needs a {control.role} name from a person, or from a model (--text-from claude)"
        )
    slot = _slot(request, control.kind, _NAME_LENGTH)
    value = request.options.values.fill(slot)
    name = check_name(value.text, slot.max_length, control.role)
    edit = fix_name(request.text, request.location, tag, name)
    return edit, value.model_copy(update={"text": name})


def _slot(request: _Request, kind: TextKind, max_length: int) -> Slot:
    capture = request.capture or Capture()
    return Slot(
        kind=kind,
        rule_id=request.occurrence.rule_id,
        page=request.page,
        target=request.occurrence.target,
        html=request.occurrence.html,
        language=request.language or request.options.language,
        context=capture.context,
        image=capture.image,
        media_type=capture.media_type,
        max_length=max_length,
    )


_FIXERS: Mapping[str, Callable[[_Request], tuple[Edit, Value | None]]] = MappingProxyType(
    {
        "html-has-lang": _page_language,
        "image-alt": _image_alt,
        **dict.fromkeys(_CONTROLS, _control_name),
    }
)

TEXT_RULES = frozenset({"image-alt", *_CONTROLS})


@dataclass(frozen=True, slots=True)
class _Document:
    language: str | None
    elements: Mapping[tuple[int, int], QueryMatch]


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
        self._documents: dict[str, _Document] = {}
        self._edits: dict[str, list[Edit]] = {}

    def fix(self, page: str, occurrence: Occurrence) -> Fix:
        fixer = _FIXERS.get(occurrence.rule_id)
        if fixer is None:
            raise CannotFixError("there's no automatic fix for this rule yet")
        location = occurrence.source
        if location is None:
            raise CannotFixError("the element couldn't be traced to its source")
        text = self._text(location.file)
        document = self._document(location.file, text)
        edit, value = fixer(
            _Request(
                text=text,
                page=page,
                occurrence=occurrence,
                location=location,
                element=document.elements.get((location.line, location.column)),
                language=document.language,
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

    def _document(self, file: str, text: str) -> _Document:
        if file not in self._documents:
            self._documents[file] = _parse(text)
        return self._documents[file]


def _parse(text: str) -> _Document:
    root = JustHTML(text, sanitize=False, track_node_locations=True).root
    elements = {
        (element.origin_line, element.origin_col): element
        for element in root.query("*")
        if element.origin_line is not None and element.origin_col is not None
    }
    language = next((((e.attrs or {}).get("lang") or "").strip() for e in root.query("html")), "")
    try:
        return _Document(language=check_language_tag(language), elements=elements)
    except ValueError:
        return _Document(language=None, elements=elements)
