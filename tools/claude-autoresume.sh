#!/usr/bin/env bash
#
# claude-autoresume.sh — resume Claude Code sessions paused by a usage limit.
#
# Scans this project's session transcripts, finds conversations whose last event
# was a usage-limit (rate-limit) error, and resumes each one sequentially —
# sleeping out the limit window and retrying — until the turn goes through.
# Launch it after you hit a limit, then walk away.
#
# Dependency-free: bash + the `claude` CLI (no jq). Current project only.
#
# Usage: claude-autoresume.sh [options]
#   --dry-run              List paused sessions and exit; resume nothing.
#   --since DUR            Ignore sessions paused longer ago than DUR (default 24h).
#   --nudge STR            Message sent to resume a session (default "continue").
#   --max-resumes N        Max limit-retries per session (default 12).
#   --retry-interval DUR   Sleep when the reset time can't be parsed (default 15m).
#   --buffer SEC           Extra seconds slept past the reset time (default 60).
#   --claude-args "..."    Extra args passed through to claude (e.g. --allowedTools).
#   --yolo                 Add --dangerously-skip-permissions (opt-in; unsafe).
#   --log FILE             Also append status lines to FILE.
#   -h, --help             Show this help.
#
# DUR accepts a bare number of seconds or a <n>[smhd] suffix (30s, 15m, 24h, 2d).
#
# Examples (run from your project's root directory):
#   claude-autoresume.sh --dry-run                 # list paused sessions only
#   claude-autoresume.sh --claude-args "--allowedTools Bash Edit Read"
#   claude-autoresume.sh --since 3h --log ~/autoresume.log
#
# Unattended headless resumes have no human to approve tool calls, so pass your
# own allowlist via --claude-args, or --yolo to skip permission checks entirely.
#
# How it works:
#   1. Discover — scan this project's transcripts and keep sessions whose last
#      usage-limit error isn't followed by a later turn (see is_limit_paused).
#   2. List — print them (oldest pause first); --dry-run stops here.
#   3. Resume — for each, run `claude -r <id> -p <nudge>` and react: success →
#      next; limit → sleep until the reset time from the *live* error, retry;
#      other error → skip, non-zero exit.
#
# Test/override hooks (env): CLAUDE_BIN, AUTORESUME_SLEEP, AUTORESUME_NOW,
# PROJECTS_DIR, LIMIT_PATTERN. Full usage guide: docs/claude-autoresume.md.
# Design: docs/design/claude-autoresume.md.
set -euo pipefail

CLAUDE_BIN="${CLAUDE_BIN:-claude}"
AUTORESUME_SLEEP="${AUTORESUME_SLEEP:-sleep}"
PROJECTS_DIR="${PROJECTS_DIR:-$HOME/.claude/projects}"
# Text that marks a usage-limit error (case-insensitive). "api_error_status":429
# is always treated as a limit in addition to these.
LIMIT_PATTERN="${LIMIT_PATTERN:-usage limit|rate limit|limit reached}"

DRY_RUN=0
SINCE="24h"
NUDGE="continue"
MAX_RESUMES=12
RETRY_INTERVAL_RAW="15m"
BUFFER=60
LOG_FILE=""
YOLO=0
CLAUDE_ARGS=()

usage() {
  cat <<'EOF'
claude-autoresume.sh — resume Claude Code sessions paused by a usage limit.

Usage: claude-autoresume.sh [options]
  --dry-run              List paused sessions and exit; resume nothing.
  --since DUR            Ignore sessions paused longer ago than DUR (default 24h).
  --nudge STR            Message sent to resume a session (default "continue").
  --max-resumes N        Max limit-retries per session (default 12).
  --retry-interval DUR   Sleep when the reset time can't be parsed (default 15m).
  --buffer SEC           Extra seconds slept past the reset time (default 60).
  --claude-args "..."    Extra args passed through to claude (e.g. --allowedTools).
  --yolo                 Add --dangerously-skip-permissions (opt-in; unsafe).
  --log FILE             Also append status lines to FILE.
  -h, --help             Show this help.

DUR accepts a bare number of seconds or a <n>[smhd] suffix (30s, 15m, 24h, 2d).
EOF
}

log() {
  printf '%s\n' "$*" >&2
  [ -n "$LOG_FILE" ] && printf '%s\n' "$*" >>"$LOG_FILE"
  return 0
}

to_seconds() {
  local d="$1"
  if [[ "$d" =~ ^([0-9]+)([smhd]?)$ ]]; then
    local n="${BASH_REMATCH[1]}" u="${BASH_REMATCH[2]}"
    case "$u" in
      s | "") echo "$n" ;;
      m) echo $((n * 60)) ;;
      h) echo $((n * 3600)) ;;
      d) echo $((n * 86400)) ;;
    esac
  else
    echo "claude-autoresume: invalid duration: $d" >&2
    return 1
  fi
}

# File mtime as epoch seconds. GNU stat takes -c; BSD stat takes -f (and on GNU
# -f means filesystem status, so GNU is tried first).
file_mtime() {
  stat -c %Y "$1" 2>/dev/null || stat -f %m "$1"
}

# Epoch for a local wall-clock time given as "YYYY-MM-DDTHH:MM[:SS]". GNU date
# parses it with -d; BSD date needs -j -f. Prints nothing when neither works.
local_to_epoch() {
  local t="$1"
  date -d "$t" +%s 2>/dev/null && return 0
  case "$t" in
    *:*:*) date -j -f '%Y-%m-%dT%H:%M:%S' "$t" +%s 2>/dev/null && return 0 ;;
    *) date -j -f '%Y-%m-%dT%H:%M' "$t" +%s 2>/dev/null && return 0 ;;
  esac
  return 1
}

now_epoch() { echo "${AUTORESUME_NOW:-$(date +%s)}"; }

# Encode $PWD the way Claude Code names its per-project transcript dir:
# every "/" and "." becomes "-".
encode_cwd() {
  local e="${PWD//\//-}"
  echo "${e//./-}"
}

# True if the transcript's last usage-limit api_error is not followed by any
# later user/assistant turn (i.e. the session is still paused on that limit).
is_limit_paused() {
  local f="$1" err_ln after
  err_ln="$(grep -niE '"subtype":"api_error"' "$f" 2>/dev/null \
    | grep -iE "($LIMIT_PATTERN|\"status\":429)" | tail -1 | cut -d: -f1)" || true
  [ -n "$err_ln" ] || return 1
  after="$(tail -n +"$((err_ln + 1))" "$f" 2>/dev/null \
    | grep -cE '"type":"(user|assistant)"')" || true
  [ "${after:-0}" -eq 0 ]
}

# Classify a live `claude -p --output-format json` result: success | limit | error.
classify() {
  local json="$1"
  if grep -q '"is_error":false' <<<"$json"; then echo success; return; fi
  if grep -qiE "\"api_error_status\":429|$LIMIT_PATTERN" <<<"$json"; then echo limit; return; fi
  echo error
}

# Echo the reset time (epoch) parsed from a limit result, or nothing if unparseable.
parse_reset_epoch() {
  local json="$1" v
  v="$(grep -oiE 'reached\|[0-9]{9,}' <<<"$json" | grep -oE '[0-9]{9,}' | head -1)" || true
  if [ -n "$v" ]; then echo "$v"; return; fi
  v="$(grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2})?' <<<"$json" | head -1)" || true
  if [ -n "$v" ]; then local_to_epoch "$v" && return; fi
  v="$(grep -oiE 'resets? at [0-9]{1,2}:[0-9]{2}' <<<"$json" | grep -oE '[0-9]{1,2}:[0-9]{2}' | head -1)" || true
  if [ -n "$v" ]; then local_to_epoch "$(date +%Y-%m-%d)T$v" && return; fi
  echo ""
}

# Resume one session, waiting out limits. Returns 0 ok, 2 non-limit error, 3 capped.
resume_session() {
  local id="$1" attempt=0 json cls target now wait
  while :; do
    attempt=$((attempt + 1))
    json="$("$CLAUDE_BIN" -r "$id" -p "$NUDGE" --output-format json ${CLAUDE_ARGS[@]+"${CLAUDE_ARGS[@]}"} 2>&1)" || true
    cls="$(classify "$json")"
    case "$cls" in
      success)
        log "  $id: resumed OK"
        return 0
        ;;
      error)
        log "  $id: non-limit error, skipping"
        return 2
        ;;
      limit)
        if [ "$attempt" -ge "$MAX_RESUMES" ]; then
          log "  $id: still limited after $MAX_RESUMES attempts, giving up"
          return 3
        fi
        target="$(parse_reset_epoch "$json")"
        now="$(now_epoch)"
        if [ -n "$target" ]; then
          wait=$((target - now + BUFFER))
          [ "$wait" -lt "$BUFFER" ] && wait="$BUFFER"
        else
          wait="$RETRY_INTERVAL"
        fi
        log "  $id: limited, sleeping ${wait}s (attempt $attempt/$MAX_RESUMES)"
        "$AUTORESUME_SLEEP" "$wait"
        ;;
    esac
  done
}

main() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --dry-run) DRY_RUN=1 ;;
      --since) SINCE="$2"; shift ;;
      --nudge) NUDGE="$2"; shift ;;
      --max-resumes) MAX_RESUMES="$2"; shift ;;
      --retry-interval) RETRY_INTERVAL_RAW="$2"; shift ;;
      --buffer) BUFFER="$2"; shift ;;
      --claude-args) read -ra CLAUDE_ARGS <<<"$2"; shift ;;
      --yolo) YOLO=1 ;;
      --log) LOG_FILE="$2"; shift ;;
      -h | --help) usage; return 0 ;;
      *) echo "claude-autoresume: unknown option: $1" >&2; usage; return 64 ;;
    esac
    shift
  done

  command -v "$CLAUDE_BIN" >/dev/null 2>&1 || {
    echo "claude-autoresume: '$CLAUDE_BIN' not found on PATH" >&2
    return 127
  }

  local since_s retry_s
  since_s="$(to_seconds "$SINCE")"
  retry_s="$(to_seconds "$RETRY_INTERVAL_RAW")"
  RETRY_INTERVAL="$retry_s"

  if [ "$YOLO" -eq 1 ]; then
    log "claude-autoresume: WARNING --yolo enables --dangerously-skip-permissions"
    CLAUDE_ARGS+=(--dangerously-skip-permissions)
  fi

  local dir
  dir="$PROJECTS_DIR/$(encode_cwd)"
  if [ ! -d "$dir" ]; then
    log "claude-autoresume: no session history for this project ($dir)"
    return 0
  fi

  # Collect "<mtime> <id>" for limit-paused sessions within the recency window.
  # File mtime is the pause time proxy: a paused transcript's last write is the
  # limit error itself, so mtime ≈ when the limit was hit.
  local now found=() f mt age id
  now="$(now_epoch)"
  for f in "$dir"/*.jsonl; do
    [ -e "$f" ] || continue
    is_limit_paused "$f" || continue
    mt="$(file_mtime "$f")"
    age=$((now - mt))
    [ "$age" -le "$since_s" ] || continue
    id="$(basename "$f" .jsonl)"
    found+=("$mt $id")
  done

  if [ "${#found[@]}" -eq 0 ]; then
    log "claude-autoresume: no limit-paused sessions in the last $SINCE"
    return 0
  fi

  # Oldest pause first.
  local ids=()
  while read -r _ id; do ids+=("$id"); done < <(printf '%s\n' "${found[@]}" | sort -n)

  echo "claude-autoresume: ${#ids[@]} limit-paused session(s) in $(basename "$dir"):"
  for id in "${ids[@]}"; do echo "  $id"; done

  if [ "$DRY_RUN" -eq 1 ]; then
    log "claude-autoresume: --dry-run, resuming nothing"
    return 0
  fi

  # Resume one at a time (parallel would just re-hit the shared limit). A single
  # failed session sets a non-zero overall exit but never aborts the rest.
  local rc=0 status
  for id in "${ids[@]}"; do
    resume_session "$id" && status=0 || status=$?
    [ "$status" -eq 0 ] || rc=1
  done
  return "$rc"
}

main "$@"
