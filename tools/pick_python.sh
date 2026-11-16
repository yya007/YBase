#!/usr/bin/env bash
# pick_python.sh: print the first interpreter on PATH that meets every project's floor.
#
#   tools/pick_python.sh <pyproject.toml> [more pyproject.toml...]
#   tools/pick_python.sh --for-path <dir-or-file>     nearest pyproject.toml at or above it
#
# The floor is the `>= X.Y` lower bound of `requires-python`. Candidates, in
# order: $PICK_PYTHON when set, then python3, python3.13 down to python3.8,
# then python. Exit 0 and print the path of the first that meets every floor;
# exit 3 with the list of what was tried when none does; exit 2 on a usage
# error, a missing pyproject or a project with no `>=` bound.
# Portability: bash 3.2 and BSD userland (no mapfile, no sed -i, no readlink -f).
set -u

usage() {
  echo "usage: pick_python.sh <pyproject.toml> [more pyproject.toml...]" >&2
  echo "       pick_python.sh --for-path <dir-or-file>" >&2
}

floor_from_file() {
  sed -n \
    's/^[[:space:]]*requires-python[[:space:]]*=.*>=[[:space:]]*\([0-9][0-9]*\)\.\([0-9][0-9]*\).*/\1.\2/p' \
    "$1" | head -1
}

nearest_pyproject() {
  dir="$1"
  [ -d "$dir" ] || dir="$(dirname "$dir")"
  dir="$(cd "$dir" 2>/dev/null && pwd)" || return 1
  while :; do
    if [ -f "$dir/pyproject.toml" ]; then
      printf '%s\n' "$dir/pyproject.toml"
      return 0
    fi
    [ "$dir" != / ] || return 1
    dir="$(dirname "$dir")"
  done
}

version_ge() {
  have_major="${1%%.*}" have_minor="${1#*.}"
  need_major="${2%%.*}" need_minor="${2#*.}"
  [ "$have_major" -gt "$need_major" ] \
    || { [ "$have_major" -eq "$need_major" ] && [ "$have_minor" -ge "$need_minor" ]; }
}

if [ "${1:-}" = "--for-path" ]; then
  [ "$#" -eq 2 ] || { usage; exit 2; }
  project="$(nearest_pyproject "$2")" || {
    echo "pick_python: no pyproject.toml found at or above $2" >&2
    exit 2
  }
  set -- "$project"
elif [ "$#" -eq 0 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
  usage
  exit 2
fi

need="0.0"
for project in "$@"; do
  if [ ! -r "$project" ] || [ ! -f "$project" ]; then
    echo "pick_python: cannot read $project" >&2
    exit 2
  fi
  floor="$(floor_from_file "$project")"
  if [ -z "$floor" ]; then
    echo "pick_python: $project has no requires-python >=X.Y lower bound" >&2
    exit 2
  fi
  if version_ge "$floor" "$need"; then
    need="$floor"
  fi
done

tried=""
seen="|"

# try_candidate <name-or-path>: print and exit 0 when it meets the floor.
try_candidate() {
  requested="$1"
  [ -n "$requested" ] || return 0
  case "$requested" in
    */*) resolved="$requested" ;;
    *)
      resolved="$(command -v -- "$requested" 2>/dev/null || true)"
      if [ -z "$resolved" ]; then
        tried="$tried  tried $requested: not found
"
        return 0
      fi ;;
  esac
  case "$seen" in
    *"|$resolved|"*) return 0 ;;
  esac
  seen="$seen$resolved|"
  if [ ! -x "$resolved" ]; then
    tried="$tried  tried $resolved: not executable
"
    return 0
  fi
  version_text="$("$resolved" --version 2>&1 || true)"
  version="$(printf '%s\n' "$version_text" | sed -n \
    's/.*Python[[:space:]]*\([0-9][0-9]*\)\.\([0-9][0-9]*\).*/\1.\2/p' | head -1)"
  if [ -z "$version" ]; then
    tried="$tried  tried $resolved: version unreadable (${version_text:-no output})
"
    return 0
  fi
  tried="$tried  tried $resolved: Python $version
"
  if version_ge "$version" "$need"; then
    printf '%s\n' "$resolved"
    exit 0
  fi
}

try_candidate "${PICK_PYTHON:-}"
try_candidate python3
for minor in 13 12 11 10 9 8; do
  try_candidate "python3.$minor"
done
try_candidate python

echo "pick_python: no interpreter on PATH meets >=$need" >&2
printf '%s' "$tried" >&2
echo "  Set PICK_PYTHON to a >=$need interpreter, or install one." >&2
exit 3
