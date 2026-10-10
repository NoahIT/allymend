from __future__ import annotations

import argparse
import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, override

from pataisa import __version__
from pataisa.cli.output import render_fix_summary, render_json, render_markdown, render_text
from pataisa.errors import (
    FolderOutsideError,
    MixedTargetsError,
    NotAFolderError,
    PataisaError,
    UnknownTargetError,
)
from pataisa.fixers import FixOptions, check_language_tag, plan_fixes
from pataisa.mapper import map_sources
from pataisa.scanner import ScanOptions, scan_directory, scan_urls

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from pataisa.core.models import ScanResult

EXIT_CLEAN = 0
EXIT_PROBLEMS = 1
EXIT_ERROR = 2


def main(argv: Sequence[str] | None = None) -> int:
    """Run the pataisa command line and return its exit code.

    The exit code is 0 when no problems were found, 1 when problems were found, and 2 when
    pataisa could not run or a page could not be scanned. Progress, warnings and errors go to
    standard error.
    """
    args = _parser().parse_args(argv)
    options = ScanOptions(timeout_ms=round(args.timeout * 1000))
    run = _run_fix if args.command == "fix" else _run_scan
    with _log_to_stderr(quiet=args.quiet):
        try:
            return run(args, options)
        except PataisaError as error:
            sys.stderr.write(f"pataisa: {error}\n")
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
            sys.stderr.write(f"pataisa: wrote {args.output}\n")
    return _exit_code(result)


def _run_fix(args: argparse.Namespace, options: ScanOptions) -> int:
    root = Path(args.folder)
    if not root.is_dir():
        raise NotAFolderError(args.folder)
    prefix = _patch_prefix(root)
    result = map_sources(root, scan_directory(root, options))
    plan = plan_fixes(root, result, FixOptions(language=args.lang), path_prefix=prefix)
    args.output.write_text(plan.patch, encoding="utf-8", newline="")
    sys.stdout.write(render_fix_summary(result, plan, args.output))
    return _exit_code(result)


def _patch_prefix(root: Path) -> str:
    try:
        relative = root.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        raise FolderOutsideError(root) from None
    return "" if relative == Path() else f"{relative.as_posix()}/"


@contextmanager
def _log_to_stderr(*, quiet: bool) -> Iterator[None]:
    package = logging.getLogger("pataisa")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("pataisa: %(message)s"))
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
        prog="pataisa",
        description="Find accessibility problems in web pages.",
        epilog="Arguments can be read from a file, one per line: pataisa scan @targets.txt",
        fromfile_prefix_chars="@",
    )
    parser.add_argument("--version", action="version", version=f"pataisa {__version__}")
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
            "Scan a folder of HTML files and write a patch that fixes the problems pataisa can "
            "fix on its own. Your files aren't changed."
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
        default=Path("pataisa.patch"),
        metavar="FILE",
        help="where to write the patch (default: pataisa.patch)",
    )
    return parser
