#!/usr/bin/env bash
# launcher.sh install|status: the `ybase` command on the PATH.
#
#   install   write a small launcher named `ybase` into YB_BIN_DIR (default: ~/.local/bin).
#             Run by `ybase setup`. Off when YBASE_LAUNCHER=off, in .env or the environment.
#   status    print the form of the command that works in this shell: `ybase` when the
#             launcher is on the PATH, else `bin/ybase`.
#
# The launcher runs the checkout the caller stands in (so a worktree runs its own copy),
# and otherwise the main checkout that installed it. It is the one file setup writes
# outside the clone without a flag, and it never replaces a file it did not write.
set -eu
. "$(dirname "$0")/lib.sh"

MARK='# ybase launcher'
bindir="${YB_BIN_DIR:-${HOME:-}/.local/bin}"
target="$bindir/ybase"

# The main checkout: a launcher must not point into a worktree that will be removed.
home="$(yb_main_checkout)"

on_path() {
  case ":${PATH:-}:" in *":$bindir:"*) return 0 ;; esac
  return 1
}

ours() { [ -f "$1" ] && sed -n '2p' "$1" 2>/dev/null | grep -q "^$MARK"; }

body() {
  # A single quote in the path is written as '\'' so the launcher reads it back whole.
  _q="$(printf '%s' "$home" | sed "s/'/'\\\\''/g")"
  cat <<LAUNCHER
#!/bin/sh
$MARK: written by \`ybase setup\`; delete it freely, setup writes it again.
# Runs the checkout you stand in, and otherwise the one named here.
home='$_q'
d="\$PWD"
while [ -n "\$d" ]; do
  if [ -x "\$d/bin/ybase" ] && [ -f "\$d/tools/profile.sh" ]; then exec "\$d/bin/ybase" "\$@"; fi
  [ "\$d" = / ] && break
  d="\$(dirname "\$d")"
done
if [ ! -x "\$home/bin/ybase" ]; then
  echo "ybase: no checkout at \$home; run bin/ybase setup in your clone to point this command at it" >&2
  exit 127
fi
exec "\$home/bin/ybase" "\$@"
LAUNCHER
}

case "${1:-}" in
  install)
    [ "$(yb_setting YBASE_LAUNCHER)" = off ] && exit 0
    [ -n "${YB_BIN_DIR:-}" ] || [ -n "${HOME:-}" ] || { yb_info "note: HOME is not set, so no ybase command was installed"; exit 0; }
    # A link counts as someone else's file even when it points at nothing: writing
    # through it would put the launcher wherever it points.
    if [ -L "$target" ] || { [ -e "$target" ] && ! ours "$target"; }; then
      yb_warn "$target exists and is not a ybase launcher; left as is, so keep typing bin/ybase or move that file"
      exit 0
    fi
    if [ -f "$target" ] && [ "$(body)" = "$(cat "$target")" ] && [ -x "$target" ]; then
      yb_ok "command: $target"
    else
      mkdir -p "$bindir"
      body > "$target"
      chmod +x "$target"
      yb_fix "wrote the ybase command to $target (runs $home)"
    fi
    on_path || yb_info "note: $bindir is not on your PATH. Until it is, type bin/ybase. To add it, put this line in your shell profile: export PATH=\"$bindir:\$PATH\""
    ;;
  status)
    _found="$(command -v ybase 2>/dev/null || true)"
    if [ -n "$_found" ] && ours "$_found"; then echo ybase; else echo bin/ybase; fi
    ;;
  *) echo "usage: launcher.sh install|status" >&2; exit 2 ;;
esac
