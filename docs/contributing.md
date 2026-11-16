# Contributing to YBase

This page is for changes to the framework itself: the command line, hooks, checks, profiles, skills and docs. Changes to a managed repo follow that repo's own rules.

## Commands

The runtime needs only git, bash and Python 3. Development uses [`uv`](https://docs.astral.sh/uv/), which builds the virtual environment from `uv.lock` and runs every tool. Prefer `uv run` over a bare `python` or `pip`, which may not be on `PATH`.

| Task | Command |
|---|---|
| Install or sync the dev environment | `uv sync --extra dev` |
| Run the tests | `uv run --extra dev pytest` |
| Run the end-to-end journeys only | `uv run --extra dev pytest tests/test_journey.py` (each walks several commands in a scratch clone of the last commit, so commit before you run them) |
| Run the profile tests (bash 3.2) | `/bin/bash tests/test_profile.sh` |
| Run the check registry | `ybase check`, or `python3 tools/checks.py` |
| Run some checks only | `ybase check links leaks` (`--list` names them all) |
| Lint | `uv run --extra dev ruff check .` (`ruff format` is optional, on files you touch: the tree is not format-clean and CI has no format check) |
| Add or remove a dependency | `uv add <pkg>` or `uv remove <pkg>`, which update `uv.lock` |

Work in a worktree: `ybase wt <kind>/<subject>`. The checks find their root from their own location, so run the copy in the worktree you changed: `"$W/bin/ybase" check`.

## The gate

`tools/checks.py` declares every check once. Three things run it: `.githooks/pre-commit` on each commit, the `checks` CI workflow, and `ybase check`. The workflow runs on Ubuntu and macOS, each with Python 3.10 and 3.13. `ybase doctor` turns the git hook on in each clone (`core.hooksPath .githooks`).

A change is ready when the tests and the check registry both pass. Never skip the git hook with `--no-verify`. If a check is wrong, fix the check in the same change and say so.

The `checks` CI workflow is the one workflow: it runs the shell profile tests, `pytest`, `ruff check`, an unattended setup, a doctor dry run and the registry on Ubuntu and macOS. There is no second linter or commit framework; the registry is the only commit gate.

## Conventions

- **Python 3.10 or later, standard library only** for anything under `bin/`, `tools/`, `profiles/`, `.claude/hooks/` and `.githooks/`. A fresh machine may have no `uv` and no third-party packages. Tests may use `pytest`.
- **Bash 3.2, on GNU and BSD userlands.** No associative arrays, `mapfile`, `${var,,}`, `sed -i`, `readlink -f` or GNU-only flags. macOS ships bash 3.2 as `/bin/bash`.
- **Ruff**, line length 100.
- **Hooks fail open.** A hook that crashes, cannot parse its input or cannot read `.env` allows the call.
- **`.env` is parsed, never sourced.** Shell tools read it with `yb_setting KEY` (`tools/lib.sh`); Python tools with `tools/envfile.py`.
- **Docs change with the behaviour they describe**, in the same commit ([rule 24](rules.md#engineering)).
- **Plain English** for anything a person reads, and no em dash ([`writing.md`](writing.md)).
- **Commits** follow [`law/commit.md`](law/commit.md): one concern each, explicit paths, and a message written for a reader outside the repo.
- **The licence is noncommercial** ([ADR 0007](adr/0007-publish-by-snapshot-noncommercial.md)). Do not add code or text whose licence forbids that, and do not call YBase open source.
- **Nothing private.** The framework must stay true and harmless for a stranger. A repo name, a path, an employer or a person goes in your KB, never here ([`kb.md`](kb.md)).

## Add a machine profile

1. `cp -R profiles/_template profiles/<name>`, then fill in `profile.sh` (scratch, worktrees, setup and doctor probes) and `NOTES.md` (what is true of every machine of this type).
2. If the type can be recognized from local files, add a branch to `yb_detect_profile` in `tools/profile.sh` and a case to `tests/test_profile.sh`. Otherwise users pin it with `ybase profile <name>`.
3. Run `ybase doctor --dry-run` on a machine of that type and read the report.

Add a profile when a class of machine needs a different setup, not when one machine has a quirk. Details: [`machines.md`](machines.md#adding-a-machine-type).

## Add a hook

Read [`law/checks.md`](law/checks.md) first.

1. Write `.claude/hooks/<name>_hook.py` in the standard library. Its module docstring says what it refuses, what passes and how to get past it.
2. Make it fail open: malformed input, an unparseable command and an internal error all allow the call. Decide from parsed tokens, never by substring.
3. Wire it in `.claude/settings.json`, copying the shape of an existing entry.
4. If it enforces a working style rather than a safety property, make it opt-in: it runs only when a `YBASE_GUARD_<NAME>=1` key is in the environment or `.env`. Add the key to the table in [`machines.md`](machines.md) and to the `.env` header in `tools/setup.sh`.
5. Add tests under `tests/`, watch them fail on a planted case, and add the hook to the table in [`architecture.md`](architecture.md#hooks) and the rule to the table in [`codex.md`](codex.md).

The `hooks` check refuses a hook that is not wired, a wired hook that does not exist, and a hook with no docstring.

## Add a check

1. Write a function `check_<name>(ctx)` in `tools/checks.py` that returns `(scanned, findings)`. Its docstring's first line is what `--list` prints.
2. Add it to `CHECKS` at the bottom of the file. That list is the only registry.
3. Add tests in `tests/test_checks.py`: a planted violation that fails and a near miss that passes.
4. Add a row to the checks table in [`architecture.md`](architecture.md#checks).

## Add a KB layout step

When a change alters the knowledge base layout, bump `templates/kb/VERSION`, add the step to `MIGRATIONS` in `tools/kb_migrate.py` and add a test for it. A step never touches git and must be safe to run twice. Details: [`kb.md`](kb.md).

## Add a skill or a moment rule

- A skill: follow [`.claude/skills/README.md`](../.claude/skills/README.md), "Adding a skill".
- A moment rule: add the moment to the table in `.claude/hooks/moment_law_hook.py`, write `docs/law/<moment>.md`, and add a line to [`law/README.md`](law/README.md) and [`codex.md`](codex.md) in the same commit. The `law` check keeps the hook and the files in step.
