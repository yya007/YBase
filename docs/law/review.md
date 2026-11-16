# Review: the rules that bind when you review a pull request or answer its review

Shown once per session by the moment hook; see [README.md](README.md). Codex reads it before the act.

## Before you post anything

1. Read the facts from the PR head, not from the diff summary or the first hunk ([rule 1](../rules.md#evidence)). A diff's direction is not readable from its first hunk.
2. Read every surface a review lives on: the timeline, the inline threads including outdated ones, and the body a bot may rewrite. A round closes only when all three are read.
3. Verify each finding, yours or another's, against the head blob. A finding that reads the diff summary describes the summary.
4. Draft every comment in chat and post only on the user's say-so, your own PR included. One exception, which the `land-pr` skill also states: a reply that answers an automated reviewer's finding on your own PR may post directly, because no person is waiting on the other side. Post at all only to answer something written there; a bot's arrival is not an addressee.
5. Reviewing your own PR is a different procedure: the `land-pr` skill. Reviewing someone else's: `review-pr`.

## The shape of a comment

- One finding per comment, as a question plus an option: what you observed, what would have to hold for it to be fine, and one way to resolve it.
- Hedge what you did not measure, and state the finding rather than your method. "Maybe not" fits evidence about a mechanism; "No" claims a measurement nobody made.
- Label every number you quote ([rule 2](../rules.md#evidence)).

## Answering a review

- Reply in the thread it answers, and say only what the diff cannot show. "Both added." is a whole reply. A reply with nothing in it but acknowledgement is a thumbs-up reaction and no comment at all.
- Your own gates are not the reviewer's. The negative control, the line budget and the stack order prove the rules you work under; they go in the project record, never in the reply.
- A deferral names its reason; "not closed" is a shrug.
- Sweep the class, not the instance ([rule 9](../rules.md#changes)): check the other open PRs for the same issue before you reply.
- End by re-requesting the reviewer: `gh pr edit --add-reviewer <them>`. Your own push expires any count of open threads you took before it, so count again after.
- Read the posted review back from the PR before reporting it posted ([rule 5](../rules.md#evidence)).
