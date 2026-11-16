---
name: session-scope
description: Use when you need to know what this session owns and what each of those things is doing right now, before reporting on it or acting on it; also the definition of the ownership tiers and write classes that session-check and session-closeout use.
---

# session-scope: what this session owns, and what each row is doing

This skill answers one question that both other session skills need answered first: which rows on this machine and in this harness belong to this session, and can each one still change anything. It reads three sides, because no single probe sees all of them: the machine, through `tools/session_inventory.py`; the harness, through its own listings; and the untracked side that is in neither. Every row gets two verdicts, an **ownership tier** and a **write class**, defined below. This file is the only place those words are defined; [`session-check`](../session-check/SKILL.md) and [`session-closeout`](../session-closeout/SKILL.md) link here and never redefine them. The skill writes nothing, stops nothing and decides nothing, which is what makes it safe to run repeatedly.

## When not to use

- To reconcile the session against its records (a research topic's boards, the worklog, lessons): that is `session-check`, which runs this skill first.
- To land, stop, reap or delete anything: that is `session-closeout`.
- To survey every worktree in a repository regardless of owner: run `ybase worktrees [--repo NAME]` directly. That is the repo's namespace, not this session's work.
- To adjudicate a peer session's rows. A peer is never in scope here, at any tier.

## The vocabulary

### Ownership tiers: whose is this row?

| Tier | Means | Example |
|---|---|---|
| `registered` | a durable record names it, so the next session can find it without this probe | the worktree git registered for your branch, a pushed branch with a PR, an experiment record naming a run |
| `discovered` | the machine or harness shows it exists, but nothing durable proves this session owns it | a process whose cwd is inside your worktree, a background task id from your own conversation |
| `stale` | the artifact is there and nothing live is behind it: residue, not work in flight | a worktree with verdict `prune`, scratch files no live process holds, a task that has exited |
| `unseen` | an admitted gap: no probe here can see it | work another machine did on this branch, a Codex background task, a process whose fields could not be read |

**A tier is reported, never dropped.** An inventory that leaves out the row whose owner it cannot prove reports a tidier world than the real one, and the tidier number is the one people act on. Write `unknown` and count it in `GAPS`. The mirror holds too: listing residue as `discovered` inflates the in-flight picture, so liveness is probed rather than assumed in either direction.

**A command line never establishes ownership.** A process's argv does not change when its role does, and a probe that matches on a name matches itself. Ownership comes from the worktree you stand in, the branches you committed on, an environment join (stage 1), and ids the harness returned to this conversation.

**The namespace is not your work.** The repository carries other sessions' branches and worktrees. `session_inventory.py` prints the namespace as a count and lists only owned rows, so a count is never read as a work item.

### Write classes: can this row still change anything?

The tier does not say whether ending the session around a row is safe. A monitor tailing a log is live, owned, and harmless; a background job whose cwd is inside your worktree endangers the next land whatever its tier.

| Write class | Means | Example |
|---|---|---|
| `tree` | it can change files in a worktree this session owns | a process with its cwd in the worktree, a subagent holding write tools |
| `ref` | it can move a branch or the landing ref | a push in flight, a script that commits |
| `lock` | it holds something the next writer must wait for | `index.lock`, a paused rebase or merge (`git_ops` in the inventory) |
| `none` | it can be left running with nothing of this session's at risk | a finished task, a read-only watcher whose evidence you can name |
| `unknown` | nothing read here settles which of the above it is | a `discovered` process whose cwd could not be read |

**An unknown write class rounds up to `tree`** for any caller deciding on it. That is the opposite of how a tier is handled, on purpose: an over-cautious write class costs a wait, while an under-cautious one lets a land include a half-written tree.

**`none` is a claim and owes its evidence**, the same as a tier. "It is only a watcher" is an argument about intent; name what you read that shows it cannot write.

**Durability is a third fact, not a class.** When the profile's scratch is not durable (`durable no` in the inventory; on `aws` this is instance-store NVMe), every unpushed commit and untracked file in a worktree on that storage dies with the instance. The inventory flags such worktrees `EPHEMERAL`; carry the flag on the row.

## Stages

### 1. Establish identity

Sessions start in YBase, and the work may sit in YBase or in a managed repo. Run from the YBase root, and name the worktree you are working in with `--repo` (`ybase worktrees --repo NAME` lists a managed repo's worktrees; `ybase repos path NAME` prints its main checkout). Run once per repo the session changed:

```bash
python3 tools/session_inventory.py --repo <worktree>                  # all harnesses
python3 tools/session_inventory.py --repo <worktree> --env-key "CLAUDE_JOB_DIR=$CLAUDE_JOB_DIR"   # Claude Code, when set
python3 tools/session_inventory.py --repo <worktree> --touched <branch>   # repeat for each other branch you committed on
```

Exit 2 means the path is not a checkout. Stop there: an empty inventory reads like a quiet session, and nothing downstream can be attributed.

The `--env-key` join is what lets a detached process be tied to this session rather than merely to a directory. Claude Code sets `CLAUDE_JOB_DIR` in the environment of the shells it starts, and their children inherit it. A subagent that runs as its own child session gets its own `CLAUDE_JOB_DIR`, so the parent's join does not cover it: run the inventory again with its value, or count it from the harness side in stage 3. Codex sets no per-session marker this skill knows of, so on Codex omit the flag; processes are then joined by cwd only, and the inventory says so in `GAPS`. The join needs `/proc`, so on macOS it is unavailable on either harness and the same gap line appears.

If `GAPS` says the remote refs are stale or were never fetched, run `git -C <worktree> fetch origin` (it moves only remote-tracking refs) and re-run. "Unpushed" measured against old refs is a guess.

### 2. Read the machine side

Read each section, not the summary line:

- **IDENTITY**: worktree, branch, upstream with ahead and behind, landing ref. Behind is not your problem yet; ahead is work that exists only here.
- **PROFILE**: profile name, scratch path (the same as `ybase env` prints), `durable yes|no`, and the scratch footprint.
- **WORKTREES**: the verdicts come straight from `ybase worktrees --repo <repo> --json` (`keep`, `reap`, `prune`, `main`, with the reason), plus `git_ops` and `EPHEMERAL`. Its `in use by N process(es)` count includes the harness standing in the worktree, so your own worktree always reads `keep` while you are in it; that is correct, not a finding.
- **BRANCHES**: the namespace count, then each owned branch with its commits on no remote and where it is checked out. An owned branch with unpushed commits and no worktree is the easiest work to lose.
- **PROCESSES**: processes of your unix user whose cwd is inside a worktree of this repository or the scratch, or that match `--env-key`. This process and its ancestors (the harness) are left out. `detached` means its parent is pid 1, the signature of a backgrounded shell that outlived its starter; a subreaper can stand in for pid 1, so the cwd and env join decide, not the ppid.

### 3. Ask the harness: the side no process probe attributes

A subagent, a background task, a monitor and a scheduled wake-up are rows in the harness's own store. The inventory cannot attribute them, and its `GAPS` says so.

- **Claude Code**: list background shells and monitors with the harness's task listing (`TaskList` and similar), scheduled wake-ups with its schedule listing where the harness has one, and subagents from their completion notices. A listing may cover only one of those registries, and an empty answer from the wrong one is worded exactly like a quiet session, so name the tool you asked beside each registry. Every background start returned an id into this conversation; any such id that no listing shows is settled by reading its output or by finding its process, never by its absence.
- **Codex**: no listing of background work is available to this skill. Write `HARNESS unseen: no harness listing on Codex` and rely on the PROCESSES section and on what you remember starting.

If a listing tool exists but is unavailable in this session, that is an `unseen` line naming it.

### 4. Name the untracked side

A command started with `nohup ... &` or `... &` inside a shell call is tracked by no harness listing. If its cwd is inside your worktree or scratch, PROCESSES already shows it. If its cwd is elsewhere and there was no env join, nothing above sees it. Sweep by structure, then read names:

```bash
ps -U "$(id -u)" -o pid= -o ppid= -o stat= -o command= | awk -v col=2 '$col == 1'
```

The awk column is a variable on purpose: a dollar sign followed by a digit in a skill can be replaced with the invocation's arguments before the shell sees it.

Two traps. Never `pgrep -f <pattern>` for something whose command line contains the pattern: the probe matches itself, and a by-name search only finds what you already suspected. And a process in state `T` (stopped, for example by Ctrl+Z) executes nothing, holds every descriptor it had, and does not act on SIGTERM until continued; list them with `ps -U "$(id -u)" -o stat= -o pid= -o command= | grep '^T'`.

**Owning a directory and pinning it are different questions.** A process can hold an open file inside your worktree or scratch without its cwd being there, and that is what makes a later delete fail. Before anyone deletes a directory, ask who holds it: `lsof +D <dir>`. This is slow on a large tree and sees only your own user's processes; say so when you rely on its empty answer.

### 5. Adjudicate every row twice

For each row from stages 2 to 4, write its tier and its write class from the tables above, with the evidence for each. Common mappings:

| Row | Tier | Write class |
|---|---|---|
| the worktree you stand in (git's registration names it) | `registered` | `lock` if `git_ops` is non-empty, `tree` if another process has its cwd there, else `none` |
| an owned branch with commits on no remote | `discovered`, and `EPHEMERAL` if its worktree is | `none`; the risk is loss, carried by the durability flag |
| a process placed in your worktree | `discovered` (an env match proves ownership but is not a durable record) | `tree` |
| a harness task whose output shows it exited | `stale` | `none` |
| a harness id no listing shows and no process matches | `unseen` | `unknown` |
| a worktree with verdict `prune` | `stale` | `none` |

### 6. Measure the footprint

Report the scratch footprint from PROFILE, and anything you created outside the profile scratch, which `docs/rules.md` rule 16 says should be nothing. Measure only your own. Removing any of it is `session-closeout`'s job.

## Output

```
IDENTITY   repo, worktree, branch, upstream (ahead/behind), landing ref, profile,
           durable yes|no, and the ownership join used (env key, or cwd only)
OWNED      one row per owned thing: kind, id or path, tier, write class, evidence,
           EPHEMERAL where it applies
HARNESS    each registry by name, the tool asked, and every live id; or `unseen: <why>`
UNTRACKED  detached or stopped processes and directory pins, with both verdicts
FOOTPRINT  scratch files and bytes, durability, anything outside the scratch
GAPS       the inventory's GAPS lines, plus every `unseen` row and every `unknown`
           write class, by section
```

`GAPS` is never empty. At minimum it says what the harness side could not list, that other machines may hold work on the same branches, and how many rows carry an `unknown` write class.
