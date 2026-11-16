---
name: git-forward
description: Use when asked to bring YBase or a managed repo forward and land whatever work never made it, or after several parallel sessions, to find every uncommitted, unpushed, untracked or stashed change that the landing branch does not have and decide what to do with each.
---

# git-forward: pull the checkout up, then find what never landed

Parallel sessions leave work behind in places nobody remembers: an edit never committed, a commit never pushed, a new file never added, a stash nobody popped. This skill fetches, sweeps every worktree of the repository with `ybase worktrees --findings`, and judges each finding against the landing refs **by content**, so a renamed file or a rebased commit is not reported as lost. Git can say whether content is on a landing ref; it cannot say whether work is worth keeping, stale or fresh, or which of two drafts wins. Those calls are yours, made one finding at a time and recorded with a reason. The skill never deletes anything and never commits a file without an owner.

## When not to use

- To remove worktrees that are safe to remove: that is [`cleanup-worktrees`](../cleanup-worktrees/SKILL.md). Run this skill first when that sweep keeps trees for uncommitted or untracked work, since this one says whether that work is new.
- To close out your own session's single worktree: that is [`session-closeout`](../session-closeout/SKILL.md).
- To land a change you already know about: work on a branch, open a draft pull request as in `session-closeout` stage 1, and take it through review with [`land-pr`](../land-pr/SKILL.md).

## Stages

1. **Fix the universe.** Decide which repository: YBase by default, or a managed repo by its name in `ybase repos`. Read that repo's `AGENTS.md` before anything lands; where it states landing rules, they win there ([`docs/rules.md`](../../../docs/rules.md) rule 20). Then decide which refs count as landed. The default is the remote's default branch; if work also lands on another branch, pass each with its own `--landing`, and pass the default too, since any `--landing` replaces it:
   ```bash
   eval "$(ybase env)"
   repo=$(ybase repos path <name>)    # a managed repo; for YBase itself, repo=$(pwd)
   land=$(git -C "$repo" symbolic-ref -q --short refs/remotes/origin/HEAD || echo origin/master)
   git -C "$repo" branch -r            # does work land anywhere besides "$land"?
   ```
   Run from the YBase root and reach the repo by path, never by `cd` (rule 23). Guards against: grading against one branch when work also lands on another, which reports landed work as stranded.

2. **Forward the checkout.** Fetch, then move the main checkout only by fast-forward, only when it is on the default branch and clean:
   ```bash
   git -C "$repo" fetch --prune origin
   main=$(git -C "$repo" worktree list --porcelain | sed -n 's/^worktree //p' | head -n 1)
   git -C "$main" rev-parse --abbrev-ref HEAD      # must print ${land#origin/}
   git -C "$main" status --porcelain | head -n 5   # must print nothing
   git -C "$main" merge --ff-only "$land"          # only when both hold
   ```
   Pass `--repo "$repo"` to every sweep below. A main checkout that is on another branch, dirty or diverged is a finding to report, not something to fix here. Never reset, rebase or force anything. Guards against: a stale landing ref, which makes landed work look unlanded.

3. **Sweep.** Save the report in scratch, then read it:
   ```bash
   ybase worktrees --repo "$repo" --findings --landing "$land" --json > "$TMPDIR/forward.json"
   ybase worktrees --repo "$repo" --findings --landing "$land"
   ```
   On a network filesystem a large tree can take minutes per `git status`. Run it in the background (Claude Code: `run_in_background`; Codex: `nohup ... &` and wait for the file) rather than under a short timeout. Read the header first: a `NOT CHECKED` line names what the sweep could not see. Guards against: spot-checking only the trees you remember.

4. **Read each tree before its files.** For each worktree, note `behind` (commits on the landing ref it lacks) and its unlanded commits. A tree with hundreds of findings, far behind, with no unlanded commits, is almost always one stale snapshot: its findings sort into `landed` and `superseded`, and only a few need eyes. Skip any tree marked `current` or in use: its findings are a live session's work in flight. Report it as live and unread, not as clean.

5. **Adjudicate by verdict.** The tool's verdicts, and what each asks of you:

   | Verdict | Means | Your move |
   |---|---|---|
   | `landed` | identical content at this path | nothing |
   | `superseded` | identical content at another path, or an older version of this path | read the evidence line, then nothing |
   | `removed-on-landing` | the landing ref deleted or moved this path | `git log -1 <ref> -- <path>`; usually on purpose |
   | `differs` | the landing ref has this path with other content | `git -C <worktree> diff <ref> -- <path>` and decide which lines are newer |
   | `novel` | neither path nor content is on any landing ref | read it |
   | `unknown` | the content could not be read | fix the cause and re-run |

   Read only the last four. Where the question is "which draft is better", open both and diff them. If many trees need reading, Claude Code can send one read-only subagent per worktree, naming the **absolute** worktree path in each brief, since a subagent inherits your directory and not your reasoning; in Codex, read them one after another. Recording stays with you.

6. **Decide, one line each.** Use a closed set of dispositions, each with a reason:

   | Disposition | Means |
   |---|---|
   | `land` | real work; land it as it stands |
   | `condense` | worth keeping in a smaller form the reason names |
   | `superseded-in-substance` | already on the landing ref in other words; the reason cites where |
   | `drop` | nothing to keep |
   | `ask` | needs the person who owns it |

   Key each decision on the finding's `blob` from the JSON, not on the tree. Write the reason about the content, not the tree, so it stays true for every copy of those bytes. On the next run, the same blob is settled and a changed blob is a fresh question. Guards against: a disposition nobody can check later, and a stale `drop` silencing content that has since changed.

7. **Read the unlanded commits.** They come back every run, because a decision about a file does not cover a commit. For each, `git show --stat <sha>`, then judge it like a finding. Compare this run's universe line with the last run's before reusing old verdicts: a tree that was in use last time was skipped, not cleared. A finding a scheduled job owns can settle itself between the sweep and your read; diff it again first.

8. **Land what you judged `land`.** Landing is the last step of the work, so do it rather than asking whether to. Cut a fresh branch from the landing tip with `ybase wt <kind>/<subject> --base "$land"`, adding `--repo <name>` for a managed repo; carry the work across (`git -C <worktree> cherry-pick <sha>` for a commit, a copy for a file); run the repo's checks (in a YBase worktree `$W`, its own `"$W/bin/ybase" check`, since the root `bin/ybase` checks only the main checkout; in a managed repo, the checks its `AGENTS.md` names, not YBase's); then land as the repo's own rules say, and where they say nothing, push and open a draft pull request as in `session-closeout` stage 1. Never push to the default branch unless the repo's rules or the user said to. An untracked file has no message and no author: land it only when its owner is clear or the user says so. In YBase the commit-time leak hook runs before every commit; in any repo, never paste a credential into the report, and never mention YBase, its KB or sibling repos in a managed repo's commits or PR (rule 22). Read the result back from the remote, since a pushed branch is not a landed change.

Shell snippets in skills must never put a digit right after a dollar sign: some skill loaders replace that with the invocation's arguments, and the corrupted line still runs.

## Output

```
git-forward: <repo>   landing <refs>   fetched <yes|no>   main checkout <forwarded|clean, already current|left: why>
universe: <N> worktrees, <K> stashes; skipped live: <list or none>; not checked: <header lines or none>

<worktree path>  (<branch>, behind <B>, unlanded commits <C>)
  <disposition>  <path or sha>  blob <sha12>  -- <reason about the content>
  ...
stash <ref>  <message>
  <disposition>  <path>  blob <sha12>  -- <reason>

landed: <branch -> draft PR url> for each `land`, read back from the remote
for the user: every `ask`, and every `drop` they may want to delete by hand
```
