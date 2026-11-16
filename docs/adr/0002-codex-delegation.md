# ADR 0002: Delegate large-output and second-opinion work to Codex

- Status: Accepted
- Date: 2026-08-23
- Note, 2026-11-13: the skill now lives in `.claude/skills/codex-delegation/`, which Codex reads through the `.agents/skills` symlink, and artifacts go to the profile's scratch directory (`$YBASE_SCRATCH/codex/`).

## Context

Two recurring costs in this workspace share one cause.

**Large output crowds the caller's context.** Reviewing a 2,000-line diff, drafting a
3,000-word guide, or writing a multi-task implementation plan produces output measured in
thousands of tokens. Generated in the main thread, it displaces the context the rest of the
task still needs, and every subsequent turn re-pays for it in the prompt.

**Self-review is structurally weak.** Asking the model that authored a design to critique
it produces a defense, not a critique. The assumptions that need challenging are precisely
the ones the author's model does not see as assumptions.

Codex is already installed and already used here: a saved lesson from one managed repo
records `codex review --base origin/master` as "a high-value adversarial gate" that "found
real" issues. But that usage was ad-hoc: no configuration, no artifact convention, and a
recorded workaround for Codex's large output ("read from the `^codex$` marker for the
verdict") that left the full dump in context anyway, paying the output cost the delegation
was supposed to avoid.

The official `codex@openai-codex` Claude Code plugin provides a `rescue` path, but it
returns Codex's stdout verbatim to the caller. That delivers the perspective benefit and
forfeits the cost benefit. It is also pinned to a versioned internal script path
(`.../codex/1.0.5/scripts/codex-companion.mjs`) that moves on upgrade.

## Decision

Add a `codex-delegation` skill (YBase-specific, tracked in `.agents/skills/`) that routes
five profiles to Codex: `review`, `critique`, `docs`, `plan`, `brainstorm`. None of them ask
Codex to edit anything; four pass `-s read-only` explicitly and `review` cannot (see
Consequences).

Three choices define it:

**Prompt-only.** No runner script, no job registry, no subagent. The skill is markdown that
tells the agent which `codex exec` command to run. Claude Code's own background tasks handle
async. Nothing to maintain when Codex or the plugin changes, and no coupling to the official
plugin's internals.

**Artifact-first.** Every delegation passes `codex exec -o <file>`, which writes only Codex's
final message: not the JSONL event stream, not the echoed diff. The caller then reads a
bounded digest (`digest_lines`, default 40) and cites the path. This supersedes the
`^codex$` marker workaround in memory: the flag is deterministic and the dump never reaches
context. Dumping the artifact is called out as forfeiting the whole point.

**Threshold-driven auto-delegation.** Profiles fire proactively at or above a measured size
(changed lines/files, input or target word count, expected task count) configured in
`.agents/codex-delegation.json`. Measured, not estimated. Below threshold, work stays local.

Governance lives in that one config file: master switch, per-profile switches, per-profile
`auto` flags, thresholds. `CODEX_DELEGATION=0|1` overrides it for a session without editing
tracked state.

Delegations inside a run record themselves in the existing `run.json` fields
(`delegation_mode`, `delegation_reason`, `delegation_candidates`), with no schema change.

## Consequences

- Large review, critique, docs, and planning output stops occupying the caller's context;
  the artifact stays greppable on disk. Note the benefit precisely: **caller-context
  occupancy falls, total tokens across both models rise** (a second model cold-reads the repo
  and generates the full answer). The win is context headroom and avoided re-payment on later
  turns, not a smaller bill in every case.
- Design critique gets an independent reader rather than a self-review, **conditionally**.
  Independence holds when the caller is not itself Codex. A Codex-hosted session hits the
  re-entrancy guard and critiques locally, which is correct behavior but delivers no second
  perspective; and because `model` is unpinned, caller and delegate could in principle be the
  same model. When independence is the point rather than cost, confirm the caller is not
  Codex, and consider pinning a specific `model`.
- `.claude/settings.json` gains `Bash(codex --version)` and `Bash(codex exec *)`, scoped to
  those two forms rather than a blanket `Bash(codex *)`, so other Codex subcommands still
  prompt.
- Skill commands prefer literals over `$(...)`. **Corrected 2026-08-23:** `allow-gate.py`
  does not reject all subshells: it permits `$(...)` when every inner command is allowed and
  the outer command still matches after substitution, rejecting only backticks and process
  substitution. Literals stay preferred to avoid the edge cases, but the original blanket
  prohibition was wrong. **ERRATUM 2026-11-14:** that correction overstated the check. The
  gate's parsing is best-effort, and a command substitution hidden by quoting can pass it;
  the gate is now opt-in and off by default ([ADR 0003](0003-allow-gate-is-opt-in.md)).
- Codex CLI flag drift is a real maintenance surface. The skill depends on `codex exec -o`,
  `-s`, `-m`, and `codex exec review --base/--uncommitted/--commit` (verified against
  codex-cli 0.149.0). A flag rename breaks the skill loudly rather than silently. That is acceptable
  for a prompt-only design, and cheaper than owning a wrapper script.
- **`codex exec review` accepts no `-s/--sandbox` flag.** The four prompt profiles are
  sandboxed explicitly; the review path is not, and depends on the built-in reviewer being
  non-mutating. That is an assumption about the CLI, not a guarantee this skill enforces.
- **Delegates must not re-delegate.** A Codex run that reads this skill will otherwise try to
  spawn a nested `codex exec`, which fails under the read-only sandbox and, combined with a
  fail-closed invariant, leaves the task undone. Guarded by testing `CODEX_SESSION_ID`, plus
  a no-recursion suffix on every prompt. The `review --base` path sends no prompt, so the env
  guard is its only protection.
- **The config is a workflow switch, not a security boundary.** `Bash(codex exec *)`
  authorizes any `codex exec` form, so `enabled: false` governs this skill's behavior and
  cannot prevent direct Codex use by other means.
- `--base` cannot be combined with a custom review prompt. This is why `review` (built-in
  reviewer) and `critique` (custom adversarial prompt) are separate profiles rather than one
  parameterized profile.
- Write-capable Codex work stays with `codex:rescue`. This skill never edits code.

## Alternatives considered

**Layer on `codex-companion.mjs`.** Reuses the official plugin's job control, background
running, and `status`/`result`. Rejected: it couples to a version-pinned internal path, and
its verbatim-stdout contract would still have to be post-processed to get the cost benefit,
inheriting the coupling without escaping the cost.

**Self-contained runner script.** A small wrapper owning artifact naming, digesting, and a
job registry. Rejected as premature: `codex exec -o` plus Claude's background tasks already
provide both halves, and a script is a maintenance surface a markdown file is not. Revisit if
delegation volume makes a job registry genuinely useful.
