# PR: the rules that bind when you open, edit, mark ready or merge a pull request

Shown once per session by the moment hook; see [README.md](README.md). Codex reads it before the act.

## Before you open

1. Base is the branch you cut from and will land on. Never a personal or sibling branch, unless this PR is a child in a stack.
2. `ybase check` passed on the head, `leaks` included, and so did the repo's full local test and lint suite. Nothing in the diff, title, body or commit messages points at a private path, alias or term ([rule 19](../rules.md#publishing)).
3. One logical change per PR, at most about 400 changed lines without lockfiles and generated files. Over that, say why in the body or split into a stack; a stack is merge order, not an argument.
4. You read your own diff end to end, then a reader who is not the author read it, and its findings are fixed before you create.
5. `gh pr create --draft ...`, always draft. Read the created PR back ([rule 5](../rules.md#evidence)).
6. Report that it is ready for the user, and stop. Only the user marks a PR ready or merges it.

## The body

- State the change, never the PR's own history: not the branch it opened on, not what was folded in, not which commits were cherry-picked. A reviewer can check none of that; it belongs in commit messages.
- Open with one problem-then-fix sentence. Then say what a reviewer cannot see from the diff: why, what was tried, what was measured and how ([rule 2](../rules.md#evidence)).
- Never list the diff file by file.
- Fill the repo's PR template, `.github/PULL_REQUEST_TEMPLATE.md` here: at least Summary, Verification, and Risk and rollback. A change that cannot be tested (infrastructure, prompts, docs) says so under Verification and names the manual check performed.

## What ships in which PR

- New work that will not fit this PR is a new PR, not a reason to close this one. An approval cannot be re-earned; take the new file out and ship what passed.
- A shared branch carries only shared things: what other people will run. Scaffolding for one run stays on the run's branch.
- A stack is merge order and project housekeeping. Link the PRs as you open them; put any order a stack cannot carry in the project record, never in a thread.

## Mark ready and merge

- Neither happens without the user's say-so for this PR. When they give it, read the PR back afterwards and confirm `MERGED` with a merge commit that is an ancestor of the base.
- A red required check blocks the merge; never override one without a written reason in the body. Every review comment is answered, and no blocking one is left open.
- Before a merge, read each red job at the base and at the fork point before calling it inherited. A gate that printed PASS for "clean" and WARN for "did not run" has told you nothing in the second case ([rule 4](../rules.md#evidence)).
- The repository you merge into owns the gate that decides: its CI, its ruleset, its formatter. When the PR goes to another repository, read that gate rather than this repo's convention.
- Prefer a squash merge for a feature branch; keep the commits only for a stack whose boundaries matter to review.
- Post nothing to the PR about the merge; the diff and the checks already say what happened. Record the outcome in the worklog.

A child repo's own `AGENTS.md` or the user's `rules.md` may relax these rules; the guard that enforces the draft rule is opt-in through `YBASE_GUARD_PR_DRAFT=1` in `.env`.
