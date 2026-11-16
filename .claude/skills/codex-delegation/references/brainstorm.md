# Profile: brainstorm

Alternative approaches and second opinions. `auto` is off by default: this profile is cheap to run and easy to over-run, so it fires only on explicit invocation.

## When

- A direction has been chosen and is worth stress-testing before committing
- The main thread has converged early and the search space was never really explored
- Explicit request for a second opinion

## Command

```
codex exec -s read-only -o <artifact> "<prompt below>"
```

## Prompt template

```
Read this repository. The problem: <problem statement>.

The approach currently favored is: <approach>. Do not start from it. Treat it as one
option among several, and do not optimize it.

Produce 3 genuinely different approaches. Different means different in mechanism or in
what they assume, not the same design with different names. For each:
- the core idea in two sentences
- what it makes easy, and what it makes hard
- what has to be true for it to be the right choice
- rough cost to build in this repo specifically

Then state which you would choose and why, in one paragraph. If the currently favored
approach is in fact the best one, say so plainly and explain what the alternatives cost.

Lead with a single OPTIONS line naming the three approaches in a few words each.
```

## Handling

An honest "the current approach is right" is a useful result, not a wasted run: a stress test that passes is information. Watch for the failure mode where all three "alternatives" are the same design restated; if that happens, the problem statement was too narrow to leave room, so widen it and re-run rather than accepting the output.
