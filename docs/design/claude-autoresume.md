# claude-autoresume: design

## Problem / user outcome

When a Claude Code session hits the usage/rate limit, the agentic turn stops and
the work is left paused until the limit window resets. The user wants a thin,
dependency-free wrapper they can launch (and walk away from) that finds the
sessions paused *because of* a usage limit and resumes them automatically once
the window reopens, no babysitting the reset clock.

## Scope

- Discover Claude Code sessions **in the current project** that are paused on a
  usage limit, and resume each sequentially until it advances one turn.
- One script: `tools/claude-autoresume.sh`. Bash + `claude` only (no `jq`).

### Non-goals (YAGNI)

- Cross-project scanning (current project only).
- Deciding whether the *whole* underlying task is "done", the wrapper only
  bridges limit pauses; a normal turn completion ends that session's resume.
- Desktop notifications, interactive TUI relaunch, parallel resume (parallel
  would just deadlock on the shared limit).

## How Claude Code stores the state we need

- Transcripts: `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`, one JSONL
  record per event. The encoded dir is `$PWD` with `/` → `-`.
- `claude -p "<prompt>" --output-format json` returns a single-line result JSON
  with `is_error`, `subtype`, `session_id`, `result`, `api_error_status`.
- API errors are recorded in transcripts as
  `{"type":"system","subtype":"api_error","level":"error","error":{"message":…,"status":…}}`.

**Known unknown:** at authoring time no real usage-limit (429) event exists in
the local history (only `529 overloaded` and connection errors). The 429
match is therefore a best reconstruction, isolated in one config constant
(`LIMIT_PATTERN` / `LIMIT_STATUS`) so it can be confirmed and tuned the first
time a real limit is hit.

## Behavior

### 1. Discovery (current project only)

- Encode `$PWD` → scan `${PROJECTS_DIR:-~/.claude/projects}/<encoded-cwd>/*.jsonl`.
- A session is **limit-paused** iff its last substantive record is an
  `api_error` matching `LIMIT_PATTERN` (default: `status:429` or message text
  matching `usage limit|rate limit|limit reached`). A later `user`/`assistant`
  record after that error ⇒ the session was continued ⇒ skip it.
- Recency filter `--since` (default `24h`): ignore sessions whose pause is older,
  so ancient abandoned sessions are not resurrected.

### 2. Resume loop

- Print the discovered list (`id · project · age`) to stdout and the log, then
  **auto-run** (no interactive prompt). `--dry-run` lists and stops.
- For each session sequentially:
  - `claude -r <id> -p "<nudge>" --output-format json <claude-args>` in the
    project cwd. `nudge` default `"continue"`.
  - `is_error:false` → log success, move to next session.
  - limit error → parse reset time from the **fresh** error (`…reached|<unix>` →
    ISO-8601 → `resets at HH:MM`; fallback `--retry-interval`, default `15m`) →
    sleep until reset + `--buffer` (default `60s`) → retry the same session,
    capped at `--max-resumes` (default `12`).
  - any other error → log, skip to next session, set overall exit non-zero (one
    bad session must not abort the run).

### Flags

`--dry-run`, `--since DUR`, `--nudge STR`, `--max-resumes N`,
`--retry-interval DUR`, `--buffer SEC`, `--claude-args "…"` (e.g. your
`--allowedTools`), `--yolo` (opt-in `--dangerously-skip-permissions`, warned),
`--log FILE`, `-h`.

Permissions default to pass-through: unattended headless needs a permission
strategy, so the user supplies `--allowedTools …` via `--claude-args`, or opts
into `--yolo`. The script never enables skip-permissions on its own.

## Error handling

- Malformed / unreadable transcript → skipped with a warning, not fatal.
- Unparseable reset time → fall back to `--retry-interval` polling.
- `--max-resumes` exhausted for a session → warn, mark exit non-zero, next.
- Missing `claude` binary → fail fast with a clear message.

## Testability (tests ship with the script)

The script honors overrides so behavior is exercised without the API or real
sleeping:

- `CLAUDE_BIN` (default `claude`): inject a fake `claude` emitting canned JSON.
- `AUTORESUME_SLEEP` (default `sleep`): no-op sleep in tests.
- `AUTORESUME_NOW` (default: current epoch): deterministic reset math.
- `PROJECTS_DIR` (default `~/.claude/projects`): point at fixture transcripts.

`tests/test_claude_autoresume.py` (pytest subprocess, matching the existing
`test_setup_*.py` convention) covers: detecting a limit-paused session vs a
normally-ended one, recency filtering, `--dry-run`, correct `-r <id>` resume
invocation, reset-time parsing + sleep computation, per-session `--max-resumes`
cap, other-error skip with non-zero exit, and missing-binary failure.

## Acceptance criteria

- `uv run pytest` and `uv run ruff check .` green.
- `claude-autoresume.sh --dry-run` in a project lists exactly the limit-paused
  sessions within the recency window and resumes nothing.
- A limit-paused fixture session drives one `claude -r <id> -p continue` after a
  computed sleep-to-reset; a fresh limit on retry re-sleeps; cap is enforced.
- No `jq` dependency; `set -euo pipefail`; `-h` prints usage.

## Canonical targets

- `tools/claude-autoresume.sh` (new)
- `tests/test_claude_autoresume.py` (new)
- `docs/design/claude-autoresume.md` (this file)
- `CLAUDE.md` scripts list: add a one-line entry. (Note, 2026-11-13: that list is gone; `CLAUDE.md`
  now only imports the rule chain, and `README.md` links `docs/claude-autoresume.md`.)
