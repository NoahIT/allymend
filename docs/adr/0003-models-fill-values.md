# 3. Language models fill in values, never code

Status: Accepted

Date: 2026-10-10

## Context

Many accessibility fixes need words a program can't know: alt text, a button's name, what a link leads to. Language models can draft those. Letting a model change code is riskier: model-written fixes that aren't checked can make a page worse, and an agent that reads page content can be steered by text hidden in the pages it scans.

Developers who use coding agents already have a model that can write this text for them.

## Decision

- Every fix has two parts: exact edits at known source positions, and the content that goes into them.
- Content comes from configuration, a heuristic such as an existing visible label, the user's coding agent, or a person. In a later phase, an optional language model can also draft it.
- A model returns one value at a time, for example `{text, rationale}`, checked against a schema and a length limit. Allymend escapes the value and inserts it. A model never writes or changes code, and there's no agent loop inside allymend.
- Using a model is opt-in, local models are supported, and allymend can show exactly what would be sent.
- Whatever the source, the result goes through the same verifier. Confidence comes from that evidence, never from a model's own claim.

## Consequences

- Allymend works fully without any model, and its runs are reproducible.
- The worst a successful prompt injection can do is produce bad text, which a person reviews before applying it.
- Some problems stay marked as needing a person, even where a model could guess.
