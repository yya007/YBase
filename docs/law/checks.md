# Checks: the rules that bind when you write or change a check, a test or a hook

Shown once per session by the moment hook; see [README.md](README.md). Codex reads it before the act.

## Before you add or change one

1. It observes the claim it makes ([rule 4](../rules.md#evidence)). For each pass, ask what would have to be false for it to be wrong, and whether it looked there. An exit code of 0 names what it did not check.
2. It fails. A report-only guard is a debt ratchet; make it fail the moment its backlog reaches zero, or gate the count under a ceiling that only lowers.
3. Its expectation comes from the specification, a protocol or a worked example, never from the code's current output. A green suite over wrong behaviour defends the defect.
4. Its universe is named, not subtracted: "every file under `memory/`" is a universe; "everything except tests and fixtures" is a subtraction whose count defends what the exceptions missed. Read the members before pinning a count.
5. You watched it fail once from the runner (`uv run --extra dev pytest`, `ybase check <name>`) on a planted violation, and pass on a near-miss. A vacuous invocation, a partial glob and a silent skip all print green.
6. It reports how much it scanned. `scanned 0` is a finding, not a pass.

## Where it lives

- One declaration ([rule 7](../rules.md#changes)): a check is a function in `tools/checks.py`, and the pre-commit hook, CI and `ybase check` all run that registry. A second list of checks anywhere is a copy that drifts; derive it or refuse it.
- A Claude Code hook under `.claude/hooks/` fires only in Claude Code. A rule that must bind every agent goes in `tools/checks.py` or `.githooks/`, and the hook stays an adapter. Say which in the docstring.
- A hook that cannot decide allows: malformed input, an unparseable command and an internal error all exit 0. Decide from the parsed token stream, never by substring.
- Probe the platform, never assume it: shell, userland, temp dir, an absent tool. Branch on the probe and never skip silently. The suite runs on every machine profile.

## Fixtures and controls

- Build a rejection fixture by copying the accepted one and changing a single field, then confirm the test goes red. A control written in the predicate's own spelling proves that spelling and nothing else.
- Anchor an extraction on the label that names the value, never on the token's shape; build the fixture from output that carries the decoys.
- A branch that adds a corpus-wide check re-runs it after every rebase: files landed mid-branch violate the new rule on someone else's file ([rule 9](../rules.md#changes)).
- Prove the guard is in force from the artifact it protects: read its effect out of a real run before you call it live.
