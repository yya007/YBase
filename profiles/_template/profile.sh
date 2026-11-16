# Profile: <name>. One sentence on which machines this covers.
#
# Copy this folder to profiles/<name>/, then teach tools/profile.sh to detect it
# (yb_detect_profile) or pin it per machine with: ybase profile <name>
#
# Variables (all optional; defaults come from yb_profile_defaults in tools/profile.sh):
#   PROFILE_SUMMARY          one line shown by `ybase doctor`
#   PROFILE_SCRATCH          where temporary files go (becomes TMPDIR for tools)
#   PROFILE_SCRATCH_DURABLE  yes | no: does scratch survive a reboot or shutdown?
#   PROFILE_WORKTREES        where `ybase wt` creates worktrees: a relative name is a folder
#                            inside each repo (default .worktrees); an absolute path gets <repo>/ under it
#
# Functions (optional):
#   profile_setup    create directories, install nothing system-wide
#   profile_doctor   probe what this machine type gets wrong; print with
#                    yb_ok / yb_info / yb_warn, never change system state, and
#                    write nothing: `doctor --dry-run` runs it too

PROFILE_SUMMARY="describe the machine type"

profile_setup() {
  mkdir -p "$PROFILE_SCRATCH"
}

profile_doctor() {
  :
}
