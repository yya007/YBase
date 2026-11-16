---
name: consolidate-branch
description: Use when a long-lived branch has diverged too far from the branch it lands on for a plain rebase and its history must be squashed and moved while other sessions keep pushing to it, or when auditing what a finished history rewrite lost and which branches and worktrees still sit on the old history.
---

# consolidate-branch: squash and move a live branch without losing a byte

A branch that is months and hundreds of commits away from the branch it lands on cannot be rebased commit by commit, and its diff against that branch is too large to read. The fix is to reconcile the content once, squash the branch to one commit on the current landing tip, and move the branch's ref there. The whole difficulty is that the branch stays live: other sessions push to it while you work, and a rewrite that misses one of their commits loses it silently. So this skill does every piece of content work before the rewrite, as ordinary pushes nobody has to notice, and keeps the rewrite itself to one force-with-lease on the branch's own ref, with a content proof before it and an audit after it. It never rewrites the default branch, never force-pushes without the user's explicit say-so, and never deletes the archive refs it creates.

## When not to use

- When `git rebase <base>` works. The machinery here buys safety against concurrent writers and costs a rehearsal; a branch nobody else pushes to needs neither.
- To land a branch. Landing goes through a draft pull request, as in [`session-closeout`](../session-closeout/SKILL.md) stage 1, and a squash here does not replace review there.
- To rewrite the default branch, or any branch you do not own. A pushed branch belongs to whoever pushes to it; a rewrite of it is theirs to run.
- To find unlanded work across worktrees: that is [`git-forward`](../git-forward/SKILL.md). Stage 5 below sends you there for trees left on the old history.

## Stages

1. **Fix the names.** Write down the repo (YBase, or a managed repo by its name in `ybase repos`), the branch, the base it lands on, and the remote, resolved by URL rather than by the name `origin`, since two checkouts of one repository routinely name the same remote differently. Read the repo's `AGENTS.md` first: where it forbids history rewrites or states its own landing rules, they win, and this skill stops ([`docs/rules.md`](../../../docs/rules.md) rule 20). Do the work in a fresh worktree; never in a checkout another session reads. Stay in YBase and reach the worktree by path (rule 23):
   ```bash
   eval "$(ybase env)"
   branch=<long-lived branch>; base=<branch it lands on>
   repo=$(ybase repos path <name>)        # for YBase itself, repo=$(pwd) and drop --repo below
   git -C "$repo" fetch --prune origin
   ybase wt chore/consolidate-branch --repo <name> --base origin/"$branch"
   wt=<the worktree path it printed>
   ```
   The snippets say `origin`; substitute the name `git -C "$wt" remote -v` gives for the URL you mean. Then confirm the base is not the branch you are about to rewrite: `git -C "$wt" symbolic-ref -q --short refs/remotes/origin/HEAD` must not print `origin/$branch`. If the repository uses a sparse checkout, read `git -C "$wt" sparse-checkout list` back: a sparse worktree silently drops every out-of-cone file from a commit, so the reconcile worktree must be full. Guards against: rewriting the wrong ref, or committing a tree with files missing.

2. **Reconcile without rewriting.** Merge the base into the branch, in the worktree, and resolve conflicts by absorbing both sides rather than picking one: months of divergence means both sides fixed things, and a clean merge cannot see a default that moved.
   ```bash
   git -C "$wt" merge origin/"$base"          # resolve, then run the repository's checks
   "$wt/bin/ybase" check                  # YBase: the worktree's own entry point; a managed repo runs the checks its AGENTS.md names
   git -C "$wt" push origin HEAD:refs/heads/"$branch"    # a plain push, never --force
   ```
   The root `bin/ybase` checks only the main checkout, never this worktree ([`README.md`](../README.md#cross-agent-contract)). This push is an ordinary fast-forward, so every other session is unaffected, and the step is interruptible and repeatable: if the base or the branch moves, merge again. When it is done the branch's tree already equals what the squash will carry, and the only thing left to change is history. Guards against: discovering a conflict after the rewrite, when there is no non-destructive way back.

3. **Announce and freeze.** Tell every session or person that pushes to the branch that it will be rewritten, name the window, and ask them to push what they have and stop. The freeze is short because stage 2 did the content work. Pushes that arrive anyway are not lost: stage 4 reads the tip fresh and leases on it. Record who was told and when, for the report.

4. **Cut over.** Read the tip fresh, archive it on the remote before anything is rewritten, build the squash commit from that tip's tree, prove it is content-identical, and only then push with a lease on exactly the tip you archived:
   ```bash
   git -C "$wt" fetch origin
   old=$(git -C "$wt" rev-parse origin/"$branch")
   archive=refs/archive/"$branch"-$(date -u +%Y%m%d)
   git -C "$wt" push origin "$old":"$archive"            # the pre-rewrite tip, kept forever
   git -C "$wt" ls-remote origin "$archive"               # read it back; must print $old
   new=$(git -C "$wt" commit-tree "$old"^{tree} -p "$(git -C "$wt" rev-parse origin/"$base")" \
         -m "Consolidate $branch onto $base (squash of $(git -C "$wt" rev-list --count origin/"$base".."$old") commits; pre-rewrite tip at $archive)")
   git -C "$wt" diff --quiet "$old" "$new" && echo "content identical" || echo "STOP: the squash changed content"
   ```
   `git diff <old-tip> <new-tip>` must be empty, because a squash changes history and never content. If it is not empty, something besides the squash happened (a sparse checkout, a stale `old`, a wrong `-p`); stop and find it. Then, **only with the user's explicit say-so for this push, and only on the branch's own ref**:
   ```bash
   git -C "$wt" push --force-with-lease="$branch":"$old" origin "$new":refs/heads/"$branch"
   git -C "$wt" ls-remote origin refs/heads/"$branch"     # must print $new
   ```
   The lease names the exact tip you archived, so a commit that arrived after your read rejects the push instead of being overwritten; a bare `--force` would overwrite it silently. On a rejected lease, make one fresh pass from the top of this stage (new `old`, new archive, new squash); never retry in a loop, since a retry can only re-push what it computed from stale state. Never run this against the default branch, and never without the user saying yes to this push in this conversation. The landing convention's "never force-push" ([`session-closeout`](../session-closeout/SKILL.md) stage 1) stands everywhere else.

5. **Audit against the old tip, by content.** After a squash, the merge-base between the new history and any other branch collapses to the base, so `git diff <new-tip>...<other>` bills the whole rewrite to every branch it is asked about. Every question after the rewrite is therefore asked against the archived old tip:
   ```bash
   git -C "$wt" fetch origin "+$archive:$archive"
   git -C "$wt" diff --stat "$archive" origin/"$branch"   # must print nothing
   for b in $(git -C "$wt" for-each-ref --format='%(refname:short)' refs/remotes/origin); do
     mb=$(git -C "$wt" merge-base "$archive" "$b" 2>/dev/null) || continue
     git -C "$wt" merge-base --is-ancestor "$mb" origin/"$base" && continue   # forks from the base; unaffected
     echo "$b: $(git -C "$wt" rev-list --count "$archive".."$b") commits not in the old tip"
   done
   ```
   A branch whose merge-base with the old tip lies on the base never touched the rewritten history and needs nothing. The loop prints the rest.
   A branch with zero commits beyond the old tip was a copy of the branch and can simply be reset by its owner. A branch with commits the old tip never had holds real work that the squash cannot contain; each needs a decision, and since rebasing a pushed branch rewrites it, the decision is its owner's (`git rebase --onto origin/$branch $archive <their-branch>` is the usual move, run by them). For local worktrees left on the old history, let the tool judge content rather than ancestry: `ybase worktrees --repo "$repo" --findings --landing origin/$branch` reports a tree that holds nothing new as `landed` or `superseded`, and names `differs` or `novel` work for [`git-forward`](../git-forward/SKILL.md). A line absent from the new tip is equally a rename or a rewrite; compare blobs per file before calling it a loss.

6. **Keep the archive refs.** They are the only instrument that can grade a branch after the rewrite, which is a use beyond recovery. Read the final state back from the remote, not from the push output, and report it.

Shell snippets in skills must never put a digit right after a dollar sign: some skill loaders replace that with the invocation's arguments, and the corrupted line still runs.

## Output

```
consolidate-branch: <repo> <branch> onto <base>   remote <url>
reconcile: merged <base tip sha> into <branch>, pushed as <sha>, checks <pass|fail>
freeze: told <who> at <time>; pushes during the window: <N or none>
cutover: old tip <sha> archived at <ref> (read back: yes); new tip <sha>; diff old..new: empty
         force-with-lease: <pushed with the user's yes at <time> | not pushed: why>
audit:   branches on the old history: <name> (<K> commits beyond the old tip, owner <who>) ...
         worktrees on the old history: <path> <landed|superseded|differs|novel> ...
         not checked: <refs the audit could not read, or none>
for the user: every branch owner to contact; every `differs` or `novel` tree (sent to git-forward)
```
