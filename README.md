# allymend

Allymend is a tool that finds accessibility problems on websites, explains them in plain language and proposes fixes to the site's source code. Each fix is checked before you see it.

The name joins "ally", the way a11y (accessibility) is often said, with "mend".

## Status

Early development, for static HTML sites. Scanning works, and so do the first fixes: a missing page language, and alt text and names for links and buttons, written by Claude when you ask for them.

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
- Write content on its own. Alt text, link names and similar text need judgment. Allymend drafts alt text and names for links and buttons only when you ask Claude to, and lists every draft for you to read; everything else is marked as needing a person.

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

This scans the folder, checks each fix as described in step 4 above, and writes the fixes that pass to `allymend.patch`; your files aren't changed. Everything it couldn't fix, including fixes that failed a check, is listed with the reason. Problems that weren't fixed directly but were gone from the page once its fixes were applied are listed separately. Review the patch, then apply it with `git apply allymend.patch` from the folder you ran allymend in. Add `--evidence checks.json` to keep a record of every check.

### Text written by Claude

Some fixes need words that a program can't know, such as alt text that describes an image, or a name for a link or button that shows only an icon. Allymend can ask Claude to write them. This is off unless you ask for it, and needs the `claude` extra and an Anthropic API key:

```
poetry install --all-extras
$env:ANTHROPIC_API_KEY = "<your key>"     # export ANTHROPIC_API_KEY=... outside PowerShell
poetry run allymend fix path/to/site --text-from claude --show-payload
poetry run allymend fix path/to/site --text-from claude
```

For each image, link or button, Claude receives a picture of it as the browser shows it and the text around it: the page title, the nearest heading, a caption, the link it is or is in and nearby text, each cut to 200 characters. Nothing else from your project is sent. `--show-payload` prints exactly that for every request and stops without sending anything.

The text Claude writes is checked like any other fix and listed in the summary. Read it before applying the patch. A link or button without a name gets an `aria-label`. When an image is all it contains, the image's alt text names it instead, so Claude is asked to say where the link goes or what the button does, and the summary lists its problem as gone too. When Claude can't tell, the link or button is left for you. When it thinks an image is decorative, allymend leaves that for you to decide too, because `alt=""` hides an image from screen readers. The model is `claude-opus-5-5` unless you choose another with `--model`.

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
