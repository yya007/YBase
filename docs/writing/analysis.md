# analysis: what a measurement means

**Surfaces:** `research/<topic>/analysis/**` in a knowledge base, and the Results block of a plan or experiment record.

## TL;DR

- Measured result first; every number labelled `[M]`, `[D]` or `[A]`, and never a headline on an assumed one.
- Say what you could not measure, and why, beside what you could.
- Report a negative result as plainly as a positive one; here the wrong path is often the finding.
- Close with a reproducibility appendix: the committed script, the exact command, the slices cited.
- Record every arm's resolved configuration, including the defaults you never set.

## Who is reading, and what that changes

A colleague or a later agent deciding whether to build on this inference. They can open the repo, so a bracketed label and a `file:line` are faster for them than a prose paraphrase. An analysis is dated and immutable ([`../../templates/research-topic/PIPELINE.md`](../../templates/research-topic/PIPELINE.md)): a changed mind is a new document, and a factual fix is an `ERRATUM` block ([`../rules.md`](../rules.md)).

## Rules

| Rule | Tag |
|---|---|
| Measured result first: the question is answered in the first sentence. | `[judgment]` |
| Every number carries `[M]`, `[D]` or `[A]` and its source ([`../rules.md`](../rules.md) rule 2). | `[mechanical]` (label present) |
| Never headline an assumed multiplier; an `[A]` number stays out of the TL;DR. | `[judgment]` |
| State what you could not measure and why, beside what you could. | `[judgment]` |
| A negative result gets the same prominence as a positive one. | `[judgment]` |
| Close with the reproducibility appendix: script, command, slices. | `[judgment]` |
| Each arm's configuration is written down resolved, read from what launched the arm, not from the plan that asked for it. A harness default is still a setting; "identical harness" is not a configuration. | `[judgment]` |
| Where the work is a fix, give two altitudes: the precise technical metric and the one-sentence impact. | `[judgment]` |
| `no-em-dash` and `one-para-per-line` are house style here but graded only on the external registers. | `[mechanical]` (scope note) |

## What it inverts

Provenance tags, banned in [`external.md`](external.md), are required here. The wrong path, cut in `external` and `message`, is documented here, because a mistaken setup is often what the measurement teaches.

## Example

Bad: "The new scheduler is about 3x faster. We also tried a larger batch, which did not help, so it is not discussed here."

Good: "Per-trajectory cost fell from 90 to 30 GPU-seconds `[M]` (runs named in Appendix A), 3.0x `[D]`. The larger-batch arm was flat at 89 `[M]`, so batch size is ruled out as the lever. 4 GPU-seconds of the gap are unattributed."
