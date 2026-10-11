# 2. Library first, single process

Status: Accepted

Date: 2026-10-10

## Context

A tool like this could be a hosted service: a web app, a job queue, workers that clone and build repositories, a database of results. That's months of infrastructure before the first useful fix, and running other people's builds safely is the hardest part of it.

Every fix also has to be verified by rebuilding and rescanning the project. The place where a project already builds reliably is the developer's machine or their CI.

## Decision

Allymend is a Python library with a typed API: scan, map, plan fixes, apply, verify. It runs as a single process on the user's machine or in their CI. The command line tool, and later an MCP server for coding agents and CI integrations, are thin layers over that API. There's no server, queue or database.

The versioned JSON output is the public contract. Terminal output, HTML reports, SARIF and patch descriptions are all generated from it.

## Consequences

- Page content stays on the user's machine unless they choose to send something to a language model (see ADR 3).
- Scanning `localhost` and private addresses is allowed in local use, because that's the main use case. Any future remote crawling has to block private and internal addresses by default.
- A hosted "scan my site" service is out of scope until much later.
- The library API and the JSON schema need versioning from the start, because everything else depends on them.
