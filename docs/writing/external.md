# external: the reader cannot open this repo

**Surfaces:** anything read outside the repo. It stacks under [`readout.md`](readout.md), [`investigation.md`](investigation.md), [`design.md`](design.md), [`tech_summary.md`](tech_summary.md), [`message.md`](message.md) and the PR surfaces in [`review.md`](review.md).

## TL;DR

- The reader has no repo access and no knowledge of this workspace: self-contained, no workspace paths, no codenames, no `[M]`/`[D]`/`[A]` tags, no metric value in a heading.
- Names are exact; a descriptive paraphrase where a real name exists is jargon.
- `PENDING` marks anything gated on an unfinished run; a guessed number never does.
- Show what shipped, not the ledger of tried-and-dropped changes (the type registers say where that goes instead).
- Document shape and correction lifecycle belong to the type register stacked on top, never here.

## Who is reading, and what that changes

Someone who can open public code, a commit, a run page or a public URL, and nothing in this repo. Impact and direction come first when leadership is in the audience; mechanism stays light, and links carry the detail. Every claim about what the system does is read from the code or config before it ships, and an absence claim ("no cap is set", "the flag is off") is grepped, never recalled, because absence claims read as background and are the ones most often wrong. A number in prose is read off the same series as the table, never from memory.

## Rules

| id | Rule | Tag |
|---|---|---|
| `external/no-workspace-path` | No workspace or personal path, not even in an appendix pointer. Cite a commit, a run id or a public URL. | `[mechanical]` |
| `external/no-codename` | No internal codename or catalog id. Name the run by its public id. | `[mechanical]` |
| `external/no-provenance-tag` | No `[M]`/`[D]`/`[A]` tag. State where the number comes from in prose. | `[mechanical]` |
| `external/no-number-in-heading` | `##` and deeper carry no metric value or stray number. A leading section index (`## 3. Setup`, `### A. Arm two`) is stripped before the check and is permitted. | `[mechanical]` |
| `external/no-euphemistic-name` | No descriptive paraphrase where a name exists: `pass@1`, not "first sample"; the benchmark's name, not "the hard benchmark"; the model's name, not "a commercial teacher". | `[mechanical]` |
| `external/three-significant-figures` | A number of 10,000 or more in a body section carries at most three significant figures (`2.47 million`). Powers of two and the appendix are exempt. | `[mechanical]` |
| `external/no-measured-rather-than-assumed` | No "measured rather than assumed" or its variants. A reader takes a number as measured unless told otherwise; the phrase spends the emphasis a real caveat needs. | `[mechanical]` |
| `no-em-dash`, `one-para-per-line`, `heading-comma-appositive` | Graded here, because the reader is outside the repo. | `[mechanical]` |
| links | Only to a commit, public code, a run page or a public URL. Prefer a commit link to a branch link, which breaks when the branch goes. Verify every link resolves before committing. | `[judgment]` |
| provenance | A number's data slice goes inline; its provenance names the producing commit or run, never an internal path. | `[judgment]` |
| distinctions | Any distinction that changes a number's meaning stays explicit: a base-model number never reads as a trained-policy result. | `[judgment]` |
| wrong path | A caveat leads with the correct setup or the conclusion; where the correct setup stands alone, the mistaken path is not mentioned. | `[judgment]` |
| method detail | Once the code has landed, link the commit; where it has not, leave the section out. Operator commands are the reader's own interface and may be spelled out. | `[judgment]` |
| names | No customer or vendor name beyond what is authorized for this audience, on top of the flat ban on secrets. | `[judgment]` |
| feedback ledger | A document edited in place keeps a ledger of owner feedback beside it (`<slug>-feedbacks.md`): one row per instruction, keyed to the commit that satisfied it, plus Regressions and Still open. A row spanning the document and the system it describes is two rows, each checked on its own evidence, the system half against the pushed branch. | `[judgment]` |
| fresh review | Before it ships, a reviewer who did not write it reads it against the registers that govern it (the `proofread` skill). A writer cannot see their own assumptions. | `[judgment]` |
| audience wins | These rules are not the job. Where a specific audience wants something the rules do not ask for, the audience wins, and the deviation is named in the outline ([`outlining.md`](outlining.md)). | `[judgment]` |

## What it inverts

Provenance tags, required by `analysis`, are banned. The wrong path, documented in `analysis` and `record`, is omitted. A metric value in a heading is banned everywhere but restated here because a dated number in a title is this register's failure mode: it goes stale and cannot be cross-referenced. Correction lifecycle is deliberately not stated, because the type registers invert it: a readout is edited in place, an investigation takes a dated erratum.

## Example

Bad: "## Cutting the step to 900 s. The flagship run [M] (see `analysis/step_time.md`) was 2.5x faster than X2."

Good: "## 3. Step time. The async arm (run `<run-id>`) took 900 s per step against 2,250 s for the synchronous baseline at the same GPU count, 2.5x; the per-step series is in Appendix B."
