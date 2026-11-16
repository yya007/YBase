# general: the rules every register inherits

Every register in this folder starts from this file. [`../writing.md`](../writing.md) is its one-page form. [`../rules.md`](../rules.md) holds the evidence rules (verify before you assert, label every number, correct with an erratum) and this file does not restate them; what is here is how prose is shaped and worded once the facts are right.

## TL;DR

- **Lead with the answer**: a `## TL;DR` of at most five bullets, then support, with every comparison in a table.
- **One fact per sentence**, the everyday word, a verb over a noun built from one.
- **No em dashes, no hard-wrapped paragraphs, no filler**: the three mechanical language rules.
- `[mechanical]` rules can be checked by a program; `[judgment]` rules are confirmed by a reader. Both bind.
- Structural tells (uniform sentence length, unnamed numbers, a moral at the end) matter more than any banned word.

## Evidence

The rules themselves are in [`../rules.md`](../rules.md) § Evidence. Their writing consequences:

| id | Rule | Tag |
|---|---|---|
| `cite-inline` | Put the evidence where the claim is: `file:line`, a run id plus metric, or a URL plus quote. Re-check line numbers before shipping; they drift. | `[judgment]` |
| `label-the-unverified` | A guess and a fact never share a sentence unmarked. Say what you could not verify and mark the seam. | `[judgment]` |
| `no-fabricated-number` | Never invent, guess or round to a plausible number or link. Unfinished work gets a visible placeholder. | `[judgment]` |
| `figure-names-its-basis` | A figure names its producer, population and metric where it first appears. Two near-identical denominators say why they differ. Ask it of every table, not once of the document. | `[judgment]` |
| `observation-before-inference` | State what was measured, then separately what it implies. An ordering that flips across metrics is a spread, not a ranking. | `[judgment]` |
| `no-heterogeneous-pooling` | Never pool populations of different size or difficulty into one headline number. Report each and let the reader compare. | `[judgment]` |
| `name-the-baseline` | Every ratio or multiple names its baseline inline: the configuration and its measured value. | `[judgment]` |
| `ratio-needs-an-absolute` | A multiple is not a capacity. Give the absolute it lands on, per unit, in the unit the reader plans in. | `[judgment]` |
| `one-change-per-comparison` | An A/B names both arms, and the baseline is the same artifact minus the one change. Where more differs, say what. | `[judgment]` |
| `report-the-current-state` | Before reporting a problem, check whether it was already acted on. Report found, changed and remaining. | `[judgment]` |
| `verify-at-the-deciding-layer` | When a code path, config or run decides a claim, verify it there, even when a note or a reviewer says otherwise. A citation is a pointer, not evidence. | `[judgment]` |

## Structure

| id | Rule | Tag |
|---|---|---|
| `lead-with-the-answer` | The conclusion first, then support. Never make the reader assemble it from a narrative. | `[judgment]` |
| `tldr-at-most-five` | A long-form document opens with `## TL;DR`: at most five self-contained bullets, headline numbers bold. Five is a ceiling, never a quota; two results get two bullets. | `[mechanical]` (presence and count) |
| `tldr-carries-no-supporting-detail` | A TL;DR bullet is a claim and its number: no setup, no second comparison, no caveat, no run ids. One bullet shape per document. | `[judgment]` |
| `title-states-the-plain-claim` | A section title says what the section concludes, in the reader's words; where that is counter-intuitive, say so and name the intuition it breaks. | `[judgment]` |
| `lead-with-the-result` | A section's first sentence is its conclusion. Method comes after. | `[judgment]` |
| `topic-sentence-bold` | Open each conclusion with one bold sentence. Skimming the bold must carry the argument. | `[judgment]` |
| `tables-over-prose` | One idea per bullet. Every comparison (options, before and after, A against B) is a table. | `[judgment]` |
| `one-section-one-genre` | Results, limitations and next steps live in separate sections, never mixed into one list or into the TL;DR. | `[judgment]` |
| `open-work-is-an-opportunity` | Unfinished work is an opportunity with its reason, not a confession. A caveat on a number sits beside that number; a queued measurement is a next step. | `[judgment]` |
| `report-the-decision-not-the-deliberation` | A settled choice is reported as settled, with its reason in one clause. An undecided list invites a reader to reopen it. | `[judgment]` |
| `section-weight-matches-its-claim` | Length tracks how much the reader's decision rests on the section, not the effort it took. Groundwork sits below the results. | `[judgment]` |
| `state-a-number-once` | Each number has one home. Do not restate a table in prose or make the same comparison from two angles. | `[judgment]` |
| `constant-column-is-context-or-noise` | A column identical in every row is explained in the caption or moved to the setup sentence. | `[judgment]` |
| `no-restating-closer` | No trailing `Conclusion` or `Bottom line` that repeats the TL;DR. Bold each conclusion where it belongs. | `[mechanical]` |
| `appendix-letters` | Several appendices are `Appendix A`, `Appendix B`, in order. | `[mechanical]` |
| `full-identifiers` | Run names, job ids, paths and commit hashes appear in full, never truncated with `...`. | `[mechanical]` |
| `legend-for-notation` | Any encoded notation (footnote letters, symbols) gets a how-to-read legend before first use. On-figure text is a value or one word and never overlaps. | `[judgment]` |

## Language

| id | Rule | Tag |
|---|---|---|
| `no-em-dash` | No em or en dashes. Use a comma, colon, parentheses or a new sentence. House style, not a detector: removing dashes alone does not make text read as human. | `[mechanical]` |
| `one-para-per-line` | One paragraph per line in Markdown; no hard mid-sentence wrapping. Code comments follow their language's column convention instead. | `[mechanical]` |
| `long-sentence` | A sentence stays under 60 words. That is a ceiling on the worst case, not a target; most sentences are far shorter. | `[mechanical]` |
| `clause-stack` | No sentence chains four or more clauses with semicolons. End the sentence or make a list. | `[mechanical]` |
| `no-formal-word` | The everyday word: `use` not `utilize`, `before` not `prior to`, `about` not `with regard to`. Field terms (`utilization` as a metric, `heuristic`, `provenance`) are not targets. | `[mechanical]` |
| `heading-comma-appositive` | No heading tacks a qualifier onto a noun phrase with a comma ("The gain, measured"). Write the noun phrase or a full statement. | `[mechanical]` |
| `expand-on-first-use` | Expand every abbreviation and alias at first use. | `[judgment]` |
| `standard-name-not-paraphrase` | Use the field-standard metric name and the exact artifact name (`pass@1`, the benchmark's real name, the model's real name). A descriptive stand-in is jargon to the reader, not simplification. | `[judgment]` |
| `verb-over-nominalization` | "We decided", not "the decision was taken". Abstract nouns hide who did the thing. | `[judgment]` |
| `explain-the-mechanism` | When you explain why, teach the mechanism from the ground up: an everyday picture, a concrete stand-in for each moving part, every number in a unit a person can hold. | `[judgment]` |
| `no-bold-table-data` | Bold is for lead sentences and TL;DR numbers, never for values in a table. | `[judgment]` |

## Patterns that read as generated

`[mechanical]`: `no-not-just-but` (`it's not just X, it's Y` and variants); `no-filler-intensifier` (`delve`, `crucial`, `seamless`, `leverage` as a verb, `testament to`, `robustly`); `no-hedge-stack` (`may potentially`, `could possibly`); `no-meta-reference` (`as requested`, `the user asked`, `I pulled`, `this replaces the previous version`).

`[judgment]`, which no pattern can see and which matter more:

- Vary sentence length. A run of same-length sentences is the strongest single tell.
- Name the number or id instead of gesturing at it ("significantly faster", "the relevant run").
- Leave open threads open, and say what would settle them.
- Do not state your own moral after the finding, hedge a fact you verified, or pad a symmetry the content lacks.
- Figurative `landscape`, figurative `navigate` and `robust` as praise are filler no regex can separate from their literal senses. Catch them by eye.

## Folder READMEs

A folder `README.md` takes `general` only. It answers, in order: what the folder is, why it exists, who reads it, and what belongs in it and what does not. A lookup table may sit in it, but never replaces those four answers ([`../rules.md`](../rules.md): a README orients, a catalog lists).
