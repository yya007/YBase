# `.claude/skills/`: procedures an agent runs by name

## TL;DR

- **One folder per skill, one tree for every agent.** Each kebab-case folder holds a `SKILL.md` with `name` and `description` in its frontmatter. Claude Code loads this directory directly; Codex reaches the same files through the tracked `.agents/skills` symlink. Invoke a skill as `/name` in Claude Code or `$name` in Codex.
- **A skill is a procedure an agent executes start to finish.** A procedure a person reads and follows is a flow, in [`docs/flows.md`](../../docs/flows.md). Where both cover the same ground, the skill holds the steps and the flow keeps a one-line pointer.
- **A skill routes; it does not restate.** When a rule already has a home (`docs/rules.md`, `docs/law/`, `docs/writing.md`, `docs/kb.md`, `docs/casebook/`), the skill names that home and the agent reads it. A copied rule keeps reading like an instruction after the original changes.
- **Repo-neutral and machine-neutral by construction.** A skill acting on a repo takes it by name from the repo list (`ybase repos path NAME`), defaults to YBase itself, reaches it with `git -C <path>`, and defers to that repo's own `AGENTS.md` for how work lands. A skill never hardcodes a path, a host, a repo name or a harness variable. Scratch is the profile's (`ybase env`), and anything harness-specific names the other harness's path too.

## The contract

| Folder | What belongs | What does not |
|---|---|---|
| `session-scope/` | the one definition of the ownership tiers and write classes; the read-only inventory of what this session owns (`tools/session_inventory.py`), the harness's own listings and the untracked side, with two verdicts per row | landing, stopping or deleting anything; reconciling against boards or the worklog; peer sessions' rows |
| `session-check/` | reconciling this session's rows against the record (a knowledge-base research topic's `projects/` boards, the primary KB's `worklog/`, lessons in the KB and `docs/casebook/`, pushed branches and PRs in each repo touched) into landed, in flight, stranded, owed and next; writes nothing | finding out what the session owns (`session-scope`); any write, land or reap (`session-closeout`); auditing other sessions |
| `session-closeout/` | ending a session: the liveness gate, landing under each repo's own rules (a draft PR by default), verifying from the remote, writing the board, the worklog in the primary KB and the owed lessons, stopping or registering what outlives the session, reaping only provably finished owned worktrees | mid-session status (`session-check`); other sessions' worktrees or branches; merging or marking a PR ready without the user |
| `git-forward/` | for YBase or a managed repo: finding every uncommitted, unpushed, untracked or stashed change the landing refs lack, judging each by content, one disposition per finding, and landing the `land` ones under the repo's own rules | removing worktrees (`cleanup-worktrees`); a session's own tree (`session-closeout`); PR mechanics (`land-pr`); deleting anything |
| `cleanup-worktrees/` | the sweep of linked worktrees no session owns, in YBase or any managed repo from the repo list: dry run, reading every refusal, asking the user, reaping only trees every check cleared, verifying the count afterwards | judging whether kept work is new (`git-forward`); a session's own tree (`session-closeout`); forced removal or branch deletion without the user's yes |
| `review-pr/` | reviewing someone else's PR in any repo: refuse your own, read facts from the PR head, sweep, verify each finding against the head, draft every comment in chat (one finding each, a question plus an option), post one review only on the user's say-so, read it back | your own PR (`land-pr`); a self-review of an uncommitted diff; deciding to request changes for the user |
| `land-pr/` | taking your own open PR from first review to merged, under the repo's own landing rules: verify each finding against the head, count the cases it claims, fix with a test that fails first, get an independent review of the patch, reply and re-request, merge only on the user's say-so, read the merge back | someone else's PR (`review-pr`); opening a PR; splitting or re-scoping it; force-pushing or admin merges |
| `proofread/` | judging a draft someone will read or act on: the mechanical gate, six lenses that read `docs/writing.md`, `docs/rules.md` and, for a research note, its topic's `PIPELINE.md` as instructions, triage and the report shape | the writing rules themselves; code review; a pre-publication scrub against private originals (`docs/casebook/publishing.md`) |
| `retro/` | a retrospective over this machine's recent Claude Code and Codex transcripts through `tools/retro.py`: distil (fed between runs by the SessionEnd and PostToolUse hooks in Claude Code), derive what the rules, the casebook and the KB lessons cover, rank, read the top few spans, date each candidate against what landed since, write candidates to the gitignored `.ybase/retro/inbox/` | promoting a candidate into a lesson or `docs/rules.md` (a human step, `docs/kb.md`); any transcript content in a tracked path; wiring the hooks (`.claude/settings.json`) |
| `consolidate-branch/` | squashing and moving a long-lived branch others still push to: reconcile by merge and plain push first, announce and freeze, archive the tip on the remote, squash by tree with an empty-diff proof, one force-with-lease on the branch's own ref only with the user's yes, then the audit against the archived tip | any branch you do not own, or the default branch; a branch a plain rebase handles; landing (`session-closeout`); judging trees left on the old history (`git-forward`); deleting an archive ref |
| `gpu-census/` | who holds the GPUs and who waits: the local census from `nvidia-smi` joined to `ps`, the cluster census from pods requesting `nvidia.com/gpu` when `kubectl` is present, each holder attributed to an owner, running separated from pending (with the reason) and from finished; reads only | deciding whether you may launch (the profile notes, and the repo or research topic in hand); diagnosing one job's internals; submitting, cancelling or preempting anything |
| `codex-delegation/` | handing large-output or second-opinion work to the Codex CLI through its read-only profiles (`review`, `critique`, `docs`, `plan`, `brainstorm`), keeping the full output on disk and a short digest in context, under the switches in `.agents/codex-delegation.json` | write-capable Codex work; small edits or quick answers; applying review or critique findings without a decision on each |
| `harvest/` | finding configuration, skills and conventions repeated across the managed repos and proposing generalised versions for YBase, as a table the user approves before anything is written; the leak check is `ybase check leaks` and its patterns run on each file | content true of one repo only; copying one repo's details into another; general-purpose skills (the user's own skill library); any change inside a managed repo |
| `adopt/` | the first run on a machine with existing repos: inventory the git repos under the repos root and every skill and agent-facing doc (user-level skill folders included), sort each into shared, duplicate, repo-specific or installed, ask in numbered rounds, and after approval write `repos.md` in the primary KB and run `ybase repos render` | reading `.env` or secret files; pushing anything; a change in a child repo except on a new local branch; editing user-level folders (the user runs those commands) |
| `cross-repo-issues/` | listing open issues across the managed repos that have a GitHub remote (`gh issue list -R`), grouped by repo, and filing a new issue in the repo it belongs to after showing the draft; posting only on the user's say-so | working on an issue; editing, closing or commenting on existing issues unasked; linking one repo's issue to a sibling repo |
| `review-skill/` | auditing one or all skills (YBase's, or a managed repo's by path) against a quality rubric (completeness, structure, output contracts, internal consistency) into a markdown report; with `--fix`, a narrow set of safe patches | writing a new skill; changing what a skill does beyond those safe patches |

## What earns a skill

All three must hold:

1. **An agent executes it**, start to finish, with a fixed output shape.
2. **It depends on something in this repo**: a tool under `tools/`, a check, a document contract. A procedure that depends on nothing here belongs in a personal skills folder, where it works in every project.
3. **It is worth invoking by name.** A step inside another procedure is a paragraph in that procedure.

## Cross-agent contract

- Frontmatter carries `name` (equal to the folder name) and a single-line `description` that says **when** to invoke the skill, since that is what an agent matches against. The `skills` check enforces both.
- A Claude Code tool (subagents, task lists, `CLAUDE_JOB_DIR`) is allowed only when the skill also gives the Codex path, or says that part is unavailable there.
- Scratch goes in the profile's scratch directory: `eval "$(ybase env)"` sets `TMPDIR`.
- **Checks run from the tree they check.** `bin/ybase` and `tools/checks.py` find their root from their own location, and the `ybase` command runs the copy in the checkout you stand in. A session stands in the main checkout (rule 23), so `ybase check` typed there checks only the main checkout. For work in a YBase worktree `$W`, run `"$W/bin/ybase" check` (and `bash "$W/tests/test_profile.sh"`). A worktree has no `.env`, so its `leaks` check reads the knowledge-base settings of its main checkout. A managed repo runs the checks its own `AGENTS.md` names, never YBase's.
- `.claude/skills/` is canonical. Never write a `SKILL.md` under `.agents/skills/`; that path is a view of this one.

## Vocabulary has one definer

Where several skills reason about the same things, one of them defines the words and the others link to that definition. [`session-scope`](session-scope/SKILL.md) defines the ownership tiers and write classes that `session-check` and `session-closeout` use.

## Adding a skill

1. Create `<slug>/SKILL.md` with `name` and `description`.
2. Add its row to the contract table above.
3. Give every Claude-specific step a Codex path.
4. If the skill replaces a flow, shrink the flow to a pointer in the same commit.
5. `"$W/bin/ybase" check skills links framework-style`, from the worktree `$W` that holds the change.
