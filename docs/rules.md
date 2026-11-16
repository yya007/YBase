# Ground rules

These hold in every repo, on every machine. The reasoning behind a rule lives in a [casebook](casebook/INDEX.md) entry or your knowledge base (KB), which the rule may link.

Rules for one moment (commit, push, worktree, PR, review, delegation, wait, check, document) live in [`law/`](law/README.md): Claude Code sees each through a hook, other agents read it first ([`codex.md`](codex.md)). Your KB's `rules.md` loads after this file and may relax a rule for your own repos.

## Evidence

1. **Verify before you assert.** Read the source, the file or the command output before you state it. Mark an unverified premise as unverified, including in a brief you hand to another agent.
2. **Label every number** as measured `[M]`, derived `[D]` or assumed `[A]`. Never headline an assumed number. A rate measured over one interval is assumed for every other interval.
3. **Read artifacts, not summaries.** A subagent's report, a dashboard or a log tail compresses what happened. Spot-check the underlying files before you build on them.
4. **A check must observe the claim it makes.** For each pass, ask what would have to be false for it to be wrong, and whether you looked at that. An exit code of 0 names what it did not check.
5. **Read the shipped artifact back from the surface its consumer reads**: the file on disk, the pushed branch, the rendered page. What you wrote is input, not evidence.

## Changes

6. **Correct with an erratum, never a silent rewrite.** A factual fix to a committed claim is a dated `ERRATUM` block in place, and every other site that asserts the claim gets one too.
7. **One fact, one declaration.** Anything maintained by hand in two places drifts. Derive the second copy from the first, or delete it.
8. **Match the fix to the verified size of the problem.** Climb doc convention, then check, then config, then new module, and stop at the first rung the measured problem allows.
9. **Sweep the class, not the instance.** When you find a defect, search for every other place it occurs, fix them in one pass, then ask what check would have caught it.
10. **Fix it where you stand, or name what stops you.** A cleanup you can land now is not a follow-up item.

## Placement

11. **File a research note by its stage and layer**, as its topic's `PIPELINE.md` says ([template](../templates/research-topic/PIPELINE.md)): evidence never recommends, and a measurement, an interpretation and a current truth go to three different places.
12. **A README orients; a catalog lists.** Do not grow a README into an index.
13. **Keep machine facts out of rules and lessons.** True of every machine of a type goes in `profiles/<type>/NOTES.md`; true of one machine goes in its generated `.ybase/MACHINE.md`; secrets go nowhere in a repo.
14. **Keep a KB topic's knowledge inside its topic.** A topic never links into another topic. A lesson that holds across topics goes to the KB's `memory/`, or to `docs/casebook/` when it names nothing private.

## Working

15. **Work in a worktree, one per unit of work** (`ybase wt <kind>/<subject> [--repo NAME]`), cut from the tip you will land on; never write in the main checkout. The guard that enforces this is opt-in: `YBASE_GUARD_READONLY_CHECKOUT=1` in `.env`.
16. **Use the profile's scratch directory** (`eval "$(ybase env)"`), never a fixed name in a shared `/tmp`.
17. **Record your own mistakes unprompted.** An error that cost real time, or a correction from the user, becomes a lesson before the work is called done: in the primary KB if it names anything private, else proposed for `docs/casebook/` ([`kb.md`](kb.md)).
18. **Write in plain English** ([`writing.md`](writing.md)): the everyday word, one fact per sentence, no em dashes.

## Publishing

19. **Treat everything committed as published**, including commit messages and author identities. Run `ybase check` before every commit, and keep private terms in your knowledge base's `deny.list`, which is never committed.

## Repos

20. **Read a repo's own `AGENTS.md` before changing it**, and the docs it names. Where it states a rule, its rule wins in that repo.
21. **What is true of one repo stays in that repo**: its code, docs, build commands, issues and rules. YBase holds only what is true of every repo.
22. **A child repo's artifacts never mention YBase, its KB or sibling repos**: not in code, comments, commits, PRs, docs or issues. Shared doctrine reaches a repo by being copied into its own `AGENTS.md`.
23. **Reach a managed repo by path, never by `cd`**: `git -C <path>`, or a worktree from `ybase wt`. Sessions start in YBase ([case](casebook/agents.md)).

## Engineering

24. **Docs first.** Change the contract (`AGENTS.md`, rules, skills, docs) with the behaviour it describes, never after, and never hide agent behaviour in runtime code.
25. **Plan non-trivial work.** For three or more steps or a cross-file change, write acceptance criteria and a plan before editing ([runs](protocols/runs.md)). When execution drifts from the plan, stop and re-plan.
26. **Debug before you escalate.** Try an alternate path and targeted research first. Escalate for missing permissions, inputs or access, not for a problem you can still work.
27. **Code with discipline** ([engineering](protocols/engineering.md)): state your assumptions, write the least code that solves the problem, change only what the request needs, and ship each behaviour change with a test.
28. **Check existing skills before writing ad-hoc logic** for a repeated task. Extend a skill rather than duplicate it, and put a fix you validated into the skill that owns it.
29. **Record what you verified and what you deferred** where the work is reported. A fix belongs in the repo, not in chat history.
30. **In a managed repo, run its lockfile-native package manager** and never edit a lockfile by hand. Adding or removing a dependency follows [dependencies](protocols/dependencies.md).

## Safety

31. **Ask first** before destructive cleanup, a large dependency or framework change, a change to a schema or a stored format, or anything reaching past the local repo: a force-push, shared infrastructure, an external service, a published artifact.
32. **Never revert work you did not make.** Another agent may own it.
33. **Never disable or route around a guard** (`.claude/file-guard`, `.claude/hooks/`). If one is wrong, change it in a reviewed commit backed by a recorded decision, an ADR ([decisions](protocols/decisions.md)).
34. **Treat environment values as need-to-know.** Never log, echo or paste a value from the environment, a secret manager or CI into a commit, a PR, chat or an artifact.
