# linux: what holds on every machine of this type

This is the fallback profile, so its notes are the ones true of Linux in general. When a class of Linux machine needs its own setup (a GPU cluster login node, a particular cloud), give it its own profile rather than growing this one.

- `/tmp` may be shared between users. Keep `TMPDIR` on the profile scratch directory when more than one person uses the machine.
- Inside a container, anything outside a mounted volume disappears when the container exits. Mount the repository, and push before you stop.
- The login shell may be bash or zsh. Scripts declare `#!/usr/bin/env bash` and never rely on the interactive shell's behavior.
