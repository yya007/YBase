#!/usr/bin/env bash
# profile-cmd.sh: show, pin or unpin the machine profile. Run via `ybase profile`.
set -eu
. "$(dirname "$0")/profile.sh"

case "${1:-}" in
  "")
    yb_load_profile
    echo "profile:   $PROFILE_NAME ($(yb_profile_source))"
    echo "detected:  $(yb_detect_profile)"
    echo "summary:   $PROFILE_SUMMARY"
    echo "scratch:   $PROFILE_SCRATCH (durable: $PROFILE_SCRATCH_DURABLE)"
    echo "worktrees: $(yb_worktrees_where)"
    echo "known:     $(yb_list_profiles)" ;;
  --unpin)
    yb_env_unset YBASE_PROFILE
    echo "unpinned; auto-detection now gives: $(yb_detect_profile)" ;;
  -*)
    yb_die "unknown flag $1" ;;
  *)
    [ -f "$YB_ROOT/profiles/$1/profile.sh" ] || yb_die "no profile '$1'. Known: $(yb_list_profiles)"
    yb_env_set YBASE_PROFILE "$1"
    echo "pinned profile '$1' on this machine (YBASE_PROFILE in .env); run: ybase doctor" ;;
esac
