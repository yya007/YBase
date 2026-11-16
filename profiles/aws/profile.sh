# Profile: aws. An EC2 instance, often shared, often with a network filesystem
# (EFS or another NFS mount) for durable data and an instance-store NVMe volume
# for fast, ephemeral work.

PROFILE_SUMMARY="AWS EC2 instance: durable network storage plus ephemeral local NVMe"

# aws_fast_dir: the first writable instance-store mount, or nothing.
# YBASE_FAST_DIR (environment or .env) wins over the candidates below.
aws_fast_dir() {
  for _c in "$(yb_setting YBASE_FAST_DIR)" /opt/dlami/nvme /mnt/nvme /mnt/nvme0 /local_disk0 /scratch /mnt/local; do
    [ -n "$_c" ] && [ -d "$_c" ] || continue
    _u="$_c/${USER:-$(id -un)}"
    if [ -d "$_u" ] && yb_dir_writable "$_u"; then echo "$_u"; return; fi
    if yb_dir_writable "$_c"; then echo "$_c"; return; fi
  done
}

_fast="$(aws_fast_dir)"
if [ -n "$_fast" ]; then
  # Fast and private, but gone when the instance stops: never the only copy of anything.
  PROFILE_SCRATCH="$_fast/ybase-tmp/$(basename "$YB_ROOT")"
  PROFILE_SCRATCH_DURABLE=no
  PROFILE_WORKTREES="$_fast/ybase-wt/$(basename "$YB_ROOT")"
fi

profile_setup() {
  mkdir -p "$PROFILE_SCRATCH" "$PROFILE_WORKTREES"
}

profile_doctor() {
  # Instance store is ephemeral: a worktree there with unpushed commits dies with the instance.
  if [ "$PROFILE_SCRATCH_DURABLE" = no ]; then
    yb_info "note: scratch and worktrees are on instance store ($PROFILE_WORKTREES); push before stopping the instance"
  else
    yb_warn "no writable instance-store volume found; scratch falls back to $PROFILE_SCRATCH (set YBASE_FAST_DIR in .env)"
  fi
  # A shared /tmp is sticky and crowded: a fixed filename can belong to another user.
  if [ -d /tmp ] && [ "$(ls -A /tmp 2>/dev/null | wc -l | tr -d ' ')" -gt 500 ]; then
    yb_warn "/tmp holds over 500 entries (shared box?); keep TMPDIR on the profile scratch: $PROFILE_SCRATCH"
  fi
  if yb_have aws; then
    if aws sts get-caller-identity >/dev/null 2>&1; then
      yb_ok "aws CLI credentials resolve"
    else
      yb_info "note: aws CLI present but no credentials resolve (expired SSO session? run: aws sso login)"
    fi
  fi
}
