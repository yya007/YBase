# ADR 0004: The leak hook applies private terms only to YBase

- Status: Superseded in part by [ADR 0005](0005-leak-hook-strict-everywhere.md): the hook no longer relaxes its rules for other repos. The `LEGACY_PATHS` decision and the open question still stand.
- Date: 2026-11-14

## Context

YBase keeps private terms in each knowledge base's `deny.list`, which is never committed. The `leaks` check reads those terms and refuses them in YBase's files and commit messages. The commit-time leak hook (`.claude/hooks/leak_hook.py`) refuses them in a commit message, a staged line, a tag message or PR text before the text is written down.

The deny list holds the names of the repos YBase manages, since YBase itself must never name them. Most work, though, happens in those managed repos, from a session started in YBase. The hook applied every deny-list term and every built-in pattern to any `git commit`, `git tag` or `gh pr` command, whichever repo it targeted. So an ordinary commit in a managed repo whose message named that repo was refused, and a clean message was refused when a staged file held any email address.

The `leaks` check had a related gap. It skipped only `memory/` and two old setup scripts, while `tests/test_no_private_terms.py` skipped every path that a later step of the consolidation moves or deletes. Filling `deny.list` as the design says would then have failed YBase's own gate on files that are about to go.

## Decision

The leak hook decides which repo a command targets: the working directory in the hook's payload, moved by any `git -C <path>`. It compares that repo's main checkout with YBase's main checkout, which it finds from its own file location, so a worktree counts as its repo.

- On YBase or one of its worktrees, every built-in pattern and every deny-list term apply, as before.
- On any other repo, only the secret and token patterns apply: a private key, a cloud access key, an account id in an ARN, a GitHub token, an API secret key, a model-hub token and a chat token. The deny list and the email and home-path patterns do not.
- The relaxed rules apply only to two recognised command shapes whose target is another repo: a plain `git` whose only options before the subcommand are `-C <path>`, and a plain `gh` with no repo selector (no `-R` or `--repo` in any position, no URL or `owner/name` argument, and no `GH_REPO` or `GH_HOST` in the environment). Anything else gets the strict rules. That includes a command the hook cannot split into words (a stray quote, as in a trailing `# don't`): if it names `git` or `gh`, its whole text is scanned. It also includes a payload with no working directory, a target outside any repo, and, anywhere on the line, any directory change (`cd`, `pushd`, `popd`), any wrapper command (`sudo`, `env`, `xargs`, `eval`, `time` and the like) and any setting whose name starts with `GIT_` or `GH_`. **ERRATUM 2026-11-14:** the first version of this bullet listed the cases the hook could not trace and treated as strict. A review found commands that target YBase and were read as another repo's, such as `gh pr create --title ... -R owner/YBase`, a `cd` inside braces and `sudo -D <dir>`. The hook now relaxes only the two shapes above.
- `LEAK_AUTHORIZED=1` as a prefix on the command still skips the hook for one call.

The `leaks` check skips the same paths as the private-terms test. Both read one declaration, `LEGACY_PATHS` in `tools/checks.py`. Its entries use prefixes, so none of them names a private term.

## Consequences

- An agent can commit in a managed repo under that repo's own name without the escape.
- Rule 22 still says a managed repo's artifacts never name YBase, its knowledge base or a sibling repo. The hook no longer enforces that in managed repos, since it cannot tell a repo's own name from a sibling's. The rule stands, and [`law/commit.md`](../law/commit.md) says so.
- A secret or token is still refused in every repo.
- A command whose target the hook misreads as another repo would skip the deny list. The hook's command recognition is best-effort: it does not see a `git` or `gh` run through an alias, a script, a function or a command substitution at all. So in YBase the `leaks` check, which YBase's pre-commit hook runs, remains the gate for commits, and PR text has no second gate. A false strict reading costs a refusal that `LEAK_AUTHORIZED=1` overrides. **ERRATUM 2026-11-14:** this bullet first said that every case the hook cannot trace falls back to the strict rules, so a misread needs a target that git itself reports as a different repo. That was false; see the erratum under Decision.
- `LEGACY_PATHS` shrinks as the consolidation moves or deletes those paths, and both the check and the test follow it. **ERRATUM 2026-11-14:** those paths are gone and the list is removed; no path is exempt from the `leaks` check.

## Open question

The `leaks` check also scans the author and committer identities of every commit after `.leaks-baseline` against the deny list. If a user puts their own handle on the list, every later commit is refused, because their identity carries the handle. There are three ways out: keep the handle off the list until the history is replaced, move the baseline, or drop the identity scan. Choosing among them is the owner's decision, and this ADR does not make it.

**Decided 2026-11-14:** the first way. The handle stays off the list while any commit in the scanned range carries it. The identity scan stays as it is. Once no scanned commit carries the handle, it can go on the list.
