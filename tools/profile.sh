# profile.sh: decide which machine profile applies, and load it. Source it.
#
# Resolution order, first match wins:
#   1. $YBASE_PROFILE        (one command, or a CI job)
#   2. YBASE_PROFILE in .env (pinned on this machine by `ybase profile <name>`)
#   3. auto-detection below     (local files only: no network, no root):
#      CI first (YB_CI if set, else CI; "true" or "1"), then the OS test
#
# Tests set YB_CI (empty means "not CI") and point YB_UNAME, YB_DMI_DIR and YB_HYPERVISOR_UUID at fixtures instead
# of the real machine.

# shellcheck source=lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# yb_is_ec2: 0 when the hardware identifies itself as an EC2 instance.
# Nitro instances report "Amazon EC2" as the DMI vendor and the instance id as
# the board asset tag; older Xen instances expose a hypervisor UUID starting "ec2".
yb_is_ec2() {
  _dmi="${YB_DMI_DIR:-/sys/class/dmi/id}"
  if [ -r "$_dmi/sys_vendor" ] && grep -qi 'amazon' "$_dmi/sys_vendor" 2>/dev/null; then
    return 0
  fi
  if [ -r "$_dmi/board_asset_tag" ] && grep -q '^i-[0-9a-f]' "$_dmi/board_asset_tag" 2>/dev/null; then
    return 0
  fi
  _hyp="${YB_HYPERVISOR_UUID:-/sys/hypervisor/uuid}"
  if [ -r "$_hyp" ] && grep -qi '^ec2' "$_hyp" 2>/dev/null; then
    return 0
  fi
  return 1
}

# yb_is_ci: 0 when running in a CI job. YB_CI, when set (even to empty), replaces CI.
yb_is_ci() {
  if [ -n "${YB_CI+x}" ]; then _ci="$YB_CI"; else _ci="${CI:-}"; fi
  case "$_ci" in true|1) return 0 ;; *) return 1 ;; esac
}

# yb_detect_profile: print the auto-detected profile name.
yb_detect_profile() {
  if yb_is_ci; then echo ci; return; fi
  case "${YB_UNAME:-$(uname -s)}" in
    Darwin) echo macos ;;
    Linux)
      if yb_is_ec2; then echo aws; else echo linux; fi ;;
    *) echo linux ;;
  esac
}

# yb_profile_name: print the profile in force, following the resolution order.
yb_profile_name() {
  _p="$(yb_setting YBASE_PROFILE)"
  if [ -n "$_p" ]; then echo "$_p"; else yb_detect_profile; fi
}

# yb_profile_source: say where the profile in force came from.
yb_profile_source() {
  if [ -n "${YBASE_PROFILE:-}" ]; then echo 'YBASE_PROFILE'
  elif [ -n "$(yb_env_get YBASE_PROFILE)" ]; then echo 'pinned in .env'
  else echo 'auto-detected'
  fi
}

yb_list_profiles() {
  for _d in "$YB_ROOT"/profiles/*/; do
    _n="$(basename "$_d")"
    case "$_n" in _*) ;; *) printf '%s ' "$_n" ;; esac
  done
}

# Defaults every profile may override. A profile file sets PROFILE_* variables
# and may redefine profile_doctor and profile_setup (see profiles/_template).
yb_profile_defaults() {
  PROFILE_SUMMARY="generic machine"
  PROFILE_SCRATCH="$YB_ROOT/tmp"
  PROFILE_SCRATCH_DURABLE=yes
  PROFILE_WORKTREES=".worktrees"   # relative: inside each repo; absolute: <dir>/<repo>/
  profile_doctor() { :; }
  profile_setup()  { :; }
}

# yb_worktrees_where: one line saying where `ybase wt` puts a worktree on this machine.
yb_worktrees_where() {
  case "$PROFILE_WORKTREES" in
    /*) echo "$PROFILE_WORKTREES/<repo>/" ;;
    *)  echo "<repo>/$PROFILE_WORKTREES/ (inside each repo)" ;;
  esac
}

# yb_load_profile: load the profile in force, then this machine's settings.
yb_load_profile() {
  PROFILE_NAME="$(yb_profile_name)"
  _pfile="$YB_ROOT/profiles/$PROFILE_NAME/profile.sh"
  if [ ! -f "$_pfile" ]; then
    yb_die "unknown profile '$PROFILE_NAME' (no profiles/$PROFILE_NAME/profile.sh). Known: $(yb_list_profiles)"
  fi
  yb_profile_defaults
  # shellcheck disable=SC1090
  . "$_pfile"
  _s="$(yb_setting YBASE_SCRATCH)"
  _w="$(yb_setting YBASE_WORKTREES)"
  PROFILE_SCRATCH="${_s:-$PROFILE_SCRATCH}"
  PROFILE_WORKTREES="${_w:-$PROFILE_WORKTREES}"
}
