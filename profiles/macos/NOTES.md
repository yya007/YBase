# macos: what holds on every machine of this type

## The userland is BSD, and the default bash is old

- `/bin/bash` is 3.2: no associative arrays, no `mapfile`, no `${var,,}`. The login shell is zsh, which does not word-split an unquoted variable the way bash does.
- `sed -i` needs an explicit empty suffix (`sed -i ''`) and GNU's form breaks. Write to a temporary file and `mv` it instead, which works on both.
- `stat`, `date`, `readlink -f`, `find -printf` and `xargs -r` differ from GNU or are missing. YBase's own tools avoid all of them.

## The filesystem

- The default APFS volume is case-insensitive. Two files whose names differ only in case collide on checkout, so never commit such a pair.
- Spotlight and Time Machine index large scratch trees. Keep bulky scratch in the repo's gitignored `tmp/` and exclude it from Time Machine if it grows.

## Compute

- No CUDA. Apple Silicon offers MPS for small local runs. Anything sized for an NVIDIA GPU runs on a remote machine under its own profile.
- Homebrew lives in `/opt/homebrew` on Apple Silicon and `/usr/local` on Intel. A script that hardcodes one breaks on the other.

## Homebrew upgrades Python under you

- A `brew install` of an unrelated tool can upgrade Homebrew's Python as a dependency. A virtualenv built on that interpreter then loses its installed packages, and the next test run fails because `pytest` itself is missing from the environment. Rebuild the environment (`uv sync --extra dev`, or recreate the venv) and run again; the code is fine.
- A test suite that finishes far faster than it usually does may not have run: collection may have aborted. Read the summary line and the exit status, not just whether output appeared.

## Credentials

- `gh auth login` stores its token in the macOS keychain. A credential that works in a terminal may not exist inside a sandboxed or CI process.
