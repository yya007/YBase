"""ybase wt: a worktree for YBase or for a managed repo. Everything runs in
temporary repos and a temporary copy of YBase; no real checkout gets a worktree."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def git(path, *args):
    env = {**os.environ, **GIT_ENV}
    return subprocess.run(["git", "-C", str(path), *args], env=env, check=True,
                          capture_output=True, text=True).stdout


def make_repo(path):
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "master")
    (path / "a.txt").write_text("a\n", encoding="utf-8")
    git(path, "add", "a.txt")
    git(path, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "init")


@pytest.fixture
def work(tmp_path):
    """A copy of YBase that is itself a git repo, inside `<tmp>/my repos`."""
    root = tmp_path / "my repos" / "YBase"
    skip = shutil.ignore_patterns(".git", ".venv", ".ybase", ".env", "tmp", ".worktrees", "__pycache__", ".pytest_cache")
    shutil.copytree(REPO, root, ignore=lambda src, names: set(skip(src, names)) | ({"kb"} if Path(src) == REPO else set()))
    (root / "kb").mkdir()
    make_repo_in_place(root)
    return root


def make_repo_in_place(root):
    git(root, "init", "-q", "-b", "master")
    git(root, "add", "bin/ybase")
    git(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "init")


def yb(root, *args, worktrees=None):
    """Run bin/ybase. `worktrees` sets YBASE_WORKTREES; None leaves the default in force."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("YBASE_")}
    env.update({"YB_ROOT": str(root), "YBASE_PROFILE": "linux",
                "YBASE_SCRATCH": str(root.parent / "scratch")})
    env["LC_ALL"] = "en_US.UTF-8"       # a-z matches capitals in this locale; the name check must not care
    if worktrees is not None:
        env["YBASE_WORKTREES"] = str(worktrees)
    return subprocess.run([str(root / "bin" / "ybase"), *args], env=env, cwd=root,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True)


def list_repo(root, name):
    (root / "kb" / "repos.md").write_text(
        f"| Name | What it is | Remote | Hint |\n|---|---|---|---|\n| {name} | x | | |\n", encoding="utf-8")


def untracked(repo):
    return [ln for ln in git(repo, "status", "--porcelain").splitlines() if ln.startswith("??")]


# ---------------------------------------------------------------- where a worktree goes
def test_wt_defaults_to_a_folder_inside_ybase(work):
    res = yb(work, "wt", "feat/add-thing")
    assert res.returncode == 0, res.stderr
    path = work / ".worktrees" / "feat-add-thing"
    assert path.is_dir()
    assert str(path) in res.stdout
    assert git(path, "branch", "--show-current").strip() == "feat/add-thing"
    assert not any(".worktrees" in ln for ln in untracked(work))


def test_wt_in_a_managed_repo_stays_inside_that_repo_and_commits_nothing_there(work):
    other = work.parent / "other"
    make_repo(other)
    list_repo(work, "other")
    res = yb(work, "wt", "fix/some-bug", "--repo", "other")
    assert res.returncode == 0, res.stderr
    path = other / ".worktrees" / "fix-some-bug"
    assert path.is_dir()
    assert git(path, "branch", "--show-current").strip() == "fix/some-bug"
    assert git(other, "status", "--porcelain").strip() == ""      # ignored through the clone's own exclude file
    assert not (other / ".gitignore").exists()
    assert "fix/some-bug" not in git(work, "worktree", "list")


def test_wt_twice_writes_the_exclude_line_once(work):
    assert yb(work, "wt", "feat/add-thing").returncode == 0
    assert yb(work, "wt", "fix/other-thing").returncode == 0
    lines = (work / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()
    assert lines.count(".worktrees/") == 1


def test_wt_an_absolute_setting_moves_worktrees_outside_with_a_folder_per_repo(work):
    other = work.parent / "other repo"
    make_repo(other)
    list_repo(work, "other repo")
    outside = work.parent / "wt"
    res = yb(work, "wt", "feat/add-thing", "--repo", "other repo", "--base", "master", worktrees=outside)
    assert res.returncode == 0, res.stderr
    assert " " in str(work)
    assert (outside / "other repo" / "feat-add-thing").is_dir()
    assert not (other / ".worktrees").exists()


# ---------------------------------------------------------------- what a worktree is called
@pytest.mark.parametrize("name,why", [
    ("add-thing", "kind"),            # no kind
    ("wt/add-thing", "kind"),         # the old prefix says nothing
    ("feat/thing", "two to five"),    # one word does not name the work
    ("feat/a-b-c-d-e-f", "two to five"),
    ("feat/Add-Thing", "lowercase"),
    ("feat/add_thing", "lowercase"),
    ("feat/tmp-thing", "tmp"),
    ("fix/wip-leak-scan", "wip"),
    ("fix/2026-11-15", "date"),
])
def test_wt_refuses_a_name_that_does_not_say_what_the_work_is(work, name, why):
    res = yb(work, "wt", name)
    assert res.returncode != 0
    assert why in res.stderr
    assert "feat/" in res.stderr                # the message shows a good name
    assert git(work, "worktree", "list").count("\n") == 1
    assert not (work / ".worktrees").exists()


@pytest.mark.parametrize("kind", ["feat", "fix", "docs", "refactor", "test", "chore"])
def test_wt_accepts_every_kind(work, kind):
    res = yb(work, "wt", f"{kind}/name-of-work")
    assert res.returncode == 0, res.stderr
    assert git(work / ".worktrees" / f"{kind}-name-of-work", "branch", "--show-current").strip() == f"{kind}/name-of-work"


# ---------------------------------------------------------------- errors and flags
def test_wt_unknown_repo_fails_with_clone_hint(work):
    res = yb(work, "wt", "feat/add-thing", "--repo", "nope")
    assert res.returncode != 0
    assert "ybase repos clone nope" in res.stderr
    assert not (work / ".worktrees").exists()


def test_wt_uncloned_repo_fails_with_clone_hint(work):
    list_repo(work, "absent")
    res = yb(work, "wt", "feat/add-thing", "--repo", "absent")
    assert res.returncode != 0
    assert "ybase repos clone absent" in res.stderr


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_wt_help_prints_usage_and_creates_nothing(work, flag):
    r = yb(work, "wt", flag)
    assert r.returncode == 0
    assert "usage: ybase wt <kind>/<subject>" in r.stdout
    assert git(work, "worktree", "list").count("\n") == 1


@pytest.mark.parametrize("name", ["--repo", "-x", "--base"])
def test_wt_refuses_a_name_that_looks_like_a_flag(work, name):
    r = yb(work, "wt", name, "Foo")
    assert r.returncode != 0
    assert "usage: ybase wt <kind>/<subject>" in r.stderr
    assert git(work, "worktree", "list").count("\n") == 1


def test_wt_base_without_a_value_says_so(work):
    res = yb(work, "wt", "feat/add-thing", "--base")
    assert res.returncode != 0
    assert "--base needs" in res.stdout + res.stderr


def _with_origin(work, tmp_path):
    """Give `work` an origin, then move the origin one commit ahead of what was fetched."""
    up = tmp_path / "up.git"
    git(tmp_path, "clone", "-q", "--bare", str(work), str(up))
    git(work, "remote", "add", "origin", str(up))
    git(work, "fetch", "-q", "origin")
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(up), str(other))
    (other / "new.txt").write_text("new\n", encoding="utf-8")
    git(other, "add", "new.txt")
    git(other, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "ahead")
    git(other, "push", "-q", "origin", "master")
    return git(other, "rev-parse", "HEAD").strip()


def test_wt_fetches_so_the_worktree_starts_at_the_remote_tip(work, tmp_path):
    tip = _with_origin(work, tmp_path)
    res = yb(work, "wt", "feat/fresh-start")
    assert res.returncode == 0, res.stderr
    assert git(work / ".worktrees" / "feat-fresh-start", "rev-parse", "HEAD").strip() == tip


def test_wt_still_works_when_the_remote_cannot_be_reached(work, tmp_path):
    _with_origin(work, tmp_path)
    git(work, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    res = yb(work, "wt", "feat/offline-start")
    assert res.returncode == 0, res.stderr
    assert "could not fetch" in res.stdout + res.stderr


# ---------------------------------------------------------------- wt done
def test_wt_done_removes_a_landed_worktree_and_its_branch(work):
    assert yb(work, "wt", "feat/add-thing").returncode == 0
    path = work / ".worktrees" / "feat-add-thing"
    (path / "b.txt").write_text("b\n", encoding="utf-8")
    git(path, "add", "b.txt")
    git(path, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "add b")
    git(work, "merge", "-q", "--ff-only", "feat/add-thing")
    res = yb(work, "wt", "done", "feat/add-thing")
    assert res.returncode == 0, res.stdout + res.stderr
    assert not path.exists()
    assert git(work, "branch", "--list", "feat/add-thing").strip() == ""


def test_wt_done_keeps_a_worktree_that_still_holds_work_and_says_why(work):
    assert yb(work, "wt", "feat/add-thing").returncode == 0
    path = work / ".worktrees" / "feat-add-thing"
    (path / "bin" / "ybase").write_text("changed\n", encoding="utf-8")
    res = yb(work, "wt", "done", "feat/add-thing")
    assert res.returncode != 0
    assert "kept" in res.stdout + res.stderr and "uncommitted" in res.stdout + res.stderr
    assert path.is_dir()
    assert git(work, "branch", "--list", "feat/add-thing").strip() != ""


def test_wt_done_in_a_managed_repo(work):
    other = work.parent / "other"
    make_repo(other)
    list_repo(work, "other")
    assert yb(work, "wt", "fix/some-bug", "--repo", "other").returncode == 0
    res = yb(work, "wt", "done", "fix/some-bug", "--repo", "other")
    assert res.returncode == 0, res.stdout + res.stderr
    assert not (other / ".worktrees" / "fix-some-bug").exists()


def test_wt_done_unknown_name_fails_and_lists_what_exists(work):
    assert yb(work, "wt", "feat/add-thing").returncode == 0
    res = yb(work, "wt", "done", "feat/no-such")
    assert res.returncode != 0
    assert "feat/add-thing" in res.stdout + res.stderr


# ---------------------------------------------------------------- one view of every repo
def test_worktrees_all_lists_ybase_and_every_cloned_managed_repo(work):
    other = work.parent / "other"
    make_repo(other)
    list_repo(work, "other")
    assert yb(work, "wt", "feat/add-thing").returncode == 0
    assert yb(work, "wt", "fix/some-bug", "--repo", "other").returncode == 0
    res = yb(work, "worktrees", "--all")
    assert res.returncode == 0, res.stderr
    assert "feat/add-thing" in res.stdout and "fix/some-bug" in res.stdout
    assert f"repo {work}" in res.stdout and f"repo {other}" in res.stdout


def test_worktrees_all_names_a_listed_repo_that_is_not_cloned(work):
    list_repo(work, "absent")
    res = yb(work, "worktrees", "--all")
    assert res.returncode == 0, res.stderr
    assert "absent" in res.stdout and "not cloned" in res.stdout


def test_wt_run_from_inside_a_worktree_still_lands_in_the_main_checkout(work):
    """A worktree has its own copy of the tool. Run from there, it must not nest a second folder."""
    assert yb(work, "wt", "feat/add-thing").returncode == 0
    inner = work / ".worktrees" / "feat-add-thing"
    for part in ("tools", "profiles"):       # the fixture commits only bin/ybase
        shutil.copytree(work / part, inner / part)
    res = yb(inner, "wt", "fix/other-thing")
    assert res.returncode == 0, res.stderr
    assert (work / ".worktrees" / "fix-other-thing").is_dir()
    assert not (inner / ".worktrees").exists()
