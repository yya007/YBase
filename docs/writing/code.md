# code: comments, docstrings and commit messages

**Surfaces:** comments and docstrings in `.py` and `.sh` files, and commit message bodies. The pull request body is in [`review.md`](review.md).

## TL;DR

- Self-contained for a reader with no access to this workspace: no workspace paths, no codenames, no catalog ids as the reason a line exists.
- The invariant sits at the fix site and states the invariant, not the history that found it.
- Put the why in plain terms, or link a durable public source.
- A block inside a function body is a few sentences. The evidence and the alternatives belong in the pull request body.
- A commit message describes the end state for whoever reads the log on the branch it lands on.

## Who is reading, and what that changes

Everyone who touches the file afterwards, most of whom never saw the change that added the comment and cannot open this repo. A comment is read many times by people who already accepted the change; it carries what the code cannot show and nothing the code already shows.

## Do / Do not

| Do | Do not |
|---|---|
| State the invariant the code now holds, in the present tense. | Narrate the investigation. The invariant is the finding; the search that reached it is not. |
| Name what breaks without it, in a clause. | Work the counterfactual case by case. That belongs in the pull request body. |
| Say why a non-obvious choice was made, where the line does not show it. | Argue the change. The reader has already accepted it. |
| Let the pull request body carry the evidence, the measurement and the alternatives. | Restate the body in the code. Text that works in both places is a copy, and the copy in the file is the one every later reader pays for. |
| Keep a block inside a function body to a few sentences. | Write more comment than code. A paragraph over a four-line check is the shape to avoid. |
| Give a module docstring the room a cold reader needs. | Give a block beside a statement that same room. Its reader arrives with the function around them. |

## Rules

| id | Rule | Tag |
|---|---|---|
| `code/no-workspace-path` | No workspace or personal path in a comment, docstring or commit message. Name the mechanism or link a public source. | `[mechanical]` |
| `code/no-codename` | No catalog id, tier name, bracket tag or bare run alias as the reason a line exists. Name the behaviour. | `[mechanical]` |
| `long-sentence`, `clause-stack`, `no-formal-word` | Apply to comment prose. A checker joins a wrapped comment block back into one paragraph before measuring, so a sentence wrapped over five lines is graded as one sentence. | `[mechanical]` |
| `tldr-at-most-five`, `appendix-letters`, `no-restating-closer`, `one-para-per-line` | Switched off: a docstring is not a publication surface, and comments wrap at a column by their language's convention. | `[mechanical]` (switched off) |
| `no-meta-reference`, `no-filler-intensifier`, `no-hedge-stack`, `full-identifiers` | Still apply to comment and docstring prose. | `[mechanical]` |

In a framework repo whose scripts may be extracted into another project, the two `code/` rules fire early on purpose: a workspace reference becomes wrong the moment it crosses a repo boundary, so it is caught before extraction, not after. Where a line plainly is not headed for extraction, a suppression with that reason is the honest response.

## What it inverts

Nothing. `code` extends `general` with two workspace-reference bans and switches off the Markdown structure rules.

## Example

Bad:

```python
# After a long investigation (see analysis/2026-03-14_timeouts.md in the workspace) we found that
# E07 runs hit the 30 s cap because the summarizer was slow, so we bumped it here. Tried 60 first.
```

Good:

```python
# The summarizer call can exceed 30 s on long contexts; a shorter cap drops the page silently.
```
