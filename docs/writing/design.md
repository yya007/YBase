# design: the shape of one proposed system

**Surface:** `research/<topic>/projects/**/design/**` in a knowledge base. Stacks on [`external.md`](external.md).

## TL;DR

- A design document is **the shape of one proposed system and the trade-offs it turns on**, written before the code and circulated to be argued with.
- **It is read by a senior lead, not by the person who will type the code.** The body carries context, impact and the line from motivation to design; every file, folder, command and exact count moves to the appendix.
- **Its TL;DR carries substance, not labels**: what is being built and what friction that removes.
- The section that makes it a design and not a manual is **Alternatives considered**, a scored matrix on named axes. **Risks** are the three to five hardest, each with a de-risk plan.
- It is **living**, edited in place with a `**Status:**` line, and ends with a few representative worked examples.

## Who is reading, and what that changes

A senior lead who owns a team's direction and is deciding whether the shape is right before anyone spends a quarter building it. They are technical and not in this code daily: a module name or a path tells them nothing. So the body argues and the appendix demonstrates; motivation is stated as friction a lead recognises from a bad week, one sentence each; numbers are for sizing (three significant figures, a ratio where significance is the point); and the voice is a senior lead's, neither negative nor absolute. Today's cost is an opportunity, not a wall: "we can take a newer upstream now; it is expensive and error-prone" invites a design discussion, where "we cannot" invites a correction of the sentence.

## Do / Do not

| Do | Do not |
|---|---|
| Say in the TL;DR what is being built and what it buys against today's flow | Open on the architecture and leave the benefit to be derived |
| Frame today's cost as expensive, slow or error-prone | Write that we cannot do a thing we could do at a price |
| Write goals as outcomes and non-goals as scope, one line each | Lift a task out of the design and call it a goal, or write a non-goal as a refusal |
| Name the one rule the design turns on, early, in one sentence | Present a layer diagram and leave the reader to infer what holds it together |
| Order `## The design` principle, then components, then layout | Lead with the directory tree |
| Score alternatives on axes chosen before the answer, coarsely (high, medium, low) unless measured | Give each alternative a sentence of why it was bad, or score every rival worse on every axis |
| Add a sentence where a rival genuinely wins on an axis | Pretend there was no trade-off; a design with none did not need a document |
| Keep `## Risks` to the three to five that are hard, each with its de-risk plan and the falsifier | List every known unknown at equal weight |
| Say "routine work such as A, B and C" | Count an illustrative set, which claims a complete list |
| Pick appendix examples where seeing the files changes what a reader believes | Mirror the body section by section in the appendix |
| Cover testing, data and assets, and monitoring cost when the design touches them; name the open-source practice borrowed | Leave the cross-cutting surfaces out because they are not the highlight |
| Say who stays compatible with what, and for how long, where a version pin decouples teams | Invent rollout stages to fill a heading |
| Update the document and its status line when implementation changes the design | Freeze it at the approved version |
| Retire it to an archive when a different design supersedes it | Leave two live designs for one system |

## Shape and budget

**About 1,500 words of prose in the body**, everything above `## Appendix`. Tables, diagrams and fenced examples do not count, so the design moves into a diagram, the comparison into a matrix and the flows into worked examples. A body that needs more is two designs or a spec. The appendix is not charged, and it is representative, not a mirror: one example per body point is a second reading of the argument with paths in it.

Sections, in order: TL;DR, `## Context`, `## Goals and non-goals`, `## The design` (with `### Principles` first, as bullets, not introduced), `## Alternatives considered`, `## Risks`, `## Appendix: worked examples`. Two optional sections where a project needs them: `## Cross-cutting concerns handling` (owed in practice by anything that trains, evaluates, holds data or serves traffic) and `## Rollout` (only where a rollout exists and is agreed; an invented plan is worse than an absent one).

**No outline.** A design's skeleton is the design. **Filenames carry no date**: the status line carries the state and version control carries the history.

## What it inverts

`investigation` is dated and immutable; this is living, because it describes a system still being built, and freezing it buys an audit trail at the price of a document that stops describing the thing it names. `readout` reports what was measured; this proposes what does not exist yet, so the decomposition and the outline do not apply, but the number discipline does.

## Mechanical rules

| id | Rule |
|---|---|
| `design/no-absolute-claim` | Refuses the first-person impossibility (`we cannot`, `there is no way to`), so a cost is framed as a cost. A bare `cannot` about what the system permits is left alone. |
| `design/no-tldr-scaffolding` | Refuses a TL;DR bullet that opens with a label for itself ("What we are building") rather than the claim. |
| `design/alternatives-need-axes` | `## Alternatives considered` holds a table of at least three columns. |
| `design/risk-budget` | `## Risks` carries at most five items. |
| `external/three-significant-figures`, every other `external/*` and `general/*` rule | As everywhere. The prose budget is a judgment item, unlike the readout's. |

## Example

Bad TL;DR bullet: "**What we are building:** a new layered package layout with a core, adapters and a plugin registry."

Good: "**One upstream pick-up a week instead of one a quarter**: the adapters own every upstream-facing call, so a version bump touches one package and the tests that pin it."
