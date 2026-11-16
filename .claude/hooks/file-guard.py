#!/usr/bin/env python3
"""PreToolUse hook: refuse a Write, Edit or NotebookEdit on a sensitive path.

Rule 33 in docs/rules.md: never route around a guard. Secrets and production
configuration must not be written by an agent at all, so this guard sits at the
write itself rather than at review time.

REFUSES: Write, Edit and NotebookEdit whose target path (`file_path`, or
`notebook_path`) contains any pattern from `.claude/file-guard` as a substring.
That file holds one pattern per line; blank lines and `#` comments are ignored.
The project root comes from $CLAUDE_PROJECT_DIR, else from this hook's own
location, never from the working directory. Denial is exit 2 with the reason on
stderr.

PASSES: any other tool; a path no pattern matches; a call with no path; a
missing pattern file; a payload the hook cannot read (fails open, so a broken
payload never stops all work).

ESCAPE: none on the command line. Changing `.claude/file-guard` or this hook
takes a reviewed commit backed by a recorded decision, an ADR
(docs/protocols/decisions.md); the user can make a refused write by hand.

Claude Code only. Codex reads the same list as a rule (docs/codex.md).
Runnable by hand: `python3 .claude/hooks/file-guard.py < payload.json`.
"""

import json
import os
import sys
from pathlib import Path

GUARDED_TOOLS = {"Write", "Edit", "NotebookEdit"}


def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    # Hook lives at <root>/.claude/hooks/file-guard.py — resolve from here,
    # not from cwd (see docs/casebook/agents.md on cwd-dependent hooks).
    return Path(__file__).resolve().parents[2]


def load_patterns(guard_file: Path) -> list[str]:
    if not guard_file.is_file():
        return []
    patterns = []
    for line in guard_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") not in GUARDED_TOOLS:
        return 0
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not file_path:
        return 0
    for pattern in load_patterns(project_root() / ".claude" / "file-guard"):
        if pattern in file_path:
            print(
                f"file-guard: '{file_path}' matches protected pattern "
                f"'{pattern}' — write blocked. Sensitive files are listed in "
                ".claude/file-guard; changing it requires an ADR (docs/rules.md, rule 33).",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
