# lib.sh: shared helpers for YBase shell tools. Source it; do not run it.
#
# Portability contract: every tool must run under the bash 3.2 that macOS ships
# as /bin/bash, and under both GNU and BSD userlands. So: no associative arrays,
# no mapfile, no ${var,,}, no `sed -i`, no `readlink -f`, no GNU-only flags.

yb_root() {
  # The repo root, derived from this file's location so no path is hardcoded.
  (cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
}

YB_ROOT="${YB_ROOT:-$(yb_root)}"
YB_STATE="$YB_ROOT/.ybase"   # per-machine state, gitignored

yb_info() { printf '%s\n' "$*"; }
yb_ok()   { printf 'ok:   %s\n' "$*"; }
yb_fix()  { printf 'fix:  %s\n' "$*"; }
yb_warn() { printf 'WARN: %s\n' "$*" >&2; YB_WARNINGS="${YB_WARNINGS:-}- $*
"; }
yb_fail() { printf 'FAIL: %s\n' "$*" >&2; }
yb_die()  { yb_fail "$*"; exit 1; }

yb_have() { command -v "$1" >/dev/null 2>&1; }

# yb_import_path <path>: <path> as the target of a Claude Code `@` import. An import path
# ends at the first unescaped whitespace, so each space is written as a backslash and a space.
yb_import_path() { printf '%s\n' "$1" | sed 's/ /\\ /g'; }

# yb_dir_writable <dir>: prove it by writing, not by inspecting permissions.
yb_dir_writable() {
  _probe="$1/.ybase-write-probe.$$"
  ( : > "$_probe" ) 2>/dev/null || return 1
  rm -f "$_probe"
}

# yb_fs_type <path>: filesystem type of the mount holding <path>, or "unknown".
yb_fs_type() {
  case "$(uname -s)" in
    Linux)
      if yb_have findmnt; then
        _t="$(findmnt -no FSTYPE -T "$1" 2>/dev/null)"
        [ -n "$_t" ] && { echo "$_t"; return; }
      fi
      stat -f -c %T "$1" 2>/dev/null || echo unknown ;;
    Darwin)
      # BSD stat has no fs-type flag, so ask mount about the device holding the path.
      _dev="$(df "$1" 2>/dev/null | awk 'NR==2 {print $1}')"
      _t="$(mount | awk -v d="$_dev" '$1 == d { s = $0; sub(/.*\(/, "", s); sub(/,.*/, "", s); print s; exit }')"
      echo "${_t:-unknown}" ;;
    *) echo unknown ;;
  esac
}

# yb_is_network_fs <fstype>: 0 for filesystems where stat-heavy work is slow.
yb_is_network_fs() {
  case "$1" in
    nfs|nfs4|cifs|smbfs|smb2|smb3|fuse.sshfs|afpfs|lustre|fuse.s3fs|webdav) return 0 ;;
    *) return 1 ;;
  esac
}

# Machine settings live in $YB_ENV_FILE (.env at the repo root). One KEY=VALUE per
# line; the value is everything after the first "=", literal. The file is parsed
# here, never sourced.
# yb_main_checkout: the main checkout $YB_ROOT belongs to; $YB_ROOT itself unless it is a
# linked worktree, whose .git file names <main>/.git/worktrees/<name>. tools/envfile.py
# reads the same file the same way.
yb_main_checkout() {
  if [ -f "$YB_ROOT/.git" ]; then
    _gd="$(sed -n 's/^gitdir: //p' "$YB_ROOT/.git" 2>/dev/null)"
    case "$_gd" in */.git/worktrees/*) printf '%s\n' "${_gd%/.git/worktrees/*}"; return ;; esac
  fi
  printf '%s\n' "$YB_ROOT"
}

# A linked worktree has no .env of its own, so it reads its main checkout's.
YB_ENV_FILE="$YB_ROOT/.env"
[ -f "$YB_ENV_FILE" ] || YB_ENV_FILE="$(yb_main_checkout)/.env"

# yb_env_get <KEY>: print the file's value for KEY (the last such line), or nothing.
yb_env_get() {
  [ -f "$YB_ENV_FILE" ] || return 0
  _val=""
  while IFS= read -r _line || [ -n "$_line" ]; do
    case "$_line" in "$1="*) _val="${_line#*=}" ;; esac
  done < "$YB_ENV_FILE"
  printf '%s' "$_val"
  [ -z "$_val" ] || printf '\n'
}

# _yb_env_rewrite <KEY> set|unset [VALUE]: copy .env through a temp file, replacing
# or dropping KEY's lines and keeping every other line; append when KEY is new.
_yb_env_rewrite() {
  _tmp="$YB_ENV_FILE.tmp.$$"
  _seen=0
  # Start from a copy so the file keeps its mode (for example 600).
  if [ -f "$YB_ENV_FILE" ]; then cp -p "$YB_ENV_FILE" "$_tmp" || return 1; fi
  : > "$_tmp" || { rm -f "$_tmp"; return 1; }
  if [ -f "$YB_ENV_FILE" ]; then
    while IFS= read -r _line || [ -n "$_line" ]; do
      case "$_line" in
        "$1="*)
          if [ "$2" = set ] && [ "$_seen" -eq 0 ]; then printf '%s=%s\n' "$1" "$3" >> "$_tmp"; fi
          _seen=1 ;;
        *) printf '%s\n' "$_line" >> "$_tmp" ;;
      esac
    done < "$YB_ENV_FILE" || { rm -f "$_tmp"; return 1; }
  fi
  if [ "$_seen" -eq 0 ] && [ "$2" = set ]; then printf '%s=%s\n' "$1" "$3" >> "$_tmp" || { rm -f "$_tmp"; return 1; }; fi
  mv "$_tmp" "$YB_ENV_FILE" || { rm -f "$_tmp"; return 1; }
}

yb_env_set()   { _yb_env_rewrite "$1" set "$2"; }
yb_env_unset() { _yb_env_rewrite "$1" unset; }

# yb_setting <KEY>: the process environment's value when non-empty, else the file's.
yb_setting() {
  eval "_v=\"\${$1:-}\""
  if [ -n "$_v" ]; then printf '%s\n' "$_v"; else yb_env_get "$1"; fi
}

# Whether this machine hands work to Codex. YBASE_CODEX_DELEGATION=off in .env
# turns it off; otherwise it is on exactly when the Codex CLI is on PATH, so a
# machine without Codex needs no setting. YBASE_CODEX_BIN names another binary
# to look for (the tests use it). Sets YB_CODEX to on|off and YB_CODEX_WHY to the reason.
yb_codex_delegation() {
  case "$(yb_setting YBASE_CODEX_DELEGATION)" in
    off|OFF|0|no|false)
      YB_CODEX=off; YB_CODEX_WHY="YBASE_CODEX_DELEGATION=off in .env or the environment" ;;
    *)
      if yb_have "${YBASE_CODEX_BIN:-codex}"; then
        YB_CODEX=on; YB_CODEX_WHY="the Codex CLI is installed"
      else
        YB_CODEX=off; YB_CODEX_WHY="the Codex CLI is not installed on this machine"
      fi ;;
  esac
}
