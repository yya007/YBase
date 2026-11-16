#!/usr/bin/env bash
# env.sh: print exports for the profile in force. Usage: eval "$(ybase env)"
set -eu
. "$(dirname "$0")/profile.sh"
yb_load_profile
mkdir -p "$PROFILE_SCRATCH"
printf 'export YBASE_ROOT=%q\n' "$YB_ROOT"
printf 'export YBASE_PROFILE_ACTIVE=%q\n' "$PROFILE_NAME"
printf 'export YBASE_SCRATCH=%q\n' "$PROFILE_SCRATCH"
printf 'export TMPDIR=%q\n' "$PROFILE_SCRATCH"
yb_codex_delegation
printf 'export YBASE_CODEX_DELEGATION=%q\n' "$YB_CODEX"
