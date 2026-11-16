# Profile: ci. A continuous-integration job: a fresh, disposable machine that
# nobody is watching. Detected when CI is "true" or "1" (see yb_detect_profile).

PROFILE_SUMMARY="CI job: disposable, unattended"

# GitHub Actions sets RUNNER_TEMP; elsewhere scratch stays in the checkout.
if [ -n "${RUNNER_TEMP:-}" ]; then
  PROFILE_SCRATCH="$RUNNER_TEMP/ybase"
else
  PROFILE_SCRATCH="$YB_ROOT/tmp"
fi
PROFILE_SCRATCH_DURABLE=no

profile_setup() {
  mkdir -p "$PROFILE_SCRATCH"
}

profile_doctor() {
  yb_info "note: CI job; nothing outside the checkout survives, and setup never prompts"
}
