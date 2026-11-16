# Push: the rules that bind when you push or land

Shown once per session by the moment hook; see [README.md](README.md). Codex reads it before the act.

## Before you push

1. `git status --short` prints nothing. Commit first; never stash around a push, since the stash is shared by every worktree of the clone.
2. The branch is the `<kind>/<subject>` branch of your own worktree, rebased onto the tip of the branch it will land on ([rule 15](../rules.md#working)).
3. `ybase check` passed on the tree you are pushing, `leaks` included: it reads every commit message after the `.leaks-baseline` commit ([rule 19](../rules.md#publishing)).
4. Push the branch: `git push -u origin <branch>`. On ephemeral scratch, push after every commit; an unpushed branch has one copy.

## How a change lands

- Land through a draft PR from the branch; see [pr.md](pr.md). Only the user marks it ready or merges.
- Never push to the default branch unless the user said to for this change.
- Never force-push a branch someone else may have fetched. `--force-with-lease=<branch>:<sha>` on your own stacked branch is the one exception, and only with a named sha.
- A pushed branch is not a landed change. The default branch serves the old text until the PR merges, so never report branch-only work as delivered.

## After you push

- Verify from the remote, never from the push output ([rule 5](../rules.md#evidence)): `git fetch origin`, then `git diff origin/<branch> -- <paths>` prints nothing and `git log origin/wt/<name> -1` names your commit.
- Once merged, verify the same way against the default branch: `git show origin/<default>:<path>`.
- Write the result where the work is reported: branch, head sha, PR link. A reader who cannot see your terminal reads an unreported push as no push.
- If the push was rejected, `git pull --rebase`, then push again as a separate call. Read the first result before issuing the second.

A child repo's own `AGENTS.md` or the user's `rules.md` may relax these rules, for example to allow direct pushes to the default branch of a private repo.
