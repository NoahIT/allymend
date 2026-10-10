# 1. Python core with a small JavaScript build plugin

Status: Accepted

Date: 2026-10-10

## Context

Pataisa scans pages in a browser, traces problems back to source files, edits those files and checks the result. Most of that works in any language with good browser automation. One part doesn't: tracing elements in a React or Vue app back to their source needs code that runs inside the project's JavaScript build, such as a Vite or webpack plugin that adds source locations to elements.

I considered three options:

- TypeScript for everything. Native to the JavaScript ecosystem, but not the language I know best, and I want to be able to explain every part of this codebase.
- Python for the tool, plus one small JavaScript package for the build plugin.
- Python only, matching rendered elements to source files with heuristics. Simpler, but the mapping would become a guess, and exact mapping is the point of the project.

## Decision

The tool is written in Python, supports Python 3.12 and newer, and is packaged with Poetry as a single distribution. The only JavaScript will be a small build plugin, added when framework support starts.

## Consequences

- Browser automation uses Playwright for Python. axe-core runs inside the page, so the tool's language doesn't affect it.
- I haven't found a Python HTML parser that both matches browser parsing and reports source positions the way parse5 does in JavaScript. The static HTML mapper has to solve that, and needs research before it's built.
- Users install the tool with pipx or uvx instead of npx.
- Once framework support starts, the repository has two toolchains. Keeping the JavaScript part small limits that cost.
