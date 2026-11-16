# ADR 0003: The allow gate is opt-in and off by default

- Status: Accepted
- Date: 2026-11-14

## Context

The allow gate (`.claude/hooks/allow-gate.py`) approves a compound shell command when every part matches an allow rule, so a chain of allowed commands does not prompt. To do that it splits and reads the command with hand-written parsing, not with a shell.

Making the tracked permission list safe to publish took three review rounds. In each round, the reviewer found new ways for the shipped list and the gate together to approve a command that ran a program no rule listed, wrote a file or reached the network.

The classes found in the first two rounds were fixed. The gate now declines all of them:

- a redirect of output to a file, `git difftool`, and a second command behind a background `&`;
- ANSI-C quoting (`$'...'`) and `$"..."`, a backslash-escaped quote (any backslash outside single quotes), an unquoted `#` comment, and a newline in the command.

The third round found more classes, and only one of them was fixed: a loop or conditional keyword that approved whatever followed it. After `do`, `then`, `else` or `elif` the rest of the part must now match a rule.

The other classes from the third round were not fixed. They are the known gaps, still approved when the gate is on:

- a command substitution hidden from the gate by quoting, such as a quoted apostrophe before `$(...)`, or a `$(...)` body that holds several commands inside double quotes;
- a shell function definition that redefines an allowed command name;
- zsh process substitution `=(...)`, zsh glob qualifiers that run code, and the zsh `${(e)...}` expansion flag;
- input redirection from a bash network pseudo-device such as `/dev/tcp/...`, which reaches the network and does not run a program.

Most of these classes were approved before the review started. A parser that tries to list what is unsafe cannot be shown complete by finding one more gap each round.

## Decision

The gate is opt-in and ships off. It approves anything only when `YBASE_ALLOW_GATE=1` is in the process environment or in the `.env` of YBase's main checkout. Any other value, a missing or unreadable `.env`, or a failure to load `tools/envfile.py` leaves it off, and off prints nothing. The same switch applies when Codex runs the gate through `.codex/hooks.json`.

The hardening from the review rounds stays in place for anyone who turns the gate on. The docs describe the gate as a convenience with known gaps, not a security boundary.

## Consequences

- A fresh install prompts for every compound command that the built-in permission system does not match. Nobody gets an approver they did not ask for.
- An owner who relied on the gate sets `YBASE_ALLOW_GATE=1` in `.env` once to keep the old behaviour.
- A user who turns the gate on is exposed to the known gaps, the classes Context lists as not fixed, for every command their allow lists cover. They should list only commands they would be content to run unprompted.
- The open alternative is a strict positive grammar: approve only a small, fully parsed subset of shell (plain words, single quotes, a fixed set of separators and descriptor redirects) and decline everything else. That would make the gate safe enough to turn back on by default. It is not built.
