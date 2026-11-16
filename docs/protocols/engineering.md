# Engineering discipline: guardrails against common coding mistakes

Open this before writing or changing code. These rules favour caution over speed; for a trivial task, use judgment. They are adapted from [andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills/blob/main/CLAUDE.md).

## Think before coding

- State your assumptions explicitly.
- When a request has more than one reading, name the readings and ask. Do not pick one silently.
- When a simpler approach exists, say so, and push back when it is warranted.
- Debug and look things up on your own, but escalate a real ambiguity in the requirement rather than guess past it.

## Simplicity first

- Write the least code that solves the problem, and nothing speculative.
- No features nobody asked for, no abstraction for code used once, no flexibility or configuration nobody asked for, and no error handling for states that cannot happen.
- If 200 lines could be 50, rewrite them. Ask whether a senior engineer would call the result overcomplicated.

## Surgical changes

- Every changed line traces to the request.
- Do not improve adjacent code, refactor what works or restyle to taste. Match the surrounding code.
- Remove only the imports and symbols your own change left unused. Flag dead code that was already there instead of deleting it.
- This supports one concern per commit ([`law/commit.md`](../law/commit.md)) and never reverting another agent's work ([`rules.md`](../rules.md)).

## Goal-driven execution

- Turn the task into a goal you can check before you implement. "Add validation" becomes "write tests for invalid input, then make them pass". "Fix the bug" becomes "write a test that reproduces it, then make it pass".
- For work with several steps, state a short plan with a check for each step.
- Strong success criteria let you loop to done on your own. Weak ones ("make it work") cause rework.
- Ship every behaviour change with a test at the level that matches it: unit, integration or smoke. A bug fix ships with a regression test that fails before the fix and passes after.
