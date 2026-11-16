#!/usr/bin/env bash
# update.sh: bring this clone up to its upstream. Run via `ybase update [--apply]`.
#
#   update           fetch the upstream (this updates remote-tracking refs and nothing
#                    else), then show the incoming commits and files and the upstream
#                    tip's short SHA; merge nothing
#   update --apply   fetch nothing; fast-forward to exactly the upstream tip the last
#                    plain `update` fetched and showed, without running any incoming git
#                    hook, then run the updated `ybase doctor` and show (not run)
#                    any pending knowledge base layout steps
#
# Refuses, changing nothing, when HEAD is detached, the branch has no upstream, tracked
# files are modified, or the branch has commits its upstream lacks (when the upstream
# also has commits you lack, it says the history was rewritten or diverged). Never
# merges, rebases or discards anything: only a fast-forward.
set -eu
. "$(dirname "$0")/lib.sh"

apply=0
for arg in "$@"; do
  case "$arg" in
    --apply) apply=1 ;;
    -h|--help) sed -n '2,/^set -eu/{/^set -eu/d;p;}' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "usage: ybase update [--apply]" >&2; exit 2 ;;
  esac
done

g() { git -C "$YB_ROOT" "$@"; }

branch="$(g symbolic-ref --quiet --short HEAD 2>/dev/null)" || yb_die "update: HEAD is detached; check out a branch first"
g rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1 \
  || yb_die "update: branch $branch has no upstream; set one with git branch --set-upstream-to"
[ -z "$(g status --porcelain --untracked-files=no)" ] \
  || yb_die "update: tracked files have uncommitted changes; commit them first, or set them aside on a branch"

upstream="$(g rev-parse --abbrev-ref --symbolic-full-name '@{u}')"
if [ "$apply" -eq 0 ]; then
  remote="$(g config "branch.$branch.remote")"
  g fetch --quiet "$remote" || yb_die "update: git fetch from $remote failed; check the network and the remote"
fi

ahead="$(g rev-list '@{u}..HEAD')"
behind="$(g rev-list 'HEAD..@{u}')"
if [ -n "$ahead" ] && [ -n "$behind" ]; then
  yb_die "update: $branch and $upstream have diverged, or the upstream history was rewritten; inspect it by hand (git log, git reflog), update will not touch it"
fi
[ -z "$ahead" ] \
  || yb_die "update: $branch has commits $upstream lacks; merge or rebase by hand, update will not"

if [ -z "$behind" ]; then
  if [ "$apply" -eq 1 ]; then
    yb_info "nothing fetched to apply; run ybase update first"
  else
    yb_info "up to date ($upstream)"
  fi
  exit 0
fi

yb_info "incoming commits from $upstream (tip $(g rev-parse --short '@{u}')):"
g log --oneline 'HEAD..@{u}'
yb_info ""
g diff --stat 'HEAD..@{u}'

g diff --name-only 'HEAD..@{u}' | while IFS= read -r f; do
  case "$f" in
    .githooks/*|bin/*|tools/*|profiles/*|.claude/hooks/*|.codex/*|.claude/settings.json|templates/kb/VERSION)
      yb_info "changes what runs on this machine: $f" ;;
  esac
done

if [ "$apply" -eq 0 ]; then
  yb_info ""
  yb_info "run ybase update --apply to merge exactly this; --apply runs the updated ybase doctor"
  exit 0
fi

yb_info "running the updated ybase doctor after the merge"
g -c core.hooksPath=/dev/null merge --ff-only --quiet '@{u}' || yb_die "update: fast-forward failed; nothing was changed"
yb_ok "fast-forwarded $branch to $upstream"

rc=0
bash "$YB_ROOT/bin/ybase" doctor || rc=$?
if [ "$rc" -ne 0 ]; then
  yb_warn "doctor exited $rc after the update; the update itself is kept"
fi

yb_info ""
yb_info "pending knowledge base layout steps (not run; apply with ybase kb migrate):"
bash "$YB_ROOT/bin/ybase" kb migrate --dry-run || true
exit "$rc"
