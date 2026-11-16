---
name: cleanup-worktrees
description: Use when linked worktrees have piled up in YBase or a managed repo and no session owns their cleanup, for example when worktree commands have gone slow, the disk is short, or after a burst of parallel sessions.
---

# cleanup-worktrees: remove the worktrees no session owns

Every session works in its own worktree, and a session can clean up only the one it owns, which is usually the one it is standing in and so cannot remove. Worktrees therefore outlive their sessions and pile up, until every command that reads the registrations slows down and the disk fills. This skill sweeps them with `ybase worktrees`, which removes a worktree only when every check ran and every check came back clear: nothing uncommitted, nothing untracked, nothing unpushed unless it already landed, not locked, not in use, not recently used. An unknown is a refusal. You read the dry run, resolve the refusals you can, show the user what would go, and reap only on their yes. Forcing a removal and deleting a branch stay human acts.

## When not to use

- To clean up after your own session: that is one worktree, and [`session-closeout`](../session-closeout/SKILL.md) owns it.
- To find out whether a kept tree holds real work: that is [`git-forward`](../git-forward/SKILL.md). This skill sends you there.
- To make room in a hurry by forcing removals. A forced removal is a decision per tree, made in Stage 3.

## Stages

1. **Choose the universe.** YBase by default; `--repo NAME` for a managed repo from the repo list, or `--repo PATH` for a clone the list does not name. To cover every managed repo, take the list rather than a directory walk:
   ```bash
   eval "$(ybase env)"
   ybase repos          # name, local path, present or missing
   ```
   A `missing` repo has no clone here and so no worktrees on this machine; say so rather than skip it in silence. Worktrees from `ybase wt --repo NAME` live in that repo's own `.worktrees/` folder unless the profile moves them, and git registers each with its repo, so a sweep by repo finds them wherever they are. `ybase worktrees --all` gives the one-screen view of every repo first. Read a repo's `AGENTS.md` before removing anything in it; where it states rules for worktrees or branches, they win there ([`docs/rules.md`](../../../docs/rules.md) rule 20). The tool exits 2 on a path that is not a repository. Report that; never read an empty sweep as a clean one. Guards against: a backlog in a repo nobody thought to name.

2. **Dry run.** One report per repository, saved in scratch:
   ```bash
   name=<a repo name from Stage 1>; repo=$(ybase repos path "$name")   # for YBase itself, repo=$(pwd)
   ybase worktrees --repo "$repo" --json > "$TMPDIR/worktrees-$(basename "$repo").json"
   ybase worktrees --repo "$repo"
   ```
   Each tree costs a `git status`, which on a network filesystem can take many minutes when the cache is cold. Run a large sweep once, in the background (Claude Code: `run_in_background`; Codex: `nohup ... &` and wait for the file), not repeatedly under a short timeout. If you set a timeout from a measurement, measure on a tree nothing has touched recently, since a warm cache understates it. Read the header before the rows: a `NOT CHECKED` line names processes the scan could not read, which were not checked as holders. A few root-owned login processes are normal; many mean the in-use check is blind.

3. **Read every refusal.** A reason you disagree with is a finding: fix its cause and re-run, never reach past the tool.

   | Reason | What it means | What to do |
   |---|---|---|
   | `locked` | someone ran `git worktree lock` | the lock reason is a message (`git -C "$repo" worktree list --porcelain`); ask its owner |
   | `current` | this command runs inside it | leave it; it is a session's own tree |
   | `in use by N process(es)` | a live process's working directory is inside it | see the note below on orphaned holders |
   | `recent` | git acted in it within `--idle-days` (default 1) | leave it; raise or lower the window only on purpose |
   | `uncommitted` or `untracked` | `git status` is not empty | usually a stale snapshot; see below |
   | `on no remote and not landed` | a commit exists only here | run `git-forward` on it; never reap |
   | `broken` | the directory has no `.git`; a removal stopped part-way | for the user, see below |
   | `could not ...` | a check did not finish | an unknown is never a pass; fix the cause and re-run |

   **Orphaned holders.** A process reparented to init and running for days, such as a forgotten poller, holds a tree forever, so "run again later" never arrives. Check each holder with `ps -o pid,ppid,etime,command -p <pid>` and report the orphans for the user to stop. Check the command again right before anyone acts, because process ids get reused.

   **A dirty tree is usually a stale snapshot.** `git status` compares against the tree's own HEAD, which on an idle tree is far behind, so the tree can look dirty in every file while holding nothing new. Ask the landing ref instead with `ybase worktrees --repo "$repo" --findings`. If every finding is `landed`, `superseded`, or a confirmed `removed-on-landing`, the tree holds nothing new and is a candidate for a forced removal. Any `differs` or `novel` goes to `git-forward` first. A forced removal is the user's call per tree. It discards tracked edits, and untracked files have no branch to come back from, so show the untracked count with the command:
   ```bash
   git -C "$repo" worktree remove --force <path>
   ```
   The tool never forces, and must not be changed to: git's own refusal at removal time is a second, independent check that sees files written after the sweep read the tree.

   **Broken trees and unregistered directories.** No re-run clears a `broken` row: git refuses to remove a tree without its `.git`, even with `--force`. The remedy is for the user to look inside, delete the directory, then run `git worktree prune`. If git had already dropped the registration when the removal stopped, the leftover directory appears under `unregistered` instead. Read it before anyone deletes it, since a parent directory can hold things that were never worktrees.

   **Rows that need no decision.** `prune` means the directory is gone and only the registration remains; `--reap` runs `git worktree prune` for those. A locked registration whose directory is gone, such as one on unmounted storage, is kept. A `reap` row that lists ignored paths will lose them, since `git worktree remove` deletes ignored files with the tree; name them to the user.

4. **Ask, then reap.** Show the user the `reap` and `prune` rows, the ignored paths they carry, and every forced removal you recommend with its counts. Only on their yes:
   ```bash
   ybase worktrees --repo "$repo" --reap
   ```
   The reap recomputes every verdict when it runs, so it acts on the tree as it is then, not on the dry run. It never forces, and it deletes a branch only with `git branch -d`, which refuses one whose commits are not merged; a squash-landed branch therefore stays, and deleting it with `-D` is the user's call. A removed worktree whose branch remains is one `git worktree add` from being back. Run forced removals one at a time, by hand, after the user has named each.

5. **Verify from the surface a reader uses.** The tool's exit status says it finished, not that the trees are gone. It prints `REFUSED` or `INCOMPLETE` for each removal that failed or left a registration or directory behind; read those lines. Then count again:
   ```bash
   git -C "$repo" worktree list | wc -l
   ybase worktrees --repo "$repo" | head -n 1
   ```

## Output

```
cleanup-worktrees: <N> repositories   idle window <D> day(s)
<repo>   before <n> registrations -> after <m>
  removed <k>: <paths>
  pruned <p>: <paths>
  kept, by reason: locked <a>, current <b>, in use <c>, recent <d>, dirty <e>, unlanded <f>, broken <g>, unknown <h>
  not checked: <header lines, or none>
for the user:
  forced removals recommended: <path, untracked count, why nothing is new> or none
  orphaned holders to stop: <pid, command, age> or none
  broken trees and unregistered directories: <paths> or none
  sent to git-forward: <paths with differs, novel or unlanded commits> or none
```
