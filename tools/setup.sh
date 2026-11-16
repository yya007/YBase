#!/usr/bin/env bash
# setup.sh: one-time, idempotent setup of this clone on this machine.
# Run via `bin/ybase setup [--profile P] [--parent-importer] [--non-interactive]
# [--kb PATH] [--repos-root PATH]`.
#
#   --profile P         pin profile P in .env instead of auto-detecting it
#   --parent-importer   also write ../CLAUDE.md importing this repo's rules, so a
#                       Claude Code session started in a sibling directory (for
#                       example a code repo next to this one) loads them too
#   --non-interactive   never read stdin or ask a question; the ci profile implies it.
#                       Without --kb, an already-set primary KB is kept, else kb/ here
#                       is initialised
#   --kb PATH           make PATH the primary knowledge base (as `kb primary` does) and
#                       skip the question
#   --repos-root PATH   set YBASE_REPOS_ROOT, replacing any value already set
#
# Safe to re-run. It never clobbers a file it did not create.
set -eu
. "$(dirname "$0")/profile.sh"

profile=""; parent=0; noninteractive=0; kb=""; repos_root=""
_usage="usage: bin/ybase setup [--profile P] [--parent-importer] [--non-interactive] [--kb PATH] [--repos-root PATH]"
while [ $# -gt 0 ]; do
  case "$1" in
    --profile) [ $# -ge 2 ] && [ -n "$2" ] || yb_die "--profile needs a profile name. $_usage"
               profile="$2"; shift 2 ;;
    --parent-importer) parent=1; shift ;;
    --non-interactive) noninteractive=1; shift ;;
    --kb) [ $# -ge 2 ] && [ -n "$2" ] || yb_die "--kb needs a path. $_usage"
          kb="$2"; shift 2 ;;
    --repos-root) [ $# -ge 2 ] && [ -n "$2" ] || yb_die "--repos-root needs a path. $_usage"
                  repos_root="$2"; shift 2 ;;
    *) yb_die "unknown argument: $1 (see ybase help)" ;;
  esac
done

mkdir -p "$YB_STATE"
if [ ! -f "$YB_ENV_FILE" ]; then
  cat > "$YB_ENV_FILE" <<'EOF'
# Machine settings for YBase. One KEY=VALUE per line; the value is everything
# after the first "=", taken literally: no quotes, and no comment after the value.
# Parsed, never sourced; never committed. The process environment wins over this file.
# All keys are optional. Each explanation sits on its own line above its key; to use a
# key, remove the "# " before it and edit the value.
#
# Pinned machine profile (default: auto-detected).
# YBASE_PROFILE=linux
# Scratch directory (default: from the profile).
# YBASE_SCRATCH=/path/to/scratch
# Parent directory for worktrees (default: from the profile).
# YBASE_WORKTREES=/path/to/worktrees   (default: .worktrees inside each repo)
# aws profile: fast local disk (default: probed).
# YBASE_FAST_DIR=/path/to/nvme
# Where managed repos are cloned (default: the directory holding YBase).
# YBASE_REPOS_ROOT=/path/to/repos
# One repo's path on this machine. The key ends in the repo's name in capitals,
# with every other character as "_" (my-repo becomes MY_REPO).
# YBASE_REPO_PATH_MY_REPO=/path/to/my-repo
# Knowledge base that receives new content (default: kb/ here).
# YBASE_KB_PRIMARY=/path/to/kb
# Additional knowledge base roots, separated by ":".
# YBASE_KB_PATHS=/path/to/kb-one:/path/to/kb-two
# 1 turns on the read-only main checkout guard.
# YBASE_GUARD_READONLY_CHECKOUT=1
# 1 turns on the draft-PR guard.
# YBASE_GUARD_PR_DRAFT=1
# 1 turns on the allow gate, a convenience with known gaps, not a security boundary.
# YBASE_ALLOW_GATE=1
# off stops setup writing the ybase command into ~/.local/bin; you then type bin/ybase.
# YBASE_LAUNCHER=off
# off stops this machine handing work to Codex. Unset, it is on when the Codex CLI is installed.
# YBASE_CODEX_DELEGATION=off
# YBASE_PUBLIC_REPO=owner/name
EOF
  yb_fix "created .env (commented template)"
fi
if [ -n "$repos_root" ]; then
  yb_env_set YBASE_REPOS_ROOT "$repos_root"
  yb_fix "set YBASE_REPOS_ROOT in .env to $repos_root"
elif [ -z "$(yb_env_get YBASE_REPOS_ROOT)" ]; then
  yb_env_set YBASE_REPOS_ROOT "$(dirname "$YB_ROOT")"
  yb_fix "set YBASE_REPOS_ROOT in .env to $(dirname "$YB_ROOT")"
fi
# Pin after the template exists, so a first run with --profile still gets the header.
[ -n "$profile" ] && bash "$YB_ROOT/tools/profile-cmd.sh" "$profile"
yb_load_profile
yb_ok "profile: $PROFILE_NAME ($(yb_profile_source))"
if [ "$PROFILE_NAME" = ci ]; then
  noninteractive=1
  [ "$(yb_profile_source)" = auto-detected ] \
    && yb_info "profile ci chosen because CI is set; questions are skipped; ybase profile <name> pins another"
fi
if [ -n "$kb" ]; then
  bash "$YB_ROOT/tools/kb.sh" primary "$kb"
elif [ "$noninteractive" -eq 0 ] && [ -z "$(yb_env_get YBASE_KB_PRIMARY)" ] && [ -t 0 ]; then
  printf 'Primary knowledge base (holds your repo list, lessons, rules and private terms) [%s/kb]: ' "$YB_ROOT"
  read -r _kb || _kb=""
  [ -z "$_kb" ] && _kb="$YB_ROOT/kb"
  bash "$YB_ROOT/tools/kb.sh" primary "$_kb"
else
  bash "$YB_ROOT/tools/kb.sh" init
fi
yb_info "note: put private terms the leak check must refuse in the primary KB's deny.list"

if [ "$parent" -eq 1 ]; then
  imp="$(dirname "$YB_ROOT")/CLAUDE.md"
  if [ -e "$imp" ]; then
    yb_ok "$imp exists (left as is)"
  else
    printf '<!-- Per-machine importer written by YBase setup. Not part of any repo. -->\n\n@%s\n' "$(yb_import_path "$(basename "$YB_ROOT")/CLAUDE.md")" > "$imp"
    yb_fix "created $imp -> $(basename "$YB_ROOT")/CLAUDE.md"
  fi
fi

# The ci profile runs ybase by path and has no shell to put a command in.
# The launcher is a convenience: a folder that cannot be written must not stop setup.
[ "$PROFILE_NAME" = ci ] || bash "$YB_ROOT/tools/launcher.sh" install \
  || yb_warn "could not write the ybase command; type bin/ybase in this clone, or set YB_BIN_DIR to a folder you can write"

echo
# Not under set -e: on a fresh machine the doctor can legitimately fail (a missing
# tool), and aborting here would swallow the next-step instructions below.
set +e
bash "$YB_ROOT/tools/doctor.sh"
rc=$?
set -e
echo
[ "$rc" -ne 0 ] && yb_warn "doctor exited $rc; fix its FAIL lines, then re-run: ybase doctor"
echo "Permissions: .claude/settings.json lists pwd, ls, wc, which, plain git status, diff, log and show, and the project's own checks. The allow gate, which approves a compound command when every part is listed, is off unless YBASE_ALLOW_GATE=1; its parsing has known gaps, so it is a convenience, not a security boundary. Put in .claude/settings.local.json, which is yours and never committed, only commands you are content to run unprompted."
echo "Next: read .ybase/MACHINE.md and profiles/$PROFILE_NAME/NOTES.md; eval \"\$(ybase env)\" sets TMPDIR."
exit "$rc"
