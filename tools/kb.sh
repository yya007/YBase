#!/usr/bin/env bash
# kb.sh: manage knowledge bases (KBs). Run via `ybase kb`.
#
#   kb                 list KBs: primary first, then extras; state is ok, missing or no-skeleton
#   kb init [PATH]     copy templates/kb/ into PATH (default: the primary KB); never overwrites
#   kb primary PATH    init PATH, then make it the KB that receives new content
#   kb add PATH        add PATH to the additional KBs
#   kb remove PATH     take PATH out of the additional KBs
#   kb migrate [PATH] [--dry-run]  bring a KB's layout up to this YBase's version (default: the primary)
#
# Settings live in .env: YBASE_KB_PRIMARY and YBASE_KB_PATHS (":" separated).
set -eu
. "$(dirname "$0")/lib.sh"

usage() { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; }

# kb_abs PATH: PATH made absolute without requiring it to exist. A leading ~ is the
# home folder: an answer typed at a prompt, or a quoted flag, reaches us unexpanded.
kb_abs() {
  case "$1" in
    "~") printf '%s\n' "$HOME" ;;
    "~/"*) printf '%s/%s\n' "$HOME" "${1#\~/}" ;;
    /*) printf '%s\n' "$1" ;;
    *) printf '%s/%s\n' "$(pwd)" "$1" ;;
  esac
}

# kb_list: one "role<TAB>path<TAB>state" line per root, primary first.
kb_list() {
  python3 - "$YB_ROOT" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "tools"))
import envfile
for i, kb in enumerate(envfile.kb_roots(Path(sys.argv[1]))):
    state = "missing" if not kb.is_dir() else "ok" if (kb / "VERSION").is_file() else "no-skeleton"
    print(f"{'primary' if i == 0 else 'extra'}\t{kb}\t{state}")
PY
}

kb_primary_path() { kb_list | sed -n '1p' | cut -f2; }

kb_init() {
  _dest="$(kb_abs "${1:-$(kb_primary_path)}")"
  _src="$YB_ROOT/templates/kb"
  mkdir -p "$_dest"
  _made=0
  while IFS= read -r _rel; do
    [ -e "$_dest/$_rel" ] && continue
    mkdir -p "$(dirname "$_dest/$_rel")"
    cp "$_src/$_rel" "$_dest/$_rel"
    _made=$((_made + 1))
  done <<EOT
$(cd "$_src" && find . -type f | sed 's#^\./##' | sort)
EOT
  if [ "$_made" -gt 0 ]; then yb_fix "kb init: wrote $_made file(s) into $_dest"
  else yb_ok "kb skeleton present: $_dest"; fi
}

# kb_paths_edit add|remove PATH: rewrite the file's YBASE_KB_PATHS.
kb_paths_edit() {
  _mode="$1"; _target="$(kb_abs "$2")"
  _found=0; _joined=""
  while IFS= read -r _p; do
    [ -z "$_p" ] && continue
    if [ "$_p" = "$_target" ]; then
      _found=1
      [ "$_mode" = remove ] && continue
    fi
    _joined="${_joined:+$_joined:}$_p"
  done <<EOT
$(yb_env_get YBASE_KB_PATHS | tr ':' '\n')
EOT
  [ "$_mode" = add ] && [ "$_found" -eq 0 ] && _joined="${_joined:+$_joined:}$_target"
  if [ -n "$_joined" ]; then yb_env_set YBASE_KB_PATHS "$_joined"; else yb_env_unset YBASE_KB_PATHS; fi
  if [ "$_mode" = add ]; then yb_ok "additional KB: $_target"
  elif [ "$_found" -eq 1 ]; then yb_ok "removed $_target (its files are untouched)"
  else yb_info "$_target was not an additional KB"; fi
}

sub="${1:-list}"
[ $# -gt 0 ] && shift
case "$sub" in
  list) kb_list ;;
  init) kb_init "$@" ;;
  primary)
    [ $# -eq 1 ] || yb_die "usage: ybase kb primary PATH"
    kb_init "$1"
    yb_env_set YBASE_KB_PRIMARY "$(kb_abs "$1")"
    yb_ok "primary KB: $(kb_abs "$1")"
    ;;
  add|remove)
    [ $# -eq 1 ] || yb_die "usage: ybase kb $sub PATH"
    kb_paths_edit "$sub" "$1"
    ;;
  migrate)
    _path=""; _flags=""; _bad=0
    for _a in "$@"; do
      case "$_a" in
        --dry-run) _flags="--dry-run" ;;
        -h|--help) echo "usage: ybase kb migrate [PATH] [--dry-run]"; exit 0 ;;
        -*) _bad=1 ;;
        *) if [ -n "$_path" ]; then _bad=1; fi; _path="$_a" ;;
      esac
    done
    [ "$_bad" -eq 0 ] || { echo "usage: ybase kb migrate [PATH] [--dry-run]" >&2; exit 2; }
    [ -n "$_path" ] || _path="$(kb_primary_path)"
    # shellcheck disable=SC2086
    python3 "$YB_ROOT/tools/kb_migrate.py" $_flags "$(kb_abs "$_path")"
    ;;
  help|-h|--help) usage ;;
  *) usage >&2; exit 2 ;;
esac
