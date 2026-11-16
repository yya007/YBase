# Profile: plan

Implementation plans written from a cold read of the repository.

## When

- `plan_expected_tasks` threshold tripped
- Multi-task work that needs sequencing and explicit acceptance criteria
- When the main thread has been deep in a problem long enough to have inherited assumptions

## Command

```
codex exec -s read-only -o <artifact> "<prompt below>"
```

## Prompt template

```
Read this repository and produce an implementation plan for: <goal>.

Constraints: <constraints and non-goals>.
Design reference, if one exists: <path>.

Before planning, state what you found in the repo that constrains the approach:
existing patterns to follow, code that must not break, conventions in AGENTS.md.

Then produce the plan as ordered tasks. For each task:
- a one-line title
- files it touches
- what it depends on
- how to verify it is done (a command, or an observable behavior, not "looks right")

Lead with a single SCOPE line: task count, rough sequencing, and the riskiest task.
Order tasks so that each one leaves the repository in a working state.

Call out explicitly: anything in the goal you could not plan because the repo does not
contain enough information, and what you would need to know.
```

## Handling

A cold reader's value is the assumptions it does not inherit. Pay particular attention to where its plan diverges from the one the main thread would have written. Divergences are where the inherited assumption lives.

Treat the plan as input, not as an approved plan. It still goes through the normal design and approval gate before implementation begins.
