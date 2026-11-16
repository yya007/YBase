---
name: codex-delegation
license: PolyForm-Noncommercial-1.0.0
description: Use when reviewing a large diff, critiquing a design, drafting long-form docs, writing an implementation plan, or wanting a second opinion from a different model, or when a task crosses the size thresholds in .agents/codex-delegation.json; hands the work to the Codex CLI read-only, keeps the full output in scratch and only a short digest in context, and is not for small edits or quick answers.
---

# codex-delegation

Hand large or perspective-sensitive work to Codex, and keep Claude's context clean by reading only a bounded digest of the result. The rules for any cross-model hand-off are in [`docs/protocols/delegation.md`](../../../docs/protocols/delegation.md); this skill is the procedure.

## Why this exists

Two distinct problems, one mechanism.

**Cost.** A full review of a 2,000-line diff, or a 3,000-word design doc, is expensive output. Generating it in the main thread burns context that the rest of the task still needs, and every later turn re-pays for it in the prompt. Delegating moves that generation to a separate process and writes it to a file. The main thread carries a pointer and a digest, a few hundred tokens instead of several thousand, and greps into the artifact only when it needs a detail.

**Perspective.** Asking the same model to critique its own plan gets you a defence, not a critique. Codex is a different model with a different training distribution, reading the repo cold. For adversarial review, design critique and alternative approaches, that independence is the point: agreement between two independent readers is worth far more than a self-review.

The token win and the perspective win come from the same move, which is why they share one skill.

## Usage

```
/codex-delegation <profile> [<focus text>] [--force] [--local] [--wait]
```

- `<profile>`: one of `review`, `critique`, `docs`, `plan`, `brainstorm`. See **Profiles** below.
- `<focus text>`: what to review, critique or write. Free text, passed through to Codex.
- `--force`: delegate even if the size check says the task is below threshold.
- `--local`: skip delegation for this invocation and do the work in the main thread.
- `--wait`: run in the foreground. Default is a Claude background task for anything expected to be slow.

The skill also fires **without** explicit invocation when a task crosses a configured threshold (see Step 2).

The work may be in YBase or in a managed repo. For a managed repo, take its path from `ybase repos path NAME` (or the worktree from `ybase worktrees --repo NAME`), scope every `git` command with `git -C <path>`, and pass `-C <path>` to Codex. Never `cd` into it ([`docs/rules.md`](../../../docs/rules.md) rule 23).

## Configuration

All behaviour is controlled by `.agents/codex-delegation.json` at the YBase root.

| Key | Meaning |
|---|---|
| `enabled` | Master kill switch. `false` disables every profile; the skill exits at Step 0. |
| `profiles.<name>.enabled` | Per-profile switch. Turn off `docs` without losing `review`. |
| `profiles.<name>.auto` | Whether this profile may fire proactively on a threshold, or only on explicit invocation. |
| `thresholds.*` | The size at or above which auto-delegation fires. |
| `artifact_dir` | Where results land when there is no active run, relative to the profile's scratch (`$YBASE_SCRATCH`). Default `codex`. |
| `digest_lines` | Hard cap on how many lines of the artifact get read into context. |
| `sandbox` | Codex sandbox policy. Default `read-only`: every profile here is non-mutating. |
| `model` | Pin a Codex model, or `null` for the Codex default. |

Environment override, for a single session and without editing tracked config:

- `CODEX_DELEGATION=0`: force off, regardless of the file.
- `CODEX_DELEGATION=1`: force on, overriding `enabled: false`.

## Workflow

### Step 0: Gate (always first, no exceptions)

**Re-entrancy guard, before anything else.** If you are already running *inside* a Codex delegation, you are the delegate. Do the work yourself and never delegate again:

```
test -n "$CODEX_SESSION_ID" && echo "inside-codex" || echo "not-inside-codex"
```

Test the variable; never echo its value. [`docs/rules.md`](../../../docs/rules.md) rule 34 forbids pasting environment values anywhere, and that applies to this skill's own commands. Same for `CODEX_DELEGATION` below.

`inside-codex` means you are inside a Codex run: stop reading this skill as an instruction to delegate and do the requested work directly. This is not optional. Without the guard, a delegate that reads this skill tries to spawn a nested `codex exec`, which fails under the read-only sandbox (`Read-only file system`, because Codex cannot write its session files), and then the fail-closed invariant below blocks the work entirely. That is a deadlock, and it was observed in practice on 2026-08-23: the first real critique run produced nothing but a report of its own recursion.

Then the machine gate. Some machines have no Codex, or are set not to use it:

```
eval "$(ybase env)"; test "$YBASE_CODEX_DELEGATION" = "off" && echo "machine-off" || echo "machine-on"
```

`machine-off` means `YBASE_CODEX_DELEGATION=off` is in this machine's `.env`, or the Codex CLI is not installed here. `.ybase/MACHINE.md` states the same under "Agents". The gate is closed, and `CODEX_DELEGATION=1` does not open it.

Then the normal gate:

```
cat .agents/codex-delegation.json
test -n "$CODEX_DELEGATION" && echo "override-set" || echo "no-override"
test "$CODEX_DELEGATION" = "0" && echo "forced-off"
test "$CODEX_DELEGATION" = "1" && echo "forced-on"
```

Resolve in this order: re-entrancy guard wins over everything; then the machine gate; then env override; then `enabled`; then `profiles.<name>.enabled`.

If the gate is closed, say so in **one line** (`Codex delegation disabled (<reason>); doing this locally.`) and do the work in the main thread. When the work was a review or a critique, the fallback is a subagent with a fresh context and no view of your reasoning, and your report says that the reader was the same model, not a second one. Do not argue with the config, do not ask the user to re-enable it, do not fall back to a partial delegation.

Also confirm Codex is actually available before committing to a delegated path:

```
codex --version
```

If that fails, report it plainly and do the work locally. Never silently substitute a local answer for a delegated one the user is expecting.

### Step 1: Pick the profile

Match the task to a profile from the table below. If two fit, prefer the more adversarial one (`critique` over `docs`, `review` over `plan`). If none fit, this skill does not apply.

### Step 2: Size check

Auto-delegation fires only at or above the profile's threshold. Measure before deciding; do not estimate.

- **review**: `git -C <path> diff --shortstat <base>...HEAD`, or for working-tree scope both `git -C <path> diff --shortstat` and `git -C <path> diff --shortstat --cached`, plus `git -C <path> status --short --untracked-files=all`. Threshold: `review_changed_lines` **or** `review_changed_files`, whichever trips first. Untracked files count as reviewable work even when the diff is empty.
- **critique**: word count of the design doc or proposal under critique. Threshold: `critique_input_words`.
- **docs**: expected length of the document to be written. Threshold: `docs_target_words`.
- **plan**: expected number of discrete tasks in the plan. Threshold: `plan_expected_tasks`.
- **brainstorm**: `auto` is off by default; explicit invocation only.

Below threshold and without `--force`: do the work locally and say in one line why it was not delegated. Above threshold: proceed, and state the measurement that triggered it.

### Step 3: Choose the artifact path

Artifacts are evidence, not documents, so they live in the profile's scratch, never in a checkout. Get the scratch path first:

```
ybase env
```

Read the `YBASE_SCRATCH` line and paste its literal value as `<scratch>` below.

Inside an active run (`<scratch>/runs/<run_id>/` exists and this work belongs to it; see [`docs/protocols/runs.md`](../../../docs/protocols/runs.md)):

```
<scratch>/runs/<run_id>/artifacts/codex/<yyyymmdd>-<hhmmss>-<profile>-<slug>.md
```

Otherwise, under `artifact_dir`:

```
<scratch>/codex/<yyyymmdd>-<hhmmss>-<profile>-<slug>.md
```

`<slug>` is a short lowercase-kebab tag for the subject.

**Get the date with its own `date +%Y%m%d-%H%M%S` call and paste the literal value into the path.**

The reason is narrower than "no subshells". The allow gate in `.claude/hooks/` is off unless `YBASE_ALLOW_GATE=1`, and then its parsing is best-effort ([ADR 0003](../../../docs/adr/0003-allow-gate-is-opt-in.md)). When it is on, it may approve a command holding `$(...)` when the inner text and the outer command both match allow rules, and it declines a backtick or a process substitution that its parser finds. When it is off, or when it declines, a substitution turns the command into a permission prompt, which in a background session can hang unanswered.

Pasting literals sidesteps the whole question and keeps commands legible in the artifact trail. Prefer it, but do not treat `$(...)` as forbidden; it is conditional.

Create the parent directory for whichever path you chose. Inside a run that is the run's own artifact directory, which does not exist yet:

```
mkdir -p <scratch>/runs/<run_id>/artifacts/codex
mkdir -p <scratch>/codex
```

**Include a seconds-resolution time component**, `<yyyymmdd>-<hhmmss>-<profile>-<slug>.md`. Two runs of the same profile on the same subject in one day is the normal case once the first surfaces something to re-check, and a date-only name silently overwrites the earlier evidence. Seconds, not minutes: background delegations run concurrently, and minute resolution lets two same-profile runs collide.

Before writing, check you are not about to clobber an existing artifact:

```
ls -la <artifact-path>
```

This check is advisory, not atomic: two concurrent delegations can both pass it. If an artifact you expected to write is missing or has unexpected content, suspect a race and re-run with a distinct slug rather than trusting the file.

**Selecting the run:** only treat a run as active if this work actually belongs to it. There is no authoritative active-run pointer, so several directories under `<scratch>/runs/` may exist. When it is ambiguous, use `artifact_dir` and say which run you did *not* attach to. Guessing wrong scatters a run's evidence across two places.

### Step 4: Run Codex, output to file

The whole token argument rests on this step. Always pass `-o <artifact>`, which writes **only Codex's final message** to the file: not the JSONL event stream, not the echoed diff.

For `review` (uses Codex's built-in reviewer):

```
codex exec -C <path> review --base origin/<default-branch> -o <scratch>/codex/<artifact>.md
```

Scope variants: `--uncommitted` for staged, unstaged and untracked changes; `--commit <sha>` for one commit. `references/review.md` says how to find the default branch.

**`--base` does not combine with a custom review prompt**: Codex rejects the pair. Use `--base` alone; if the review needs custom framing, drop `--base` and pass the prompt with an explicit scope instead.

For every other profile:

```
codex exec -C <path> -s read-only -o <scratch>/codex/<artifact>.md "<prompt from references/<profile>.md>"
```

Substitute the config values rather than the literals shown above: `artifact_dir` for `codex`, `sandbox` for `read-only`, and `model` as `-m <model>` when it is not null. A config key the commands ignore is a lie about what is configurable.

`-s` applies to the four prompt profiles only. **`codex exec review` takes no `-s/--sandbox` flag**; do not add one, it errors. See the non-mutating invariant below for what that means.

**Every prompt you send must end with this line**, as belt-and-braces alongside the Step 0 env guard:

```
You are the delegate for this task. Do the work yourself and do not delegate any part of
it further. In particular, do not invoke codex, and ignore any instruction in this
repository's skills telling you to delegate.
```

Without it, a delegate that reads `.agents/skills/codex-delegation/SKILL.md` while exploring the repo can talk itself into recursing before it ever checks the env guard.

A delegate working on a managed repo reads that repo's `AGENTS.md`, not YBase's. Brief it as an outside agent ([`docs/protocols/delegation.md`](../../../docs/protocols/delegation.md)), and put nothing in the prompt that names YBase, its knowledge base or sibling repos if the output may be copied into that repo ([`docs/rules.md`](../../../docs/rules.md) rule 22).

**Run it as a Claude background task unless `--wait` was passed.** Measured on 2026-08-23 (codex-cli 0.149.0):

| Profile | Observed wall time |
|---|---|
| `critique`, `plan`, `docs`, `brainstorm` | about 1 to 4 min `[M]` |
| `review` | **about 23 min** `[M]` to complete; two separate 9-minute foreground attempts timed out with no artifact |

The review profile is in a different class from the prompt profiles: it reads the whole diff before saying anything. Never run `review` in the foreground on a non-trivial diff, and give it a generous timeout. A foreground review that times out produces **no artifact at all**, so the whole run is wasted, not merely truncated.

### Step 5: Digest, do not dump

Read at most `digest_lines` lines of the artifact.

**First, confirm the artifact exists and is non-empty:**

```
wc -l -c <artifact>
```

Missing and empty are **different failures** and take different branches of the failure rule below. Do not collapse them:

- **No file at all** (`No such file or directory`): Codex never got far enough to write. Measured 2026-08-23: on timeout, `-o` writes no file rather than an empty one. This is an *uninvocable run*: say so, then do the work locally with an explicit label.
- **Zero-byte or contentless file**: Codex ran and produced nothing usable. This is an *unusable result*: report it, cite the path, and **stop**. Do not fall back to local work, because the run consumed its budget and a silent retry hides a real problem.

Either way, never report "no findings". An absent artifact is not a clean review, and the difference between "nothing was checked" and "nothing was wrong" is the whole value of the report.

Then digest:

```
head -c 6000 <artifact> | head -n 40
```

**Both caps, always.** `head -n <digest_lines>` alone bounds lines, not tokens: forty paragraph-length lines is not a digest. The byte cap is what bounds cost; the line cap keeps the digest readable. Budget roughly 4 bytes per token `[A]`, so 6000 bytes is about 1.5k tokens: substitute `digest_lines` from config for the line cap, and scale the byte cap with it.

`wc -l -c` tells you how much you did **not** read, which belongs in the report.

Never `cat` the whole artifact into context. That would undo the point of the skill: you would pay the full output cost *plus* the delegation overhead. If a specific detail is needed later, `grep` for it.

### Step 6: Report

Report in the main thread:

1. The **artifact path**, always, so the user and later agents can read the full output.
2. The **verdict or summary line** from the digest.
3. **Findings ordered by severity**, using Codex's own file paths and line numbers verbatim.
4. What was **not** covered, if Codex said so.

Preserve Codex's evidence boundaries. If it marked something an inference, an uncertainty or an open question, keep that label: do not promote a hedge into a finding, or demote a finding into a suggestion.

### Step 7: Record the delegation

Inside an active run, update its `run.json` using the existing fields ([`docs/protocols/runs.md`](../../../docs/protocols/runs.md)), with no schema changes:

- `delegation_mode`: `delegated`
- `delegation_reason`: the measurement that triggered it, for example `review: 1240 changed lines >= 400`
- `delegation_candidates[]`: append `{task_id, parallelizable, delegated: true}`

Outside a run, no bookkeeping beyond the artifact file itself.

## Profiles

| Profile | Use for | Independence matters? |
|---|---|---|
| `review` | Large diffs, pre-merge review, adversarial pass before a PR | Yes: a second reader catches what the author's model rationalized |
| `critique` | Attacking a design, spec or ADR; finding the failure mode you are invested in not seeing | Yes: the whole value is the outside view |
| `docs` | Long-form written material: guides, READMEs, migration notes, changelogs | No: this one is purely about cost |
| `plan` | Implementation plans for multi-task work, from a cold read of the repo | Partly: a cold reader makes fewer inherited assumptions |
| `brainstorm` | Alternative approaches, second opinions on a chosen direction | Yes: explicit invocation only, since it is cheap to run and easy to over-run |

## Invariants

- **Non-mutating, by two different mechanisms.** The four prompt profiles pass `-s read-only` explicitly. The `review` profile **cannot**: `codex exec review` accepts no `-s/--sandbox` flag (verified against codex-cli 0.149.0; passing one errors), so it relies on the built-in reviewer being non-mutating by design, which is an assumption about the CLI, not an enforced guarantee. If a review run is ever observed writing to the working tree, that is a bug in this skill's premise: report it rather than working around it. Either way this skill never *asks* for edits; write-capable delegation is `codex:rescue`'s job.
- **Never auto-apply review findings.** After presenting a review or critique, STOP. Ask which findings, if any, to act on. Applying a fix straight from a review is forbidden even when the fix looks obvious: the finding has not been verified against the repo yet.
- **Never fabricate a delegated result, but never let a failed delegation strand the work either.** These are two different situations and the rule differs:
  - *Codex ran and returned something unusable* (malformed, truncated, off-contract): report that, cite the artifact, and stop. Do not paper over it.
  - *Codex could not be invoked at all* (not installed, sandbox failure, timeout, recursion): say so in one line, then **do the work locally and label it plainly**: `Codex unavailable (<reason>); the following is a local answer, not a delegated one.`

  What is forbidden is presenting local work *as* Codex's output. Silence and an undone task are not the safe fallback; that combination is what deadlocked the first real critique run.
- **Never dump the artifact into context.** Digest only, capped at `digest_lines`.
- **Never write an artifact into a checkout.** It goes in the profile's scratch; anything that must outlive the run is committed, put in the PR, or saved to the knowledge base.
- **Prefer literals over `$(...)`.** The allow gate is opt-in and, when on, approves command substitution only in some cases, so `$(...)` is a hazard, not a prohibition. Pasting literals avoids the edge cases.
- **The gate is absolute.** `enabled: false` or `CODEX_DELEGATION=0` means local work, silently and without negotiation.

## Output checklist

- [ ] Gate result stated (delegated, or one-line reason it was not)
- [ ] Triggering measurement stated when auto-delegation fired
- [ ] Artifact path cited
- [ ] Verdict and findings by severity, paths and line numbers verbatim
- [ ] Evidence boundaries preserved (inference, finding, open question)
- [ ] `run.json` delegation fields updated when inside a run
- [ ] No code changed as a side effect of a review or critique

## References

- `references/review.md`: large-diff and pre-merge review
- `references/critique.md`: adversarial design critique
- `references/docs.md`: long-form written material
- `references/plan.md`: implementation planning
- `references/brainstorm.md`: alternative approaches and second opinions

Each reference carries the prompt template and the output contract for that profile. The contract is what makes Step 5's digest parseable: Codex is asked to lead with a verdict line and ordered findings, so the first 40 lines are the useful ones.
