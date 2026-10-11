from __future__ import annotations

import argparse
import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, override

from allymend import __version__
from allymend.cli.output import (
    render_evidence,
    render_fix_summary,
    render_json,
    render_markdown,
    render_payloads,
    render_text,
)
from allymend.errors import (
    AllymendError,
    CannotFixError,
    FolderOutsideError,
    MixedTargetsError,
    ModelError,
    NotAFolderError,
    UnknownTargetError,
)
from allymend.fixers import FixOptions, check_language_tag, plan_fixes
from allymend.mapper import map_sources
from allymend.scanner import ScanOptions, capture_elements, scan_directory, scan_urls
from allymend.verifier import verify_fixes

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from allymend.core.models import ScanResult, Slot, Value
    from allymend.llm.claude import ClaudeValues

EXIT_CLEAN = 0
EXIT_PROBLEMS = 1
EXIT_ERROR = 2


def main(argv: Sequence[str] | None = None) -> int:
    """Run the allymend command line and return its exit code.

    The exit code is 0 when no problems were found, 1 when problems were found, and 2 when
    allymend could not run or a page could not be scanned. Progress, warnings and errors go to
    standard error.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "fix" and args.show_payload and args.text_from is None:
        parser.error("--show-payload needs --text-from")
    options = ScanOptions(timeout_ms=round(args.timeout * 1000))
    run = _run_fix if args.command == "fix" else _run_scan
    with _log_to_stderr(quiet=args.quiet):
        try:
            return run(args, options)
        except AllymendError as error:
            sys.stderr.write(f"allymend: {error}\n")
            return EXIT_ERROR


def _run_scan(args: argparse.Namespace, options: ScanOptions) -> int:
    result = _scan(args.targets, options)
    if args.format == "json":
        report = render_json(result, include_markup=args.include_markup)
    elif args.format == "markdown":
        report = render_markdown(result)
    else:
        report = render_text(result)
    if args.output is None:
        sys.stdout.write(report)
    else:
        args.output.write_text(report, encoding="utf-8", newline="\n")
        if not args.quiet:
            sys.stderr.write(f"allymend: wrote {args.output}\n")
    return _exit_code(result)


def _run_fix(args: argparse.Namespace, options: ScanOptions) -> int:
    root = Path(args.folder)
    if not root.is_dir():
        raise NotAFolderError(args.folder)
    prefix = _patch_prefix(root)
    writer = _text_writer(args)
    result = map_sources(root, scan_directory(root, options))
    captures = {} if writer is None else capture_elements(root, result, {"image-alt"}, options)
    if writer is not None and args.show_payload:
        preview = _Preview()
        fix_options = FixOptions(language=args.lang, values=preview)
        plan_fixes(root, result, fix_options, path_prefix=prefix, captures=captures)
        sys.stdout.write(render_payloads([(slot, writer.request(slot)) for slot in preview.slots]))
        return EXIT_CLEAN
    fix_options = FixOptions(language=args.lang, values=writer)
    planned = plan_fixes(root, result, fix_options, path_prefix=prefix, captures=captures)
    plan = verify_fixes(root, planned, options)
    args.output.write_text(plan.patch, encoding="utf-8", newline="")
    if args.evidence is not None:
        args.evidence.write_text(render_evidence(result, plan), encoding="utf-8", newline="\n")
    sys.stdout.write(render_fix_summary(result, plan, args.output, args.evidence))
    return _exit_code(result)


def _text_writer(args: argparse.Namespace) -> ClaudeValues | None:
    if args.text_from is None:
        return None
    try:
        from allymend.llm.claude import ClaudeValues  # noqa: PLC0415  only with the claude extra
    except ImportError:
        message = 'Claude support isn\'t installed; install it with: pip install "allymend[claude]"'
        raise ModelError(message) from None
    writer = ClaudeValues(model=args.model)
    if not args.show_payload:
        writer.check_credentials()
    return writer


class _Preview:
    """A value source that only records the slots it is asked to fill."""

    def __init__(self) -> None:
        self.slots: list[Slot] = []

    def fill(self, slot: Slot) -> Value:
        self.slots.append(slot)
        raise CannotFixError("not sent: --show-payload")


def _patch_prefix(root: Path) -> str:
    try:
        relative = root.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        raise FolderOutsideError(root) from None
    return "" if relative == Path() else f"{relative.as_posix()}/"


@contextmanager
def _log_to_stderr(*, quiet: bool) -> Iterator[None]:
    package = logging.getLogger("allymend")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("allymend: %(message)s"))
    level = package.level
    package.setLevel(logging.WARNING if quiet else logging.INFO)
    package.addHandler(handler)
    try:
        yield
    finally:
        package.removeHandler(handler)
        package.setLevel(level)


def _scan(targets: Sequence[str], options: ScanOptions) -> ScanResult:
    folders = [target for target in targets if not target.startswith(("http://", "https://"))]
    for folder in folders:
        if not Path(folder).is_dir():
            raise UnknownTargetError(folder)
    if not folders:
        return scan_urls(targets, options)
    if len(targets) > 1:
        raise MixedTargetsError
    root = Path(folders[0])
    return map_sources(root, scan_directory(root, options))


def _exit_code(result: ScanResult) -> int:
    if any(page.error is not None for page in result.pages):
        return EXIT_ERROR
    if any(page.occurrences for page in result.pages):
        return EXIT_PROBLEMS
    return EXIT_CLEAN


def _seconds(value: str) -> float:
    seconds = float(value)
    if seconds <= 0:
        message = "must be a positive number of seconds"
        raise argparse.ArgumentTypeError(message)
    return seconds


def _language(value: str) -> str:
    try:
        return check_language_tag(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


class _ArgumentParser(argparse.ArgumentParser):
    @override
    def convert_arg_line_to_args(self, arg_line: str) -> list[str]:
        line = arg_line.strip()
        return [] if not line or line.startswith("#") else [line]


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="allymend",
        description="Find accessibility problems in web pages.",
        epilog="Arguments can be read from a file, one per line: allymend scan @targets.txt",
        fromfile_prefix_chars="@",
    )
    parser.add_argument("--version", action="version", version=f"allymend {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    shared = _ArgumentParser(add_help=False)
    shared.add_argument(
        "--timeout",
        type=_seconds,
        default=30.0,
        metavar="SECONDS",
        help="how long to wait for each page to load, and again for it to be checked (default: 30)",
    )
    shared.add_argument(
        "-q", "--quiet", action="store_true", help="show only warnings and errors, not progress"
    )

    scan = commands.add_parser(
        "scan",
        parents=[shared],
        help="scan a folder of HTML files or web pages",
        description="Scan a folder of HTML files, or one or more web pages by their URLs.",
    )
    scan.add_argument(
        "targets",
        nargs="+",
        metavar="target",
        help="a folder of HTML files, or one or more URLs (@FILE reads them from a file)",
    )
    scan.add_argument(
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="output format (default: text)",
    )
    scan.add_argument(
        "--output", type=Path, metavar="FILE", help="write the report to FILE instead"
    )
    scan.add_argument(
        "--include-markup",
        action="store_true",
        help="include each element's HTML in JSON output",
    )

    fix = commands.add_parser(
        "fix",
        parents=[shared],
        help="write fixes for a folder of HTML files as a patch",
        description=(
            "Scan a folder of HTML files and write a patch that fixes the problems allymend can "
            "fix on its own. Each fix is checked in a browser before it's written. Your files "
            "aren't changed."
        ),
    )
    fix.add_argument("folder", help="the folder of HTML files, inside the current folder")
    fix.add_argument(
        "--lang",
        type=_language,
        metavar="TAG",
        help="the pages' language, such as en or en-GB; needed to fix a missing page language",
    )
    fix.add_argument(
        "--output",
        type=Path,
        default=Path("allymend.patch"),
        metavar="FILE",
        help="where to write the patch (default: allymend.patch)",
    )
    fix.add_argument(
        "--evidence",
        type=Path,
        metavar="FILE",
        help="also write the checks behind each fix as JSON",
    )
    fix.add_argument(
        "--text-from",
        choices=["claude"],
        help=(
            "write missing text, such as alt text, with a language model; each element and the "
            "text around it is sent to the model's provider"
        ),
    )
    fix.add_argument(
        "--model",
        metavar="NAME",
        help="the model that writes the text (default: claude-opus-5-5)",
    )
    fix.add_argument(
        "--show-payload",
        action="store_true",
        help="with --text-from, show what would be sent, and stop without sending anything",
    )
    return parser
