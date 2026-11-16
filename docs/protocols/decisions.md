# Decisions: where a change of design is written down

Open this when a change alters how something works, not only what it does. Record the decision before or with the change, never after, and in the repo the change belongs to: a decision about a managed repo goes in that repo's own documents, never in YBase.

| The change | Where it is recorded |
|---|---|
| a cross-cutting architecture or workflow choice | an architecture decision record (ADR), under the repo's `docs/adr/` |
| how agents operate in the repo | that repo's `AGENTS.md`; in YBase, [`docs/rules.md`](../rules.md) or the [`docs/law/`](../law/README.md) file for the moment |
| what the product or runtime does | the repo's specification, wherever its `AGENTS.md` says it lives |
| layering or data flow | the repo's architecture document, for example `docs/architecture.md` |
| a skill or a template | the skill under `.claude/skills/`, or the file under [`templates/`](../../templates/) |
| how a shared behaviour is evaluated | an eval definition under the repo's `docs/evals/` |

The result of evaluating one run goes in that run's folder, `$YBASE_SCRATCH/runs/<run_id>/eval.md`, written from [`templates/run/run-eval-template.md`](../../templates/run/run-eval-template.md). See [`runs.md`](runs.md).
