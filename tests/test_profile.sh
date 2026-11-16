#!/usr/bin/env bash
# test_profile.sh: profile detection and resolution order, against fixtures.
# Runs under bash 3.2. Usage: bash tests/test_profile.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FIX="$(mktemp -d "${TMPDIR:-/tmp}/ybase-test.XXXXXX")"
trap 'rm -rf "$FIX"' EXIT
pass=0; fail=0

expect() {  # expect <label> <want> <got>
  if [ "$2" = "$3" ]; then pass=$((pass + 1)); echo "pass $1"
  else fail=$((fail + 1)); echo "FAIL $1: want '$2', got '$3'"; fi
}

# Each case runs in a subshell so state and environment do not leak between them.
detect() {  # detect <uname> <dmi dir> [hypervisor uuid file]
  ( YB_ROOT="$FIX/repo" YB_UNAME="$1" YB_DMI_DIR="$2" YB_HYPERVISOR_UUID="${3:-$FIX/none}"
    YB_CI=""  # empty means "not CI", even when this suite itself runs in CI
    . "$ROOT/tools/profile.sh"; yb_detect_profile )
}

mkdir -p "$FIX/repo" "$FIX/dmi-nitro" "$FIX/dmi-tag" "$FIX/dmi-other" "$FIX/empty"
echo "Amazon EC2" > "$FIX/dmi-nitro/sys_vendor"
echo "i-0123456789abcdef0" > "$FIX/dmi-tag/board_asset_tag"
echo "Dell Inc." > "$FIX/dmi-other/sys_vendor"
echo "ec2e1916-9099-7caf-fd21-012345abcdef" > "$FIX/xen-uuid"

expect "darwin is macos"               macos "$(detect Darwin "$FIX/empty")"
expect "nitro vendor is aws"           aws   "$(detect Linux "$FIX/dmi-nitro")"
expect "instance asset tag is aws"     aws   "$(detect Linux "$FIX/dmi-tag")"
expect "xen hypervisor uuid is aws"    aws   "$(detect Linux "$FIX/empty" "$FIX/xen-uuid")"
expect "other vendor is linux"         linux "$(detect Linux "$FIX/dmi-other")"
expect "no dmi is linux"               linux "$(detect Linux "$FIX/empty")"
expect "unknown kernel is linux"       linux "$(detect FreeBSD "$FIX/empty")"

# Resolution order: env beats pin beats detection.
name() {  # name <env profile or empty> <pin or empty>
  ( YB_ROOT="$FIX/repo" YB_UNAME=Darwin YB_DMI_DIR="$FIX/empty" YB_CI=""
    rm -f "$FIX/repo/.env"
    if [ -n "$2" ]; then echo "YBASE_PROFILE=$2" > "$FIX/repo/.env"; fi
    if [ -n "$1" ]; then YBASE_PROFILE="$1"; export YBASE_PROFILE; else unset YBASE_PROFILE; fi
    . "$ROOT/tools/profile.sh"; yb_profile_name )
}
expect "detection when nothing set"    macos "$(name "" "")"
expect "pin beats detection"           linux "$(name "" linux)"
expect "env beats pin"                 aws   "$(name aws linux)"

# CI: detected before the OS test; YB_CI overrides CI; empty or other values mean not CI.
ci_name() {  # ci_name <CI or "-" for unset> <YB_CI or "-" for unset> <pin or empty>
  ( YB_ROOT="$FIX/repo" YB_UNAME=Darwin YB_DMI_DIR="$FIX/empty"
    rm -f "$FIX/repo/.env"
    unset YBASE_PROFILE YB_CI CI
    [ "$1" = "-" ] || CI="$1"; [ "$2" = "-" ] || YB_CI="$2"
    export CI YB_CI 2>/dev/null
    [ "$1" = "-" ] && unset CI; [ "$2" = "-" ] && unset YB_CI
    if [ -n "$3" ]; then echo "YBASE_PROFILE=$3" > "$FIX/repo/.env"; fi
    . "$ROOT/tools/profile.sh"; yb_profile_name )
}
expect "ci detected from CI=true"          ci    "$(ci_name true - "")"
expect "ci detected from CI=1"             ci    "$(ci_name 1 - "")"
expect "CI unset falls through to the OS"  macos "$(ci_name - - "")"
expect "CI=false falls through to the OS"  macos "$(ci_name false - "")"
expect "YB_CI overrides CI"                ci    "$(ci_name false 1 "")"
expect "empty YB_CI switches CI off"       macos "$(ci_name true "" "")"
expect "a pinned profile beats CI"         linux "$(ci_name true - linux)"

# Every shipped profile loads, sets a summary and a scratch dir, and defines its hooks.
for p in "$ROOT"/profiles/*/; do
  n="$(basename "$p")"
  case "$n" in _*) continue ;; esac
  got="$( YB_ROOT="$ROOT" YBASE_PROFILE="$n" YB_STATE="$FIX/state"
          . "$ROOT/tools/profile.sh"; yb_load_profile
          [ -n "$PROFILE_SUMMARY" ] && [ -n "$PROFILE_SCRATCH" ] && type profile_doctor >/dev/null && echo loaded )"
  expect "profile $n loads" loaded "$got"
done

echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
