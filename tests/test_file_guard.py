"""Tests for .claude/hooks/file-guard.py.

The hook is driven as a subprocess with a PreToolUse-style JSON payload on
stdin and a throwaway project root (CLAUDE_PROJECT_DIR) containing a
.claude/file-guard pattern list. Exit 2 = blocked, exit 0 = allowed.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "file-guard.py"


def _run(tmp_path, payload, patterns="\n".join([".env", "credentials", ".pem"])):
    guard_dir = tmp_path / ".claude"
    guard_dir.mkdir(exist_ok=True)
    (guard_dir / "file-guard").write_text(f"# test patterns\n{patterns}\n")
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        env=env,
        capture_output=True,
        text=True,
    )


def _payload(tool="Write", file_path="src/app.py"):
    return {"tool_name": tool, "tool_input": {"file_path": file_path}}


def test_blocks_write_to_guarded_path(tmp_path):
    result = _run(tmp_path, _payload(file_path="deploy/.env.production"))
    assert result.returncode == 2
    assert "file-guard" in result.stderr
    assert ".env" in result.stderr


def test_allows_write_to_normal_path(tmp_path):
    result = _run(tmp_path, _payload(file_path="src/pipeline/config.py"))
    assert result.returncode == 0
    assert result.stderr == ""


def test_blocks_edit_and_notebook_edit(tmp_path):
    assert _run(tmp_path, _payload(tool="Edit", file_path="a/credentials.json")).returncode == 2
    nb = {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": "keys/server.pem.ipynb"}}
    assert _run(tmp_path, nb).returncode == 2


def test_ignores_unguarded_tools(tmp_path):
    result = _run(tmp_path, _payload(tool="Read", file_path="deploy/.env"))
    assert result.returncode == 0


def test_comments_and_blanks_ignored(tmp_path):
    result = _run(tmp_path, _payload(file_path="src/app.py"), patterns="# src is fine\n\nsrc/app")
    assert result.returncode == 2  # real pattern matches
    result = _run(tmp_path, _payload(file_path="notes.md"), patterns="# notes.md\n")
    assert result.returncode == 0  # commented pattern does not


def test_fails_open_on_garbage_stdin(tmp_path):
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, str(HOOK)], input="not json", env=env, capture_output=True, text=True
    )
    assert result.returncode == 0


def test_fails_open_when_pattern_list_missing(tmp_path):
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)  # no .claude/file-guard created
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(_payload(file_path="deploy/.env")),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
