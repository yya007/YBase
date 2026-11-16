# ADR 0006: Whether to delegate to Codex is decided per machine

- Status: Accepted
- Date: 2026-11-14
- Extends: [ADR 0002](0002-codex-delegation.md)

## Context

ADR 0002 put the switches for Codex delegation in `.agents/codex-delegation.json`, a tracked file, with `CODEX_DELEGATION` as a one-session override. A tracked file says the same thing on every machine. Machines differ: one has the Codex CLI and a login, another has neither, and a third has it but should not use it. On a machine without Codex the skill found out only by running `codex --version` after it had already chosen to delegate.

## Decision

The machine is the widest gate. `YBASE_CODEX_DELEGATION=off` in a machine's `.env` turns delegation off there. Unset, delegation is on exactly when the Codex CLI is on `PATH`, so a machine without Codex needs no setting. `ybase doctor` writes the result under "Agents" in `.ybase/MACHINE.md`, and `ybase env` exports it. The skill reads it before the tracked config, and the one-session override cannot turn on a machine that is off.

When delegation is off, a review or critique goes to a subagent with a fresh context, and the report says that no second model read the work.

## Consequences

- Every session knows at start whether Codex exists here, because `MACHINE.md` is always loaded.
- The tracked config keeps its meaning: what to delegate and at what size, on machines that can.
- The check is that the CLI is installed, not that it is logged in. A machine with Codex installed and no login still reads as on, and the skill's own `codex --version` and run failure paths report that.
- A fallback review by the same model is weaker than a second model. The report has to say which one happened.
