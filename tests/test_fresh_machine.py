"""End to end: a fresh clone is usable after one setup command."""
import os
import pty
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# Claude Code's import pattern: an import path ends at the first unescaped whitespace,
# so a space in a path must be written as a backslash and a space.
IMPORT = re.compile(r"(?:^|\s)@((?:[^\s\\]|\\ )+)")


def _imports(text):
    return [m.replace("\\ ", " ") for m in IMPORT.findall(text)]


def test_fresh_clone_is_usable_after_one_setup(tmp_path):
    home = tmp_path / "home dir"
    home.mkdir()
    clone = home / "YBase"
    subprocess.run(["git", "clone", "--quiet", str(ROOT), str(clone)], check=True)

    env = {k: v for k, v in os.environ.items() if not k.startswith("YBASE_")}
    env.update(
        HOME=str(tmp_path / "fake-home"),
        YBASE_PROFILE="linux",
        GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
        GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com",
    )
    (tmp_path / "fake-home").mkdir()

    res = subprocess.run(
        ["/bin/bash", "bin/ybase", "setup"], cwd=clone, env=env,
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300,
    )
    assert res.returncode == 0, res.stdout + res.stderr

    assert (clone / ".env").is_file()
    for name in ("MACHINE.md", "KB.md", "REPOS.md"):
        assert (clone / ".ybase" / name).is_file(), name
    assert (clone / "kb" / "VERSION").read_text().strip() == "1"

    for doc in (clone / "CLAUDE.md", clone / ".ybase" / "KB.md", clone / ".ybase" / "MACHINE.md"):
        imports = _imports(doc.read_text())
        assert imports, f"{doc.name} has no @ lines"
        for imp in imports:
            target = Path(imp)
            if not target.is_absolute():
                target = doc.parent / imp
            assert target.is_file(), f"{doc.name} imports missing file {imp}"

    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=clone, env=env,
        capture_output=True, text=True, check=True,
    )
    assert status.stdout == ""

    checks = subprocess.run(
        [sys.executable, "tools/checks.py"], cwd=clone, env=env,
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
    )
    assert checks.returncode == 0, checks.stdout + checks.stderr


def _scratch_clone(tmp_path):
    """A clone of this repo with the working tree's runtime code laid over it."""
    home = tmp_path / "home"
    home.mkdir()
    clone = home / "YBase"
    subprocess.run(["git", "clone", "--quiet", str(ROOT), str(clone)], check=True)
    for part in ("bin", "tools", "profiles"):
        shutil.copytree(ROOT / part, clone / part, dirs_exist_ok=True)
    (tmp_path / "fake-home").mkdir()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("YBASE_") and k not in ("CI", "YB_CI", "RUNNER_TEMP")}
    env.update(
        HOME=str(tmp_path / "fake-home"),
        YB_CI="",
        YBASE_PROFILE="linux",
        GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
        GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com",
    )
    return clone, env


def _env_value(clone, key):
    for line in (clone / ".env").read_text().splitlines():
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return None


def _setup_on_tty(clone, env, args):
    """Run setup with stdin attached to a terminal nobody types on."""
    master, slave = pty.openpty()
    try:
        res = subprocess.run(
            ["/bin/bash", "bin/ybase", "setup", *args], cwd=clone, env=env,
            stdin=slave, capture_output=True, text=True, timeout=60,
        )
    finally:
        os.close(master)
        os.close(slave)
    return res


def test_non_interactive_setup_never_reads_stdin(tmp_path):
    clone, env = _scratch_clone(tmp_path)
    res = _setup_on_tty(clone, env, ["--non-interactive"])
    assert res.returncode == 0, res.stdout + res.stderr
    assert "Primary knowledge base" not in res.stdout + res.stderr
    assert (clone / "kb" / "VERSION").is_file()

    pipe = subprocess.run(
        ["/bin/bash", "bin/ybase", "setup", "--non-interactive"], cwd=clone, env=env,
        stdin=subprocess.PIPE, capture_output=True, text=True, timeout=60,
    )
    assert pipe.returncode == 0, pipe.stdout + pipe.stderr


def test_ci_profile_setup_never_prompts(tmp_path):
    clone, env = _scratch_clone(tmp_path)
    env.pop("YBASE_PROFILE")
    env["YB_CI"] = "true"
    res = _setup_on_tty(clone, env, [])
    assert res.returncode == 0, res.stdout + res.stderr
    assert "Primary knowledge base" not in res.stdout + res.stderr
    assert "profile: ci" in res.stdout


def test_auto_detected_ci_says_how_to_pin_another_profile(tmp_path):
    clone, env = _scratch_clone(tmp_path)
    env.pop("YBASE_PROFILE")
    env["YB_CI"] = "true"
    res = _setup_on_tty(clone, env, [])
    assert res.returncode == 0, res.stdout + res.stderr
    line = next((x for x in res.stdout.splitlines() if "chosen because CI is set" in x), "")
    assert "questions are skipped" in line and "ybase profile <name>" in line, res.stdout

    # A pinned ci profile is not auto-detected: no such line.
    (tmp_path / "second").mkdir()
    clone2, env2 = _scratch_clone(tmp_path / "second")
    env2["YBASE_PROFILE"] = "ci"
    res2 = _setup_on_tty(clone2, env2, [])
    assert "chosen because CI is set" not in res2.stdout


def test_kb_flag_sets_the_primary_kb(tmp_path):
    clone, env = _scratch_clone(tmp_path)
    kb = tmp_path / "my kb"
    res = subprocess.run(
        ["/bin/bash", "bin/ybase", "setup", "--non-interactive", "--kb", str(kb)],
        cwd=clone, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert (kb / "VERSION").is_file()
    assert _env_value(clone, "YBASE_KB_PRIMARY") == str(kb)
    assert not (clone / "kb" / "VERSION").exists()

    # Interactive run: --kb suppresses the question.
    (tmp_path / "second").mkdir()
    clone2, env2 = _scratch_clone(tmp_path / "second")
    res = _setup_on_tty(clone2, env2, ["--kb", str(tmp_path / "other")])
    assert res.returncode == 0, res.stdout + res.stderr
    assert "Primary knowledge base" not in res.stdout + res.stderr
    assert _env_value(clone2, "YBASE_KB_PRIMARY") == str(tmp_path / "other")


def test_non_interactive_keeps_an_already_set_primary_kb(tmp_path):
    clone, env = _scratch_clone(tmp_path)
    kb = tmp_path / "kept"
    run = ["/bin/bash", "bin/ybase", "setup", "--non-interactive"]
    kw = dict(cwd=clone, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
    assert subprocess.run([*run, "--kb", str(kb)], **kw).returncode == 0
    assert subprocess.run(run, **kw).returncode == 0
    assert _env_value(clone, "YBASE_KB_PRIMARY") == str(kb)


def test_repos_root_flag_is_written(tmp_path):
    clone, env = _scratch_clone(tmp_path)
    root = tmp_path / "repos"
    run = ["/bin/bash", "bin/ybase", "setup", "--non-interactive", "--repos-root", str(root)]
    kw = dict(cwd=clone, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
    res = subprocess.run(run, **kw)
    assert res.returncode == 0, res.stdout + res.stderr
    assert _env_value(clone, "YBASE_REPOS_ROOT") == str(root)
    # It overwrites a value that is already there.
    other = tmp_path / "elsewhere"
    res = subprocess.run([*run[:-1], str(other)], **kw)
    assert res.returncode == 0, res.stdout + res.stderr
    assert _env_value(clone, "YBASE_REPOS_ROOT") == str(other)


def test_unknown_flag_still_dies(tmp_path):
    clone, env = _scratch_clone(tmp_path)
    for args in (["--bogus"], ["--kb"], ["--repos-root"], ["--profile"]):
        res = subprocess.run(
            ["/bin/bash", "bin/ybase", "setup", "--non-interactive", *args], cwd=clone, env=env,
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60,
        )
        assert res.returncode != 0, args
        assert "usage" in (res.stdout + res.stderr).lower() or "unknown argument" in (res.stdout + res.stderr), args


def test_a_tilde_in_the_kb_path_means_the_home_folder(tmp_path):
    clone, env = _scratch_clone(tmp_path)
    home = tmp_path / "home dir"
    home.mkdir()
    env = {**env, "HOME": str(home)}
    res = subprocess.run(
        ["/bin/bash", "bin/ybase", "setup", "--non-interactive", "--kb", "~/notes/kb"],
        cwd=clone, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert (home / "notes" / "kb" / "VERSION").is_file()
    assert _env_value(clone, "YBASE_KB_PRIMARY") == str(home / "notes" / "kb")
    assert not (clone / "~").exists()


def _codex_state(clone, env, **extra):
    """What `ybase env` says about Codex delegation: "on", "off" or None."""
    res = subprocess.run(["/bin/bash", "bin/ybase", "env"], cwd=clone, env={**env, **extra},
                         stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    for line in res.stdout.splitlines():
        if line.startswith("export YBASE_CODEX_DELEGATION="):
            return line.split("=", 1)[1]
    return None


def _fake_codex(tmp_path):
    fake = tmp_path / "fakebin" / "codex"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(0o755)
    return str(fake)


def test_codex_delegation_is_off_on_a_machine_without_codex(tmp_path):
    clone, env = _scratch_clone(tmp_path)
    assert _codex_state(clone, env, YBASE_CODEX_BIN="no-such-codex-binary") == "off"


def test_codex_delegation_is_on_where_codex_is_installed(tmp_path):
    clone, env = _scratch_clone(tmp_path)
    assert _codex_state(clone, env, YBASE_CODEX_BIN=_fake_codex(tmp_path)) == "on"


def test_the_env_file_turns_codex_delegation_off_for_this_machine(tmp_path):
    clone, env = _scratch_clone(tmp_path)
    (clone / ".env").write_text("YBASE_CODEX_DELEGATION=off\n", encoding="utf-8")
    assert _codex_state(clone, env, YBASE_CODEX_BIN=_fake_codex(tmp_path)) == "off"


def test_forcing_codex_delegation_on_without_codex_still_reads_off(tmp_path):
    clone, env = _scratch_clone(tmp_path)
    (clone / ".env").write_text("YBASE_CODEX_DELEGATION=on\n", encoding="utf-8")
    assert _codex_state(clone, env, YBASE_CODEX_BIN="no-such-codex-binary") == "off"


def test_doctor_writes_the_codex_state_where_every_session_reads_it(tmp_path):
    clone, env = _scratch_clone(tmp_path)
    res = subprocess.run(["/bin/bash", "bin/ybase", "setup", "--non-interactive"], cwd=clone,
                         env={**env, "YBASE_CODEX_BIN": "no-such-codex-binary"},
                         stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    machine = (clone / ".ybase" / "MACHINE.md").read_text(encoding="utf-8")
    assert "Codex delegation: **off**" in machine
    assert "YBASE_CODEX_DELEGATION" in (clone / ".env").read_text(encoding="utf-8")
