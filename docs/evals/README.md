# docs/evals/

Eval definitions for shared-behavior changes (see
[`docs/protocols/decisions.md`](../protocols/decisions.md)). One file per eval: what
behavior is being pinned down, the cases, and the pass criteria. Run-specific eval
*results* do not live here. They go in the run's folder in the profile's scratch
directory, `$YBASE_SCRATCH/runs/<run_id>/eval.md`.

## Evals

- [`codex-delegation.md`](codex-delegation.md): guards (re-entrancy, failure fallback, gate), digest bounding, and
  caller-context economics for the `codex-delegation` skill.
