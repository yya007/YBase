"""`ybase setup` puts a `ybase` command on the PATH, so nobody types `bin/`.

The launcher is a small file outside the clone. It runs the checkout the caller stands
in, and otherwise the checkout that installed it.
"""
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "launcher.sh"
SKIP = shutil.ignore_patterns(".git", ".venv", ".ybase", ".env", "tmp", ".worktrees", "__pycache__", ".pytest_cache")


def stub(path: Path, says: str) -> Path:
    """A folder that looks like a checkout: its entry point prints who it is."""
    (path / "bin").mkdir(parents=True)
    (path / "tools").mkdir()
    (path / "tools" / "profile.sh").write_text("")
    entry = path / "bin" / "ybase"
    entry.write_text(f'#!/bin/sh\necho "{says} $*"\n')
    entry.chmod(0o755)
    return path


def clean_env() -> dict:
    """This machine's environment without its settings and without its own `ybase` command:
    a test must see the same thing whether or not the launcher is installed here."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("YBASE_")}
    env["PATH"] = os.pathsep.join(d for d in env.get("PATH", "").split(os.pathsep)
                                  if d and not (Path(d) / "ybase").exists())
    return env


def launcher(args, root: Path, bindir: Path, **extra):
    env = clean_env()
    env.update(YB_ROOT=str(root), YB_BIN_DIR=str(bindir), LC_ALL="en_US.UTF-8", **extra)
    return subprocess.run(["/bin/bash", str(SCRIPT), *args], env=env, cwd=root,
                          capture_output=True, text=True)


def call(bindir: Path, cwd: Path, *args):
    return subprocess.run([str(bindir / "ybase"), *args], cwd=cwd, capture_output=True, text=True)


def test_install_writes_an_executable_that_runs_the_installing_checkout(tmp_path):
    home = stub(tmp_path / "home checkout", "home")
    res = launcher(["install"], home, tmp_path / "bin")
    assert res.returncode == 0, res.stderr
    assert "fix:" in res.stdout and str(tmp_path / "bin" / "ybase") in res.stdout
    assert os.access(tmp_path / "bin" / "ybase", os.X_OK)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    out = call(tmp_path / "bin", elsewhere, "wt", "feat/a b")
    assert out.stdout == "home wt feat/a b\n"


def test_inside_another_checkout_that_checkout_runs(tmp_path):
    home = stub(tmp_path / "home", "home")
    other = stub(tmp_path / "home" / ".worktrees" / "feat-x", "worktree")
    launcher(["install"], home, tmp_path / "bin")
    deep = other / "docs" / "deep"
    deep.mkdir(parents=True)
    assert call(tmp_path / "bin", deep, "check").stdout == "worktree check\n"
    assert call(tmp_path / "bin", home / "tools", "check").stdout == "home check\n"


def test_a_folder_with_only_a_bin_ybase_is_not_a_checkout(tmp_path):
    home = stub(tmp_path / "home", "home")
    launcher(["install"], home, tmp_path / "bin")
    fake = tmp_path / "fake"
    (fake / "bin").mkdir(parents=True)
    (fake / "bin" / "ybase").write_text("#!/bin/sh\necho fake\n")
    (fake / "bin" / "ybase").chmod(0o755)
    assert call(tmp_path / "bin", fake).stdout.startswith("home")


def test_a_quote_in_the_checkout_path_survives(tmp_path):
    home = stub(tmp_path / "it's $HOME `x`", "home")
    assert launcher(["install"], home, tmp_path / "bin").returncode == 0
    assert call(tmp_path / "bin", tmp_path).stdout == "home \n"


def test_a_missing_checkout_is_named(tmp_path):
    home = stub(tmp_path / "home", "home")
    launcher(["install"], home, tmp_path / "bin")
    shutil.rmtree(home)
    out = call(tmp_path / "bin", tmp_path)
    assert out.returncode == 127
    assert str(home) in out.stderr and "setup" in out.stderr


def test_install_twice_changes_nothing_and_a_moved_checkout_is_picked_up(tmp_path):
    home = stub(tmp_path / "home", "home")
    launcher(["install"], home, tmp_path / "bin")
    again = launcher(["install"], home, tmp_path / "bin")
    assert again.stdout.startswith("ok:") and "fix:" not in again.stdout
    moved = stub(tmp_path / "moved", "moved")
    res = launcher(["install"], moved, tmp_path / "bin")
    assert "fix:" in res.stdout
    assert call(tmp_path / "bin", tmp_path).stdout == "moved \n"


def test_a_file_someone_else_put_there_is_left_alone(tmp_path):
    home = stub(tmp_path / "home", "home")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "ybase").write_text("#!/bin/sh\necho mine\n")
    res = launcher(["install"], home, tmp_path / "bin")
    assert res.returncode == 0
    assert (tmp_path / "bin" / "ybase").read_text() == "#!/bin/sh\necho mine\n"
    assert "WARN" in res.stderr and "left" in res.stderr


def test_switched_off_installs_nothing(tmp_path):
    home = stub(tmp_path / "home", "home")
    res = launcher(["install"], home, tmp_path / "bin", YBASE_LAUNCHER="off")
    assert res.returncode == 0
    assert not (tmp_path / "bin").exists()
    (home / ".env").write_text("YBASE_LAUNCHER=off\n")
    launcher(["install"], home, tmp_path / "bin")
    assert not (tmp_path / "bin").exists()


def test_status_says_which_form_of_the_command_works(tmp_path):
    home = stub(tmp_path / "home", "home")
    bindir = tmp_path / "bin"
    assert launcher(["status"], home, bindir).stdout.strip() == "bin/ybase"
    launcher(["install"], home, bindir)
    assert launcher(["status"], home, bindir).stdout.strip() == "bin/ybase"  # not on PATH
    on = launcher(["status"], home, bindir, PATH=f"{bindir}:{clean_env()['PATH']}")
    assert on.stdout.strip() == "ybase"


def test_install_says_when_the_folder_is_not_on_the_path(tmp_path):
    home = stub(tmp_path / "home", "home")
    bindir = tmp_path / "bin"
    res = launcher(["install"], home, bindir)
    assert "PATH" in res.stdout + res.stderr and str(bindir) in res.stdout + res.stderr
    on = launcher(["install"], stub(tmp_path / "two", "two"), bindir, PATH=f"{bindir}:{clean_env()['PATH']}")
    assert "export PATH" not in on.stdout + on.stderr


def _real_copy(tmp_path: Path) -> Path:
    work = tmp_path / "YBase"
    shutil.copytree(ROOT, work, ignore=SKIP)
    git = ["git", "-C", str(work), "-c", "user.name=T", "-c", "user.email=t@example.com"]
    subprocess.run(["git", "init", "-q", "-b", "master", str(work)], check=True)
    subprocess.run([*git, "add", "bin/ybase"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "x"], check=True)
    return work


def _setup(work: Path, bindir: Path, **extra):
    env = clean_env()
    env.update({"YBASE_PROFILE": "linux", "YB_BIN_DIR": str(bindir), "HOME": str(work.parent / "home"), **extra})
    return subprocess.run(["/bin/bash", str(work / "bin" / "ybase"), "setup", "--non-interactive"], env=env,
                          cwd=work, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)


def test_setup_installs_the_launcher_and_the_machine_file_names_the_command(tmp_path):
    work = _real_copy(tmp_path)
    bindir = tmp_path / "bin"
    res = _setup(work, bindir)
    assert res.returncode == 0, res.stdout + res.stderr
    assert (bindir / "ybase").is_file()
    assert "- command: `bin/ybase`" in (work / ".ybase" / "MACHINE.md").read_text()
    res = _setup(work, bindir, PATH=f"{bindir}:{clean_env()['PATH']}")
    assert "- command: `ybase`" in (work / ".ybase" / "MACHINE.md").read_text()
    out = subprocess.run([str(bindir / "ybase"), "help"], cwd=tmp_path, capture_output=True, text=True)
    assert out.stdout.startswith("usage: ybase <command>")


def test_setup_from_a_worktree_points_the_launcher_at_the_main_checkout(tmp_path):
    work = _real_copy(tmp_path)
    wt = work / ".worktrees" / "feat-x"
    subprocess.run(["git", "-C", str(work), "worktree", "add", "-q", "-b", "feat/x", str(wt)], check=True)
    for name in ("tools", "profiles", "templates", "docs", "pyproject.toml"):
        src = work / name
        (shutil.copytree if src.is_dir() else shutil.copy)(src, wt / name)
    bindir = tmp_path / "bin"
    res = _setup(wt, bindir)
    assert res.returncode == 0, res.stdout + res.stderr
    text = (bindir / "ybase").read_text()
    assert str(work.resolve()) in text and ".worktrees" not in text


def test_the_ci_profile_installs_nothing(tmp_path):
    work = _real_copy(tmp_path)
    res = _setup(work, tmp_path / "bin", YBASE_PROFILE="ci")
    assert res.returncode == 0, res.stdout + res.stderr
    assert not (tmp_path / "bin").exists()


def test_the_machine_file_tells_a_machine_without_the_launcher_to_use_the_path(tmp_path):
    work = _real_copy(tmp_path)
    _setup(work, tmp_path / "bin")
    line = next(ln for ln in (work / ".ybase" / "MACHINE.md").read_text().splitlines() if ln.startswith("- command:"))
    assert "run `bin/ybase ...` from this clone" in line


def test_setup_carries_on_when_the_launcher_cannot_be_written(tmp_path):
    work = _real_copy(tmp_path)
    blocker = tmp_path / "a-file"
    blocker.write_text("")
    res = _setup(work, blocker / "bin")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "WARN" in res.stderr and "bin/ybase" in res.stderr
    assert (work / ".ybase" / "MACHINE.md").is_file()


def test_a_dangling_link_at_the_target_is_left_alone(tmp_path):
    home = stub(tmp_path / "home", "home")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "ybase").symlink_to(tmp_path / "outside")
    res = launcher(["install"], home, tmp_path / "bin")
    assert res.returncode == 0
    assert not (tmp_path / "outside").exists()
    assert "WARN" in res.stderr


def test_an_empty_setting_in_the_environment_does_not_override_the_file(tmp_path):
    home = stub(tmp_path / "home", "home")
    (home / ".env").write_text("YBASE_LAUNCHER=off\n")
    launcher(["install"], home, tmp_path / "bin", YBASE_LAUNCHER="")
    assert not (tmp_path / "bin").exists()


def test_a_worktree_reads_the_settings_of_its_main_checkout(tmp_path):
    work = _real_copy(tmp_path)
    (work / ".env").write_text("YBASE_KB_PRIMARY=/somewhere/kb\n")
    wt = work / ".worktrees" / "feat-x"
    subprocess.run(["git", "-C", str(work), "worktree", "add", "-q", "-b", "feat/x", str(wt)], check=True)
    shutil.copytree(work / "tools", wt / "tools")
    env = clean_env()
    env.pop("YB_ROOT", None)
    read = ". tools/lib.sh; yb_setting YBASE_KB_PRIMARY"
    out = subprocess.run(["/bin/bash", "-c", read], cwd=wt, env=env, capture_output=True, text=True)
    assert out.stdout.strip() == "/somewhere/kb", out.stderr
    (wt / ".env").write_text("YBASE_KB_PRIMARY=/own/kb\n")
    out = subprocess.run(["/bin/bash", "-c", read], cwd=wt, env=env, capture_output=True, text=True)
    assert out.stdout.strip() == "/own/kb"
