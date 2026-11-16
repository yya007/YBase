# Multi-agent execution: several agents on one run

Open this when more than one agent works on the same run. The run itself is described in [`runs.md`](runs.md); the rules that bind each dispatch are in [`law/delegate.md`](../law/delegate.md).

## When several agents help

More agents buy breadth and clean contexts, and they cost tokens. Anthropic reports that an agent uses about 4 times the tokens of a chat, and a multi-agent system about 15 times ([source](#sources)). Spend that only where it pays.

| Good fit | Poor fit |
|---|---|
| the parts are independent and can run at the same time | each step needs the result of the one before |
| the material is larger than one context can hold | every agent would need the same shared context |
| the same measurement is repeated across many variants | a tightly coupled change across a few files, which is most coding |

Scale the number of agents to the question, and write the number and the reason in the plan:

- A lookup or a single fact: one agent, no fleet.
- A comparison of a few options: two to four workers, one per option.
- A broad survey or many variants: more workers, only when each one owns a part no other worker touches.

## Who decides what

The person keeps the outer loop: which question matters, which measure can be trusted, and what to do next. Agents run the inner loop: build, run, score, compare, plot. An agent that meets an outer-loop choice stops and reports it. It does not pick.

| Role | Does | Never |
|---|---|---|
| Lead | plans, writes the briefs, integrates, keeps the run's files current | measures its own work as the only check |
| Worker | one scoped task in its own worktree, reports by file | edits outside what it owns, or changes how results are measured |
| Verifier | reads the artifacts cold and gives a verdict | sees the worker's reasoning before forming its own |

The lead writes its plan to the run's files before it dispatches anyone. A lead that loses its context then resumes from the files, and a worker that fails is restarted from its task file, not from the beginning of the run.

## Freeze what must be comparable

When several workers measure the same kind of thing, the lead builds the measuring pipeline once and every worker runs it unchanged: the same inputs, metric, judge, sample count and figure. A worker varies one thing, in one small file it owns. Five agents each left to choose a judge and a sample size report five numbers that cannot be compared.

- Split what a worker runs from what it may write. The pipeline, the shared code and the frozen inputs are read-only to workers; the brief names the one folder they write in.
- Anything you had to correct a worker about belongs in the pipeline, so the next worker cannot get it wrong.
- Fix the metric and the stopping rule before the first result. A worker that adds samples after seeing a weak result, or swaps the metric, has changed the experiment.

## Ownership

- Declare the files and folders you own before you edit anything.
- Never edit outside what you own without an explicit handoff.
- Give each agent its own worktree. Two agents in one worktree share one index, whatever harness each runs under.
- Never revert changes you did not make. Another agent's work in progress looks like noise until it lands.

## Briefs

[`law/delegate.md`](../law/delegate.md) binds every brief. For a worker in a fleet the brief also names:

- the objective, in one sentence;
- the one thing this worker varies or the one part it covers, and what the neighbouring workers cover;
- the file to write and the command to run;
- the reply: the path of the artifact and one sentence on what it shows.

## Results travel as files

A worker writes its full output to an artifact and returns the path and a short digest. A result retold through two agents loses detail at each step, and a large output pasted into the lead's context crowds out the plan.

## Handoffs

Write every handoff from [`templates/run/handoff-template.md`](../../templates/run/handoff-template.md). It names:

- the run id, and the task id when there is one;
- the scope owned;
- the artifacts produced, by path;
- what is completed and what is pending;
- the decisions made;
- risks and blockers;
- the next commands;
- the verification result.

## State

Task state lives in the run's files, not only in chat:

- each worker updates its own `tasks/<task_id>.md`;
- the integrator mirrors status, dependencies and verification in `tasks/index.md`.

## Integration and verification

The integrator checks that the pieces agree with each other across files before the run is called done.

- Read raw outputs, not only the summary or the figure. A judge that silently failed to label a third of the replies still produces a clean chart.
- Audit the method as well as the result: look for a choice no careful person would make, such as a home-made detector standing in for the agreed judge.
- Judge the end state, not the path. Two workers may reach a correct result by different routes.
- When a result surprises you, check the pipeline before you believe the result.

A verifier gives one of three verdicts:

| Verdict | Meaning |
|---|---|
| `pass` | the output can proceed |
| `revise` | the output must be corrected before completion |
| `fail` | the output is unsafe or incomplete and is not treated as done |

On a machine where Codex delegation is on, the verifier for a large or risky piece is a second model ([`delegation.md`](delegation.md)). Where it is off, the verifier is a subagent with a fresh context, and the run's report says so.

## Sources

- Anthropic, "How we built our multi-agent research system", 13 June 2025: <https://www.anthropic.com/research/multi-agent-research-system>. Fit, cost, effort scaling, brief contents, results as files, durable state, judging the end state.
- "How to run better research with agent fleets", LessWrong, 6 November 2026: <https://www.lesswrong.com/posts/WKtD59uHLKwEYGFCm/how-to-run-better-research-with-agent-fleets>. Outer and inner loop, the frozen pipeline, read-only pipeline files, reading raw outputs, auditing method choices.
