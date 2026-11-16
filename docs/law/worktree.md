# Worktree: the rules that bind when you create, switch or remove a worktree or branch

Shown once per session by the moment hook; see [README.md](README.md). Codex reads it before the act.

## Before you cut

1. Never write in the main checkout. It stays on the default branch and is read-only; every change, a one-line fix included, goes through a worktree ([rule 15](../rules.md#working)).
2. `git fetch origin`, then check whether the default branch already fixed what you are about to fix: `git log --oneline origin/<default> -- <paths>`. If so, follow its solution.
3. Cut from the tip you will land on. `ybase wt <kind>/<subject>` fetches `origin` first and does this by default and takes `--base <ref>` otherwise. Re-cut rather than carry an old base; a base read once ages into conflicts and hides fixes that already shipped.
4. One worktree per unit of work, and the whole unit in it. A unit can be larger than a folder: when a rule lives in a doc, a check and its test at once, one worktree takes all three.
5. Name the work, not the session. The name is `<kind>/<subject>`: the kind is `feat`, `fix`, `docs`, `refactor`, `test` or `chore`, and the subject is two to five lowercase words joined by hyphens that say what changes, as in `fix/leak-scan-symlinks`. The tool refuses filler (`tmp`, `wip`, `new`) and dates. The branch takes the name, and the folder is `<repo>/.worktrees/<kind>-<subject>`.
6. Every worktree of a repo lives in that repo's `.worktrees/` folder, which the clone's own `.git/info/exclude` hides. Never commit that folder or add it to a managed repo's `.gitignore`. A profile or `YBASE_WORKTREES` may move the folder to another disk.
7. `eval "$(ybase env)"` at the start of a command that needs scratch, run from YBase and not from inside the worktree, so scratch lands in the profile's directory ([rule 16](../rules.md#working)).

## While you work in it

- Stage explicit paths only; never `git add -A` or `git commit -a`. Several sessions share one clone, and `git stash` is clone-global: never use it bare.
- Commit each item as it goes green. A worktree is disposable, and uncommitted work in it has no second copy. If the profile says scratch is not durable, push before the machine stops.
- Refresh a shared file before editing it (`git checkout origin/<default> -- <file>`), and read each commit's diff for an unexpected deletion: that is you overwriting someone's landed work.
- Keep a task's inputs, outputs and run files in the profile's scratch directory, never in the checkout. Scratch is working space, not the record; what must last is committed or saved to the knowledge base.
- Never infer that an existing worktree is yours from its name. A brief names the absolute path, or you create a new one.
- Check what a worktree's `origin` points at before trusting a read from it. A sibling checkout fetches cleanly and still answers from a stale tree.

## Before you remove it

- `ybase wt done <kind>/<subject> [--repo NAME]` removes your own worktree and its branch once the work has landed; it refuses, and says why, while anything in it would be lost.
- `ybase worktrees` lists a repo's trees with what each still holds, and `--all` lists YBase and every managed repo at once. Remove a tree only when its branch is pushed and its work is landed or deliberately abandoned, and say which.
- Never remove a tree another session may own. The `cleanup-worktrees` skill holds the repo-wide sweep.

A child repo's own `AGENTS.md` or the user's `rules.md` may relax these rules; the guard that enforces rule 1 is opt-in through `YBASE_GUARD_READONLY_CHECKOUT=1` in `.env`.
