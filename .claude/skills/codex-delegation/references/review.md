# Profile: review

Large-diff and pre-merge review, run through Codex's built-in reviewer.

## When

- `review_changed_lines` or `review_changed_files` threshold tripped
- Pre-merge adversarial pass on a branch
- A diff large enough that reviewing it in the main thread would crowd out the task

## Command

Branch scope (the common case). **Discover the default branch; never hardcode `origin/master`.** It differs between repos, and the wrong base either reviews nothing or reviews the whole history:

```
git -C <path> symbolic-ref --short refs/remotes/origin/HEAD
```

That fails in clones where `origin/HEAD` was never set. Fall back to:

```
git -C <path> remote show origin
```

and read its `HEAD branch:` line. Do not guess `master` when both fail. Ask, because
reviewing against a wrong base fails silently rather than loudly.

Paste the result as the base:

```
codex exec -C <path> review --base origin/<default-branch> -o <artifact>
```

Working-tree scope:

```
codex exec -C <path> review --uncommitted -o <artifact>
```

Single commit:

```
codex exec -C <path> review --commit <sha> -o <artifact>
```

**No `-s/--sandbox` flag exists on `codex exec review`**: passing one errors. This path relies on the built-in reviewer being non-mutating, which is an assumption about the CLI rather than an enforced sandbox. See the invariant in `SKILL.md`.

**`--base` and a custom prompt are mutually exclusive**: Codex rejects the combination. When custom framing is needed, use `--uncommitted` or `--commit` with a prompt, or use the `critique` profile instead.

The built-in reviewer already carries a review prompt, so no prompt text is passed for `--base` runs. This is why `review` and `critique` are separate profiles rather than one parameterized profile.

**Consequence for re-entrancy:** because `--base` sends no prompt, the "do not delegate further" suffix cannot be attached on this path. The `CODEX_SESSION_ID` guard in `SKILL.md` Step 0 is the only protection here, which is why that guard is mandatory rather than advisory.

**`<path>`** is the checkout or worktree under review: YBase's own, or a managed repo's from `ybase repos path NAME` or `ybase worktrees --repo NAME`. Scope with `git -C <path>` from the YBase root and pass `-C <path>` to Codex. Do not `cd` into a managed repo: [`docs/rules.md`](../../../../docs/rules.md) rule 23 forbids it because it wedges the hooks.

## Output contract

Codex's native reviewer emits findings with file paths and line numbers. When passing custom instructions (non-`--base` scopes), append:

```
Lead with a single VERDICT line: one of "ship", "revise", or "block", followed by a
one-sentence reason. Then list findings ordered by severity, highest first. For each
finding give: severity, file:line, what is wrong, and why it matters. Mark anything you
could not verify against the code as an explicit inference. End with what you did not
review and why. Do not propose patches; findings only.
```

## Handling

Findings are **claims, not facts** until checked against the repo. Present them, ordered by severity, with paths verbatim. Then stop and ask which to act on. Do not fix anything as part of the review. That invariant holds even for one-line obvious fixes, because an unverified finding applied blind is how a review makes code worse.
