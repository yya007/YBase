# review: to an author, about one artifact

**Surfaces:** pull request bodies, pull request review comments and replies, review documents.

## TL;DR

- Addressed to an author about one artifact: lead with the verdict, anchor every finding to a quote or a `file:line`, critique the artifact and never the author.
- A **review document** labels each comment (`issue`, `suggestion`, `nit`, `question`, `praise`, `thought`), marks blocking status, and groups findings under `P0`/`P1`/`P2` numbered `F<n>`.
- A **PR comment** keeps `nit:` as its only label and ends in something the author can do.
- A **reply** answers the question that was asked, at the length of the question, and carries only what the diff cannot show.
- A **PR body** states the end state of one change and none of the pull request's own history.

## Who is reading, and what that changes

An author who will act on the review, and later a reader with less context than either of you, reading the thread cold. Both are outside this repo, so [`external.md`](external.md) holds: no workspace paths, no codenames. The landing convention (a branch in a worktree, a draft PR, the user marks ready and merges) is in [`../rules.md`](../rules.md) and the skills that drive a review.

## A review document

| Rule | Tag |
|---|---|
| Lead with the verdict. | `[judgment]` |
| Label every comment with its intent ([Conventional Comments](https://conventionalcomments.org/)) and write `(blocking)` or `(non-blocking)` beside it; `nit` and `thought` are non-blocking by nature. | `[mechanical]` (label present) |
| Group findings under `P0`/`P1`/`P2` and number them `F<n>`, so a reader takes the blockers first and can cite one later. | `[mechanical]` |
| Anchor every finding to a verbatim quote or a `file:line`. | `[judgment]` |
| Separate confirmations from corrections. Disclose what you could not inspect and your confidence. | `[judgment]` |
| Do not pile nits at the weight of issues. | `[judgment]` |

## A PR comment

- `nit:` is the only label; `nits:` for a short list. The full ceremony is noise on this surface, and a friendlier substitute ("tiny one") spends a line to say less.
- Every comment ends in the smallest step the author can take: read the field directly, add an assert, add the case to the test. Name the step, not the diff, and keep it as a question so the author can say no.
- Never discount your own findings. "None of them blocking" tells the author to skip them. Blocking status and severity are the reviewer's own triage and stay out of the comment.
- Praise is one clause that names the thing. Warmth past a clause reads as padding.
- Say each thing once, at the narrowest place it fits. A limit on one finding goes on that finding, not in the summary.
- Soften the ask, not the fact. "Would reading it directly be safer?" is soft; "this might possibly be a problem" is a verified fact hedged into noise.
- A conclusion about someone else's mechanism is offered, not pronounced: "that line could read low", or a question. What you read out of the tree (the call order, the file that exists) stays flat.
- Vary the shape. Five comments that each run observation, consequence, question read as one template.
- Ask in the first person plural and link what would settle it: a PR, a permalink, a row of data.

## A reply to a review of your own PR

- A link with a line range is a question about those lines. Open them before drafting.
- A yes or no question gets yes or no, then one clause of mechanism.
- The verdict word matches the evidence you hold; a judgment about their harness is not a measurement. "Maybe not" fits a mechanism argument; "no" claims a measurement.
- State the finding, not the method or owner that would produce it: "exposure is low, 2 of 3,100 rows", not "exposure is the sweep's job".
- Verify what their suggestion turns on, not what your answer turns on.
- The question sets the length. On a reply, length reads as defence.
- Carry only what the diff cannot show: that you accepted a finding, where you drew a scope line, why something was left alone. Strike every sentence a reader could verify by opening the change.
- When nothing survives the strike, react with a thumbs-up instead of posting "done".
- Your own gates are not evidence for the reviewer ("all tests red before", "within the line budget"); those belong in your worklog.
- A deferral names its reason and what closing it would take.

## A PR body

| Do | Do not |
|---|---|
| State the end state: what the code does now, and what moves for a caller who ignores it. | Narrate the pull request's own history: which branch it opened on, what was folded in, which commits were cherry-picked, the draft stage. |
| Name a sibling PR where its design bears on this one (`Supersedes #<n>, which prescribed the opposite remedy`). | Name its mechanics. A reviewer should be able to open what you named and read it. |
| Describe the diff as one change, grouped by what the code does. | Sort it by the pull request each piece came from. Ported work is this PR's work. |
| Put what each review round taught into the code and into your project record. | Put it in the body. A body describes a change, not the negotiation. |
| Write for a reader with no repo access; lead each section with its conclusion; put any two-axis comparison in a table. | Rely on a mechanical check. A dense body passes every pattern rule and still loses the reviewer. |

Do not post, as a comment, that you closed or superseded the PR, folded it into another, rebased or re-pushed, retargeted or renamed it, where the work landed, or a summary of your own diff. Each has a home that is not a comment: the code, the body or your record. A review bot's arrival is not an addressee; its finding is.

## What it inverts

Nothing. `review` adds a labelling scheme on top of `general`. The plain-English rules describe a comment but are not enforced on a posted one, which is a record of what was said.

## Example

Bad comment: "Non-blocking, and more of a question than a comment: I think this cannot handle an empty list and will probably crash, but feel free to ignore."

Good comment: "nit: `rows[0]` reads the first element before the empty check on line 12. Would moving the check up, or adding the empty case to `test_rows`, be the smaller fix?"
