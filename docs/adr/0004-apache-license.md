# 4. Apache License 2.0

Status: Accepted

Date: 2026-10-10

## Context

Pataisa should stay free for anyone to use, including companies that want to run it in their CI. Released versions stay open under any open source license, so the real question was whether others may build closed products on top of it.

- Apache-2.0 allows that, includes an explicit patent grant and is widely accepted by companies.
- MPL-2.0 keeps changes to pataisa's own files open.
- AGPL-3.0 keeps everything open but puts many companies off using the tool at all.

## Decision

Pataisa is licensed under the Apache License 2.0. Every commit is signed off under the [Developer Certificate of Origin](https://developercertificate.org/) (`git commit -s`), so the origin of each change is on record.

## Consequences

- axe-core (MPL-2.0) can be used with it. If its files are bundled, they stay unmodified and keep their license notices.
- Pa11y (LGPL-3.0) won't be bundled.
- Notices required by bundled third-party code go in `NOTICE`.
