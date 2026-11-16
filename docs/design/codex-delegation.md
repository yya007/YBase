# Codex Delegation: Design

- Date: 2026-08-23
- Status: Implemented, then revised the same day after an adversarial Codex critique of this
  very design found real defects (recursion deadlock, an unachievable sandbox invariant, a
  false allow-gate rationale, and an overstated cost claim). Revisions are recorded in
  **Post-implementation critique** below.
- ADR: `docs/adr/0002-codex-delegation.md`
- Note, 2026-11-13: paths below are as they were on 2026-08-23. The skill now lives in `.claude/skills/codex-delegation/`, artifacts
  go to `$YBASE_SCRATCH/codex/`, and managed repos sit beside YBase instead of inside it.

## User outcome / problem

Codex is installed and occasionally used here, but ad-hoc. Two benefits go uncaptured:

1. **Cost, specifically, caller-context cost.** Large output, a review of a big diff, a
   long document, a multi-task plan, occupies the caller's context when generated in the
   main thread, and is re-paid in the prompt on every later turn. Delegating moves that
   generation elsewhere; the caller carries a digest instead.

   State this precisely, because the loose version is false: **delegation does not reduce
   total tokens across both models.** A second model cold-reads the repository and generates
   the full answer, so total consumption goes *up*. What goes down is the caller's context
   occupancy and the compounding re-payment of that output on every subsequent turn. Whether
   it is a net win depends on the relative cost of the two models and how many turns follow,
   for a long thread that would otherwise carry a large review in-context, it usually is; for
   a one-shot task that ends immediately afterward, it usually is not.
2. **Perspective.** A model critiquing its own design produces a defense. A different model
   reading the repo cold produces a critique. That independence is what makes adversarial
   review, design critique, and alternative-approach generation worth running at all.

Existing usage captured (2) partially and (1) not at all: a saved lesson from one managed repo
records reading Codex's verdict "from the `^codex$` marker", which means the full dump had
already landed in context.

## Constraints and non-goals

**Constraints**

- Prompt-only. No runner script, no job registry, no subagent. (Explicit user decision.)
- Must not couple to the official plugin's version-pinned internals.
- Commands prefer literals over `$(...)`. **Corrected 2026-08-23:** the original claim that
  `allow-gate.py` rejects *all* subshells was wrong, it permits `$(...)` when every inner
  command is allowed and the outer command still matches after substitution, and rejects
  backticks and process substitution outright. Literals remain preferred (they avoid the
  edge cases and stay legible in the artifact trail), but the prohibition was overstated.
- Commands must not echo environment values, `AGENTS.md` forbids echoing them into skill
  artifacts, so the gate tests variables rather than printing them.
- Must be easy to switch off, at master and per-profile granularity. (Explicit user decision.)
- Conform to the Agent Skills specification, per `AGENTS.md`.

**Non-goals**

- Write-capable delegation. Codex making edits stays with `codex:rescue`.
- Research delegation. Dropped from scope by the user.
- A shareable skill in the user's skill library. YBase-local "for now", per the user.
- Replacing subagent delegation. Cross-model delegation is a separate axis, not a substitute.

## Accepted decisions

| Decision | Rationale |
|---|---|
| Prompt-only skill, markdown only | Nothing to maintain across Codex/plugin upgrades |
| `codex exec -o <file>` for every profile | Writes only the final message; supersedes the `^codex$` marker workaround |
| Digest capped by bytes *and* lines | Dumping the artifact forfeits the cost benefit entirely; a line cap alone does not bound tokens |
| Five profiles: review, critique, docs, plan, brainstorm | Matches the user's scope; each gets its own output contract |
| Auto-delegate above measured size thresholds | User's choice over opt-in-only and over always-auto |
| Prompt profiles pass `-s read-only`; `review` cannot (no such flag) | This skill produces text; edits are `codex:rescue`'s job. The review path relies on the built-in reviewer being non-mutating, an assumption, not an enforced sandbox |
| Single config file `.agents/codex-delegation.json` | One place to look; `CODEX_DELEGATION=0` for a session override |
| Reuse `run.json` delegation fields | Existing schema already models delegation; no migration |
| `review` and `critique` are separate profiles | `--base` cannot combine with a custom prompt |
| Permission scoped to `codex exec *` + `codex --version` | Blanket `codex *` would authorize unrelated subcommands |

## Open questions

- **Threshold calibration.** Initial values (400 changed lines, 8 files, 600/800 words, 5
  tasks) are estimates. They need a few real delegations to tune; too low burns runs on work
  the main thread could do, too high never fires.
- **Promotion to the user's skill library.** Nothing here is YBase-specific except the allow-gate
  caveat and the run-artifact paths. If it proves out, it is a shareable-skill candidate.
- **Digest quality.** The 40-line cap assumes profiles' output contracts front-load the
  verdict. If Codex drifts from the contract, the cap truncates something useful, watch for
  this before raising the cap, since raising it is the wrong fix.

## Acceptance criteria

- `enabled: false` or `CODEX_DELEGATION=0` results in local work and a one-line notice.
- A delegation writes a file under the artifact directory and reports its path.
- No profile's normal path reads more than `digest_lines` lines of the artifact.
- No skill command echoes an environment value.
- No skill command relies on `$(...)` where a literal would do.
- A delegate never spawns a nested delegation (`CODEX_SESSION_ID` guard).
- An infrastructure failure produces labeled local work, never an undone task.
- A review or critique never results in an edit without an explicit decision.
- A failed or uninvoked Codex run is reported as such, never replaced by a local answer
  presented as the delegation's output.
- Every skill command's flags exist in the installed Codex CLI.

## Canonical targets

- `.agents/skills/codex-delegation/SKILL.md` + `references/{review,critique,docs,plan,brainstorm}.md`
- `.agents/codex-delegation.json`
- `.agents/skills/.gitignore` (whitelist)
- `.claude/settings.json` (permission rules)
- `AGENTS.md` (cross-model delegation doctrine)
- `docs/adr/0002-codex-delegation.md`

## Post-implementation critique (2026-08-23)

The first real use of the skill was a `critique` run against this design. It deadlocked,
the delegate read the skill, decided *it* should delegate, tried to spawn a nested
`codex exec` (which fails under the read-only sandbox because Codex cannot write its session
files), and was then blocked by the fail-closed invariant from answering locally. It produced
no critique, only a report of its own recursion. The second run, with a guard, produced a
critique that found four defects the authoring model had missed.

**Accepted and fixed:**

| Finding | Fix |
|---|---|
| No re-entrancy guard, delegates recurse | `CODEX_SESSION_ID` test in Step 0; no-recursion suffix on every prompt |
| Fail-closed invariant strands the work | Split: unusable *result* → report and stop; *uninvocable* → labeled local fallback |
| `-s read-only` invariant unachievable for `review` | `codex exec review` has no `-s` flag (verified); invariant restated honestly as an assumption about the built-in reviewer |
| Allow-gate rationale false | Gate permits conditional `$(...)`; guidance downgraded from prohibition to preference |
| Step 0 echoed env values | Conflicts with `AGENTS.md`; now tests without printing |
| `digest_lines` bounds lines, not tokens | Byte cap added alongside the line cap |
| Config keys unread by commands | `artifact_dir`, `sandbox`, `model` now substituted into commands |
| Run artifact directory never created; same-day name collisions | `mkdir -p` for the run path; time component in artifact names |
| `origin/master` hardcoded | Default-branch discovery; `git -C` / `-C` scoping for managed repos |

**Accepted as true, not fixed, recorded instead:**

- *Thresholds are proxies, not measurements.* `docs_target_words` and `plan_expected_tasks`
  predict output that does not exist yet. Real, and inherent to deciding before generating.
- *`auto` is convention, not enforcement.* Nothing observes tasks globally; the gate runs
  only after an agent chooses to load the skill. This is the accepted cost of prompt-only.
- *The permission rule is not a kill switch.* `Bash(codex exec *)` authorizes any `codex exec`
  form, so the config cannot prevent non-compliant direct use. The switch governs *this
  workflow*, not access to Codex, it was never a security boundary and should not be read as
  one.

**Rejected:**

- *Delete the `docs` and `plan` profiles.* They were explicitly requested. The critique's
  argument, that the caller must read the full document anyway, so nothing is saved, holds
  for a document consumed immediately, but not for one written to `docs/` and reviewed
  separately, which is the normal case.
- *`CODEX_SESSION_ID` is unproven.* It was verified in both directions before use: set inside
  a `codex exec` run, unset outside. The related point that no *regression test* pins this is
  fair and is the open question below.

**Remaining open question:** no eval exists under `docs/evals/`, and `AGENTS.md` requires one
for shared-behavior changes. The measurement that matters is caller-context occupancy across
a realistic multi-turn task, not the trivial 14 B / 1,773 B smoke test, that proves the
mechanism works, not that the economics do. Until that eval exists, the cost claim above is
reasoning, not evidence.
