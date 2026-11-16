# Roadmap

Open product questions about YBase itself. Each item keeps its number from an earlier review, so a gap in the numbers is an item that was dropped or finished. Status is `open` or `done`.

Filing an item as an issue is the owner's call. When one is filed, link the issue here; when one is finished, mark it `done` in the same change.

## Purpose and measurement

**S1. Write down the mission and how to measure it.** `open`
YBase says what it is for, but not how to tell whether it is working. Add three or four measurable outcomes, such as changes landed per month across the managed repos, the share of tasks finished without a human stepping in, and follow-up fixes per landed change. Each item below should then tie to at least one of them.

**S2. Measure framework work against repo work.** `open`
Work on YBase itself can grow faster than the work it exists to support. A small report could count commits and pull requests over the last 30 days in YBase and in each repo from the repo list, using `git -C <path>`. Its output, with a one-line decision on where the next block of agent time goes, would land in the primary KB's worklog.

## Things that should compound

**S3. Check that lessons actually get saved.** `open`
Rule 17 says an agent records its own mistakes before work is called done, and the `session-closeout` skill asks for the lessons a session owes. Nothing yet shows whether KB `memory/` grows. After a month, count the lessons written; if there are almost none, either make the closeout step harder to skip or shrink the lesson machinery to match real use.

**S4. Manage the set of skills, not only each skill.** `open`
A user's skills come from several places: YBase, their own skill library and plugins. Skills with overlapping triggers get picked for the wrong task, and every installed skill costs context. `review-skill` audits one skill's quality; it should also flag trigger overlap, and each overlap group should get a one-line note on when to pick which.

**S5. Use evals to tell whether a change helps.** `open`
Only the `codex-delegation` skill has an eval in `docs/evals/`. Rules and skills change without any measure of whether the change made agents better. Start with a cheap eval, such as the allow gate over its existing approve and block cases, then require an eval result before changing a heavily used skill.

## Operations

**S6. Make run history visible.** `open`
A run's records live in the profile's scratch folder (`$YBASE_SCRATCH/runs/`) and disappear with it. So nobody can say how many runs needed rescue or where agents stall. Append one line per finished run to the primary KB's worklog (date, repo, outcome, interrupts, skills used); it belongs in the KB because it names repos.

**S8. Rebuild the run protocol on harness features.** `open`
[`protocols/runs.md`](protocols/runs.md) predates native task lists, subagents and worktree isolation in the agent harnesses. Split the lasting contract (a plan before code, clear ownership, evidence of verification) from the file mechanics. Retire each mechanic a harness now provides, and record the decision as an ADR.

**S11. Make the README sell the product, not the setup.** `done`
The README now opens with what YBase is for and how a session flows through it, and setup comes after. Keep that order when the README changes.
