# Security

YBase ships guards that run on a user's machine: a leak check, a file guard and hooks that refuse some commands. A flaw in one of them can expose private text or let a harmful command through.

## What to report privately

- A way to get a secret, a private term or a personal path past the `leaks` check or the commit-time leak hook, beyond the limits already written down in [`docs/adr/0005-leak-hook-strict-everywhere.md`](docs/adr/0005-leak-hook-strict-everywhere.md).
- A way around the file guard or another blocking hook.
- Private content you find in this repository or its history.

## How to report

Use GitHub's private vulnerability reporting on this repository (the "Report a vulnerability" button under the Security tab). Say what you ran, what you expected the guard to do and what it did. Leave out your own private terms: replace them with a made-up word that shows the same behaviour.

Please do not open a public issue or pull request for these. Ordinary bugs go in a normal issue.

## What the guards are not

The hooks read shell commands as text and recognise the common forms. They are a second check for a careful user, not a sandbox. The allow gate is a convenience that is off by default and is not a security boundary ([`docs/adr/0003-allow-gate-is-opt-in.md`](docs/adr/0003-allow-gate-is-opt-in.md)).
