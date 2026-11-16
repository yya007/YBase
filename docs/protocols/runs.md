# Runs: tracking a non-trivial task in files

Open this when a task has three or more steps, changes behaviour across files, or will be split between agents. A run gives the work a written design, a task list and a record of what was verified, so another agent or a later session can pick it up from files instead of from chat.

## Where a run lives

A run is a folder in the machine's scratch directory, never in a checkout:

```
$YBASE_SCRATCH/runs/<run_id>/
  run.json
  design.md
  plan.md
  tasks/index.md
  tasks/<task_id>.md
  artifacts/<worker_id>/...
  verification.json
  eval.md            when the run is evaluated
  final.md
```

`eval "$(ybase env)"` sets `YBASE_SCRATCH`. Scratch is not shared between machines, and on some profiles it does not survive a stop (read `profiles/<profile>/NOTES.md`). Anything that must outlive the run goes into the repo through a commit, into the pull request, or into the knowledge base.

The run id is `<yyyymmdd>-<skill or topic>-<suffix>`, unique under `runs/`. It stays in the run's own files: never put a run id or a task id in a commit message or a pull request ([`law/commit.md`](../law/commit.md)).

## run.json

At minimum:

- `run_id`, `skill`, `status`, `created_at`, `updated_at`
- `delegation_mode` (`local` or `delegated`), `delegation_reason`, `delegation_considered_at`
- `delegation_candidates`: a list of `{task_id, parallelizable, delegated}`
- `parent_run_id`, when the run was forked
- `canonical_targets`: the files or folders the run may change, each with the repo it belongs to

## Lifecycle

- **Create** a run when non-trivial work starts and no compatible run is active.
- **Attach** to an existing run when continuing the same task on the same targets.
- **Fork** a new run, with `parent_run_id`, when the scope, the owner or the targets change materially.
- **Re-plan on drift.** When execution departs from the design or the plan, stop and update them before continuing.
- **Complete** a run only when every task that is not canceled is `done`, or is deferred by name in `final.md`.

## Design before tasks

Write `design.md` from [`templates/run/design-brief-template.md`](../../templates/run/design-brief-template.md) before implementing or delegating. It holds at least:

- the user outcome or problem;
- constraints and non-goals;
- accepted decisions and open questions;
- acceptance criteria;
- canonical targets.

Then turn the approved design into explicit task units before editing any shared target.

## Tasks

`tasks/index.md` is the task registry, from [`templates/run/task-index-template.md`](../../templates/run/task-index-template.md). Each row has `task_id`, `title`, `status` (`backlog`, `ready`, `in_progress`, `blocked`, `done` or `canceled`), `owner`, `depends_on`, `design_ref`, `canonical_target` and `verification`.

Each `tasks/<task_id>.md` comes from [`templates/run/task-template.md`](../../templates/run/task-template.md) and records the status, owner, dependencies, allowed paths, deliverables, acceptance checks, artifact paths and progress notes.

## Ownership

- One integrator owns `run.json`, `design.md`, `plan.md` and `tasks/index.md`.
- Each worker owns only its own `tasks/<task_id>.md` and its artifact folder, unless a new handoff says otherwise.
- Record every change of task state in the run's files, not only in chat. [`multi-agent.md`](multi-agent.md) has the rest of the rules for several agents.

## Delegation

Consider delegation for every run and record the decision in `run.json`. When you keep a candidate local, write down why. The rules for when and how to delegate are in [`law/delegate.md`](../law/delegate.md); handing work to Codex is in [`delegation.md`](delegation.md).

## Trackers and skills

An issue tracker may mirror task state, but the run folder stays the record. A skill that runs long work uses this protocol instead of inventing its own: it states where delegation can happen, which artifacts each step hands over, how the result is verified and which steps must stay in order.
