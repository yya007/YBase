---
name: land-pr
description: Use when driving your OWN open pull request in YBase or a managed repo from its first review to merged ("resolve the review comments", "fix the bot's findings on PR 123", "get this PR landed"); verifies each finding, fixes, gets an independent review, replies, and merges only as the repo's own landing rules and the user say.
---

# land-pr: take your own PR from first review to merged

This skill covers the window after your pull request (PR) exists and someone, a person or an automated reviewer, has looked at it. It reads every review surface, verifies each finding against the PR head before acting on it, fixes what is real with a test that fails first, gets an independent review of its own patch, answers each finding in its thread, and re-requests review. A finding can be right about the symptom and wrong about the remedy, so the skill measures how many real cases a finding's claim covers before taking its fix. It merges only under the repo's own landing rules. Read the repo's `AGENTS.md` first: where it states how a PR is reviewed, marked ready or merged, that wins in that repo ([`docs/rules.md`](../../../docs/rules.md) rule 20). Where it states nothing, the framework default holds ([`docs/law/pr.md`](../../../docs/law/pr.md)): a reviewed PR, opened as draft; the user marks it ready and merges unless they said otherwise; never a force-push; never a push straight to the default branch.

## When not to use

- The PR is someone else's: use [`review-pr`](../review-pr/SKILL.md).
- No PR exists yet: open one as a draft first (as in [`session-closeout`](../session-closeout/SKILL.md) stage 1), then come back once it has been reviewed.
- The question is whether to split, re-scope or abandon the PR. The skill measures that and asks; it does not decide it.

## Stages

Set up once, from the YBase root. `W` is the worktree that holds the PR's branch (`ybase worktrees --repo NAME` lists a managed repo's worktrees; without `--repo`, YBase's own), and `R` is that repo's GitHub name, from `git -C "$W" remote get-url origin`:

```bash
eval "$(ybase env)"; W=<worktree>; R=<owner>/<repo>; N=<pr>; O=${R%/*}; P=${R#*/}
S="$YBASE_SCRATCH/land-pr-$N"; mkdir -p "$S"
```

Reach the worktree by path (`git -C "$W" ...`), never by `cd` ([`docs/rules.md`](../../../docs/rules.md) rule 23). In a managed repo, nothing you write (commits, replies, the PR body) mentions YBase, its knowledge base or sibling repos (rule 22).

1. **Confirm the PR is yours, and read its shape.**
   ```bash
   gh pr view "$N" --repo "$R" --json author,state,isDraft,headRefName,headRefOid,baseRefName,reviewDecision > "$S/pr.json"
   gh api user --jq .login
   gh pr list --repo "$R" --base "$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['headRefName'])" "$S/pr.json")" --json number,author
   ```
   A different author means stop and use `review-pr`. Note any PR based on this branch: merging changes its base, and its owner needs to hear that. Record the local `git -C "$W" rev-parse HEAD`; if it differs from `headRefOid`, reconcile before touching anything.

2. **Read all three review surfaces.** A review lives on the PR body, on the inline threads and on the timeline. A threads-only sweep reports clean over a body summary that an automated reviewer rewrote.
   ```bash
   gh pr view "$N" --repo "$R" --json body,reviews,comments --jq '.body, (.reviews[],.comments[] | "\(.author.login) \(.state // "comment"): \(.body[0:150])")'
   gh api graphql -F owner="$O" -F name="$P" -F n="$N" -f query='query($owner:String!,$name:String!,$n:Int!){repository(owner:$owner,name:$name){pullRequest(number:$n){reviewThreads(first:100){nodes{isResolved isOutdated path line comments(first:1){nodes{databaseId author{login} body}}}}}}}' \
     --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved|not) | "\(.comments.nodes[0].databaseId)\t\(.isOutdated)\t\(.path):\(.line)\t\(.comments.nodes[0].author.login)\t\(.comments.nodes[0].body[0:100])"'
   ```
   Count the open threads; an outdated one is still open, since its line moved but its question did not. Write the list to `$S/findings.md`, one row per finding.

3. **Verify each finding against the head, and measure its population.** Read the file at the head, not the hunk the comment quotes, and try to construct the state the finding claims. Three outcomes are normal and each needs a different reply: the finding is real; it is stale because the tree moved under it; or it is right about the symptom and wrong about the remedy. When a finding says a class of input is mishandled, count how many real members that class has right now (`grep -c`, a listing, a short stdlib script). That number decides whether the fix is a guard, a rename, a constant or nothing, and it is the sentence the reply is built from. Label it `[M]` per rule 2.

4. **Fix, test first, and sweep the class.** Before the first edit, save the baseline failure list with stage 6's command, writing to `$S/fail_base.txt` instead of `$S/fail_now.txt`. Write the failing test, watch it fail on the current code, then fix. A test that passes before the fix proves nothing. Derive a bound from the thing it protects rather than restating it. Then sweep the class (rule 9), which has three answers: it is this PR's and is fixed here; it is wider but still small enough to fix here; or it predates this PR and is shared with code the PR never touched. In the third case, harden what this PR introduced, leave the older twin alone, and name it in the PR body for the user to decide, because widening the fix puts unreviewed changes into this PR.

5. **Get an independent review of your own patch.** You cannot see what you did not think to check. Brief a reviewer with the worktree path, the diff (`git -C "$W" diff <base>...HEAD`), how to run the tests, and the baseline failure list; give it the code, not your conclusion.
   - Claude Code: spawn a subagent with a fresh context (the Agent tool) and that brief, read-only.
   - Codex: start a fresh read-only session with the same brief (for example `codex exec --sandbox read-only "<brief>"`).
   - Neither available: ask the user for a human reviewer, and say the patch is unreviewed until then.

   Its findings are claims: verify each one as in stage 3 before fixing any. If the reviewer hands back a patch with its own test, that test asserts whatever the patch does, including a defect the patch introduced. Run it against the pre-fix code and see it fail, and read what it actually pins.

6. **Re-verify, and compare the failure set, not the count.**
   ```bash
   python3 -m unittest discover -s "$W/tests" -t "$W" 2>&1 | grep -E '^(FAIL|ERROR): ' | sort > "$S/fail_now.txt"
   comm -13 "$S/fail_base.txt" "$S/fail_now.txt"    # new failures: must print nothing
   ```
   That is YBase's runner; in a managed repo use the one its `AGENTS.md` names and reduce the output to one sorted line per failing test (with pytest, `python3 -m pytest -q -rfE 2>&1 | grep -E '^(FAILED|ERROR) ' | sort`). An unchanged count can hide one test fixed and one broken. Run the repository's own gates too. In YBase, the worktree's own: `"$W/bin/ybase" check` and `bash "$W/tests/test_profile.sh"`; the root `bin/ybase` checks only the main checkout ([`README.md`](../README.md#cross-agent-contract)). In a managed repo, the gates its `AGENTS.md` names, not YBase's. A failure that predates this round is reported with its number and why you think it predates the change, never silently fixed in this PR and never silently ignored.

7. **Push, and keep the body and title true.** `git -C "$W" push` with no force; if the remote moved, fetch and integrate, then push again. Re-read the title and body against the diff: a title that still promises what the PR no longer does is a finding in its own right. Follow the repository's template if it has one (`.github/pull_request_template.md`). The body states the change, not the PR's history. Writing follows [`docs/writing.md`](../../../docs/writing.md).

8. **Reply in each thread, then re-request review.** Draft every reply in `$S/` first.
   - A reply goes in the thread of the finding it answers, never as a detached PR comment. It says only what the diff cannot show, in under about 100 words: the measured population, why a remedy was not taken, what a deferral is waiting on. Hedge what you did not measure. Your own checks and process stay out of it.
   - A reply that would only say "done" is a `+1` reaction instead: `gh api --method POST "repos/$R/pulls/comments/<id>/reactions" -f content=+1`.
   - A reply to an automated reviewer's finding may post directly. A reply to a person is shown to the user first, unless they said to handle the replies.
   ```bash
   LC_ALL=C grep -n "$(printf '\342\200\224')" "$S"/reply*.md     # must print nothing: no em dashes
   gh api --method POST "repos/$R/pulls/$N/comments/<id>/replies" -F body=@"$S/reply1.md" --jq .html_url
   gh pr edit "$N" --repo "$R" --add-reviewer <login>
   ```
   An automated reviewer is re-triggered the way it documents, often a mention comment. Then wait for it and for every check, read as states rather than a rollup: `gh pr checks "$N" --repo "$R" --watch`. Pending is not a pass, and a check that reported no result is not a pass. Your own push expires your thread count: after the reviewers have had time to answer the new head, repeat stage 2 before calling the round closed.

9. **Report readiness, and merge only when told.** Present the Output below and stop. Marking ready (`gh pr ready`) and merging are the user's calls unless they already said otherwise. When told to merge, re-read the head and the checks, then use the method the repository or the user names:
   ```bash
   gh pr merge "$N" --repo "$R" --squash --match-head-commit "<headRefOid>"   # or --merge / --rebase
   ```
   Never `--admin` to get past a required check or review unless the user said so for this PR. `--match-head-commit` refuses if someone pushed after your last read.

10. **Read the merge back, and pay what it owes.**
    ```bash
    gh pr view "$N" --repo "$R" --json state,mergeCommit,mergedAt
    git -C "$W" fetch origin && git -C "$W" merge-base --is-ancestor <mergeCommit> origin/<base> && echo "on the base"
    ```
    Read each child PR from stage 1 (`gh pr view <child> --repo "$R" --json baseRefName,mergeable`) and tell its owner if it now conflicts. Add the week's line to the worklog in the primary knowledge base, and record any mistake that cost real time as a lesson (rule 17), routed as [`docs/kb.md`](../../../docs/kb.md) says: private ones to the primary KB, generic ones proposed for `docs/casebook/` on a fresh YBase branch with its own draft PR. Run `ybase worktrees --repo <repo>` and report this worktree's verdict; `--reap` removes every safe worktree, not just yours, so run it only if the user agrees. Post nothing to the PR about the merge.

## Output

After stage 9, one block per round:

```
PR <url> at head <sha>, base <base>, draft=<yes|no>
Findings: <k> open threads read across body, threads, timeline
  <id> <path:line> <author>  real|stale|remedy-rejected  -> <fixed in sha | replied | deferred: reason>  [population: <n> [M]]
Independent review: <who>, <k> findings, <j> verified and fixed
Tests: failure set vs baseline: <no change | +a -b, listed>   Gates: <pass | pre-existing FAIL: what>
Checks: <name state> ...   Re-requested: <logins>
Needs you: <mark ready | merge | decide on: ...>
```

After stage 10: `Merged <mergeCommit> into <base> at <time>, read back from the PR and the base. Children: <state>. Worklog: <KB file>. Worktree verdict: <keep|reap>.`
