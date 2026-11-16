"""ybase update: report incoming commits, apply only on request, refuse unsafe states."""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
UPDATE = ROOT / "tools" / "update.sh"


def git(cwd, *args):
    res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=ENV)
    assert res.returncode == 0, res.stderr
    return res.stdout.strip()


ENV = {k: v for k, v in os.environ.items() if not k.startswith(("YBASE_", "GIT_"))}
ENV.update(
    YBASE_PROFILE="linux",
    GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
    GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com",
)


@pytest.fixture
def world(tmp_path):
    """A bare upstream, a clone of it (the machine), and a second clone that publishes."""
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "--quiet", str(ROOT), str(seed)], check=True, env=ENV)
    # A detached or branchless ROOT (as CI leaves it on pull requests) gives a detached seed.
    subprocess.run(["git", "-C", str(seed), "checkout", "-q", "-B", "main"], check=True, env=ENV)
    upstream = tmp_path / "upstream.git"
    subprocess.run(["git", "clone", "--quiet", "--bare", str(seed), str(upstream)], check=True, env=ENV)
    machine = tmp_path / "machine"
    pusher = tmp_path / "pusher"
    for d in (machine, pusher):
        subprocess.run(["git", "clone", "--quiet", str(upstream), str(d)], check=True, env=ENV)
    (tmp_path / "home").mkdir()
    ENV["HOME"] = str(tmp_path / "home")
    return machine, pusher


def publish(pusher, rel="NEWS.txt", text="news\n"):
    path = pusher / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    git(pusher, "add", rel)
    git(pusher, "commit", "--quiet", "-m", f"add {rel}")
    git(pusher, "push", "--quiet")


def run_update(machine, *args):
    env = dict(ENV, YB_ROOT=str(machine))
    return subprocess.run(
        ["/bin/bash", str(UPDATE), *args], cwd=machine, env=env,
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300,
    )


def test_shows_incoming_commits_and_applies_nothing_by_default(world):
    machine, pusher = world
    publish(pusher)
    before = git(machine, "rev-parse", "HEAD")
    res = run_update(machine)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "add NEWS.txt" in res.stdout
    assert "NEWS.txt" in res.stdout
    assert "run ybase update --apply to merge exactly this" in res.stdout
    assert git(machine, "rev-parse", "HEAD") == before


def test_apply_fast_forwards(world):
    machine, pusher = world
    env = dict(ENV, YB_ROOT=str(machine))
    subprocess.run(["/bin/bash", str(machine / "bin" / "ybase"), "kb", "init"], cwd=machine, env=env,
                   check=True, capture_output=True)  # the local KB is gitignored, so the tree stays clean
    publish(pusher)
    assert run_update(machine).returncode == 0
    res = run_update(machine, "--apply")
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert (machine / "NEWS.txt").is_file(), out
    assert git(machine, "rev-parse", "HEAD") == git(machine, "rev-parse", "@{u}")
    lines = res.stdout.splitlines()
    assert "== knowledge bases" in lines, out  # doctor ran
    marker = "pending knowledge base layout steps (not run; apply with ybase kb migrate):"
    assert marker in lines, out
    after = out[out.index(marker):]
    assert "is up to date (layout version" in after, out  # the dry run's own output


def test_a_failing_doctor_keeps_the_merge_and_sets_the_exit_status(world):
    machine, pusher = world
    publish(pusher, "tools/doctor.sh", "#!/usr/bin/env bash\necho STUB-DOCTOR-RAN\nexit 3\n")
    assert run_update(machine).returncode == 0
    before = git(machine, "rev-parse", "HEAD")
    res = run_update(machine, "--apply")
    out = res.stdout + res.stderr
    assert res.returncode == 3, out
    assert "STUB-DOCTOR-RAN" in res.stdout, out
    assert git(machine, "rev-parse", "HEAD") != before
    assert git(machine, "rev-parse", "HEAD") == git(machine, "rev-parse", "@{u}")
    assert "doctor exited 3 after the update; the update itself is kept" in res.stderr, out


def test_an_unknown_argument_is_refused(world):
    machine, pusher = world
    publish(pusher)
    before = git(machine, "rev-parse", "HEAD")
    for args in (("--aply",), ("--apply", "extra"), ("extra", "--apply")):
        res = run_update(machine, *args)
        assert res.returncode == 2, args
        assert "usage: ybase update [--apply]" in res.stderr, args
        assert git(machine, "rev-parse", "HEAD") == before, args


def test_up_to_date(world):
    machine, _ = world
    res = run_update(machine)
    assert res.returncode == 0
    assert "up to date" in res.stdout


def test_dirty_tree_is_refused(world):
    machine, pusher = world
    publish(pusher)
    (machine / "README.md").write_text("local edit\n")
    before = git(machine, "rev-parse", "HEAD")
    res = run_update(machine, "--apply")
    assert res.returncode == 1
    assert "changes" in res.stderr
    assert git(machine, "rev-parse", "HEAD") == before
    assert (machine / "README.md").read_text() == "local edit\n"


def test_untracked_files_do_not_block(world):
    machine, _ = world
    (machine / "scratch.txt").write_text("x\n")
    assert run_update(machine).returncode == 0


def test_local_commits_are_refused(world):
    machine, pusher = world
    (machine / "mine.txt").write_text("mine\n")
    git(machine, "add", "mine.txt")
    git(machine, "commit", "--quiet", "-m", "local work")
    before = git(machine, "rev-parse", "HEAD")
    res = run_update(machine, "--apply")
    assert res.returncode == 1
    assert "commits" in res.stderr
    assert git(machine, "rev-parse", "HEAD") == before


def test_no_upstream_is_refused(world):
    machine, _ = world
    git(machine, "checkout", "--quiet", "-b", "lonely")
    res = run_update(machine)
    assert res.returncode == 1
    assert "upstream" in res.stderr


def test_detached_head_is_refused(world):
    machine, _ = world
    git(machine, "checkout", "--quiet", "--detach")
    res = run_update(machine)
    assert res.returncode == 1
    assert "detached" in res.stderr


def test_unreachable_remote_fails_without_changing_head(world, tmp_path):
    machine, _ = world
    git(machine, "remote", "set-url", "origin", str(tmp_path / "does-not-exist.git"))
    before = git(machine, "rev-parse", "HEAD")
    res = run_update(machine)
    assert res.returncode == 1
    assert "fetch" in res.stderr
    assert git(machine, "rev-parse", "HEAD") == before


@pytest.mark.parametrize(
    "rel",
    [
        ".claude/hooks/new-guard.sh", ".claude/settings.json", "templates/kb/VERSION",
        ".githooks/post-merge", "bin/newcmd", "tools/newtool.sh", "profiles/ci/profile.env",
        ".codex/config.toml",
    ],
)
def test_a_hook_or_settings_change_is_called_out(world, rel):
    machine, pusher = world
    publish(pusher, rel, "changed\n")
    res = run_update(machine)
    assert res.returncode == 0, res.stdout + res.stderr
    assert any(
        line.startswith("changes what runs") and rel in line for line in res.stdout.splitlines()
    ), res.stdout


def test_ordinary_change_is_not_called_out(world):
    machine, pusher = world
    publish(pusher)
    assert "changes what runs" not in run_update(machine).stdout


def test_apply_merges_only_what_the_last_update_showed(world):
    machine, pusher = world
    publish(pusher, "A.txt", "a\n")
    shown = run_update(machine)
    assert shown.returncode == 0, shown.stdout + shown.stderr
    tip_a = git(pusher, "rev-parse", "HEAD")
    assert tip_a[:7] in shown.stdout
    publish(pusher, "B.txt", "b\n")
    res = run_update(machine, "--apply")
    assert res.returncode == 0, res.stdout + res.stderr
    assert git(machine, "rev-parse", "HEAD") == tip_a
    assert (machine / "A.txt").is_file()
    assert not (machine / "B.txt").exists()


def test_apply_with_nothing_fetched_says_so(world):
    machine, pusher = world
    publish(pusher)
    before = git(machine, "rev-parse", "HEAD")
    res = run_update(machine, "--apply")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "nothing fetched to apply; run ybase update first" in res.stdout
    assert git(machine, "rev-parse", "HEAD") == before


def test_apply_says_it_runs_the_updated_doctor(world):
    machine, pusher = world
    publish(pusher)
    res = run_update(machine)
    assert "--apply runs the updated ybase doctor" in res.stdout


def test_apply_does_not_run_an_incoming_post_merge_hook(world, tmp_path):
    machine, pusher = world
    marker = tmp_path / "hook-ran"
    publish(pusher, ".githooks/post-merge", f"#!/bin/sh\ntouch '{marker}'\n")
    git(pusher, "update-index", "--chmod=+x", ".githooks/post-merge")
    git(pusher, "commit", "--quiet", "-m", "make executable")
    git(pusher, "push", "--quiet")
    git(machine, "config", "core.hooksPath", ".githooks")
    assert run_update(machine).returncode == 0
    res = run_update(machine, "--apply")
    assert res.returncode == 0, res.stdout + res.stderr
    assert (machine / ".githooks" / "post-merge").is_file()
    assert not marker.exists()


def test_a_diverged_upstream_is_refused_with_its_own_message(world):
    machine, pusher = world
    (machine / "mine.txt").write_text("mine\n")
    git(machine, "add", "mine.txt")
    git(machine, "commit", "--quiet", "-m", "local work")
    publish(pusher)
    res = run_update(machine)
    assert res.returncode == 1
    assert "diverged" in res.stderr and "rewritten" in res.stderr
    assert "by hand" in res.stderr
    assert "merge or rebase" not in res.stderr
