# pataisa

Pataisa is a tool that finds accessibility problems on websites, explains them in plain language and proposes fixes to the site's source code. Each fix is checked before you see it.

*Pataisa* is Lithuanian for "correction".

## Status

Early development. Nothing is usable yet. The first release, 0.1.0, will cover static HTML sites and three kinds of fixes: page language, viewport settings and form labels.

## How it will work

1. Scan pages in a real browser with [axe-core](https://github.com/dequelabs/axe-core).
2. Trace each problem back to the place in your source code that produced it.
3. Explain who the problem affects and which [WCAG 2.2](https://www.w3.org/TR/WCAG22/) success criterion it relates to.
4. Where a fix can be made safely, apply it to a temporary copy of your project, scan again and check that:
   - the problem is gone;
   - nothing new broke;
   - the fix didn't simply hide content from assistive technology.
5. Give you a diff to review. Nothing changes in your project unless you apply it.

## What it won't do

- Tell you that your site is accessible or compliant with any law. Automated checks find only part of real accessibility problems. The rest needs people, including people who use assistive technology.
- Patch pages in the browser at runtime. Pataisa is not an overlay; it changes source code.
- Invent content. Alt text, link names and similar text need your judgment, so those findings are marked as needing a person.

## Trying it

Scanning works today. Fixes don't exist yet.

```
poetry install
poetry run playwright install chromium
poetry run pataisa scan path/to/site
poetry run pataisa scan https://www.w3.org/WAI/demos/bad/before/home.html
```

A folder is served locally and every HTML file in it is scanned, and each problem is traced to the line in your file that produces it. You can also give one or more URLs, and each of those pages is scanned. Add `--format json` for machine-readable output, or `--format markdown` for a report grouped by rule.

To scan a list of pages, put one URL per line in a file and pass it with `@`, for example `poetry run pataisa scan @live/targets.txt`.

The report goes to standard output, or to a file with `--output`. Progress and warnings go to standard error, so they never end up in the report. `--quiet` hides the progress.

The exit code is 0 when nothing was found, 1 when problems were found, and 2 when a page couldn't be scanned.

## Development

You need Python 3.12 or newer, [Poetry](https://python-poetry.org/) 2.x and GNU Make.

```
make install    # dependencies and git hooks
make lint       # formatting, lint rules and types
make test       # tests with coverage
make live       # scan the public pages in live/targets.txt into live/report.md
```

The same scan can be started by hand from GitHub's Actions tab ("Live scan"). Its report appears on the run's summary page.

## License

[Apache License 2.0](LICENSE).
