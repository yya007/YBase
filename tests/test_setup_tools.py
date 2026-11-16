"""Tests for tools/setup-tools.sh.

Driven as a subprocess with a TOOLS_MANIFEST override, so no real installers
(uv/npm/brew) or network are involved: fake tools use `bash` as an
always-present check command and `touch <marker>` as the install command.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "setup-tools.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None,
    reason="bash is required to exercise setup-tools.sh",
)


def _run(tmp_path, manifest_lines, dry_run=False):
    manifest = tmp_path / "tools.txt"
    manifest.write_text("\n".join(manifest_lines) + "\n")
    env = os.environ.copy()
    env["TOOLS_MANIFEST"] = str(manifest)
    if dry_run:
        env["DRY_RUN"] = "1"
    return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)


def test_skips_tool_already_on_path(tmp_path):
    # `bash` is definitely on PATH, so the install command must never run.
    marker = tmp_path / "should-not-exist"
    result = _run(tmp_path, [f"fake|bash|touch {marker}"])
    assert result.returncode == 0, result.stderr
    assert "skip   fake (already installed)" in result.stdout
    assert not marker.exists()


def test_installs_missing_tool(tmp_path):
    marker = tmp_path / "installed-marker"
    result = _run(tmp_path, [f"fake|definitely-not-a-command-xyz|touch {marker}"])
    assert result.returncode == 0, result.stderr
    assert "install fake" in result.stdout
    assert marker.exists()
    assert "1 installed" in result.stdout


def test_dry_run_installs_nothing(tmp_path):
    marker = tmp_path / "installed-marker"
    result = _run(tmp_path, [f"fake|definitely-not-a-command-xyz|touch {marker}"], dry_run=True)
    assert result.returncode == 0, result.stderr
    assert "install fake" in result.stdout  # plan printed...
    assert not marker.exists()  # ...but nothing ran


def test_failed_install_warns_and_exits_nonzero(tmp_path):
    ok_marker = tmp_path / "ok-marker"
    lines = [
        "broken|definitely-not-a-command-xyz|false",
        f"good|also-not-a-command-xyz|touch {ok_marker}",
    ]
    result = _run(tmp_path, lines)
    assert result.returncode != 0
    assert "broken: install failed" in result.stderr
    assert ok_marker.exists()  # failure does not block later tools
    assert "1 installed" in result.stdout and "1 error" in result.stdout


def test_malformed_line_warns_and_errors(tmp_path):
    result = _run(tmp_path, ["just-a-name", "fake|bash|true"])
    assert result.returncode != 0
    assert "malformed manifest line" in result.stderr
    assert "skip   fake" in result.stdout  # valid line still processed


def test_comments_and_blanks_ignored(tmp_path):
    result = _run(tmp_path, ["# comment", "", "fake|bash|true", "   "])
    assert result.returncode == 0, result.stderr
    assert "1 skipped" in result.stdout


UPDATE_SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "update-tools.sh"


def _run_update(tmp_path, manifest_lines, dry_run=False, via_wrapper=False):
    manifest = tmp_path / "tools.txt"
    manifest.write_text("\n".join(manifest_lines) + "\n")
    env = os.environ.copy()
    env["TOOLS_MANIFEST"] = str(manifest)
    if not via_wrapper:
        env["UPDATE"] = "1"
    if dry_run:
        env["DRY_RUN"] = "1"
    script = UPDATE_SCRIPT if via_wrapper else SCRIPT
    return subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)


def test_update_refreshes_installed_tool(tmp_path):
    marker = tmp_path / "updated-marker"
    # `bash` is on PATH -> tool counts as installed -> update_cmd runs.
    result = _run_update(tmp_path, [f"fake|bash|true|touch {marker}"])
    assert result.returncode == 0, result.stderr
    assert "update fake" in result.stdout
    assert marker.exists()
    assert "1 updated" in result.stdout


def test_update_never_installs_missing_tool(tmp_path):
    marker = tmp_path / "should-not-exist"
    result = _run_update(tmp_path, [f"fake|not-a-command-xyz|touch {marker}|touch {marker}"])
    assert result.returncode == 0, result.stderr
    assert "skip   fake (not installed)" in result.stdout
    assert not marker.exists()


def test_update_skips_tool_without_update_cmd(tmp_path):
    result = _run_update(tmp_path, ["fake|bash|true"])  # 3-field line: no update_cmd
    assert result.returncode == 0, result.stderr
    assert "no update procedure" in result.stdout


def test_update_dry_run_changes_nothing(tmp_path):
    marker = tmp_path / "updated-marker"
    result = _run_update(tmp_path, [f"fake|bash|true|touch {marker}"], dry_run=True)
    assert result.returncode == 0, result.stderr
    assert "update fake" in result.stdout
    assert not marker.exists()


def test_update_failure_warns_and_exits_nonzero(tmp_path):
    result = _run_update(tmp_path, ["broken|bash|true|false"])
    assert result.returncode != 0
    assert "broken: update failed" in result.stderr


def test_install_mode_skips_update_only_tools(tmp_path):
    result = _run(tmp_path, ["uponly|not-a-command-xyz|-|true"])
    assert result.returncode == 0, result.stderr
    assert "update-only tool" in result.stdout


def test_wrapper_runs_update_mode(tmp_path):
    marker = tmp_path / "updated-marker"
    result = _run_update(tmp_path, [f"fake|bash|true|touch {marker}"], via_wrapper=True)
    assert result.returncode == 0, result.stderr
    assert marker.exists()
    assert "1 updated" in result.stdout
