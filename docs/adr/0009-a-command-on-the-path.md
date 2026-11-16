# ADR 0009: Setup puts a `ybase` command on the PATH

- Status: Accepted
- Date: 2026-11-15

## Context

Every command was typed as `bin/ybase <command>`, which works only from the root of the clone. The prefix appeared in every doc, skill and message. It also read as a file path, not as the name of a tool.

Setup had so far written nothing outside the clone unless a flag asked for it.

## Decision

1. **Setup writes a launcher.** `bin/ybase setup` writes a small shell file named `ybase` into `~/.local/bin`. Docs, skills and messages say `ybase <command>`. Only `bin/ybase setup` keeps the prefix, because it is the command that creates the launcher.
2. **The launcher runs the checkout you stand in.** It walks up from the current folder to the first folder that holds `bin/ybase` and `tools/profile.sh`, and runs that copy. Outside any checkout it runs the main checkout that installed it. A worktree therefore runs its own code, and a managed repo gets the main checkout's.
3. **It points at the main checkout, never at a worktree.** Setup run from a worktree records the main checkout, so removing the worktree does not break the command.
4. **It stays out of what it does not own.** Setup never replaces a file it did not write, and never edits a shell profile. When the folder is not on the PATH it prints the line to add.
5. **It can be switched off.** `YBASE_LAUNCHER=off` installs nothing, and so does the `ci` profile, whose jobs call `bin/ybase` by path.
6. **The machine file says which form works.** The doctor writes `command: ybase` or `command: bin/ybase` into `.ybase/MACHINE.md`, so an agent on a machine without the launcher knows to use the path.

## Alternatives considered

- **Tell each person to add `bin/` to their PATH.** Rejected: it edits a shell profile, and a worktree would run the main checkout's code and not its own.
- **A shell alias or function.** Rejected: an agent's shell does not load aliases.
- **A separate `launcher install` command.** Rejected: one more step on every machine, for a file that is safe to write and easy to refuse.
- **Install the project as a Python package with a console script.** Rejected: the entry point is a shell script, and a package install is tied to one environment.

## Consequences

- Setup now writes one file outside the clone without a flag. The file carries a marker line, and setup rewrites only a file with that marker.
- A test that runs setup must not reach the real folder. `tests/conftest.py` points `YB_BIN_DIR`, the test-only override for the folder, at a throwaway one for the whole run.
- A worktree runs its own code but has no `.env`. The shell tools now read the main checkout's `.env` from a worktree, as the Python tools already did.
- The launcher runs whatever checkout it finds above the current folder. Typing `ybase` inside a copy you do not trust runs that copy's code, as running its `bin/ybase` would.
- Moving the clone leaves the launcher pointing at the old place. The launcher then names that place and says to run setup again.
- `"$W/bin/ybase" check` stays the way to check a worktree from a session that stands in the main checkout.
