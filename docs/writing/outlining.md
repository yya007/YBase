# Outlining a readout

A methodology note, not a register. [`general.md`](general.md) grades the language, [`external.md`](external.md) what an outside reader can follow, [`readout.md`](readout.md) the document's shape; this note says what shape the argument takes before the words exist.

## TL;DR

- **Every readout is paired with an outline**, `<slug>-outline.md` beside it, and the pairing is checked.
- **A sentence outline, not a topic outline.** Each row states the claim its section proves. "The setup" is a topic; "the arms differ only in scheduling" is a claim.
- **The readout never runs ahead of its outline.** Its `##` headings are a subsequence of the outline's section list, in order; the outline may lead.
- **A significant change is a structural one.** Adding, renaming or reordering a section goes through the outline; rewriting prose under a standing claim does not.
- **A rule set aside is named in the outline's `## Deviations`**, with the reason.

## Where this comes from

| Principle (published practice) | The local rule it produces |
|---|---|
| **Lead with the answer.** The pyramid principle puts the recommendation on top, supported by grouped arguments that are mutually exclusive and collectively exhaustive. | The outline states one governing claim before any section claim. If it takes two sentences, it is two readouts. |
| **Action titles, not descriptive ones.** Reading only the titles should give the argument. | Each row says what the section proves. |
| **Fix purpose and audience first, and review the outline before drafting.** | `## Audience and access` comes first and decides what counts as a valid citation below it. Outline review is the cheap review, the one that can still change the shape. |
| **Reverse-outline what exists.** One sentence per section, then look for rows that repeat, sections that resist one sentence, and rows that do not connect to the thesis. | The method for backfilling an outline, and for auditing a readout that has grown. What it surfaces is reported, not silently rewritten. |

## What an outline contains

| Section | What goes in it |
|---|---|
| `## Audience and access` | Who reads it, and what they can open: commits, run pages, public links. |
| `## TL;DR: the governing claim` | The single sentence the whole readout proves. |
| `## Section claims` | One row per `##` section, in order: the heading (without its index), the claim it proves, the evidence it rests on. |
| `## Out of scope` | What the readout deliberately does not claim. Deciding scope is the outline's job, which is why the readout itself carries no out-of-scope note. |
| `## Deviations` (only when there is one) | One line per rule set aside: the rule, and why following it would make the document worse. |

## Setting a rule aside, and saying so

Unstated, a rule broken on purpose and a rule never read are the same artifact, so a reviewer either re-raises a settled decision or lets a mistake through. Stated, the deviation is one reviewable line, and a rule that keeps appearing in Deviations sections is a rule with the wrong scope, which nothing else would surface. Write the rule, then the reason: `readout.md, no padded TL;DR: kept a fourth bullet, because it is the caveat the decision turns on`. It goes in the outline, not the readout; an outside reader has no use for it. Add the line in the same edit that breaks the rule; written later it is a rationalisation, and usually never written.

## Writing one

1. Create `<slug>-outline.md` beside the readout with the five sections above.
2. Answer audience and access first. An unanswerable citation question here is an unsourceable claim later.
3. Write the governing claim. No single sentence means two readouts.
4. List the sections, each with what it proves and what proves it. A row with no evidence is a section with nothing behind it yet.
5. Get the outline reviewed, then draft section by section. Adding a section means adding its row first.

## Reverse-outlining a readout that already exists

1. Write each section's claim in one sentence. A section that resists this is doing more than one job.
2. Compare adjacent rows. Two rows making the same point mean the sections merge or one takes a different angle.
3. Check each row against the governing claim. A row that does not support it belongs in a different document.
4. Report what this surfaces rather than fixing it in the same pass. Rewriting circulated prose is its own decision.

## What a check sees, and what it cannot

Mechanical: the sibling outline exists; the readout's headings are a subsequence of the outline's list. Judgment, and no check will cover these: whether a claim is true, whether the sections are exclusive and exhaustive or merely adjacent, whether a row asserts anything or only labels a topic, and whether a deviation that was made was recorded. An absent `## Deviations` and no deviations look identical to a program, which is why that requirement sits on the writer.

## Sources

- The pyramid principle, on leading with the answer and grouping arguments: [Think Insights](https://thinkinsights.net/insights/minto-pyramid-principle), [ModelThinkers](https://modelthinkers.com/mental-model/minto-pyramid-scqa).
- Action titles in consulting readouts: [Management Consulted](https://managementconsulted.com/pyramid-principle/).
- Technical report outlining, on purpose statements and outline review before drafting: [Seneca Polytechnic](https://pressbooks.senecapolytechnic.ca/formaltechnicalreports/part/creating-an-outline/).
- Reverse outlining: [University of Wisconsin-Madison Writing Center](https://writing.wisc.edu/handbook/reverseoutlines/), [Explorations of Style](https://explorationsofstyle.com/2011/02/09/reverse-outlines/).
