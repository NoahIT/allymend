# allymend

Allymend is a tool that finds accessibility problems on websites, explains them in plain language and proposes fixes to the site's source code. Each fix is checked before you see it.

The name joins "ally", the way a11y (accessibility) is often said, with "mend".

## Status

Early development. Scanning works, and fixing has started. The first release, 0.1.0, will cover static HTML sites and three kinds of fixes: page language, viewport settings and form labels.

## How it works

1. Scan pages in a real browser with [axe-core](https://github.com/dequelabs/axe-core).
2. Trace each problem back to the place in your source code that produced it.
3. Explain who the problem affects and which [WCAG 2.2](https://www.w3.org/TR/WCAG22/) success criterion it relates to.
4. Where a fix can be made safely, load the page with and without it in a browser and check that:
   - the problem is gone;
   - nothing new broke;
   - the fix didn't simply hide content from assistive technology.
5. Give you a diff to review. Nothing changes in your project unless you apply it.

## What it won't do

- Tell you that your site is accessible or compliant with any law. Automated checks find only part of real accessibility problems. The rest needs people, including people who use assistive technology.
- Patch pages in the browser at runtime. Allymend is not an overlay; it changes source code.
- Invent content. Alt text, link names and similar text need your judgment, so those findings are marked as needing a person.

## Trying it

```
poetry install
poetry run playwright install chromium
poetry run allymend scan path/to/site
poetry run allymend scan https://www.w3.org/WAI/demos/bad/before/home.html
```

A folder is served locally and every HTML file in it is scanned, and each problem is traced to the line in your file that produces it. You can also give one or more URLs, and each of those pages is scanned. Add `--format json` for machine-readable output, or `--format markdown` for a report grouped by rule.

To scan a list of pages, put one URL per line in a file and pass it with `@`, for example `poetry run allymend scan @live/targets.txt`.

The report goes to standard output, or to a file with `--output`. Progress and warnings go to standard error, so they never end up in the report. `--quiet` hides the progress.

The exit code is 0 when nothing was found, 1 when problems were found, and 2 when a page couldn't be scanned.

### Fixing

So far allymend can fix one problem on its own: a missing page language.

```
poetry run allymend fix path/to/site --lang en
```

This scans the folder, checks each fix as described in step 4 above, and writes the fixes that pass to `allymend.patch`; your files aren't changed. Everything it couldn't fix, including fixes that failed a check, is listed with the reason. Review the patch, then apply it with `git apply allymend.patch` from the folder you ran allymend in. Add `--evidence checks.json` to keep a record of every check.

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
