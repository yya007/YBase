# claude-autoresume

`tools/claude-autoresume.sh` resumes Claude Code sessions that were paused
because they hit a usage/rate limit. You launch it **after** a limit stops your
work, then walk away: it waits out the reset window and resumes the paused
conversation(s) for you.

It's a thin, dependency-free bash wrapper. Only `bash` and the `claude` CLI are
required (no `jq`).

## When to use it

You're working in a project, hit the usage limit, and Claude stops mid-task.
Instead of watching the clock and manually re-running `claude --continue` when
the window reopens, run this once and leave it. It handles the sleep-and-resume.

It does **not** start new work or decide whether your overall task is "done". It
only bridges limit pauses. Once a resumed turn completes normally, that session
is finished as far as the wrapper is concerned.

## Quick start

From your project's root directory:

```bash
# See what it would resume, without resuming anything:
tools/claude-autoresume.sh --dry-run

# Resume for real. Unattended headless runs need a permission strategy:
# supply the tools you're willing to auto-approve:
tools/claude-autoresume.sh --claude-args "--allowedTools Bash Edit Read"
```

Run it from the same directory where you were working. Discovery is scoped to
the current project only (see below).

## How it works

1. **Discover.** Claude Code stores each conversation as a transcript at
   `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl` (the encoded dir is your
   working directory with every `/` and `.` turned into `-`). The script scans
   only the directory matching your current `$PWD`. A session counts as
   *limit-paused* when its last usage-limit `api_error` record is **not** followed
   by any later user/assistant turn (a later turn means you already continued it).
   Sessions whose pause is older than `--since` (default 24h) are ignored, so old
   abandoned sessions aren't resurrected.

2. **List.** The discovered sessions (oldest pause first) are printed, then it
   proceeds automatically. `--dry-run` stops here.

3. **Resume.** Each session is resumed **sequentially** (parallel would just
   re-hit the shared limit immediately). For each one it runs
   `claude -r <id> -p "<nudge>"` and reacts to the result:
   - **success**: done, move to the next session;
   - **limit**: read the reset time from the *live* error (so timing is always
     current, never stale history), sleep until then plus `--buffer`, and retry,
     up to `--max-resumes` times;
   - **any other error**: skip that session and mark a non-zero exit (one bad
     session never aborts the run).

   Because timing comes from the live error, it self-corrects: if the window has
   already reopened by the time it runs, the first attempt just succeeds.

## Options

| Flag | Default | Purpose |
|------|---------|---------|
| `--dry-run` | off | List paused sessions and exit; resume nothing. |
| `--since DUR` | `24h` | Ignore sessions paused longer ago than this. |
| `--nudge STR` | `continue` | Message sent to resume each session. |
| `--max-resumes N` | `12` | Max limit-retries per session before giving up. |
| `--retry-interval DUR` | `15m` | Sleep used when a reset time can't be parsed. |
| `--buffer SEC` | `60` | Extra seconds slept past the reset time. |
| `--claude-args "..."` | none | Extra args passed through to `claude` (e.g. `--allowedTools`). |
| `--yolo` | off | Add `--dangerously-skip-permissions` (unsafe; warned). |
| `--log FILE` | none | Also append status lines to `FILE`. |
| `-h`, `--help` | | Show usage. |

`DUR` accepts bare seconds or an `<n>[smhd]` suffix: `30s`, `15m`, `24h`, `2d`.

## Permissions

Headless resumes run without a human to approve tool calls, so you must choose a
permission strategy up front. The script never loosens permissions on its own:

- **Recommended:** pass an allowlist, e.g.
  `--claude-args "--allowedTools Bash Edit Read"`.
- **Escape hatch:** `--yolo` adds `--dangerously-skip-permissions`. Only use this
  in an environment you trust; it prints a warning.

## Examples

```bash
# Resume, but only sessions paused in the last 3 hours:
tools/claude-autoresume.sh --since 3h --claude-args "--allowedTools Bash Edit Read"

# Longer nudge and a run log you can tail from another terminal:
tools/claude-autoresume.sh \
  --nudge "keep going where you left off" \
  --log ~/autoresume.log \
  --claude-args "--allowedTools Bash Edit Read"

# Trusted sandbox, fully hands-off:
tools/claude-autoresume.sh --yolo
```

## Known limitation

At authoring time there was no real usage-limit (`429`) event in local history to
match against, only `529 overloaded` and connection errors. The usage-limit
detection is therefore a best reconstruction of the format, isolated in a single
config constant, `LIMIT_PATTERN` (overridable via the environment). The first
time you actually hit a limit, check the offending transcript's `api_error`
record and tune `LIMIT_PATTERN` in one place if the wording differs.

## Design & tests

- Design: `docs/design/claude-autoresume.md`.
- Tests: `tests/test_claude_autoresume.py` drives the script as a subprocess with
  a fake `claude`, a recording fake `sleep`, and fixture transcripts (via the
  `CLAUDE_BIN`, `AUTORESUME_SLEEP`, `AUTORESUME_NOW`, and `PROJECTS_DIR`
  environment overrides), so the suite needs no API access and never really
  sleeps. Run with `uv run pytest tests/test_claude_autoresume.py`.
