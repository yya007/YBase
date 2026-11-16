#!/usr/bin/env bash
# doctor.sh: normalize what can be normalized on this machine, probe what cannot,
# and write the result to .ybase/MACHINE.md for agents to read.
#
#   ybase doctor             normalize + probe + write MACHINE.md
#   ybase doctor --dry-run   probe only; print intended fixes and the report
#
# Normalizing means repo-local settings only. The doctor never edits global git
# config, shell profiles or anything outside this repository and the profile's
# scratch and worktree directories.
set -u
. "$(dirname "$0")/profile.sh"

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1
# A dry run writes nothing, and that includes the bytecode a python3 child (such
# as `kb.sh list`) would cache under tools/__pycache__.
if [ "$DRY" -eq 1 ]; then PYTHONDONTWRITEBYTECODE=1; export PYTHONDONTWRITEBYTECODE; fi
YB_WARNINGS=""
FAILED=0
yb_load_profile

# git_local <key> <want>: make a repo-local git setting hold.
git_local() {
  _cur="$(git -C "$YB_ROOT" config --local --get "$1" 2>/dev/null || true)"
  if [ "$_cur" = "$2" ]; then
    yb_ok "git $1=$2"
  elif [ "$DRY" -eq 1 ]; then
    yb_fix "(dry run) would set git $1=$2 (now: ${_cur:-unset})"
  else
    git -C "$YB_ROOT" config --local "$1" "$2"
    yb_fix "set git $1=$2 (was: ${_cur:-unset})"
  fi
}

echo "== profile: $PROFILE_NAME ($(yb_profile_source)), $PROFILE_SUMMARY"

echo "== toolchain"
for _t in git python3; do
  if yb_have "$_t"; then yb_ok "$_t: $($_t --version 2>&1 | sed -n '1p')"
  else yb_fail "$_t not found; YBase needs it"; FAILED=1; fi
done
# The floor is the `>= X.Y` bound of requires-python in pyproject.toml.
PY_FLOOR="$(sed -n 's/^[[:space:]]*requires-python[[:space:]]*=.*>=[[:space:]]*\([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p' \
  "$YB_ROOT/pyproject.toml" 2>/dev/null | sed -n '1p')"
PY_FLOOR="${PY_FLOOR:-3.10}"
if yb_have python3; then
  _pv="$(python3 --version 2>&1 | sed -n '1s/^Python \([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p')"
  if [ -n "$_pv" ] && [ "${_pv%%.*}" -lt "${PY_FLOOR%%.*}" ] ||
     { [ -n "$_pv" ] && [ "${_pv%%.*}" -eq "${PY_FLOOR%%.*}" ] && [ "${_pv#*.}" -lt "${PY_FLOOR#*.}" ]; }; then
    yb_warn "python3 on PATH is $_pv, below YBase's floor of $PY_FLOOR; its tools may fail (tools/pick_python.sh --for-path . names one that meets it)"
  fi
fi
if yb_have gh; then
  if gh auth status >/dev/null 2>&1; then yb_ok "gh authenticated"
  else yb_info "note: gh installed but not authenticated (gh auth login) - needed only for GitHub work"; fi
else
  yb_info "note: gh not installed - needed only for GitHub work"
fi

echo "== repository"
if git -C "$YB_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  git_local pull.rebase true
  git_local rebase.autoStash true
  git_local core.hooksPath .githooks
  if [ -z "$(git -C "$YB_ROOT" config user.email 2>/dev/null)" ]; then
    yb_warn "no git user.email; set one for this repo: git config user.email <you@example.com>"
  fi
else
  yb_warn "$YB_ROOT is not a git checkout"
fi
FS="$(yb_fs_type "$YB_ROOT")"
if yb_is_network_fs "$FS"; then
  yb_warn "repo is on a network filesystem ($FS): stat-heavy git is slow; see profiles/$PROFILE_NAME/NOTES.md"
else
  yb_ok "repo filesystem: $FS"
fi

echo "== storage"
if [ "$DRY" -eq 0 ]; then profile_setup; mkdir -p "$PROFILE_SCRATCH"; fi
if [ "$DRY" -eq 1 ]; then
  # A dry run writes nothing, not even a probe file.
  if [ -d "$PROFILE_SCRATCH" ]; then
    yb_ok "scratch present: $PROFILE_SCRATCH (durable: $PROFILE_SCRATCH_DURABLE; dry run, not probed by writing)"
  else
    yb_info "note: scratch $PROFILE_SCRATCH would be created"
  fi
elif [ -d "$PROFILE_SCRATCH" ] && yb_dir_writable "$PROFILE_SCRATCH"; then
  yb_ok "scratch writable: $PROFILE_SCRATCH (durable: $PROFILE_SCRATCH_DURABLE)"
else
  yb_fail "scratch not writable: $PROFILE_SCRATCH"; FAILED=1
fi

echo "== compute"
yb_codex_delegation
GPU="none detected"
if yb_have nvidia-smi; then
  _n="$(nvidia-smi -L 2>/dev/null | grep -c '^GPU' || true)"
  _m="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | sed -n '1p')"
  [ "${_n:-0}" -gt 0 ] && GPU="$_n x $_m"
elif [ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ]; then
  GPU="Apple Silicon (MPS)"
fi
yb_ok "GPU: $GPU"

echo "== profile checks ($PROFILE_NAME)"
profile_doctor

echo "== knowledge bases"
KB_LINES="$(bash "$YB_ROOT/tools/kb.sh" list)"
KB_LIST=""; KB_IMPORTS=""
TAB="$(printf '\t')"
while IFS="$TAB" read -r _role _path _state; do
  [ -z "$_role" ] && continue
  KB_LIST="$KB_LIST- $_role: \`$_path\` ($_state)
"
  case "$_state" in
    ok)
      yb_ok "$_role KB: $_path"
      _kbv="$(tr -d ' \n\r' < "$_path/VERSION")"; _cur="$(tr -d ' \n\r' < "$YB_ROOT/templates/kb/VERSION")"
      case "$_kbv" in
        ''|*[!0-9]*) yb_warn "$_role KB $_path has an unreadable VERSION (ybase kb init \"$_path\")" ;;
        *)
          if [ "$_kbv" -lt "$_cur" ]; then yb_warn "$_role KB $_path is at layout version $_kbv, current is $_cur: run ybase kb migrate \"$_path\""
          elif [ "$_kbv" -gt "$_cur" ]; then yb_warn "$_role KB $_path is at layout version $_kbv, newer than this YBase knows ($_cur): update YBase"; fi ;;
      esac ;;
    # An unplugged drive or unmounted share reads as missing; init would make a folder there.
    missing) yb_warn "$_role KB $_path is missing; if it is on a drive or share, mount it. kb init is only for a new KB" ;;
    *) yb_warn "$_role KB $_path is $_state (ybase kb init \"$_path\")" ;;
  esac
  if [ "$_role" = primary ] && [ -f "$_path/rules.md" ]; then KB_IMPORTS="$KB_IMPORTS@$(yb_import_path "$_path/rules.md")
"; fi
  if [ -f "$_path/memory/INDEX.md" ]; then KB_IMPORTS="$KB_IMPORTS@$(yb_import_path "$_path/memory/INDEX.md")
"; fi
done <<EOT
$KB_LINES
EOT
KB_REPORT="# Knowledge bases (generated by \`ybase doctor\`)

New content goes to the primary KB unless a request names another. Layout and rules: \`docs/kb.md\`.

$KB_LIST
$KB_IMPORTS"

YB_COMMAND="$(bash "$YB_ROOT/tools/launcher.sh" status)"
REPORT="$(cat <<EOF
# MACHINE: facts about this machine

> Generated by \`ybase doctor\` on $(date -u +%Y-%m-%dT%H:%MZ). Per machine and gitignored: never commit it.
> Facts true of every machine of this type live in [\`profiles/$PROFILE_NAME/NOTES.md\`](../profiles/$PROFILE_NAME/NOTES.md); read that next.

## Identity
- profile: **$PROFILE_NAME** ($(yb_profile_source)): $PROFILE_SUMMARY
- os/arch: $(uname -s) $(uname -m), kernel $(uname -r)
- shell: ${SHELL:-unknown}; bash for tools: ${BASH_VERSION}
- command: \`$YB_COMMAND\`$([ "$YB_COMMAND" = ybase ] || echo ' (no `ybase` on the PATH here: where a doc says `ybase ...`, run `bin/ybase ...` from this clone)')

## Storage
- repo: \`$YB_ROOT\` on \`$FS\`$(yb_is_network_fs "$FS" && echo ' (network filesystem: prefer `git diff --stat` over `git status`)')
- scratch (use as TMPDIR): \`$PROFILE_SCRATCH\`, durable: **$PROFILE_SCRATCH_DURABLE**
- worktrees (\`ybase wt\`): \`$(yb_worktrees_where)\`

## Compute
- GPU: $GPU

## Agents
- Codex delegation: **$YB_CODEX** ($YB_CODEX_WHY). When it is off, do the work in this session or hand it to a subagent, and say that no second model reviewed it.

## Warnings
${YB_WARNINGS:-- none}

## Machine-type notes ($PROFILE_NAME)
Claude Code inlines the import below; other agents open the file it names.

@$(yb_import_path "../profiles/$PROFILE_NAME/NOTES.md")
EOF
)"

if [ "$DRY" -eq 1 ]; then
  echo "== MACHINE.md (dry run, not written)"
  printf '%s\n' "$REPORT"
else
  mkdir -p "$YB_STATE"
  printf '%s\n' "$REPORT" > "$YB_STATE/MACHINE.md"
  printf '%s\n' "$KB_REPORT" > "$YB_STATE/KB.md"
  python3 "$YB_ROOT/tools/repos.py" render >/dev/null || yb_warn "could not write .ybase/REPOS.md"
  echo "wrote .ybase/MACHINE.md, .ybase/KB.md and .ybase/REPOS.md"
fi
exit "$FAILED"
