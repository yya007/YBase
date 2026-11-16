# investigation: one question, answered with evidence

**Surface:** an investigation or debugging write-up, dated and immutable once circulated. Stacks on [`external.md`](external.md).

## TL;DR

- An investigation is an **evidence-backed answer to one question**: the question in the title, the finding in the heading that answers it.
- The wrong turn is the finding here, so every ruled-out alternative is named with what ruled it out.
- About 1,000 words, short noun-phrase headings, tables over prose: depth of method is the deliverable, and tables buy it room.
- Immutable: a correction is a dated `ERRATUM` block in place, never a silent edit. That is the opposite of [`readout.md`](readout.md).
- An investigation that found nothing is a first-class outcome, with a `**Status:** open` line and four fields in place of the conclusion.

## Who is reading, and what that changes

Someone outside the repo who has hit the same question, or who is being asked to accept a conclusion a readout states in one line. They need to see the method well enough to disagree with it, which is what a readout withholds. Depth is not length: they reach for a table of arms and results, not paragraphs describing them.

## Do / Do not

| Do | Do not |
|---|---|
| Name the question in the title and the finding in the heading that answers it | Name a section for its subject and make the reader hunt |
| Lead with the result, then the method | Build up to the result through the method |
| Name every alternative with the measurement that ruled it out | Present only the hypothesis that survived, which reads as luck |
| State the calibration of any model or simulation the conclusion rests on | Headline a simulated number without the measurement it was checked against |
| Report what could not be measured and what would settle it | Leave a gap silent |
| Put every set of arms, causes or figures in a table | Walk a list in a paragraph |
| Pay for a new section by cutting another | Grow the document to fit it |
| Correct with a dated `ERRATUM` block in place at the claim | Edit in place, which is the readout's rule and the inverse of this one |
| Close with the script, the exact command and the slices cited | Assert reproducibility without the command |
| Say in the header whether the question is answered or open | Report an elimination as a diagnosis, which retires the question for every later reader |
| Give scope and cost before mechanism: how much was affected, for how long, which results it invalidates | Open on the mechanism |
| Say how it was detected and what would have detected it sooner | Hide the monitoring gap, which is often the more actionable finding |
| Name contributing factors where several contributed | Elect one root cause, which claims the others were tested |
| Name the artifact: the commit, the config, the instrument, the prior diagnosis | Name the person |
| State the lesson that outlives the question | Stop at the answer |

## Shape and budget

**About 1,000 words, counted before shipping** (table cells count, delimiter rows do not). The method is the deliverable, so every arm feels load-bearing to the writer who ran it. Ask of each row which claim it supports; "it was expensive to produce" keeps nothing in.

**Headings are labels**: `Cause`, `Method`, `Limits`, `Scores`. The one exception is the finding heading, which may name the finding as a clause and still carries no figure. Catch `how/why/what/which` plus a clause, with or without a question mark. Column headers are one to three words.

**Prose after a table says what the table cannot**: the conclusion, the caveat or the one confusion the table invites, then stop.

## When the cause is not found

One `**Status:**` line under the title, `answered` or `open`. An open investigation that reads as closed is worse than no document, because it retires the question for everyone who finds it. An open one owes four things in place of its conclusion:

| Field | Carries |
|---|---|
| Live alternatives | the candidates elimination has not reached |
| Missing evidence | the observation that would separate them, and why no retained artifact holds it |
| Next check | the one measurement to make next, named so someone else could run it |
| Cost | what that check costs, so a reader can weigh continuing against dropping it |

## Blameless by construction

The subject is an artifact, never its author. "The prior diagnosis excluded the timeout path on grounds that do not hold here" carries the same information as a name. A writer who expects to be named argues rather than publishes, and the elimination record stops being written. Your own wrong turns take the same voice and are usually the most useful rows.

## What it inverts

Against `readout`: dated and immutable, with named rather than numbered sections, because it is read alone rather than walked through. Against `external`'s "show what shipped": the tried-and-dropped ledger is the deliverable, bounded to alternatives bearing on the question. Against `analysis`: this is the finished answer for an outside reader; work in progress stays in `analysis/`.

## Mechanical rules

None of its own. `general` and `external` apply in full, minus `external`'s readout-only checks. The 1,000-word budget is a judgment item, because twelve table rows and twelve sentences do not cost a reader the same. The erratum block is the one `record` and `reference` use, placed immediately after the claim it corrects, with the original sentence left standing:

```
> **ERRATUM <YYYY-MM-DD>:** <what the document said, what is true, how it was established>. <One clause on what changes for the conclusion, or that nothing does.>
```

## Example

Bad heading and lead: "## How we measured it. We first tried the profiler, then the timer, then noticed the queue."

Good heading and lead: "## Cause: the queue, not the model. Admission waits account for the whole gap: 270 s of the 290 s step difference on the matched pair, with the model-side timings level (table below). The profiler and timer arms are in Method with what each ruled out."
