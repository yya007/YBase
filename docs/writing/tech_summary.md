# tech_summary: one project's decisions on one page

**Surface:** a one-page record of a project's key technical decisions, kept beside the project and rewritten as it moves. Stacks on [`external.md`](external.md).

## TL;DR

- A tech summary is **one project's key technical decisions on one page**: what was promoted, adopted, dropped, deferred or reversed, and the fact that settled each.
- The dropped option is content here: the row that says what ruled it out stops the next reader re-proposing it.
- Living, one file per project named for the project; a new decision is a new row, not a rewrite.
- A table document: the decisions table carries the substance; prose is a status line, a TL;DR and a few lessons.
- Evidence cites a run id, a pull request or a commit, never a workspace path.

## Who is reading, and what that changes

Someone joining the project, or leading a neighbouring one, who wants what has already been settled and on what evidence, without reading the plans and logs. They act on a row: reuse a choice, avoid a dropped option, reopen one when the evidence changes. A row without its evidence is useless to them; a row about a routine fix wastes the page.

## Do / Do not

| Do | Do not |
|---|---|
| Keep the dropped option with the measurement that ruled it out | Show only what shipped |
| Name both sides: the option kept and the option set aside | Write a row naming only the winner, which reads as a changelog |
| Give each row its number, its baseline and its producer | Cite "the experiments showed" |
| Use one of five verdict words: adopted, promoted, dropped, deferred, reversed | Invent a verdict per row, which defeats scanning the column |
| Keep a reversed decision as two rows, the original and the reversal | Edit the original to match the later answer, which erases why it changed |
| Say for a deferred row what would reopen it | Park a choice with no trigger |
| Stop at the decisions that changed direction, usually five to fifteen | Copy every board item into the table |

## Shape

A status line under the title, carrying the date the table was last checked against the project's records; then `## TL;DR`, `## Decisions` (newest first), `## Open decisions`, `## Lessons`. Prose outside the tables stays under about 400 words; a decision that needs more than a cell of argument links an investigation. The filename is the project's name, no date, because the file is rewritten as the project moves.

## Rules

| Rule | Tag |
|---|---|
| Every row names both the option kept and the option set aside. | `[judgment]` |
| Every row's evidence carries its number, its baseline and its producer. | `[judgment]` |
| A dropped row says what ruled it out; a deferred row says what would reopen it. | `[judgment]` |
| The verdict is one of the five words. | `[mechanical]` (column values) |
| Only decisions that changed what the project builds, ships or measures are rows. | `[judgment]` |
| The section list above is present. | `[mechanical]` (sections present) |

## What it inverts

`external` says show what shipped and omit the wrong path. Here the option set aside, with what set it aside, is half the value. Everything else in `external` holds: exact names, inline numbers, provenance by run id or commit.

## Example

Bad row: "Switched to the async scheduler."

Good row: "Async scheduler over the synchronous one | adopted | 1.6x cheaper per trajectory on the matched pair (run `<run-id>`, PR #<n>); synchronous kept as the control arm."
