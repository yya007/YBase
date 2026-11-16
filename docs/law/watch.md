# Watch: the rules that bind when you wait on a job, a command or a poller

Shown once per session by the moment hook; see [README.md](README.md). Codex reads it before the act.

## Before you wait

1. Bound every wait with a deadline. An unbounded `until <cond>; do sleep N; done` never ends once its condition stops being possible, and such a waiter holds its worktree with it. Size the bound to what the command can legitimately need, and measure that rather than guess it.
2. Watch progress on the artifact the job exists to produce, never a proxy: not a pid, not a `Running` state, not a scheduler's "admitted". A dead job polled by pid looks busy.
3. Run the watcher's read command once by hand and watch it fail loudly on a bad id. A watcher's silence must mean nothing happened, never that it could not look: keep its stderr and exit non-zero when the read fails.
4. Give a long command a sentinel of its own: redirect to a file and append `EXIT=$?`, then poll for that line, never the wrapper's exit code. A timeout's code, a truncated log and an empty log are all success-shaped non-answers.
5. Write status and logs under the profile's scratch, `eval "$(ybase env)"`, never under a fixed name in a shared `/tmp` ([rule 16](../rules.md#working)).

## Finding and stopping a watcher

- Never match a process by a pattern that matches the probe itself; `pgrep -f <pattern>` lists the shell that runs it. Match on a field the watcher alone carries, such as its pid file, and read it back before you kill anything.
- Fork a watcher only after the submit receipt, or kill it by pid the moment the launch aborts. One forked before the submit outlives every aborted attempt.
- Enumerate leftover background work by structure (orphaned processes, their environment), not by name: a grep returns only what you already suspected.

## Reading the result

- A waiter decides finished only from a positive terminal signal. An empty query, an absent state string or a poll that ran out of count has answered nothing, and nothing destructive follows it.
- Scope the wait predicate to your own run's region of an append-only status file; the previous run's terminal line makes a fresh loop return at once.
- Read the final state from the artifact and report it with its label ([rule 2](../rules.md#evidence)). A green log with no artifact is a spent resource, not a result.
