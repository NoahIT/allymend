from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pataisa import __version__
from pataisa.cli.output import render_json, render_text
from pataisa.errors import PataisaError, UnknownTargetError
from pataisa.scanner import ScanOptions, scan_directory, scan_url

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pataisa.core.models import ScanResult

EXIT_CLEAN = 0
EXIT_PROBLEMS = 1
EXIT_ERROR = 2


def main(argv: Sequence[str] | None = None) -> int:
    """Run the pataisa command line and return its exit code.

    The exit code is 0 when no problems were found, 1 when problems were found, and 2 when
    pataisa could not run or a page could not be scanned.
    """
    args = _parser().parse_args(argv)
    try:
        result = _scan(args.target, ScanOptions(timeout_ms=round(args.timeout * 1000)))
    except PataisaError as error:
        sys.stderr.write(f"pataisa: {error}\n")
        return EXIT_ERROR

    if args.format == "json":
        report = render_json(result, include_markup=args.include_markup)
    else:
        report = render_text(result)
    if args.output is None:
        sys.stdout.write(report)
    else:
        args.output.write_text(report, encoding="utf-8", newline="\n")
        sys.stderr.write(f"pataisa: wrote {args.output}\n")
    return _exit_code(result)


def _scan(target: str, options: ScanOptions) -> ScanResult:
    if target.startswith(("http://", "https://")):
        return scan_url(target, options)
    folder = Path(target)
    if not folder.is_dir():
        raise UnknownTargetError(target)
    return scan_directory(folder, options)


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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pataisa", description="Find accessibility problems in web pages."
    )
    parser.add_argument("--version", action="version", version=f"pataisa {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    scan = commands.add_parser(
        "scan",
        help="scan a folder of HTML files or a web page",
        description="Scan a folder of HTML files, or one web page by its URL.",
    )
    scan.add_argument("target", help="a folder of HTML files, or an http or https URL")
    scan.add_argument(
        "--format", choices=["text", "json"], default="text", help="output format (default: text)"
    )
    scan.add_argument(
        "--output", type=Path, metavar="FILE", help="write the report to FILE instead"
    )
    scan.add_argument(
        "--include-markup",
        action="store_true",
        help="include each element's HTML in JSON output",
    )
    scan.add_argument(
        "--timeout",
        type=_seconds,
        default=30.0,
        metavar="SECONDS",
        help="how long to wait for each page to load (default: 30)",
    )
    return parser
