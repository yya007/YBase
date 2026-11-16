#!/usr/bin/env bash
#
# update-tools.sh — update the optional workspace tooling.
#
# Thin wrapper: runs setup-tools.sh in update mode (refresh what's installed,
# never install anything new). Supports the same DRY_RUN / TOOLS_MANIFEST
# overrides — see setup-tools.sh for details.
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPDATE=1 exec bash "$SCRIPT_DIR/setup-tools.sh"
