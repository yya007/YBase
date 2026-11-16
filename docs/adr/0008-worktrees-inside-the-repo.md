# ADR 0008: Worktrees live inside their repo, under a name that says the work

- Status: Accepted
- Date: 2026-11-15

## Context

`ybase wt <name>` put every worktree in one folder beside YBase and named the branch `wt/<name>`. Two things went wrong.

The folder was derived from where the tool ran. Run from inside a worktree, it made a second worktree folder nested in the first. Worktrees of managed repos sat far from the repo they belonged to, so a person looking at a repo could not see its worktrees, and cleaning up meant knowing a second place.

The `wt/` prefix said only that a tool made the branch. Names such as `wt/fix` or `wt/test2` reached the remote and told a reviewer nothing.

## Decision

1. **One folder per repo.** A worktree goes in `<repo>/.worktrees/<kind>-<subject>`. This holds for YBase and for every managed repo.
2. **Hidden without a commit.** The tool adds `.worktrees/` to the clone's own `.git/info/exclude`. A managed repo therefore gets no commit and no `.gitignore` line, which keeps rule 22: nothing in it shows who made the worktree. YBase also lists the folder in its `.gitignore`, so tools that read only that file skip it.
3. **A profile may still move it.** A relative `PROFILE_WORKTREES` or `YBASE_WORKTREES` is a folder inside each repo. An absolute one is a parent folder with one folder per repo. The `aws` profile keeps worktrees on its fast disk this way.
4. **The name is `<kind>/<subject>`.** The kind is `feat`, `fix`, `docs`, `refactor`, `test` or `chore`. The subject is two to five lowercase words joined by hyphens. The tool refuses a name without a kind, filler words and dates. The branch takes the name as it is.
5. **One exit.** `ybase wt done <kind>/<subject>` removes one worktree and its branch, with the same checks as the sweep. `ybase worktrees --all` reports on YBase and every managed repo.

## Alternatives considered

- **Keep the sibling folder and fix the nesting.** Rejected: it fixes the bug and leaves worktrees away from their repos.
- **A line in each managed repo's `.gitignore`.** Rejected: it is a commit in a child repo made for the home repo's sake.
- **A naming skill instead of a refusal in the tool.** Rejected: a skill can be skipped, and the rule is small enough to check.

## Consequences

- A tool that walks the main checkout must skip `.worktrees/`. `pytest` is told to, and the test fixtures that copy the tree leave it out.
- A worktree made before this change stays where it is. Git still registers it, so `ybase worktrees` lists it and reaps it as before.
- A session whose sandbox allows writes only inside the folder it started in can now write to a YBase worktree without an extra folder.
- A branch name no longer shows that the tool made it. Nothing relied on that.
