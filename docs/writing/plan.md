# plan: what we will do, and how we will know

**Surfaces:** `research/<topic>/opportunities/**` and `research/<topic>/projects/**/PLAN*` in a knowledge base, and any spec that commits to work.

## TL;DR

- Imperative and decision-bearing: state the decision as a decision, with its owner and its state.
- Every item carries motivation, hypothesis, verification plan, labelled impact estimate and validation tier.
- An opportunity stands on four legs before it ships: `[lit]`, `[code]`, `[run]`, `[status]`. An empty leg is written out in words, never dropped.
- Estimate in the scarce resource (compute hours, queue slots, runs), not in engineering effort.
- Long documents are numbered, because a numbered anchor survives edits.

## Who is reading, and what that changes

Someone deciding whether to spend resources, or picking the work up cold. They need the decision, what would falsify it and what it costs, in that order. The stage contract is in [`../../templates/research-topic/PIPELINE.md`](../../templates/research-topic/PIPELINE.md): `opportunities/` is the only place an idea may be proposed, and an experiment's record is written before it launches, design and falsifier first.

## Rules

| Rule | Tag |
|---|---|
| State the decision as a decision: "we will", not "we could consider". Name the claim state and its owner. | `[judgment]` |
| Each item: motivation, hypothesis, verification plan, impact estimate with `[M]`/`[D]`/`[A]`, validation tier. | `[judgment]` |
| Four legs named: `[lit]` the external evidence, `[code]` what the system does today (including whether the default branch already changed it), `[run]` what we measured, `[status]` whether it was already tried. | `[judgment]` |
| No engineering-effort estimate. Size the scarce resource. | `[judgment]` |
| A hypothesis names its falsifier: the observation that would mean it is wrong. | `[judgment]` |
| Number the sections of a long plan and cross-reference by number. | `[judgment]` |
| A field-table header (title, goal, impact band, tier, status) may stand in for `## TL;DR` where the folder's template defines one, so the fields are not restated in prose that drifts. | `[mechanical]` (either form present) |
| `no-em-dash` and `one-para-per-line` are house style here but graded only on the external registers. | `[mechanical]` (scope note) |

## What it inverts

Numbered headings, which `general` leaves optional, are expected in a long plan. The TL;DR may take the shape of a schema'd field table instead of five bullets.

## Example

Bad: "It might be worth looking into a smaller summarizer at some point; it could save compute."

Good: "Swap the summarizer for the smaller checkpoint. Hypothesis: per-step cost falls 15% `[A]` with pass@1 within 2 points. Falsifier: pass@1 drops more than 2 points on either benchmark. Legs: `[lit]` the two distillation notes in `literature/`; `[code]` the summarizer is set in one config key; `[run]` no measurement yet; `[status]` never tried. Cost: two single-node runs. Owner named. State: proposed."
