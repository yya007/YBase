# Delegate: the rules that bind when you hand work to a subagent or another agent

Shown once per session by the moment hook; see [README.md](README.md). Codex reads it before the act.

## Before you dispatch

1. Delegate a separable issue: self-contained work that would derail this thread. Parking it loses it; doing it inline costs the thread. Delegate when parallelism, specialization or a clean context helps; read-only research and disjoint analysis are delegated by default. Keep tightly coupled state changes local.
2. The brief carries only verified facts, and marks an unverified premise as unverified ([rule 1](../rules.md#evidence)). A hypothesis handed down comes back confirmed.
3. The brief carries its own limits: the absolute worktree path it may write in, and the destructive actions allowed. Otherwise send it read-only. A subagent inherits your working directory, not the reasoning that chose it, so an unstated constraint is an absent one.
4. Name the conventions it must follow by file (`docs/rules.md`, `docs/writing.md`, the law file for its moment), never by restating them.
5. State the objective in one sentence, then fix the output shape: which files it reports, what counts as done, and what it must say it did not do. Name what is out of scope and which worker owns the neighbouring part, or two workers do the same work.
6. One scoped task per worker, with the files it owns named. A handoff follows [`templates/run/handoff-template.md`](../../templates/run/handoff-template.md); several agents on one run follow [`docs/protocols/multi-agent.md`](../protocols/multi-agent.md).
7. Inside a run, record the decision for each candidate in `run.json`, with the reason when you keep it local ([`docs/protocols/runs.md`](../protocols/runs.md)).

## What the brief says

- For a move or port of existing text or code: say verbatim for docstrings, comments and the numbers in them, then diff the port against the original and read the deletions.
- For a search or a negative result: "absent", "dead" or "unaffected" is valid only when the probe found a planted known-present case. Brief the delegate to report the command and its exit status, not a summary.
- For a Codex delegate: it reads `AGENTS.md`, not `CLAUDE.md` or the files it imports, and no Claude Code hook sees its edits. Point it at [`docs/codex.md`](../codex.md) and the worktree path; the git hooks still bind it. Use Codex for large output or an independent second opinion, through the `codex-delegation` skill, on a machine where `.ybase/MACHINE.md` says Codex delegation is on; where it is off, a fresh-context subagent takes the work and the report says no second model read it; [`docs/protocols/delegation.md`](../protocols/delegation.md) has the rest.
- Scratch is the profile's directory, `eval "$(ybase env)"` ([rule 16](../rules.md#working)), never a fixed name in a shared `/tmp`.

## When it reports back

- Read artifacts, not summaries ([rule 3](../rules.md#evidence)): open the files it wrote and run the command it says passed before building on its report. Delegated output goes to a file; read back a bounded digest, never the whole of it.
- Review and critique findings are claims until you verify them. Decide which to act on before editing anything.
- A subagent's mistake arrives in the same confident register as its findings. Spot-check against the head of the tree, not against the brief.
- If its method was invalid, reopen every conclusion drawn from it, not only the one you noticed.
- Two agents in one worktree share one index whatever harness they run under. One worktree per agent, one unit per branch.
