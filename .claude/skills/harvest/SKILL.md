---
name: harvest
description: Use when asked to harvest, lift, promote or standardise what several managed repos have in common (agent docs, configuration, skills, hooks, checks, conventions), or after a repo is added or a repo has seen substantial work; finds what repeats across the managed repos and proposes generalised versions for YBase as a table the user approves before anything is written.
---

# harvest: lift what every managed repo repeats into YBase

Good conventions usually appear in one repo first: a sharp `AGENTS.md` section, a pre-commit setup, a PR template, a skill that removes a recurring friction. When the same thing shows up in several managed repos, it is probably true of every repo, and YBase is where such things live ([`docs/rules.md`](../../../docs/rules.md) rule 21). This skill is the pull direction: survey the managed repos, find what repeats, strip what is specific to one repo, and propose a generalised version for YBase. Nothing is written until the user approves the proposal row by row. The push direction, a shared rule reaching a repo by being copied into its own `AGENTS.md` (rule 22), is a change in that repo and not this skill.

## When not to use

- Content true of one repo only. It stays in that repo (rule 21).
- Copying one repo's details into another repo. That is a change in the receiving repo, made there under its own rules.
- A general-purpose skill that does not manage the home. YBase ships only skills that manage the home ([`README.md`](../README.md), "What earns a skill"); propose it for the user's own skill library instead and stop there.
- A lesson. Lessons are routed by [`docs/kb.md`](../../../docs/kb.md): private ones to the primary knowledge base (KB), generic ones to `docs/casebook/`.

## Ground rules

- **Read-only until approved.** Stages 1 to 6 read. The only write before approval is the proposal file in scratch.
- **Never change a managed repo.** Every read goes through `git -C <path>` from the YBase root (rule 23). A repo that should change is a separate task in that repo.
- **Never read `.env`, secret files or local settings** in any repo: `.env*`, `*.pem`, `*.key`, credential files, `.claude/settings.local.json`. Read only tracked files (`git -C <path> ls-files`).
- **The proposal is private.** It names managed repos, so it lives in scratch and in chat, never in a YBase commit, branch name or PR (rule 19).
- **Idempotent.** If nothing new repeats, the proposal is empty. Do not invent work.

## Stages

1. **Inventory the repos.**
   ```bash
   eval "$(ybase env)"; mkdir -p "$TMPDIR/harvest"
   ybase repos                      # name, local path, present or missing
   ```
   For each present repo: `git -C <path> rev-parse --git-dir` (skip and report a path that is not a repo), `git -C <path> ls-files | wc -l` (skip and report an empty repo), and `git -C <path> remote get-url origin` for context. Read its `AGENTS.md` first (rule 20): it may say which of its files are meant to stay local. A `missing` repo is reported as not surveyed, never as having nothing to lift. Guards against: a proposal that silently covers half the repos.

2. **Survey each repo.** Read these tracked paths where they exist; this is the menu of candidates, so do not hunt for files that are not there:
   - Agent docs: `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, the docs `AGENTS.md` names.
   - Agent config: `.claude/settings.json`, `.claude/hooks/`, `.claude/commands/`, `.claude/agents/`, `.claude/skills/`, `.agents/skills/`, `.codex/`.
   - Engineering config: `.pre-commit-config.yaml`, `.github/workflows/`, `.github/pull_request_template.md`, `.gitignore`.
   - Opinionated tool settings in `pyproject.toml`, `package.json`, `tsconfig.json`, linter configs: line length, target version, lint rules. Not dependencies.

   For each asset record the repo, the path, a one-line summary and its blob (`git -C <path> rev-parse HEAD:<file>`), so identical copies are found by hash rather than by eye. Write the survey to `$TMPDIR/harvest/survey.md`.

3. **Find what repeats.** Group the assets by kind and compare across repos. The same blob in two or more repos is the strongest signal. Near-identical copies (`diff` the two files) are the next: pick the richest as the base and note what each other copy adds. An asset found in one repo only is weak evidence; lean towards `leave` unless it is plainly universal.

4. **Check YBase first.** Before proposing anything, look for the equivalent YBase already has, and read it:

   | Kind | Where it lives in YBase |
   |---|---|
   | always-on rules | `docs/rules.md` |
   | rules for one moment (commit, push, PR, review) | `docs/law/` |
   | long procedures | `docs/protocols/` |
   | lessons | `docs/casebook/` |
   | guards and allow lists | `.claude/hooks/`, `.claude/settings.json` (a short reviewed allow list only; broader approvals stay in each user's local settings) |
   | named procedures | `.claude/skills/` |
   | templates | `templates/` |
   | checks | the registry in `tools/checks.py` |
   | machine facts | `profiles/<type>/NOTES.md` |

   A rule the user wants for their own repos but which is not true of every user's repos goes to the primary KB's `rules.md`, not the framework. If YBase's version is older or thinner, propose an **update**, never a duplicate.

5. **Classify.** Each candidate lands in exactly one bucket:

   | Bucket | Means | Action |
   |---|---|---|
   | `lift-verbatim` | already generic: no repo name, domain term, product path or hardcoded branch | copy as it stands |
   | `lift-distilled` | generic at heart, with repo-specific sections or values | copy, then generalise (stage 6) |
   | `update` | YBase has it, and the repos carry something it lacks | a surgical change to the YBase file |
   | `in-ybase` | YBase already has the same thing | nothing; record it so the next pass skips it |
   | `leave` | its value is in one repo's specifics | nothing; record the reason |

   Ask in order: does YBase already have it; is it about one repo's domain; are generic and specific parts mixed; would it drop into any repo unchanged. When unsure, choose `leave`: a missed lift comes back next pass, a contaminated framework file is published.

6. **Generalise.** For `lift-distilled` and `update` rows, apply these transforms to a draft in `$TMPDIR/harvest/`:
   - A hardcoded `master` or `main` becomes a lookup: `git symbolic-ref -q --short refs/remotes/origin/HEAD`.
   - A path that exists in one repo only is dropped, or kept as an explicit example.
   - A section about one product (mission, domain workflow, product skills) is dropped whole, not rewritten.
   - Domain vocabulary is removed unless its meaning is generic.
   - Repo names, owners, hosts and local paths become generic examples: `my-repo`, `example.com`, `<path>`.

   Then run the leak check on each draft: the same patterns as `ybase check leaks`, on the one file, as the [`proofread`](../proofread/SKILL.md) skill's stage 2 shows. Run it from the YBase root, where it reads the `deny.list` of every KB. If no `deny.list` has an uncommented line, the private-term half checked nothing: say so, and ask the user to fill the primary KB's `deny.list` before stage 8.

7. **Propose, and stop.** Write the proposal to `$TMPDIR/harvest/proposal-<YYYY-MM-DD>.md` and show it in chat:

   ```
   harvest: <YYYY-MM-DD>   repos surveyed <n> of <m> (not surveyed: <names and why>)

   | # | What | Found in | Bucket | Destination | Change | Why it holds for every repo |
   |---|------|----------|--------|-------------|--------|-----------------------------|
   | 1 | PR template | repo-a, repo-b (same blob) | lift-verbatim | templates/... | add | ... |

   skipped: <# or asset>: <in-ybase | leave>: <reason>
   leak check: <findings, or clean>; deny.list: <n terms | empty>
   ```

   Group the rows into the commits they would become, one scope each (rules, a skill, a template, a check). Ask the user to approve, change or drop each row, as numbered questions with your recommendation. Nothing is written until they answer.

8. **Apply the approved rows.** In a worktree, never the main checkout (rule 15):
   ```bash
   ybase wt docs/harvest-<scope>
   ```
   `W` is the worktree path it prints. Write each approved row from its stage 6 draft, then run `"$W/bin/ybase" check` and fix what it reports. The root `bin/ybase` checks only the main checkout, which does not hold these files ([`README.md`](../README.md#cross-agent-contract)). Commit one scope at a time, staging named paths. A commit message says what was generalised and why it holds for every repo; it never names a managed repo, since that name is private (rule 19). Record the provenance (which repos each lift came from) in the worklog of the primary KB instead. Land through a draft PR as [`docs/law/pr.md`](../../../docs/law/pr.md) says. Never push to the default branch unless the user says to.

9. **Verify.** Read the result back from the remote, not from the push output (rule 5): the branch tip, the PR, and `"$W/bin/ybase" check` on the tree you pushed. Re-run stage 6's leak check, from the YBase root, against the committed files.

## Output

```
harvest: <YYYY-MM-DD>   repos surveyed <n> of <m>
proposed <k> rows: <a> lift-verbatim, <b> lift-distilled, <c> update; skipped <d> (in-ybase <e>, leave <f>)
approved <j>; applied in <branch> -> draft PR <url> at <sha>, read back from the remote
leak check: <clean | findings fixed>; deny.list <n terms | empty>
provenance: <KB worklog file>
not done: <rows declined or deferred, and why>
```
