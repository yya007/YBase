# Profile: macos. A personal laptop or desktop: local SSD, one user, no CUDA.

PROFILE_SUMMARY="macOS workstation: local disk, single user, no CUDA"

# Scratch stays inside the repo (gitignored). macOS gives each user a private
# $TMPDIR, so the shared-/tmp hazard of a Linux server does not apply here.
PROFILE_SCRATCH="$YB_ROOT/tmp"
PROFILE_SCRATCH_DURABLE=yes

profile_setup() {
  mkdir -p "$PROFILE_SCRATCH"
}

profile_doctor() {
  # /bin/bash on macOS is 3.2. YBase tools are written for it; your own scripts may not be.
  _bv="$(/bin/bash -c 'echo ${BASH_VERSINFO[0]}' 2>/dev/null)"
  if [ "${_bv:-0}" -lt 4 ]; then
    yb_info "note: /bin/bash is ${_bv:-unknown}.x; scripts using bash 4+ features need a Homebrew bash"
  fi
  # The default APFS volume is case-insensitive: two paths differing only in case collide.
  # Probed without writing: on such a volume both spellings name the same file.
  if [ "$YB_ROOT/AGENTS.md" -ef "$YB_ROOT/agents.md" ]; then
    yb_info "note: this filesystem is case-insensitive; never commit two names that differ only in case"
  fi
  case "$(uname -m)" in
    arm64) yb_info "note: Apple Silicon (Homebrew prefix /opt/homebrew); GPU work uses MPS locally or runs remotely" ;;
    *)     yb_info "note: Intel Mac (Homebrew prefix /usr/local)" ;;
  esac
}
