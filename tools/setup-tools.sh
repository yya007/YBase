#!/usr/bin/env bash
#
# setup-tools.sh — install / update the OPTIONAL workspace tooling (agent CLIs).
#
# These are user-level tools the workspace benefits from but does not require:
# code knowledge graphs (gitnexus), browser-session channels (OpenCLI),
# internet-access channels (agent-reach + yt-dlp), MCP tool running (mcporter).
# None of them touch the repos; all install user-scoped (uv tool / npm -g /
# brew — no sudo).
#
# Modes:
#   install (default)  missing tool -> install; present tool -> skip
#   update (UPDATE=1)  present tool -> run its update command; missing -> skip
#                      (per the upstream guides: only upgrade what is already
#                      installed — never pull in tools the user didn't ask for)
#
# Behaviour per tool:
#   - install/update fails -> WARN and continue; exit non-zero at the end
#
# Usage:
#   tools/setup-tools.sh                # install everything missing
#   UPDATE=1 tools/setup-tools.sh       # update everything installed
#   tools/update-tools.sh               # same as UPDATE=1 (wrapper)
#   DRY_RUN=1 tools/setup-tools.sh      # print actions, change nothing
#
# Test / advanced overrides:
#   TOOLS_MANIFEST=/path   # read "name|check_cmd|install_cmd|update_cmd" lines
#                          # from a file instead of the built-in manifest
#                          # (# / blank lines ignored). Used by the test suite.
#
set -euo pipefail

DRY_RUN="${DRY_RUN:-0}"
UPDATE="${UPDATE:-0}"

# Dry-run action lines carry a DRY prefix.
DRY_PREFIX=""
[ "$DRY_RUN" = "1" ] && DRY_PREFIX="DRY    "

# Built-in manifest: "name|check_cmd|install_cmd|update_cmd".
#   check_cmd    looked up with `command -v`
#   install_cmd  runs via bash -c; "-" means update-only (never auto-install)
#   update_cmd   runs via bash -c; empty means no update procedure (skip)
# Fields are split on "|", so name/check/install must not contain one; only
# update_cmd (the last field) may, since it absorbs the remainder of the line.
# agent-reach installs from a moving main.zip, so its update forces a
# re-download (--reinstall implies --refresh). twitter/bili are installed by
# agent-reach itself, not by us — update-only ("-") keeps their platform
# signatures fresh without pulling them onto machines that never opted in.
# Update guides: https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/update.md
read -r -d '' DEFAULT_MANIFEST <<'EOF' || true
agent-reach|agent-reach|uv tool install "agent-reach @ https://github.com/Panniantong/agent-reach/archive/main.zip"|uv tool upgrade --reinstall agent-reach
yt-dlp|yt-dlp|uv tool install yt-dlp|uv tool upgrade yt-dlp
gitnexus|gitnexus|npm install -g gitnexus|npm update -g gitnexus
opencli|opencli|npm install -g @jackwener/opencli|npm update -g @jackwener/opencli
mcporter|mcporter|npm install -g mcporter|npm update -g mcporter
ffmpeg|ffmpeg|brew install ffmpeg|brew upgrade ffmpeg
twitter-cli|twitter|-|uv tool upgrade twitter-cli
bilibili-cli|bili|-|uv tool upgrade bilibili-cli
EOF

manifest() {
  if [ -n "${TOOLS_MANIFEST:-}" ]; then
    cat "$TOOLS_MANIFEST"
  else
    printf '%s\n' "$DEFAULT_MANIFEST"
  fi
}

installed=0 updated=0 skipped=0 errors=0

while IFS= read -r line; do
  # Trim surrounding whitespace; skip blank lines and comments.
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  case "$line" in '' | \#*) continue ;; esac

  IFS='|' read -r name check_cmd install_cmd update_cmd <<<"$line"
  if [ -z "${name:-}" ] || [ -z "${check_cmd:-}" ] || [ -z "${install_cmd:-}" ]; then
    echo "warn   skipping malformed manifest line: $line" >&2
    errors=$((errors + 1))
    continue
  fi

  present=0
  command -v "$check_cmd" >/dev/null 2>&1 && present=1

  if [ "$UPDATE" = "1" ]; then
    # Update mode: refresh what exists; never install anything new.
    if [ "$present" = "0" ]; then
      echo "skip   $name (not installed)"
      skipped=$((skipped + 1))
    elif [ -z "${update_cmd:-}" ]; then
      echo "skip   $name (no update procedure defined)"
      skipped=$((skipped + 1))
    else
      echo "${DRY_PREFIX}update $name ($update_cmd)"
      if [ "$DRY_RUN" = "1" ]; then
        updated=$((updated + 1))
      elif bash -c "$update_cmd"; then
        updated=$((updated + 1))
      else
        echo "WARN   $name: update failed" >&2
        errors=$((errors + 1))
      fi
    fi
    continue
  fi

  # Install mode.
  if [ "$present" = "1" ]; then
    echo "skip   $name (already installed)"
    skipped=$((skipped + 1))
    continue
  fi
  if [ "$install_cmd" = "-" ]; then
    echo "skip   $name (update-only tool, not auto-installed)"
    skipped=$((skipped + 1))
    continue
  fi

  echo "${DRY_PREFIX}install $name ($install_cmd)"
  if [ "$DRY_RUN" = "1" ]; then
    installed=$((installed + 1))
  elif bash -c "$install_cmd"; then
    installed=$((installed + 1))
  else
    echo "WARN   $name: install failed" >&2
    errors=$((errors + 1))
  fi
done < <(manifest)

echo
echo "Done: $installed installed, $updated updated, $skipped skipped, $errors error(s)."
[ "$errors" -eq 0 ]
