# Codex: what changes when Claude Code's hooks cannot see you

Read this after the files [`AGENTS.md`](../AGENTS.md) names. Those carry the rules. This file says only what changes when the agent running them is Codex, or any agent other than Claude Code. It adds no rule of its own.

## TL;DR

- Claude Code enforces some rules with hooks under `.claude/hooks/`. Codex runs one of them, the allow gate, which is off unless `YBASE_ALLOW_GATE=1`. Every other guard is a rule you hold yourself.
- Git hooks do bind you: `.githooks/pre-commit` runs the check registry on every commit once `ybase doctor` has enabled it in the clone.
- Skills are the same files for both agents. Find them through `.agents/skills`; invoke one as `$name`.
- Read the law file for each moment yourself before the act, since no hook will show it to you.
- Do not add a second `CLAUDE.md`. Report what you touched and what you did not do.

## Which guards Codex runs

`.codex/hooks.json` wires one hook for Codex: the allow gate (`.claude/hooks/allow-gate.py`). Codex sets no `CLAUDE_PROJECT_DIR`, so the wiring finds the gate from the git toplevel of the working directory; outside YBase it finds none and allows the call without a word. It is off unless `YBASE_ALLOW_GATE=1` is in the environment or in `.env`; off, it prints nothing and Codex asks as usual. When on, it splits a compound shell command into parts and approves the command when every part matches an allow rule in the Claude Code settings files, `.claude/settings.json` among them; otherwise Codex asks as usual. It refuses nothing. The tracked `.claude/settings.json` lists `pwd`, `ls`, `wc`, `which`, the exact forms of `git status`, `git diff`, `git log` and `git show`, `git rev-parse`, `git ls-files`, `git branch --show-current`, `git remote -v`, and the project's own check and listing commands. The gate's command parsing is best-effort and has known gaps: a command substitution hidden by quoting, a function definition, zsh process substitution and glob qualifiers, and input redirection from a network pseudo-device such as `/dev/tcp/...`. Through these an approved command can run a program that no rule lists or reach the network. It is a convenience for commands you would be content to run unprompted, not a security boundary ([ADR 0003](adr/0003-allow-gate-is-opt-in.md)). Broader approvals go in your own `.claude/settings.local.json`, which is never committed.

Every other hook under `.claude/hooks/` fires only on Claude Code's tool calls, so none of them sees yours. Hold yourself to the rules they enforce:

| Rule | Where it is written | What the Claude Code hook refuses |
|---|---|---|
| Never write to a path listed in `.claude/file-guard`, such as `.env` or a key file | this file | a Write or Edit on a matching path (`file-guard`) |
| Never scan the filesystem from a root: no `find`, `grep -r`, `rg` or `du` over `/`, a mount point or a home folder; search the repo or the one folder that holds the answer | this file | a recursive walk rooted outside the repo |
| Never match a process with a pattern that matches the probe itself | [`law/watch.md`](law/watch.md) | a `pgrep -f` or `pkill -f` whose pattern matches the command running it (a `ps` piped to `grep` is not seen; hold that rule yourself) |
| Under zsh, split an expansion on purpose or quote it: `for x in $VAR` and `set -- $VAR` pass one item | this file | a bare `$VAR` in a `for` list or after `set --` when the shell is zsh |
| Run project Python on an interpreter that meets the `requires-python` floor; `tools/pick_python.sh --for-path .` names one | this file | `python3 -m pytest`, `-m unittest`, `-c` or a script on an interpreter below the floor of the nearest `pyproject.toml` |
| Run `ybase check` before every commit; everything committed is published ([rule 19](rules.md#publishing)) | [`law/commit.md`](law/commit.md) | a commit or PR text with a leak the `leaks` check would name |
| Write only in your own worktree; the main checkout is read-only ([rule 15](rules.md#working)) | [`law/worktree.md`](law/worktree.md) | a write under the main checkout, only when `YBASE_GUARD_READONLY_CHECKOUT=1` |
| Open every PR as a draft; only the user marks it ready or merges | [`law/pr.md`](law/pr.md) | `gh pr create` without `--draft`, and `gh pr ready`, only when `YBASE_GUARD_PR_DRAFT=1` |

The last two guards are opt-in and ship off. Their rules stand whether or not the guard is on: the guard only enforces them.

A wide filesystem scan gets its own line because it hurts other people. A shared filesystem has a throughput limit for everyone on it, and a recursive walk from its root spends that limit for the whole machine or fleet. If a root is unavoidable, bound the depth (`-maxdepth 3`) and stay on one device (`-xdev`). Ask the interpreter where a package lives rather than walking for it.

## The git hooks do bind you

`.githooks/pre-commit` belongs to git, not to a harness. It runs `tools/checks.py`, the one declaration of every check, on each commit in any clone where `ybase doctor` has set `core.hooksPath`. Run `ybase doctor` once in a fresh clone, then let the hook gate you. Never pass `--no-verify`. If a check is wrong, fix the check in the same change and say so.

Never run a bare `git stash`. The stash is shared by every worktree of the clone, and a pop can take another session's work.

## One instruction source and one skill tree

`AGENTS.md` is the instruction source both agents share. Claude Code reaches it through `CLAUDE.md`, which imports it with the rest of the chain. Codex reads `AGENTS.md` itself, follows none of those imports, and follows the numbered reading list in that file instead.

Do not add another `CLAUDE.md`, at the root or anywhere below it. Claude Code joins memory files from every parent folder, so a second one loads the same text twice, and a Codex session never reads it at all.

Skills have one editable home, `.claude/skills/`. Codex finds them through `.agents/skills`, a tracked symlink to that folder. Edit or add a skill there and both agents see it; never write a `SKILL.md` under `.agents/skills/`. Invoke a skill as `/name` in Claude Code and `$name` in Codex. Where a skill names a Claude Code tool such as a subagent, it also gives the Codex path or says the step is unavailable; take that path.

## The law for a moment is a file you read before the moment

Claude Code sessions see `docs/law/<moment>.md` the first time they run a matching command, because the moment hook shows it to them. You run without that hook, so read the file yourself before the act:

- before `git commit`, with or without `--amend`, and before a rebase or cherry-pick: [`law/commit.md`](law/commit.md)
- before `git push`, or landing a branch: [`law/push.md`](law/push.md)
- before `git worktree add`, `remove` or `prune`, `ybase wt` or `ybase worktrees --reap`: [`law/worktree.md`](law/worktree.md)
- before `gh pr create`, `edit`, `ready`, `merge` or `close`: [`law/pr.md`](law/pr.md)
- before `gh pr review`, `gh pr comment` or a review call through `gh api`: [`law/review.md`](law/review.md)
- before handing work to a subagent or another agent: [`law/delegate.md`](law/delegate.md)
- before `sleep`, `until`, `while`, `wait`, `timeout`, `watch` or `tail -f`, or any poller you leave on a job: [`law/watch.md`](law/watch.md)
- before writing or changing anything under `tools/`, `tests/` or `.githooks/`, and before a hook under `.claude/hooks/`: [`law/checks.md`](law/checks.md)
- before writing under YBase's `docs/`, or under `research/`, `memory/` or `worklog/` in a knowledge base: [`law/docs.md`](law/docs.md)

This list names the same moments as the table in [`law/README.md`](law/README.md) and the registry in the moment hook. When one changes, change all three in one commit.

## Run Claude Code and Codex in parallel by worktree

The agent brand is not the isolation boundary; the worktree and the branch are. Give each concurrent agent its own worktree (`ybase wt <kind>/<subject> [--repo NAME]`) and keep one unit of work on one branch. Two agents in one worktree share one index whatever harness they run under, so explicit pathspecs cannot stop one from committing a file the other changed between calls. Never infer that an existing worktree is yours from its name. A brief names the absolute path, or you create a new one.

## Give Codex write access to the places work happens

Codex's `workspace-write` sandbox allows writes only inside the folder the session started in, and it has no network. A session started in YBase can then read a managed repo but cannot fetch into it or create a worktree for it: `ybase wt <kind>/<subject> --repo NAME` fails with `Operation not permitted`. Start Codex with the worktree folder and the repo's `.git` folder as extra writable folders:

```bash
codex --add-dir <worktree folder> --add-dir <path of the managed repo>/.git
```

The worktree folder is `<path of the managed repo>/.worktrees` unless `.ybase/MACHINE.md` names another, and `.ybase/REPOS.md` names each repo's path. Git records a new worktree, and every commit made in it, inside the repo's `.git` folder. Name that folder itself: Codex keeps the `.git` folder of any writable folder read-only, so adding the repo is not enough.

> **ERRATUM 2026-11-14.** This section first said to add the path of the managed repo. A trial showed that Codex then still refuses the write under `.git`. Adding the `.git` folder itself was tried and works for creating the worktree and editing in it.

Two limits remain inside the sandbox [M: one trial, Codex CLI 0.165]:

- No network. `ybase wt` cannot fetch, and says it starts from the last fetched tip. A package install fails, so a new worktree has no dependencies. Install them before you start Codex, or run the tests that need them from a session that has network.
- Process listing (`ps`) is refused.

When a command is refused this way, report it and stop; do not look for another place to write.

## Report what you changed, and where

Name the files you touched and the worktree you touched them in, and say plainly what you did not do. Your caller cannot see your tool calls, so an unstated limit reads to them as work you completed. Verify from the surface the reader uses ([rule 5](rules.md#evidence)): the file on disk, the pushed branch, the created PR, never your own output.
