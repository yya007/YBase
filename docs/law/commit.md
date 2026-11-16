# Commit: the rules that bind when you commit

Shown once per session by the moment hook; see [README.md](README.md). Codex reads it before the act.

## Before you commit

1. Be in your own worktree, never in the main checkout ([rule 15](../rules.md#working)).
2. Read the diff you are about to stage: `git diff` for the tree, `git diff --cached` after staging. Stage explicit paths; never `git add -A` or `git commit -a`.
3. Never stage a secret, a credential, a key or a `.env` file. If `git status` shows one staged, stop and ask.
4. Run `ybase check`. The pre-commit hook runs the same registry; a failure there is a failure to fix, never one to skip.
5. Commit each item as it goes green, without asking first. A worktree is disposable, and uncommitted work in one has no second copy. In a series, check each commit landed before staging the next ([casebook](../casebook/git.md)).

## What one commit holds

- One concern. Group related edits and split unrelated ones. Never mix a refactor, a rename or formatting churn with a behaviour change.
- A reviewer understands it from its message and diff alone, and it builds and passes the tests on its own. Prefer a series of small commits to one large mixed one.

## The message

- Write it for a reader outside this repository ([rule 19](../rules.md#publishing)).
- First line: what changed, in the imperative, at most 72 characters. Body: why, in plain words, with the trade-offs and the alternatives considered.
- Everything committed is published, the message and the author identity included. No private alias, internal id (a run or task id included), personal path or term from a knowledge base's `deny.list`; the `leaks` check reads every commit message after the `.leaks-baseline` commit.
- The leak hook applies every pattern and the deny list in every repo ([ADR 0005](../adr/0005-leak-hook-strict-everywhere.md)). The deny list names the managed repos, so a managed repo's commit that names itself, or stages an email or a home path, is refused in a Claude Code session started in the YBase folder (no other session loads the hook, so there the rule binds you without a guard): when the user has said that text may ship there, prefix the command with `LEAK_AUTHORIZED=1`. Never name YBase, its KB or a sibling repo in a managed repo ([rule 22](../rules.md#repos)).
- Cite what the reader can open: a file in this repo, a public source. A path that exists only on your machine is a pointer the reader cannot follow, and renaming it does not launder it.

## Never bypass the gate

- Never `--no-verify`. A gate that cannot fail you protects nobody; if a check is wrong, fix the check in the same change and say so where the work is reported.
- `ybase check` reads the whole tree. After changing a rule or a check, run it again: your change may break files you did not touch ([rule 9](../rules.md#changes)).

## Rebase and recover

- Rebase, never merge, onto the branch you will land on. A rebase paused on a conflict leaves HEAD at the upstream tip, so read `git status` and `git reflog` before reporting a commit as missing.
- Restoring a file from an older revision reverts every later fix to it. Run `git log --oneline <old>..HEAD -- <path>` first; that list is what you would drop.
- Never put a pipeline on the left of `&&` when the right side commits, pushes or deletes: the status is the last stage's. Run them as separate calls and read the first result before issuing the second.
