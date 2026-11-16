# reference: current truth

**Surfaces:** `research/<topic>/understanding/**` and `research/<topic>/literature/**` in a knowledge base, any `CATALOG.md`.

## TL;DR

- Present tense: what the system or the source does now, anchored to `file:line` or a URL plus quote.
- A living body with an append-only `## History`; mutability is a section boundary.
- Corrections are `ERRATUM` blocks, never silent rewrites.
- Describes what is, never what should be; a "we should" belongs in `opportunities/`.
- A synthesis may close with a `Bottom line` that adds the one takeaway, never one that repeats the TL;DR.

## Who is reading, and what that changes

Someone about to build on a fact about the system or a source. They will act on it without re-deriving it, so every claim must be checkable at the anchor it cites, and a stale claim must be visibly stale. A literature note's shape is fixed by [`../../templates/research-topic/PIPELINE.md`](../../templates/research-topic/PIPELINE.md) § literature; an `understanding/` document is living and rewritten when the system changes.

## Rules

| Rule | Tag |
|---|---|
| Present tense, describing what the code or source does. | `[judgment]` |
| Every claim anchored: `file:line` for code, URL plus quote for a source. Re-check anchors before shipping. | `[judgment]` |
| A living document ends with `## History`, append-only, one dated line per change. | `[mechanical]` (section present) |
| A factual fix is a dated `ERRATUM` block beside the claim ([`../rules.md`](../rules.md) rule 6). | `[judgment]` |
| No recommendation. A sentence saying what the system should do moves to `opportunities/`. | `[judgment]` |
| Coin no shorthand. An abbreviation is one the field already uses, expanded at first use. | `[judgment]` |
| The summary is a bold `**TL;DR:**` lead line under the title; that form satisfies `tldr-at-most-five`. | `[mechanical]` (either form present) |
| Where a source's surfaces disagree (paper, code, weights), the executable one decides and the disagreement goes in `## Caveats`. | `[judgment]` |

## What it inverts

`no-restating-closer` is relaxed: a synthesis (comparison matrix, survey, deep dive) may end with a `Bottom line`, provided it adds the single takeaway rather than restating the summary. The literal `## TL;DR` heading is replaced by the lead line.

## Example

Bad: "The retry logic is fairly generous and should probably be tightened."

Good: "The client retries five times with exponential backoff starting at 200 ms (`client/http.py:142-158`). Retries are not capped by elapsed time. `## History`: 2026-03-14, retry count read from the current default branch."
