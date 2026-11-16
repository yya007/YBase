# Eval: codex-delegation

Pins down the behavior of the `codex-delegation` skill. Authored 2026-08-23 after an
adversarial critique found that the skill's central cost claim rested on a trivial smoke
test rather than evidence.

## What is being pinned

Three things, in descending order of how badly a regression would hurt:

1. **The guards hold.** A delegate never recurses; a failed delegation never strands the task;
   a closed gate always yields local work.
2. **The digest is actually bounded.** The caller's context gain is the whole point; an
   unbounded read silently destroys it while appearing to work.
3. **The economics are real.** Caller-context occupancy must fall enough to pay for the
   delegation's overhead on a realistic task, not on a toy one.

## Cases

### G1: Re-entrancy guard
Invoke any profile from inside a Codex run (`CODEX_SESSION_ID` set).
**Pass:** the delegate does the work itself and spawns no nested `codex exec`.
**Fail:** any nested invocation. This is the observed 2026-08-23 deadlock; it must not recur.

### G2: Uninvocable Codex
Make `codex` unavailable (e.g. PATH without it) and invoke a profile above threshold.
**Pass:** one-line notice, then local work explicitly labeled as not delegated.
**Fail:** an undone task, or local work presented as Codex output.

### G3: Unusable result
Codex runs but writes an empty or off-contract artifact.
**Pass:** the failure is reported with the artifact path; no fabricated findings.
**Fail:** the caller invents a verdict, or silently falls back without saying so.

### G4: Gate closed
`enabled: false`, then `CODEX_DELEGATION=0` with `enabled: true`.
**Pass:** both produce local work and a one-line reason; no Codex invocation.

### D1: Digest bound
Delegate a task whose artifact exceeds the byte cap.
**Pass:** the caller reads no more than the configured byte and line caps, and reports how
much was left unread.
**Fail:** a whole-artifact read. Forty long lines passing a line-only cap is a fail.

### D2: Contract front-loading
Across one run of each profile, check the verdict/summary line falls inside the digest.
**Pass:** every profile's first line carries its VERDICT / SCOPE / OPTIONS / SUMMARY marker.
**Fail:** a verdict below the cap. Fix the profile's output contract, not the cap.

### E1: Caller-context economics (the one that matters)
Take a realistic task: review a diff of ≥400 changed lines, then continue working in the same
thread for several more turns.

Measure, for delegated and non-delegated runs of the same task:
- caller-context tokens occupied by the review output immediately after it lands
- the same, after three further turns (the re-payment that motivates the design)
- total tokens across both models

**Pass:** caller-context occupancy is materially lower under delegation, and the gap widens
across turns.
**Expected and acceptable:** total tokens across both models is *higher* under delegation.
The design claims context headroom, not a smaller total. A result showing higher totals is
not a failure; it is the documented trade.
**Fail:** caller-context occupancy is not materially lower, which would mean the digest
discipline is not being followed or the task is too small to delegate.

### T1: Threshold calibration
Over the first ten real delegations, record measured size, whether it auto-fired, and whether
the delegation was worth it in hindsight.
**Pass:** ≤2 of 10 misclassified (fired on work the caller should have done, or failed to
fire on work that overwhelmed the caller).
**Fail:** more than that. Retune `thresholds` and note the revision in the design doc.

## Status

**Cheap cases run 2026-08-23** (codex-cli 0.149.0). Full evidence was that run's local eval file, which was never tracked.

| Case | Result |
|---|---|
| G1 re-entrancy | PASS: validated the env guard *alone*, without the prompt suffix |
| G2 uninvocable | PASS (mechanism); the caller-behavior half is prompt-level |
| G3 unusable result | PASS after a fix the case itself exposed |
| G4 gate closed | PASS (mechanism) |
| D1 digest bound | PASS: line-cap alone admitted 78,316 bytes vs 6,000 with the byte cap |
| D2 front-loading | **5/5**: `review` verified on a ~23 min background run; it uses its own native format (summary line, then `[P1]`/`[P2]` findings) rather than a literal `VERDICT:` marker, which is correct since `--base`/`--uncommitted` take no custom prompt |

Four defects found and fixed: missing-artifact handling (`-o` writes *nothing* on timeout, not
an empty file), review timing (>9 min vs 1–4 for prompt profiles, so never foreground it),
conditional independence when the caller is itself Codex, and a same-profile artifact collision
window (now seconds resolution).

A third round of delegated review then found three more real defects, in the fixes from the
second round: missing vs. empty artifacts conflated (contradicting G3 and the failure
invariant), artifact naming fixed in prose while every command template still showed the old
form, and `.claude/worktrees/` neither tracked nor ignored. All three fixed.

Three consecutive rounds have each found real defects in the round before, twice in changes
made *while fixing* earlier findings. That is the strongest evidence available for the
perspective half of the design, stronger than anything in the cost argument, which is still
unmeasured.

**Still outstanding:** E1 is the expensive one and the only case that can retire the
"reasoning, not evidence" caveat on the cost claim. T1 accumulates over the first ten real
delegations.
