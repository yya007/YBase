# ADR 0001: Resolve the allow-gate hook from `$CLAUDE_PROJECT_DIR`

- Status: Accepted
- Date: 2026-06-19
- Note, 2026-11-13: when this was written, managed repos were cloned inside YBase; they now sit beside it, and the same failure applies to any `cd` into a managed repo.
- Note, 2026-11-14: the gate is now opt-in and off by default ([ADR 0003](0003-allow-gate-is-opt-in.md)). The wiring this ADR decides is unchanged; "runs on every Bash call" below means the hook starts, and it approves nothing unless `YBASE_ALLOW_GATE=1`.
- Note, 2026-11-14 (wiring): the command below still exited non-zero when `$CLAUDE_PROJECT_DIR` was unset and the working directory was outside YBase, which is every call from Codex in a managed repo or outside any repo: `python3` exits 2 for a missing script, and 2 blocks the call. The allow gate and the file guard, in `.claude/settings.json` and `.codex/hooks.json`, now use the fail-open wrapper of the other hooks: find the script from `$CLAUDE_PROJECT_DIR`, then from `git rev-parse --show-toplevel`, exit 0 when it is not there, and pass through only exit status 2. The allow gate's wrapper still moves to the project root first, because the gate reads `.claude/settings.json` relative to its working directory, and exits 0 if it cannot.

## Context

The `PreToolUse:Bash` allow-gate hook in `.claude/settings.json` located the gate
script with:

```
bash -c 'cd $(git rev-parse --show-toplevel) && python3 .claude/hooks/allow-gate.py'
```

`git rev-parse --show-toplevel` resolves against the shell's current working
directory, which persists across tool calls. The moment a command `cd`s into a
managed repo (each is its own git repo), the next gate invocation resolves the
toplevel to that repo, which has no `.claude/hooks/allow-gate.py`. The hook then
errors and **blocks every later Bash command, including the `cd` back to the root
that would fix it.** There is no in-band recovery; the session must reset its cwd
from outside the gated path (`!cd <root>`) or restart. This happened in practice
while adding a remote to a managed repo.

## Decision

Resolve the gate location from `$CLAUDE_PROJECT_DIR` (which Claude Code sets to
the project root for hooks), falling back to the previous behavior if unset:

```
bash -c 'cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}" && python3 .claude/hooks/allow-gate.py'
```

The gate still runs on every Bash call. This changes only *where* the hook looks
for the gate, not whether it runs. It is a robustness fix, not a bypass.

## Consequences

- The cwd deadlock can no longer occur after a `cd` into a managed repo.
- Hook config is cached at session start, so the change takes effect on the next
  session (or hook reload), not retroactively in a session already deadlocked.
- If `$CLAUDE_PROJECT_DIR` is ever unset, behavior is identical to before.
- Operational guidance still stands: prefer `git -C <path> ...` over `cd` into a
  managed repo (rule 23 in `docs/rules.md`, and the casebook entry
  `reach-a-sibling-repo-with-git-c-not-cd` in `docs/casebook/agents.md`).
