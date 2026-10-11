# 5. Rename to Allymend

Status: Accepted

Date: 2026-10-11

## Context

The project started as pataisa, Lithuanian for "correction". The name means nothing to most people who would use the tool, and it doesn't say what the tool is for. Nothing had been released, so renaming was still cheap.

## Decision

The project is called Allymend: "ally", the way a11y (accessibility) is often said, joined with "mend". The Python package, the command and the repository are all `allymend`. The name was free on PyPI and npm, and no other project on GitHub used it, when it was chosen.

## Consequences

- The command is `allymend scan` and `allymend fix`, and the default patch file is `allymend.patch`.
- The old repository URL redirects to the new one, so existing links keep working.
- The name appears in the user agent of the scanning browser, `allymend/<version>`, so site owners can recognise its requests.
