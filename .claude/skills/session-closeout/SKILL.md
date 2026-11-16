---
name: session-closeout
description: Use at the end of a session, after session-scope and session-check, to land the work under each repo's own landing rules, verify it from the remote, write the worklog to the primary knowledge base and the records the rules owe, stop or register what outlives the session, and reap only worktrees that are provably finished.
---

# session-closeout: land the work, record the thread, prune only what is proven

This is the session skill that decides and writes. It enumerates nothing itself: what this session owns comes from [`session-scope`](../session-scope/SKILL.md), whose ownership tiers and write classes are the only vocabulary used here, and how that reconciles against the repo comes from [`session-check`](../session-check/SKILL.md). The order is deliberate: gate on liveness, land, verify from the remote, write the record, dispose of what outlives the session, then prune. Pruning is last because everything before it is what makes a deletion provable. The record stage produces commits too, so it loops back through landing once; budget for that rather than reading it as an interruption.

## When not to use

- Mid-session, to find out where you stand: run `session-check`, which writes nothing.
- To clean up other sessions' worktrees or branches. Ownership is this skill's first filter; a repo-wide sweep under the name of tidying up after yourself deletes other people's work.
- When the user asked for something other than the repo's landing convention. Their instruction wins; record it in the report.

## Stages

### 0. Gate: is this session safe to close?

Run `session-scope`, then `session-check`. Liveness is settled before the land, because a process still writing into the worktree can put half a change into the commit. Project each owned row's two verdicts:

| Ownership tier | Write class | Verdict |
|---|---|---|
| any | `tree`, `ref` or `lock` | `BLOCKED` |
| any | `unknown` | `BLOCKED`: an unknown write class rounds up to `tree` |
| `unseen` | any | `BLOCKED`: no probe settles it, so a person must |
| `stale`, or a task that has exited | `none` | `REAPABLE`, and a directory only if nothing pins it (`lsof +D`) |
| `registered` or `discovered` | `none` | `SAFE` |

`SAFE` proceeds. `REAPABLE` is disposed of in stage 4, or in stage 5 for a worktree. `BLOCKED` is asked, never decided, and it has three answers, not two: stop it and proceed; let it finish and re-run the closeout; or stop the closeout for now. Offer all three; the middle one is usually right and is the one an agent in a hurry omits.

Until a `BLOCKED` row is resolved, only stage 6 runs. Stage 3 is not exempt because it looks like bookkeeping: it writes files into the same tree the live writer is using.

Whether a row can write is mechanical. Whether its work is worth keeping is not, and for anything not provably finished it is the user's answer. Err toward not stopping: a wrongly stopped long run is unrecoverable, a wrongly kept watcher is a line in the report. A stall with no new output is a reason to ask, never a licence, because a buffered pipe and a dead process look the same from here.

### 1. Land under the repo's own rules

Land each repo the session changed: YBase, or a managed repo whose path `ybase repos path NAME` prints. Read that repo's `AGENTS.md` first; where it states landing rules, they win in that repo ([`docs/rules.md`](../../../docs/rules.md) rule 20). Where it states none, the framework default holds ([`docs/law/push.md`](../../../docs/law/push.md), [`docs/law/pr.md`](../../../docs/law/pr.md)): work on a branch in a worktree (rule 15), land through a reviewed pull request opened as a draft, never force-push, and never push to the default branch unless the user explicitly says to. Only the user marks the PR ready or merges it, unless they said otherwise. The user's `rules.md` in the knowledge base (KB) may relax the default for their own repos.

```bash
"<worktree>/bin/ybase" check                      # YBase work: the worktree's own entry point, before every commit (rule 19)
git -C <worktree> add <paths> && git -C <worktree> commit   # stage named paths, not everything in the tree
git -C <worktree> push -u origin <branch>            # never --force; a rejected push means the remote moved
gh pr create -R <owner>/<repo> --draft --base <base> --head <branch>   # or the forge's equivalent; reuse an existing PR
```

The root `bin/ybase` checks only the main checkout, so YBase work is checked with the worktree's own `bin/ybase` ([`README.md`](../README.md#cross-agent-contract)). A managed repo runs the checks its `AGENTS.md` names, not YBase's.

`<landing>` is the ref `session_inventory.py` and `ybase worktrees --repo <repo>` print, such as `origin/master`; `<base>` is its branch name, `master`. A managed repo's commits, branch names and PR text never mention YBase, its KB or sibling repos (rule 22). Stage named paths: the worktree may hold scratch or another task's files, and a blanket add publishes them (rule 19 treats everything committed as published).

If a push is rejected, fetch and rebase onto the moved branch; do not force. If the branch has drifted far from the landing ref, the landing is still owed: the effort to reconcile is not a reason to report branch-only work as delivered. When the profile's scratch is not durable and the worktree is flagged `EPHEMERAL`, the push is also what saves the work, so do it even if the PR must wait.

Without a forge CLI, push the branch and give the user the compare URL; the PR is then a gap in the report, not a claim.

### 2. Verify from the remote

```bash
git -C <worktree> fetch origin
git -C <worktree> rev-parse HEAD origin/<branch>                 # the two must match
git -C <worktree> diff --stat <landing>...origin/<branch>        # the file count you meant to land
gh pr view <branch> -R <owner>/<repo> --json state,isDraft,headRefOid,url   # draft, open, at that commit
```

The push output is not evidence, and neither is your own commit ([`docs/rules.md`](../../../docs/rules.md) rule 5). Ask what landed, not whether it landed: compare the file count in the remote diff with the files you meant to commit, because a rebase can drop a file with no conflict to read, and a content check finds only what you thought to look for. A push that prints "Everything up-to-date" when you expected a change means your commit is not where you think. After a rebase, run the repo's checks again: another session's commit can change what the checks require between your last local run and the push.

A draft PR is in flight, not landed. Report it as such, with its URL and head commit.

### 3. Write the record

In this order, so the item that holds the thread is written first:

1. **The board.** If the session worked on a KB research topic with a `projects` stage, update each touched row under `<kb>/research/<topic>/projects/`, and fill the experiment record for any run: results, then conclusions ([`templates/research-topic/PIPELINE.md`](../../../templates/research-topic/PIPELINE.md#projects)). A task whose state moved and whose row did not is invisible work. Repo work has no board; skip to item 2.
2. **What the rules already owe**, which is `session-check`'s `OWED` list. Your own mistakes become lessons unprompted (rule 17), routed as [`docs/kb.md`](../../../docs/kb.md) says: a lesson that names anything private goes to the primary KB's `memory/<repo>/`, with its line in `memory/INDEX.md`; a generic one is proposed for [`docs/casebook/`](../../../docs/casebook/README.md) in the entry shape there. Search first and extend an existing lesson rather than adding a near-duplicate. A correction reaches every site that asserts the old claim (rule 6), not only the file you were reading. A tested opportunity gets its status ([`docs/flows.md`](../../../docs/flows.md), "Analyze a run").
3. **The worklog entry, last.** Append to `<primary KB>/worklog/<ISO week>.md` (`ybase kb` lists the primary first; the week is the one `session-check` printed; create the file with its `# YYYY-Www` heading if absent), dated, saying what changed, why, and which branch or PR carries it, per [`templates/kb/worklog/README.md`](../../../templates/kb/worklog/README.md). Append only: a superseded entry earns a later entry, never an edit. Link rules and lessons; do not restate them. The entry is private, so it may name repos; nothing from it is copied into a repo.

Writes into a KB are not commits on the work branch. The local KB is gitignored; a KB inside another repo follows that repo's own `AGENTS.md`, and YBase never commits or pushes there on its own. A casebook proposal or an erratum in a repo is a commit on the work branch: go back through stages 1 and 2 for it, same branch, same draft PR, verified again from the remote.

### 4. Register or stop everything that outlives the session

Every live task, process, scheduled wake-up and remote job ends this stage either registered or stopped. Nothing stays `discovered`.

- **Registered** means a durable record names it and says what it is for: an experiment record, a board row, or the worklog entry. That is what lets the next session find it without this probe.
- **Stopped** means stopped at the layer that owns it and then read back. An acknowledged cancel is not a stopped job.

By kind:

- **Harness rows.** Claude Code: stop background shells and monitors with the harness's stop tool (`TaskStop` or similar), and delete or register each scheduled wake-up; a wake-up that fires into a session nobody reads is the same leak as an unrecorded run. Codex: no harness listing is available, so this reduces to the process rows below.
- **Processes.** Stop only a process this session provably owns: the env join matched, or the harness returned its id to this conversation. Otherwise report it and ask. Read back with `kill -0 <pid>`, which fails once the process is gone. A stopped (`T`) process does not act on SIGTERM until it is continued: send `kill -CONT <pid>` after the TERM. Never stop by command name; a peer's process can share it.
- **Remote jobs.** Registering is always safe. Stopping needs proof this session submitted it, or the user.
- **Scratch.** Remove the files you created under the profile scratch (`ybase env` prints the path), identified by what you made this session, never by a name pattern, which can match a peer's files. Check `lsof +D <dir>` first; a held file makes the delete fail or defer.

### 5. Reap only what is provably finished

```bash
ybase worktrees --repo <repo>   # each repo the session changed; read every verdict and reason first
```

A worktree is a candidate only if this session owns it, and it is reaped only on verdict `reap`: no uncommitted or untracked files, nothing on no remote unless it landed, not locked, not in use, idle past `--idle-days` (default 1). A worktree you used today therefore reads `keep` with a `recent:` reason. For a worktree this session owns and has finished with, read it again with `ybase worktrees --repo <repo> --idle-days 0`; recency is the one reason your own ownership answers, and only for your own rows. `--reap` acts on every `reap` row in the repository, not only yours, and removes with `git worktree remove` (never `--force`) and deletes a branch only with `git branch -d`, which refuses an unmerged one. So:

- If every `reap` row is this session's, run `ybase worktrees --repo <repo> --reap`, with the same `--idle-days` you read with, and read back with `ybase worktrees --repo <repo>`.
- If any `reap` row belongs to someone else, do not run `--reap`. Remove your own with the two commands it uses, `git -C <repo> worktree remove <path>` then `git -C <repo> branch -d <branch>`, and list the others for the user.

**Your own worktree reads `keep` while you stand in it**, because the harness's process is inside it. Do not remove the directory you are standing in: the session loses its working directory and every later command fails. Leave it first. Claude Code, for a worktree the harness entered: `ExitWorktree` with remove, once nothing but you keeps its verdict at `keep`. Codex, or any other worktree: `cd` back to the YBase root, re-run `ybase worktrees --repo <repo>`, and reap from there. A worktree whose draft PR is still under review loses nothing on removal, since the branch is on the remote and `git worktree add <path> <branch>` restores it; still, offer the choice rather than make it, because review fixes need a worktree. A `keep` verdict vetoes every other signal.

### 6. Report

Run even when stage 0 blocked everything else. Report only what you read back, not what you ran.

## Output

```
GATE        SAFE | BLOCKED (each row, its two verdicts, and the three choices offered)
LANDED      branch, remote tip, file count, PR URL and state (draft), or "not landed: <why>"
RECORD      board rows, lessons (KB path or casebook commit), errata sites and the worklog
            entry written, each with its file or commit
REGISTERED  what outlives the session and the record that names it
STOPPED     what was stopped, and how the stop was read back
REAPED      worktrees and branches removed; KEPT ones with their verdict reason
STILL LIVE  everything still running after this session ends, remote jobs and wake-ups
            included
NEXT        what the next session should pick up, and the board row or worklog entry it
            comes from; or "board is silent"
SKIPPED     anything deliberately not done, and why
```

A closeout that reports only its successes leaves the next session to discover the rest; `STILL LIVE`, `NEXT` and `SKIPPED` are the lines a reader cannot reconstruct.
