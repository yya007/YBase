import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import envfile  # noqa: E402


def sh(root: Path, script: str, extra_env: dict | None = None) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("YBASE_")}
    env["YB_ROOT"] = str(root)
    env.update(extra_env or {})
    out = subprocess.run(
        ["/bin/bash", "-c", f". {REPO}/tools/lib.sh; {script}"],
        env=env, capture_output=True, text=True, check=True, cwd=REPO,
    )
    return out.stdout


def test_set_then_get_round_trips_odd_value(tmp_path):
    sh(tmp_path, "yb_env_set YBASE_SCRATCH '/a b/c=d #e'")
    assert sh(tmp_path, "yb_env_get YBASE_SCRATCH") == "/a b/c=d #e\n"
    assert envfile.read_env(tmp_path) == {"YBASE_SCRATCH": "/a b/c=d #e"}


def test_set_replaces_and_keeps_other_lines(tmp_path):
    (tmp_path / ".env").write_text("# mine\nFOO=1\nYBASE_PROFILE=linux\n", encoding="utf-8")
    sh(tmp_path, "yb_env_set YBASE_PROFILE aws")
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "# mine\nFOO=1\nYBASE_PROFILE=aws\n"


def test_set_appends_when_absent_even_without_trailing_newline(tmp_path):
    (tmp_path / ".env").write_text("FOO=1", encoding="utf-8")
    sh(tmp_path, "yb_env_set YBASE_PROFILE aws")
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "FOO=1\nYBASE_PROFILE=aws\n"


def test_unset_removes_only_that_key(tmp_path):
    (tmp_path / ".env").write_text("# mine\nFOO=1\nYBASE_PROFILE=linux\nBAR=2\n", encoding="utf-8")
    sh(tmp_path, "yb_env_unset YBASE_PROFILE")
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "# mine\nFOO=1\nBAR=2\n"
    assert sh(tmp_path, "yb_env_get YBASE_PROFILE") == ""


def test_setting_prefers_process_environment(tmp_path):
    (tmp_path / ".env").write_text("YBASE_PROFILE=linux\n", encoding="utf-8")
    assert sh(tmp_path, "yb_setting YBASE_PROFILE") == "linux\n"
    assert sh(tmp_path, "yb_setting YBASE_PROFILE", {"YBASE_PROFILE": "aws"}) == "aws\n"
    assert sh(tmp_path, "yb_setting YBASE_PROFILE", {"YBASE_PROFILE": ""}) == "linux\n"


def clean_copy(tmp_path: Path) -> Path:
    work = tmp_path / "YBase"
    shutil.copytree(
        REPO, work,
        ignore=shutil.ignore_patterns(".git", ".venv", ".ybase", ".env", "tmp", ".worktrees", "__pycache__", ".pytest_cache"),
    )
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    return work


def test_setup_with_profile_flag_still_writes_header(tmp_path):
    work = clean_copy(tmp_path)
    env = {k: v for k, v in os.environ.items() if not k.startswith("YBASE_")}
    res = subprocess.run(
        [str(work / "bin" / "ybase"), "setup", "--profile", "linux"],
        env=env, cwd=work, stdin=subprocess.DEVNULL, capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    text = (work / ".env").read_text(encoding="utf-8")
    assert text.startswith("# Machine settings for YBase")
    assert "YBASE_PROFILE=linux\n" in text.splitlines(True)
    assert "fix:  created .env" in res.stdout
    assert "Permissions: .claude/settings.json lists pwd, ls, wc, which" in res.stdout
    assert "is off unless YBASE_ALLOW_GATE=1" in res.stdout
    assert "a convenience, not a security boundary" in res.stdout
    assert "only commands you are content to run unprompted" in res.stdout
    assert "# YBASE_ALLOW_GATE=1" in text
    assert not any(ln.startswith("YBASE_ALLOW_GATE") for ln in text.splitlines())  # shipped off
    for claim in ("read-only", "never approves"):
        assert claim not in res.stdout


def test_set_and_unset_keep_file_mode(tmp_path):
    envpath = tmp_path / ".env"
    envpath.write_text("A=1\n", encoding="utf-8")
    envpath.chmod(0o600)
    sh(tmp_path, "yb_env_set YBASE_PROFILE aws")
    assert envpath.stat().st_mode & 0o777 == 0o600
    sh(tmp_path, "yb_env_unset YBASE_PROFILE")
    assert envpath.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".env.tmp.*"))


def test_setup_twice_is_idempotent(tmp_path):
    work = clean_copy(tmp_path)
    env = {k: v for k, v in os.environ.items() if not k.startswith("YBASE_")}
    env["YBASE_PROFILE"] = "linux"

    def run():
        return subprocess.run(
            [str(work / "bin" / "ybase"), "setup"],
            env=env, cwd=work, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        )

    first_run = run()
    assert first_run.returncode == 0, first_run.stderr
    assert any(ln.startswith("fix:") for ln in first_run.stdout.splitlines()), first_run.stdout
    envpath = work / ".env"
    assert envpath.exists()
    with envpath.open("a", encoding="utf-8") as fh:
        fh.write("MY_OWN=1\n")
    first = envpath.read_bytes()
    second_run = run()
    assert second_run.returncode == 0, second_run.stderr
    assert not [ln for ln in second_run.stdout.splitlines() if ln.startswith("fix:")], second_run.stdout
    assert envpath.read_bytes() == first
    assert "MY_OWN=1" in envpath.read_text(encoding="utf-8")
