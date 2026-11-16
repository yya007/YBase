"""`ybase publish` and `ybase absorb`, against a local bare repo standing in
for the public one. The private side is a copy of this working tree, so these tests do
not need a commit first."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
IDENT = {"GIT_AUTHOR_NAME": "Owner", "GIT_AUTHOR_EMAIL": "owner@example.com",
         "GIT_COMMITTER_NAME": "Owner", "GIT_COMMITTER_EMAIL": "owner@example.com"}
TERM = "zebra" + "corn"  # a made-up private term, split so this file passes the leak scan


def g(cwd, *args, **env):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True,
                          env={**os.environ, **IDENT, **env}).stdout.strip()


@pytest.fixture
def world(tmp_path):
    """private: a committed copy of this tree. public: an empty bare repo. kb: one deny term."""
    private, public, kb = tmp_path / "private", tmp_path / "public.git", tmp_path / "kb"
    private.mkdir()
    files = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others",
                            "--exclude-standard"], capture_output=True, check=True).stdout.decode()
    for rel in filter(None, files.split("\0")):
        src, dst = ROOT / rel, private / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_symlink():
            os.symlink(os.readlink(src), dst)
        elif src.is_file():
            shutil.copy2(src, dst)
    with (private / ".publishignore").open("a") as f:
        f.write("private-notes.md\nprivate-dir/\n")
    (private / "private-notes.md").write_text("stays home\n")
    (private / "private-dir").mkdir()
    (private / "private-dir" / "a.md").write_text("stays home\n")
    g(private, "init", "-q", "-b", "master")
    g(private, "add", "-A")
    g(private, "commit", "-q", "-m", "private work")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(public)], check=True)
    kb.mkdir()
    (kb / "deny.list").write_text(TERM + "\n")
    (private / ".env").write_text(f"YBASE_PUBLIC_REPO={public}\nYBASE_KB_PRIMARY={kb}\n")
    return private, public


def run(private, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("YBASE_")}
    return subprocess.run(["/bin/bash", str(private / "bin" / "ybase"), *args],
                          capture_output=True, text=True, env={**env, **IDENT})


def publish(private, *flags):
    return run(private, "publish", "--skip-tests", *flags)


def commit(private, rel, text, message="change"):
    (private / rel).write_text(text)
    g(private, "add", rel)
    g(private, "commit", "-q", "-m", message)


def branches(public):
    return g(public, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()


def test_first_publish_is_one_snapshot_without_ignored_paths_or_history(world):
    private, public = world
    res = publish(private)
    assert res.returncode == 0, res.stdout + res.stderr
    assert branches(public) == ["master"]
    assert g(public, "rev-list", "--count", "master") == "1"
    assert f"Upstream-Rev: {g(private, 'rev-parse', 'HEAD')}" in g(public, "log", "-1", "--format=%B", "master")
    listed = g(public, "ls-tree", "-r", "--name-only", "master").splitlines()
    assert "LICENSE" in listed and "bin/ybase" in listed
    for hidden in (".publishignore", "private-notes.md", "private-dir/a.md"):
        assert hidden not in listed
    assert "private work" not in g(public, "log", "--format=%B", "master")


def test_a_later_publish_pushes_a_sync_branch_and_leaves_main_alone(world):
    private, public = world
    assert publish(private).returncode == 0
    before = g(public, "rev-parse", "master")
    commit(private, "docs/roadmap.md", "# Roadmap\n\nNew line.\n")
    res = publish(private)
    assert res.returncode == 0, res.stdout + res.stderr
    branch = f"sync/{g(private, 'rev-parse', 'HEAD')[:10]}"
    assert sorted(branches(public)) == ["master", branch]
    assert g(public, "rev-parse", "master") == before
    assert g(public, "diff", "--name-only", "master", branch) == "docs/roadmap.md"


def test_nothing_changed_pushes_nothing(world):
    private, public = world
    assert publish(private).returncode == 0
    res = publish(private)
    assert res.returncode == 0 and "nothing to publish" in res.stdout
    assert branches(public) == ["master"]


def test_dry_run_pushes_nothing(world):
    private, public = world
    res = publish(private, "--dry-run")
    assert res.returncode == 0, res.stdout + res.stderr
    assert branches(public) == []


def test_a_private_term_stops_the_publish(world):
    private, public = world
    commit(private, "docs/roadmap.md", "# Roadmap\n\nBuilt for " + TERM + ".\n")
    res = publish(private)
    assert res.returncode == 1
    assert "REFUSED" in res.stderr
    assert branches(public) == []


def test_no_deny_list_stops_the_publish(world):
    private, public = world
    (private / ".env").write_text(f"YBASE_PUBLIC_REPO={public}\n")
    res = publish(private)
    assert res.returncode == 1 and "deny-list" in res.stderr
    assert branches(public) == []


def test_another_licence_stops_the_publish(world):
    private, public = world
    commit(private, "LICENSE", "MIT License\n")
    res = publish(private)
    assert res.returncode == 1 and "LICENSE is not" in res.stderr
    assert branches(public) == []


def test_uncommitted_changes_stop_the_publish(world):
    private, public = world
    (private / "README.md").write_text("draft\n")
    res = publish(private)
    assert res.returncode == 1 and "uncommitted" in res.stderr


def test_absorb_takes_a_public_commit_once_and_keeps_its_author(world, tmp_path):
    private, public = world
    assert publish(private).returncode == 0
    visitor = tmp_path / "visitor"
    subprocess.run(["git", "clone", "-q", str(public), str(visitor)], check=True)
    (visitor / "docs" / "roadmap.md").write_text("# Roadmap\n\nFrom a contributor.\n")
    who = {"GIT_AUTHOR_NAME": "Visitor", "GIT_AUTHOR_EMAIL": "visitor@example.com"}
    g(visitor, "commit", "-q", "-am", "Fix the roadmap", **who)
    g(visitor, "push", "-q", "origin", "master")
    sha = g(visitor, "rev-parse", "HEAD")

    res = run(private, "absorb")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "1 public commit(s) absorbed" in res.stdout
    assert g(private, "log", "-1", "--format=%an") == "Visitor"
    assert f"cherry picked from commit {sha}" in g(private, "log", "-1", "--format=%B")
    assert "From a contributor." in (private / "docs" / "roadmap.md").read_text()

    again = run(private, "absorb")
    assert "0 public commit(s) absorbed" in again.stdout
    after = publish(private)
    assert "nothing to publish" in after.stdout


def test_publish_refuses_while_a_public_commit_is_not_absorbed(world, tmp_path):
    private, public = world
    assert publish(private).returncode == 0
    visitor = tmp_path / "visitor"
    subprocess.run(["git", "clone", "-q", str(public), str(visitor)], check=True)
    (visitor / "docs" / "roadmap.md").write_text("# Roadmap\n\nFrom a contributor.\n")
    g(visitor, "commit", "-q", "-am", "Fix the roadmap")
    g(visitor, "push", "-q", "origin", "master")
    commit(private, "docs/kb.md", "# KB\n")

    res = publish(private)
    assert res.returncode == 1 and "absorb" in res.stderr
    assert branches(public) == ["master"]
