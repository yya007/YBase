# Delegation to Codex: a second model as a worker or a reviewer

Open this before handing work to Codex from a Claude Code session. The rules that bind every dispatch, to a subagent or to another model, are in [`law/delegate.md`](../law/delegate.md). This file adds what is specific to a cross-model hand-off.

## When to use another model

Delegating to Codex is a separate choice from delegating to a subagent. Two reasons justify it:

- **Size.** The output is large. Codex pays for it outside your context, and you read back only a digest.
- **Independence.** A different model reading the repo cold gives a real second opinion. Reviewing your own work gives a defence of it.

## The paths

- The `codex-delegation` skill owns read-only delegation. Its profiles are `review`, `critique`, `docs`, `plan` and `brainstorm`, and none of them asks Codex to edit.
- Work where Codex writes files goes through the Codex plugin's `codex:rescue` instead.
- Usage guide: [`docs/codex-delegation.md`](../codex-delegation.md). Evaluation: [`docs/evals/codex-delegation.md`](../evals/codex-delegation.md).

## Rules

- **Background a review.** The `review` profile takes far longer than the prompt profiles: over 9 minutes measured `[M]`, against 1 to 4 for the others. A review that times out in the foreground writes no artifact at all, so the whole run is lost rather than cut short.
- **Expect no second opinion from Codex inside Codex.** A caller that is itself Codex hits the re-entrancy guard and answers locally. That is correct behaviour, but it gives no independent view.
- **Write the output to a file and read back a bounded digest.** Pasting the output into your context gives up the reason for delegating.
- **Treat review and critique findings as claims.** Verify each one, and decide explicitly which to act on, before any edit.
- **Brief Codex as an outside agent.** It reads `AGENTS.md`, not `CLAUDE.md`, and no Claude Code hook sees its edits. Point it at [`docs/codex.md`](../codex.md) and the absolute worktree path.

## Configuration

Three layers decide whether a hand-off happens, widest first:

| Layer | Where | What it says |
|---|---|---|
| This machine | `YBASE_CODEX_DELEGATION=off` in `.env`; unset, it is on exactly when the Codex CLI is installed | whether Codex exists here at all. `ybase doctor` writes the answer under "Agents" in `.ybase/MACHINE.md`, so every session reads it at start |
| Every machine | `.agents/codex-delegation.json` | the master switch, a switch per profile and the size thresholds |
| One session | `CODEX_DELEGATION=0` or `1` in the environment | off or on for this session; it cannot turn on a machine that is off |

## When Codex is off

A machine without Codex still gets the work done; it loses the second model, not the second read.

- Large output stays in this session, or goes to a subagent that writes it to a file and returns a digest.
- A review or critique goes to a subagent with a fresh context: give it the diff or the document, never your reasoning or your conclusion.
- Say in the report that the reviewer was the same model. A reader who expects an independent model must not be left to assume one.
