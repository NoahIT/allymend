# Threat model

Version 0, 2026-10-10. Most of allymend isn't built yet, so this describes the design. I'll update it as each part lands.

## What allymend does

Allymend runs on a developer's machine or in their CI with that user's permissions. It serves a project's files to a headless browser, scans the pages, reads the source files, writes patched copies to a temporary directory and produces reports and patch files. Later versions add a URL scan mode, an MCP server for coding agents and optional language model calls (see [data-flow.md](data-flow.md)).

## What needs protecting

- The user's source code: allymend must never change it on its own, and every patch must do what its report says.
- The user's machine: files outside the project, running processes, credentials.
- Secrets inside the project or its environment.
- Page content, which can include personal data on authenticated pages.
- The allymend repository and its releases.

## Trust boundaries

| Input | Trusted? |
|---|---|
| The user's command line and config | Yes. The user chose them. |
| The project's own files and build commands | Partly. They're the user's, but a cloned project can be hostile. |
| Scanned pages: markup, scripts, text | No |
| axe-core results (they describe page content) | No |
| Values from a coding agent or language model | No |
| Remote sites in URL scan mode | No |

## Threats and mitigations

| Threat | Mitigation |
|---|---|
| Page content steers allymend, for example text that reads like instructions, or attributes naming files to edit. | Page data never chooses a file, a command or a URL. Source locations come from parsing the project's own files. Any location found in the page is checked against the project root before use. |
| A patch writes outside the project. | Paths are resolved and rejected if they leave the project root. Patches are applied only to a temporary copy; the user applies the final diff. |
| A fix hides a problem instead of solving it (adding `aria-hidden`, removing an element). | The verifier rejects these edits and compares the accessibility tree before and after. Confidence comes from that evidence. |
| An inserted value breaks out of its context, for example a label containing markup. | Values are escaped for where they go (attribute, text, JSX string) and limited in length. |
| A hostile page attacks the browser or exhausts resources. | Headless Chromium with its sandbox; navigation and script timeouts; downloads refused; page count and size limits. |
| Pointing allymend at an untrusted project runs that project's build. | The build and serve commands come only from the user's config, never from scanned content. The docs say plainly that verifying fixes runs the project's build. |
| URL scan mode is used to reach internal services (SSRF). | Remote crawling blocks private, loopback and link-local addresses and cloud metadata endpoints, including after redirects. Local scans of `localhost` stay allowed because that's the main use. |
| Secrets or page content end up in reports, logs or CI artifacts. | No page content is stored unless asked for. Authentication is held as a reference to a secret, never its value. Reports redact what they can. |
| The HTML report runs script from a scanned page. | Everything taken from a page is escaped in the report, and the report sets a restrictive Content Security Policy. |
| Page content is sent to a language model provider. | Off by default. Opt-in per run, the exact payload can be shown first, data is kept to the minimum, and local models work. |

## Supply chain

| Threat | Mitigation |
|---|---|
| A compromised or brand-new dependency release | Every pinned version is at least 14 days old, and Poetry enforces this when locking (`solver.min-release-age`). The lock file is committed. Dependabot waits 14 days before proposing updates. |
| A known vulnerability in a dependency | OSV-Scanner checks `poetry.lock` in CI. Dependabot alerts and security updates are on. |
| A tampered GitHub Action or tool download | Actions and pre-commit hooks are pinned to full commit SHAs. Downloaded binaries are checked against SHA-256 hashes. |
| A malicious workflow change | actionlint and zizmor check workflows before each commit. The CI token is read-only, and checkout doesn't keep it. |
| A leaked secret in the repository | gitleaks runs before each commit and over the full history in CI. GitHub secret scanning and push protection are on. |
| Unreviewed or impersonated changes | Commits are signed. `main` only changes through pull requests that pass every CI check, and force pushes and deletions are blocked on `main` and `develop`. |

## Accepted risks for now

- Allymend runs with the user's full permissions. It doesn't sandbox the user's own build.
- Pages loaded in the browser can make their own network requests, as they would in any browser.
- axe-core runs inside the page it checks, so a page can interfere with it, for example by replacing it or faking its results. Results that come back in the wrong shape are reported as an error, but a page that fakes plausible results can hide its own problems. This only affects that page's report.
