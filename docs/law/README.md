# docs/law/: the rules that bind at a moment

## TL;DR

- One file per moment an agent can recognize from a command or a path: committing, pushing, taking a worktree, opening a PR, reviewing one, delegating, waiting on a job, writing a check, writing a document.
- Each file holds only the rules that bind at that moment, as imperatives, and links the ground rule it applies by number. It never restates a rule from [`docs/rules.md`](../rules.md).
- In Claude Code, `.claude/hooks/moment_law_hook.py` shows the file the first time a session runs a matching command, then lets the retry through. Once per session per moment.
- Codex and other agents run without that hook. They read the file themselves before the act; [`docs/codex.md`](../codex.md) lists which file goes with which command.

## The moments

| File | Binds when you |
|---|---|
| [`commit.md`](commit.md) | `git commit`, with or without `--amend`; read it before a rebase or cherry-pick too |
| [`push.md`](push.md) | `git push`, or land a branch |
| [`worktree.md`](worktree.md) | `git worktree add`, `remove` or `prune`; `ybase wt`; `ybase worktrees --reap` |
| [`pr.md`](pr.md) | `gh pr create`, `edit`, `ready`, `merge` or `close` |
| [`review.md`](review.md) | `gh pr review`, `gh pr comment`, or a review call through `gh api` |
| [`delegate.md`](delegate.md) | hand work to a subagent or to another agent |
| [`watch.md`](watch.md) | `sleep`, `until`, `while`, `wait`, `timeout`, `watch` or `tail -f`: any poller or wait on a job or a background command |
| [`checks.md`](checks.md) | write or change anything under `tools/`, `tests/`, `.githooks/` or `.claude/hooks/` |
| [`docs.md`](docs.md) | write under YBase's `docs/`, or under `research/`, `memory/` or `worklog/` in a knowledge base |

## What belongs here

A rule whose moment a command announces. A rule with no such trigger stays in `docs/rules.md`. A rule a hook already refuses lives in that hook's message, not here. The reasoning behind a rule, with its evidence, lives in [`docs/casebook/`](../casebook/INDEX.md) or in your knowledge base.

## The ceiling

Keep each file between 15 and 45 lines. A harness truncates a hook's output silently past a limit, so when a moment outgrows its file, split the moment rather than lengthen the file.

The command table in the hook is the registry. This table and the list in `docs/codex.md` name the same moments; when you add one, change all three in one commit.
