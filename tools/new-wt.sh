#!/usr/bin/env bash
# new-wt.sh: one worktree per unit of work, in one known folder per repo.
#   ybase wt <kind>/<subject> [--repo NAME] [--base REF]   create
#   ybase wt done <kind>/<subject> [--repo NAME]           remove once landed
# Without --repo the repo is YBase itself; with it, a managed repo from the repo list.
# The worktree goes in <repo>/.worktrees/, which the clone's own exclude file hides
# from git, unless the profile or YBASE_WORKTREES names an absolute folder.
set -eu
. "$(dirname "$0")/profile.sh"
yb_load_profile

usage="usage: ybase wt <kind>/<subject> [--repo NAME] [--base REF]  |  ybase wt done <kind>/<subject> [--repo NAME]"
KINDS="feat fix docs refactor test chore"
FILLER="tmp temp wip new misc stuff foo bar"

# yb_wt_name_problem NAME: print why NAME is not a good worktree name; print nothing when it is.
yb_wt_name_problem() {
  _kind="${1%%/*}"; _subject="${1#*/}"
  case "$1" in */*) ;; *) _kind="" ;; esac
  case " $KINDS " in
    *" $_kind "*) ;;
    *) echo "a name starts with a kind: feat, fix, docs, refactor, test or chore"; return ;;
  esac
  # LC_ALL=C: in other locales the range a-z also matches capital letters.
  printf '%s\n' "$_subject" | LC_ALL=C grep -Eq '^[a-z0-9]+(-[a-z0-9]+)*$' \
    || { echo "the subject is lowercase words joined by hyphens"; return; }
  _n=0
  for _w in $(printf '%s' "$_subject" | tr - ' '); do
    _n=$((_n + 1))
    case " $FILLER " in *" $_w "*) echo "'$_w' says nothing about the work"; return ;; esac
    case "$_w" in
      *[!0-9]*) ;;
      ????*) echo "a date does not name the work"; return ;;
    esac
  done
  if [ "$_n" -lt 2 ] || [ "$_n" -gt 5 ]; then echo "the subject is two to five words"; fi
}

mode=create
if [ "${1:-}" = done ]; then mode=done; shift; fi
name="${1:-}"
case "$name" in
  -h|--help)
    echo "$usage"
    echo "Creates branch <kind>/<subject> in <repo>/.worktrees/<kind>-<subject>, cut from the default branch."
    echo "Kinds: $KINDS. The subject is two to five lowercase words joined by hyphens: fix/leak-scan-symlinks."
    echo "'done' removes the worktree and its branch once the work is landed and nothing in it would be lost."
    echo "Without --repo the repo is YBase; with it, a managed repo from the repo list."
    exit 0 ;;
  ""|-*) yb_die "$usage (the name comes first and cannot start with '-')" ;;
esac
shift
base=""
repo_name=""
while [ $# -gt 0 ]; do
  case "$1" in
    --base) base="${2:-}"; [ -n "$base" ] || yb_die "--base needs a branch, tag or commit"; shift 2 ;;
    --repo) repo_name="${2:-}"; [ -n "$repo_name" ] || yb_die "--repo needs a repo name"; shift 2 ;;
    *) yb_die "unknown argument: $1" ;;
  esac
done
if [ "$mode" = create ]; then
  problem="$(yb_wt_name_problem "$name")"
  [ -z "$problem" ] || yb_die "'$name' is not a worktree name: $problem. Example: feat/worktree-home, fix/leak-scan-symlinks"
fi

repo="$YB_ROOT"
if [ -n "$repo_name" ]; then
  repo="$(python3 "$YB_ROOT/tools/repos.py" path "$repo_name" 2>/dev/null)" \
    || yb_die "unknown repo '$repo_name'; see ybase repos, or add it to repos.md and run: ybase repos clone $repo_name"
  [ -d "$repo" ] && git -C "$repo" rev-parse -q --git-dir >/dev/null 2>&1 \
    || yb_die "repo '$repo_name' is not cloned at $repo; run: ybase repos clone $repo_name"
fi
# The tool may be running from a linked worktree's own copy. Its worktrees belong to the
# main checkout, which git lists first, so a worktree never nests inside another.
_main="$(git -C "$repo" worktree list --porcelain 2>/dev/null | sed -n '1s/^worktree //p')"
[ -n "$_main" ] && repo="$_main"
if [ "$mode" = done ]; then
  exec python3 "$YB_ROOT/tools/worktrees.py" --repo "$repo" --done "$name"
fi
# Fetch first, so the remote's default branch is its tip now and not the tip of the
# last fetch. Best effort: offline, the worktree is cut from what is already here.
if git -C "$repo" remote get-url origin >/dev/null 2>&1; then
  git -C "$repo" fetch -q origin 2>/dev/null \
    || yb_warn "could not fetch origin; the worktree starts from the last fetched tip"
fi
if [ -z "$base" ]; then
  # Cut from the tip you will land on: the remote's default branch when there is one.
  # Same order as tools/worktrees.py, so the two never disagree about "landed".
  base="$(git -C "$repo" symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || true)"
  if [ -z "$base" ]; then
    for _c in origin/master origin/main master main; do
      if git -C "$repo" rev-parse -q --verify "$_c" >/dev/null; then base="$_c"; break; fi
    done
  fi
  [ -n "$base" ] || yb_die "no default branch found; pass --base REF"
fi

folder="$(printf '%s' "$name" | tr / -)"
case "$PROFILE_WORKTREES" in
  /*) path="$PROFILE_WORKTREES/$(basename "$repo")/$folder" ;;
  *)
    # Inside the repo. The clone's own exclude file hides the folder, so nothing is
    # committed in the repo and a managed repo never learns who made the worktree.
    path="$repo/$PROFILE_WORKTREES/$folder"
    _common="$(cd "$repo" && cd "$(git rev-parse --git-common-dir)" && pwd)"
    mkdir -p "$_common/info"
    grep -qxF "$PROFILE_WORKTREES/" "$_common/info/exclude" 2>/dev/null \
      || printf '%s\n' "$PROFILE_WORKTREES/" >> "$_common/info/exclude" ;;
esac
[ -e "$path" ] && yb_die "$path already exists"
mkdir -p "$(dirname "$path")"
git -C "$repo" worktree add --no-track -b "$name" "$path" "$base"
echo "worktree: $path  (branch $name from $base)"
echo "next: work by path from YBase (git -C \"$path\" ...), and run the repo's own tests and checks against that path"
echo "when it has landed: ybase wt done $name${repo_name:+ --repo \"$repo_name\"}"
if [ "$PROFILE_SCRATCH_DURABLE" = no ]; then
  echo "note: this directory is on ephemeral storage; push $name before the machine stops"
fi
