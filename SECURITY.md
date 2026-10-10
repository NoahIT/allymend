# Security policy

## Reporting a vulnerability

Please report security problems privately through [GitHub's vulnerability reporting](https://github.com/NoahIT/pataisa/security/advisories/new), not in a public issue.

Include what you found, how to reproduce it and the version or commit you used. I'll reply as soon as I can and keep you updated until it's fixed.

## Supported versions

There are no releases yet. Fixes go into the latest code on the `main` branch.

## What counts

Pataisa opens web pages in a browser and edits source code, so these matter most:

- a scanned page making pataisa run commands, read or write files outside the project it was pointed at, or send data anywhere;
- a crafted page or project making pataisa produce a patch that does something other than what it reports;
- secrets or page content leaking into reports or logs.
