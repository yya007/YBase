"""`ybase doctor`, run against a copy of the repository, never the real one."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def work(tmp_path):
    root = tmp_path / "YBase"
    skip = shutil.ignore_patterns(".git", ".venv", ".ybase", ".env", "tmp", ".worktrees", "__pycache__", ".pytest_cache")

    def ignore(src, names):  # never copy the real working tree's kb/
        return set(skip(src, names)) | ({"kb"} if Path(src) == REPO else set())

    shutil.copytree(REPO, root, ignore=ignore)
    (root / "kb").mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def doctor(root, *args, extra=None):
    # Hermetic: drop PYTHONDONTWRITEBYTECODE too, since hosted CI runners do not set it and a
    # dry run must write no bytecode on its own.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("YBASE_") and k != "PYTHONDONTWRITEBYTECODE"}
    env["YB_ROOT"] = str(root)
    env["YBASE_SCRATCH"] = str(root.parent / "scratch")
    env.update(extra or {})
    return subprocess.run([str(root / "bin" / "ybase"), "doctor", *args], env=env, cwd=root,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True)


def snapshot(*dirs):
    out = {}
    for d in dirs:
        for p in [d, *d.rglob("*")]:
            st = p.lstat()
            out[p] = (st.st_mtime_ns, st.st_size)
    return out


@pytest.mark.parametrize("profile", ["macos", "linux", "aws"])
def test_dry_run_writes_nothing(work, tmp_path, profile):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    before = snapshot(work, scratch)
    res = doctor(work, "--dry-run", extra={"YBASE_PROFILE": profile})
    assert "MACHINE.md (dry run, not written)" in res.stdout, res.stdout + res.stderr
    assert not (work / "tmp").exists()
    assert not (work / ".ybase").exists()
    after = snapshot(work, scratch)
    changed = sorted(str(q.relative_to(tmp_path)) for q in set(before) | set(after)
                     if before.get(q) != after.get(q))
    assert changed == [], changed


def test_a_missing_kb_is_not_offered_kb_init(work, tmp_path):
    gone = tmp_path / "unplugged" / "kb"
    res = doctor(work, extra={"YBASE_PROFILE": "linux", "YBASE_KB_PATHS": str(gone)})
    line = next(ln for ln in res.stderr.splitlines() if str(gone) in ln)
    assert "missing" in line and f'kb init "{gone}"' not in line, line
    assert "only for a new" in line, line
    assert not gone.exists()
    nos = doctor(work, extra={"YBASE_PROFILE": "linux"})  # an empty kb/ still gets the init hint
    assert f'kb init "{work}/kb"' in nos.stderr, nos.stderr


def fake_python(bin_dir, version):
    """A python3 that reports `version` for --version and runs the real interpreter otherwise."""
    bin_dir.mkdir()
    shim = bin_dir / "python3"
    shim.write_text(f'#!/bin/sh\n[ "$1" = --version ] && {{ echo "Python {version}"; exit 0; }}\n'
                    f'exec "{sys.executable}" "$@"\n', encoding="utf-8")
    shim.chmod(0o755)
    return f"{bin_dir}{os.pathsep}{os.environ['PATH']}"


def test_python_below_the_floor_is_a_warning(work, tmp_path):
    path = fake_python(tmp_path / "bin", "3.9.6")
    res = doctor(work, extra={"YBASE_PROFILE": "linux", "PATH": path})
    warn = [ln for ln in res.stderr.splitlines() if ln.startswith("WARN:") and "3.9" in ln]
    assert warn and "3.10" in warn[0], res.stderr
    assert res.returncode == 0, res.stdout + res.stderr


def test_python_at_the_floor_is_not_a_warning(work, tmp_path):
    path = fake_python(tmp_path / "bin", "3.10.0")
    res = doctor(work, extra={"YBASE_PROFILE": "linux", "PATH": path})
    assert not [ln for ln in res.stderr.splitlines() if ln.startswith("WARN:") and "python3" in ln], res.stderr
