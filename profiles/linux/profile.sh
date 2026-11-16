# Profile: linux. Any Linux machine no more specific profile claims: a
# workstation, an on-premises server, or a container.

PROFILE_SUMMARY="generic Linux machine"

PROFILE_SCRATCH="$YB_ROOT/tmp"
PROFILE_SCRATCH_DURABLE=yes

profile_setup() {
  mkdir -p "$PROFILE_SCRATCH"
}

profile_doctor() {
  if [ -f /.dockerenv ] || grep -qs 'docker\|containerd\|kubepods' /proc/1/cgroup 2>/dev/null; then
    yb_info "note: running inside a container; anything outside a mounted volume is lost when it exits"
  fi
}
