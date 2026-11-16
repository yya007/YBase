"""Tests for tools/session_inventory.py, run against throwaway repositories.
Each fact the skills rely on is shown to appear when planted, not only to be
absent on a clean tree. Run: python3 -m unittest discover -s tests"""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import session_inventory as si  # noqa: E402

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, env=ENV).stdout


class Fixture:
    """A bare remote, a clone with one pushed commit, and a linked worktree on branch `work`."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.remote, self.main, self.wt = base / "remote.git", base / "main", base / "wt"
        subprocess.run(["git", "init", "-q", "--bare", str(self.remote)], check=True, env=ENV)
        subprocess.run(["git", "clone", "-q", str(self.remote), str(self.main)], check=True,
                       capture_output=True, env=ENV)
        (self.main / "a.txt").write_text("a\n")
        git(self.main, "add", "a.txt")
        git(self.main, "commit", "-qm", "init")
        git(self.main, "push", "-q", "origin", "HEAD")
        git(self.main, "worktree", "add", "-q", "-b", "work", str(self.wt))

    def commit_in_wt(self, name="b.txt"):
        (self.wt / name).write_text("b\n")
        git(self.wt, "add", name)
        git(self.wt, "commit", "-qm", "work")

    def inv(self, cwd=None, touched=(), env_key=None):
        return si.inventory(str(cwd or self.wt), list(touched), env_key)


def by_branch(inv, name):
    return next(w for w in inv["worktrees"] if w.get("branch") == name)


class Inventory(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def tearDown(self):
        self.f.tmp.cleanup()

    def test_outside_a_checkout_is_exit_2(self):
        d = tempfile.mkdtemp()
        try:
            self.assertIsNone(si.inventory(d, [], None))
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(si.main(["--repo", d]), 2)
        finally:
            shutil.rmtree(d)

    def test_identity_names_the_worktree_and_branch(self):
        i = self.f.inv()["identity"]
        self.assertEqual(i["worktree"], str(self.f.wt))
        self.assertEqual(i["branch"], "work")

    def test_owned_is_the_worktree_you_stand_in_not_every_worktree(self):
        inv = self.f.inv()
        self.assertTrue(by_branch(inv, "work")["owned"])
        main = next(w for w in inv["worktrees"] if w["main"])
        self.assertFalse(main["owned"])

    def test_unpushed_branch_without_a_worktree_is_counted_and_owned_only_when_touched(self):
        git(self.f.main, "branch", "side")
        git(self.f.main, "worktree", "add", "-q", str(self.f.wt.parent / "side"), "side")
        (self.f.wt.parent / "side" / "s.txt").write_text("s\n")
        git(self.f.wt.parent / "side", "add", "s.txt")
        git(self.f.wt.parent / "side", "commit", "-qm", "side")
        git(self.f.main, "worktree", "remove", str(self.f.wt.parent / "side"))
        side = next(b for b in self.f.inv()["branches"] if b["branch"] == "side")
        self.assertEqual((side["unpushed"], side["checked_out_at"], side["owned"]), (1, "", False))
        side = next(b for b in self.f.inv(touched=["side"])["branches"] if b["branch"] == "side")
        self.assertTrue(side["owned"])

    def test_commit_in_worktree_shows_as_unpushed_and_keep(self):
        self.f.commit_in_wt()
        w = by_branch(self.f.inv(), "work")
        self.assertEqual((w["unpushed"], w["verdict"]), (1, "keep"))

    def test_index_lock_and_paused_rebase_are_reported(self):
        gd = git(self.f.wt, "rev-parse", "--absolute-git-dir").strip()
        Path(gd, "index.lock").write_text("")
        Path(gd, "rebase-merge").mkdir()
        self.assertEqual(by_branch(self.f.inv(), "work")["git_ops"], ["index.lock", "rebase-merge"])

    def test_main_checkout_gets_counts_when_you_stand_in_it(self):
        (self.f.main / "dirty.txt").write_text("x\n")
        main = next(w for w in self.f.inv(cwd=self.f.main)["worktrees"] if w["main"])
        self.assertTrue(main["owned"])
        self.assertEqual(main["untracked"], 1)

    def test_stale_fetch_is_a_gap(self):
        gaps = " ".join(self.f.inv()["gaps"])
        self.assertIn("never fetched", gaps)
        git(self.f.main, "fetch", "-q")
        fh = Path(git(self.f.main, "rev-parse", "--git-common-dir").strip())
        fh = (fh if fh.is_absolute() else self.f.main / fh) / "FETCH_HEAD"
        old = time.time() - 7200
        os.utime(fh, (old, old))
        self.assertIn("min ago", " ".join(self.f.inv()["gaps"]))

    def test_profile_reports_durability(self):
        p = self.f.inv()["profile"]
        self.assertIn(p["durable"], ("yes", "no", "unknown"))
        self.assertIn("footprint", p)

    def test_render_has_every_section(self):
        text = si.render(self.f.inv())
        for head in ("IDENTITY", "PROFILE", "WORKTREES", "BRANCHES", "PROCESSES", "GAPS"):
            self.assertIn(head, text)


@unittest.skipUnless(Path("/proc/self/cwd").exists() or shutil.which("lsof"), "no /proc and no lsof")
class Processes(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def tearDown(self):
        self.f.tmp.cleanup()

    def spawn(self, env=None):
        p = subprocess.Popen(["sleep", "30"], cwd=str(self.f.wt), env=env)
        self.addCleanup(p.wait)
        self.addCleanup(p.kill)
        time.sleep(0.2)
        return p

    def test_a_process_in_the_worktree_is_found_and_placed(self):
        p = self.spawn()
        row = next((r for r in self.f.inv()["processes"] if r["pid"] == p.pid), None)
        self.assertIsNotNone(row)
        self.assertEqual(row["where"], str(self.f.wt))

    def test_this_process_and_its_ancestors_are_left_out(self):
        pids = {r["pid"] for r in si.inventory(str(Path.cwd()), [], None)["processes"]}
        self.assertNotIn(os.getpid(), pids)

    @unittest.skipUnless(Path("/proc/self/environ").exists(), "env join needs /proc")
    def test_env_key_join_marks_the_process(self):
        p = self.spawn(env=dict(os.environ, YB_TEST_SESSION="abc"))
        row = next(r for r in self.f.inv(env_key="YB_TEST_SESSION=abc")["processes"] if r["pid"] == p.pid)
        self.assertTrue(row["env_match"])


if __name__ == "__main__":
    unittest.main()
