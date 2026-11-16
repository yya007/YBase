"""Tests for tools/claude-autoresume.sh.

Driven as a subprocess with CLAUDE_BIN, AUTORESUME_SLEEP, AUTORESUME_NOW, and
PROJECTS_DIR overrides, so no real `claude`, network, or sleeping is involved:
a fake `claude` emits canned result JSON from a queue, a fake `sleep` records
the durations it was asked to wait, and fixture transcripts stand in for
session history.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "claude-autoresume.sh"
NOW = 2_000_000_000  # fixed "current time" for deterministic recency + reset math

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None,
    reason="bash is required to exercise claude-autoresume.sh",
)

# Transcript record fragments.
_USER = '{"type":"user","message":{"role":"user","content":"hi"}}'
_ASSISTANT = '{"type":"assistant","message":{"role":"assistant","content":[]}}'
_LIMIT_ERR = (
    '{"type":"system","subtype":"api_error","level":"error",'
    '"error":{"message":"Claude AI usage limit reached","status":429}}'
)


def _encode(cwd: str) -> str:
    """Mirror the script's per-project dir encoding: '/' and '.' become '-'."""
    return cwd.replace("/", "-").replace(".", "-")


def _make_fake_claude(tmp_path: Path, responses: list[str]) -> Path:
    """A fake `claude` that returns queued responses and logs its argv.

    Each queue token: 'success', 'error', 'limit', or 'limit:<epoch>'. Once the
    queue is exhausted the last token repeats.
    """
    resp_file = tmp_path / "responses.txt"
    resp_file.write_text("\n".join(responses) + "\n")
    fake = tmp_path / "fake-claude"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        'echo "$*" >> "$FAKE_ARGS_LOG"\n'
        'n=$(cat "$FAKE_STATE" 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > "$FAKE_STATE"\n'
        f'resp=$(sed -n "${{n}}p" "{resp_file}")\n'
        f'[ -z "$resp" ] && resp=$(tail -1 "{resp_file}")\n'
        'case "$resp" in\n'
        '  success) echo \'{"type":"result","subtype":"success","is_error":false,'
        '"session_id":"s","result":"done"}\' ;;\n'
        '  limit:*) ep="${resp#limit:}"; echo "{\\"type\\":\\"result\\",'
        '\\"is_error\\":true,\\"api_error_status\\":429,'
        '\\"result\\":\\"Claude AI usage limit reached|$ep\\"}" ;;\n'
        '  limit) echo \'{"type":"result","is_error":true,"api_error_status":429,'
        '"result":"usage limit reached"}\' ;;\n'
        '  error) echo \'{"type":"result","is_error":true,"api_error_status":500,'
        '"result":"boom"}\' ;;\n'
        "esac\n"
    )
    fake.chmod(0o755)
    return fake


def _make_fake_sleep(tmp_path: Path) -> Path:
    fake = tmp_path / "fake-sleep"
    fake.write_text('#!/usr/bin/env bash\necho "$1" >> "$SLEEP_LOG"\n')
    fake.chmod(0o755)
    return fake


def _run(tmp_path, transcripts, args=None, responses=None, mtimes=None):
    """Set up a project + transcripts and run the script. Returns (result, ctx)."""
    work = tmp_path / "work"
    work.mkdir()
    projects = tmp_path / "projects"
    session_dir = projects / _encode(str(work))
    session_dir.mkdir(parents=True)
    for name, lines in transcripts.items():
        f = session_dir / f"{name}.jsonl"
        f.write_text("\n".join(lines) + "\n")
        t = (mtimes or {}).get(name, NOW)
        os.utime(f, (t, t))

    args_log = tmp_path / "args.log"
    sleep_log = tmp_path / "sleep.log"
    env = os.environ.copy()
    env.update(
        CLAUDE_BIN=str(_make_fake_claude(tmp_path, responses or ["success"])),
        AUTORESUME_SLEEP=str(_make_fake_sleep(tmp_path)),
        AUTORESUME_NOW=str(NOW),
        PROJECTS_DIR=str(projects),
        FAKE_ARGS_LOG=str(args_log),
        FAKE_STATE=str(tmp_path / "state"),
        SLEEP_LOG=str(sleep_log),
    )
    result = subprocess.run(
        ["bash", str(SCRIPT), *(args or [])],
        cwd=str(work),
        env=env,
        capture_output=True,
        text=True,
    )
    ctx = {
        "args_log": args_log.read_text() if args_log.exists() else "",
        "sleeps": sleep_log.read_text().split() if sleep_log.exists() else [],
    }
    return result, ctx


def test_dry_run_lists_paused_only(tmp_path):
    result, ctx = _run(
        tmp_path,
        {
            "paused": [_USER, _ASSISTANT, _LIMIT_ERR],
            "continued": [_USER, _LIMIT_ERR, _USER],  # user turn after the error
            "normal": [_USER, _ASSISTANT],  # never hit a limit
        },
        args=["--dry-run"],
    )
    assert result.returncode == 0, result.stderr
    assert "paused" in result.stdout
    assert "continued" not in result.stdout
    assert "normal" not in result.stdout
    assert ctx["args_log"] == ""  # dry-run resumes nothing


def test_recency_filter_excludes_old_pauses(tmp_path):
    result, _ = _run(
        tmp_path,
        {"paused": [_USER, _LIMIT_ERR]},
        args=["--dry-run", "--since", "1h"],
        mtimes={"paused": NOW - 7200},  # paused 2h ago, older than 1h window
    )
    assert result.returncode == 0, result.stderr
    assert "no limit-paused sessions" in result.stderr


def test_resume_success_uses_resume_flag(tmp_path):
    result, ctx = _run(
        tmp_path,
        {"paused": [_USER, _LIMIT_ERR]},
        responses=["success"],
    )
    assert result.returncode == 0, result.stderr
    assert "-r paused" in ctx["args_log"]
    assert "-p continue" in ctx["args_log"]
    assert ctx["sleeps"] == []  # window already open, no wait


def test_limit_then_success_sleeps_until_reset(tmp_path):
    reset = NOW + 3600
    result, ctx = _run(
        tmp_path,
        {"paused": [_USER, _LIMIT_ERR]},
        responses=[f"limit:{reset}", "success"],
        args=["--buffer", "60"],
    )
    assert result.returncode == 0, result.stderr
    assert ctx["sleeps"] == ["3660"]  # (reset - NOW) + buffer
    assert ctx["args_log"].count("-r paused") == 2


def test_max_resumes_cap_gives_up_nonzero(tmp_path):
    result, ctx = _run(
        tmp_path,
        {"paused": [_USER, _LIMIT_ERR]},
        responses=["limit"],  # always limited
        args=["--max-resumes", "2", "--retry-interval", "30s"],
    )
    assert result.returncode == 1
    assert ctx["args_log"].count("-r paused") == 2  # capped at 2 attempts
    assert ctx["sleeps"] == ["30"]  # slept once before the capped attempt


def test_non_limit_error_skips_nonzero(tmp_path):
    result, ctx = _run(
        tmp_path,
        {"paused": [_USER, _LIMIT_ERR]},
        responses=["error"],
    )
    assert result.returncode == 1
    assert ctx["args_log"].count("-r paused") == 1  # no retry on a real error
    assert ctx["sleeps"] == []


def test_no_history_dir_is_clean_exit(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    env = os.environ.copy()
    env.update(
        CLAUDE_BIN=str(_make_fake_claude(tmp_path, ["success"])),
        AUTORESUME_SLEEP=str(_make_fake_sleep(tmp_path)),
        PROJECTS_DIR=str(tmp_path / "projects"),  # does not exist
        FAKE_ARGS_LOG=str(tmp_path / "args.log"),
        FAKE_STATE=str(tmp_path / "state"),
        SLEEP_LOG=str(tmp_path / "sleep.log"),
    )
    result = subprocess.run(
        ["bash", str(SCRIPT)], cwd=str(work), env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "no session history" in result.stderr


def test_help_exits_zero(tmp_path):
    result = subprocess.run(["bash", str(SCRIPT), "-h"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "Usage:" in result.stdout


def test_missing_binary_fails(tmp_path):
    env = os.environ.copy()
    env["CLAUDE_BIN"] = "definitely-not-a-command-xyz"
    result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
    assert result.returncode == 127
    assert "not found on PATH" in result.stderr
