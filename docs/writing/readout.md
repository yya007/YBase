# readout: a batch of changes and their measured impact

**Surface:** the one document a meeting is walked through, for a reader deciding whether to adopt, fund or continue the work. Stacks on [`external.md`](external.md). The number method is [`performance-reporting.md`](performance-reporting.md); the argument is shaped first in [`outlining.md`](outlining.md).

## TL;DR

- A readout is a **view over a batch of changes with their measured impact**, living and edited in place.
- Every cross-arm number is normalized before it is described, and "where the gain comes from" is a subtraction that sums to the headline.
- Attribution is the failure mode this register exists to catch: a lever row carrying the headline multiple, a bottleneck written as a design property, a verdict word the document's own error bar contradicts.
- About 1,200 words of prose; 2,000 is the ceiling. Table rows are free, so detail moves into a table rather than getting cut.
- Body sections are numbered and appendix subsections lettered, so a reader can be sent to "section 4" or "appendix B".

## Who is reading, and what that changes

Engineering and leadership who can open runs and commits but not this repo. They need the result first, the basis second, and the mechanism only if they ask. The voice is a technical leader's: verdicts, sizes and consequences, with mechanism present to justify them. Every heading, column name and bullet comes from the reader's decision, never from the team's own vocabulary, structure or history: "default" and "shipped" are what the code calls things, "measurement bugs" is what the work felt like, and a three-bullet summary is a shape chosen before there was content.

## Shape

| Part | Rule |
|---|---|
| Title | `<Project>: <area of work>`. No number, multiple or status word: a title is quoted into decks and invites, where it outlives its figures. |
| Above the TL;DR | At most one plain sentence of purpose. No draft, audience or scope preamble. |
| TL;DR | Bullets only, no table. One bullet per impact, each opening on its bold number or verdict within the first 40 characters and naming the metric, its size and two or three members of the split. A third bullet is not owed. System changes that cannot move the sampled distribution and model-level changes that can are separate bullets. |
| Section 1 | The overview, the only place the whole project speaks: motivation (an industry standard matched, a headroom observed, or damage to a decision the reader owns), the problem, where it stands. About 150 words, never past 250. |
| Setup | A table in front of the first section that reports numbers, saying whether it is the pinned protocol carried unchanged. Never its own opening section. |
| Headings | Short noun phrases a reader can be sent to (`Motivation`, `Quality`, `Open questions`). Never a sentence, a question or a claim; the section's bold first sentence carries the claim. Column headers the same, one to three words. |
| Foundation work | One short section below the results, as a table of what was wrong and what it now guarantees. No per-defect narrative; rows enumerated from the project's PR record, not from memory. |
| Closing section | One section of open questions, each as the question, what would answer it and what it is worth. No status section, no in-flight items, no "Limitations" list. |
| Appendix | Unnumbered, subsections lettered with an index. A is the usage guide (flag or default, the commit it holds from, what to re-tune), B the artifact inventory carrying provenance and not results. Superseded arms go here, labelled superseded. No per-figure method table. |

## Do / Do not

| Do | Do not |
|---|---|
| Multiply by each column's own GPU count and divide by its own trajectories before writing flat, same, slower or doubled | Compare wall-clock seconds across arms holding different hardware |
| Decompose the headline gap into rows that sum to it, with a row for the unattributed remainder | Assert a share ("four fifths of it is generation") that no column has to add up to |
| Give an enabling change the effect it unblocks plus its measured direct effect | Write "the 4x above" in a lever row, which double-counts against every other row |
| Write the bound that binds now, with the earlier bounds and what removed each | Write "X is generation-bound" as a property of X |
| Name the operational axes a configuration was chosen on, each with what would change it | Let a situational choice read as a universal one |
| Choose the verdict word against the instrument the document itself computes | Headline a gap as "trails" two sentences after bounding drift at a larger value |
| Frame a reconciliation as "what each gap actually is" | Frame it as "numbers that look inconsistent" |
| Carry a quality-neutrality claim both ways: an argument from construction and an end-to-end measurement | Let "we reasoned it is safe" stand in for "we ran it and looked" |
| Split a regression count by cause (expected trade-off, instrument variance, our defect) with one row-level example each | Report a pooled "7 broken" that reads as damage nobody understood |
| Fix a wrong number where it sits | Add an `Update (<date>)` block; that is what puts this type over budget |
| Keep a limitation only where a reader would act differently for knowing it | Keep a caveat whose job is to show the writer thought of it |
| State one conclusion after a table, then where the evidence sits | Re-quote numbers the table already carries, or gloss a standard metric name |
| Cite public code, a PR or a run link; name a configuration for its audience or purpose | Name a workspace path, a branch, "on master", or a configuration called `default` |
| File a finding outside the subject as its own investigation and cite it in one clause | Carry it because it is interesting, or add an out-of-scope note |
| Frame what you found as opportunities the instrument was missing | Call prior work defective; its authors are in the audience |

## What it inverts

Against `record` and `analysis`: a readout is current state, edited in place. A wrong number is fixed where it sits, with no dated erratum and no changelog, so a reader arriving today cannot tell which sentences were rewritten. One carve-out: a figure that already circulated keeps an undated standing correction, one clause beside the number ("1.4x above its floor, not the 5x reported earlier"), never a bullet, a heading or a narrative of the error. Against `analysis`: provenance tags are banned, and the intervention matrix stays in the investigation this cites; the readout carries the conclusion and its size.

## Mechanical rules

`external/readout-length-budget` (2,000 words of prose, tables free), `external/tldr-leads-with-the-result`, `external/no-out-of-scope-note`, `external/three-significant-figures`, `external/readout-needs-outline` and `external/outline-matches-readout` fire on this type only. Everything in [`external.md`](external.md) and [`general.md`](general.md) applies as well. The 1,200-word target is a judgment item; the ceiling is the check. A naming convention here constrains the document, never the system it describes: when following one starts changing code, the rule has been over-read.

## Example

Bad TL;DR bullet: "The single-node async configuration produces a training trajectory for 30 GPU-seconds against the two-node baseline's 54, measured on four runs (ids in Appendix B), which is 1.8x realized and 2.6x steady, with quality pending."

Good: "**1.8x cheaper per trajectory** on half the GPUs (2.6x on the steady basis), quality level on both benchmarks within the eval's own drift."
