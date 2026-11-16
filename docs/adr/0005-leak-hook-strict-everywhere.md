# ADR 0005: The leak hook applies the same rules in every repo

- Status: Accepted
- Date: 2026-11-14
- Supersedes: the scope decision in [ADR 0004](0004-leak-hook-scope.md)

## Context

ADR 0004 let the commit-time leak hook (`.claude/hooks/leak_hook.py`) apply only the secret and token patterns to a command that targets a repo other than YBase. The aim was to let a managed repo's commit name that repo, which the deny list holds, without an escape.

To do that the hook had to work out which repo a shell command targets. It reads the command as text, so it models shell grammar by hand. Three reviews in a row found commands that target YBase and were read as another repo's:

- a repo selector that comes from a shell variable, as in `U=<PR URL>; gh pr comment "$U" ...`;
- a directory change the hook did not recognise, as in `X=cd; $X <dir>` or zsh's `chdir`;
- a command the tokeniser could not split, which was allowed unchecked.

Each fix narrowed the relaxed case and the next review found another route. The cause is structural: the relaxed rules are only as safe as the hook's reading of the shell, and that reading cannot be made complete.

## Decision

The hook applies every built-in pattern and every deny-list term to every `git commit`, `git tag` and `gh pr` command it recognises, whichever repo the command targets. It no longer works out the target, and the code that did so is removed.

`LEAK_AUTHORIZED=1` as a prefix on the command, or in the environment, skips the hook for one call. That is the way to commit in a managed repo when the message or the staged lines hold a term on the list, the repo's own name included.

## Consequences

- No reading of the command can lower the rules applied to the message, tag or PR text the hook finds, so the routes above are closed as a class.
- The staged lines are a weaker surface. The hook reads the diff in the payload's working directory, moved by `git -C <path>`. A commit that reaches its repo another way (a `cd` first, `GIT_DIR`, `--git-dir`, or a payload with no working directory) has its message checked but not its staged lines. This was true before this decision too.
- A managed repo's commit that names the repo, or stages an email address or a home path, is refused until the command carries the escape. The escape is on the command line, where a later reader sees it.
- The escape skips every pattern for that call, secrets and tokens included. Use it only when the user has said the text may ship.
- Recognition is still best-effort. A `git` or `gh` run through an alias, a script, a function, `eval` or a command substitution is not seen, and some message spellings are not read (`-m"x"` with no space, `--mess=`, `-F -`). In YBase the `leaks` check that the pre-commit hook runs remains the gate for commits. PR text has no second gate.
- Rule 22 is enforced by the hook again for terms on the list: a managed repo's artifacts that name a sibling repo are refused like any other private term.
