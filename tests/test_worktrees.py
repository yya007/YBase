"""Tests for tools/worktrees.py. Each verdict and each keep reason is planted in a
throwaway repository and shown to fire. Run: python3 -m unittest discover -s tests"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "tools" / "worktrees.py"


class Sandbox:
    """A bare `origin`, a clone of it, and helpers to cut worktrees from the clone."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(os.path.realpath(self.tmp.name))
        self.env = {**os.environ, "HOME": str(self.root), "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        self.env.pop("YB_ROOT", None)
        self.env.pop("GIT_DIR", None)
        self.env.pop("GIT_WORK_TREE", None)
        self.origin = self.root / "origin.git"
        self.main = self.root / "main"
        self.wt_dir = self.root / "wt"
        self.git(self.root, "init", "-q", "--bare", str(self.origin))
        self.git(self.origin, "symbolic-ref", "HEAD", "refs/heads/master")
        self.git(self.root, "clone", "-q", str(self.origin), str(self.main))
        self.git(self.main, "symbolic-ref", "HEAD", "refs/heads/master")
        self.write(self.main, "a.txt", "alpha\n")
        self.write(self.main, "docs/b.md", "bravo v1\n")
        self.write(self.main, "old.txt", "to be deleted on master\n")
        self.commit(self.main, "init")
        self.git(self.main, "push", "-q", "-u", "origin", "master")
        self.git(self.main, "remote", "set-head", "origin", "master")

    def close(self):
        self.tmp.cleanup()

    def git(self, cwd, *args) -> str:
        r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=self.env)
        if r.returncode != 0:
            raise AssertionError(f"git {' '.join(args)}: {r.stderr}")
        return r.stdout

    def write(self, cwd, rel, text):
        p = Path(cwd) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def commit(self, cwd, msg):
        self.git(cwd, "add", "-A")
        self.git(cwd, "commit", "-qm", msg)

    def add(self, name, base="origin/master") -> Path:
        path = self.wt_dir / name
        self.git(self.main, "worktree", "add", "-q", "-b", f"wt/{name}", str(path), base)
        return path

    def land_on_master(self, msg, files):
        for rel, text in files.items():
            if text is None:
                (self.main / rel).unlink()
            else:
                self.write(self.main, rel, text)
        self.commit(self.main, msg)
        self.git(self.main, "push", "-q", "origin", "master")
        self.git(self.main, "fetch", "-q", "origin")

    def report(self, *args, cwd=None, idle="0") -> dict:
        r = subprocess.run([sys.executable, str(TOOL), "--repo", str(self.main), "--json",
                            "--idle-days", idle, *args],
                           capture_output=True, text=True, env=self.env, cwd=str(cwd or self.root))
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        return json.loads(r.stdout)

    def row(self, report, path) -> dict:
        for w in report["worktrees"]:
            if os.path.realpath(w["path"]) == os.path.realpath(str(path)):
                return w
        raise AssertionError(f"no row for {path}")


class Base(unittest.TestCase):
    def setUp(self):
        self.s = Sandbox()

    def tearDown(self):
        self.s.close()

    def verdict(self, path, *args, cwd=None, idle="0"):
        w = self.s.row(self.s.report(*args, cwd=cwd, idle=idle), path)
        return w["verdict"], w["reason"], w


class Verdicts(Base):
    def test_main_checkout(self):
        rep = self.s.report()
        self.assertEqual(rep["worktrees"][0]["verdict"], "main")
        self.assertEqual(rep["landing"], "origin/master")

    def test_reap_when_everything_is_pushed(self):
        p = self.s.add("pushed")
        self.s.write(p, "new.txt", "work\n")
        self.s.commit(p, "work")
        self.s.git(p, "push", "-q", "origin", "wt/pushed")
        v, reason, w = self.verdict(p)
        self.assertEqual((v, reason), ("reap", "everything is pushed"))
        self.assertFalse(w["landed"])
        self.assertEqual(len(w["unlanded_commits"]), 1)

    def test_reap_when_landed_by_ancestry_though_unpushed(self):
        p = self.s.add("merged")
        self.s.write(p, "c.txt", "charlie\n")
        self.s.commit(p, "c")
        self.s.git(self.s.main, "merge", "-q", "--ff-only", "wt/merged")
        self.s.git(self.s.main, "push", "-q", "origin", "master")
        self.s.git(self.s.main, "fetch", "-q")
        v, reason, w = self.verdict(p)
        self.assertEqual(v, "reap")
        self.assertTrue(w["landed"])

    def test_squash_landed_branch_counts_as_landed(self):
        p = self.s.add("squash")
        self.s.write(p, "s1.txt", "one\n")
        self.s.commit(p, "s1")
        self.s.write(p, "s2.txt", "two\n")
        self.s.write(p, "a.txt", "alpha edited\n")
        self.s.commit(p, "s2")
        # The two commits land as one: no single commit's patch matches, so git cherry says "+".
        self.s.land_on_master("squash of wt/squash", {"s1.txt": "one\n", "s2.txt": "two\n", "a.txt": "alpha edited\n"})
        cherry = self.s.git(self.s.main, "cherry", "origin/master", "wt/squash")
        self.assertIn("+", cherry)
        v, reason, w = self.verdict(p)
        self.assertEqual(v, "reap", reason)
        self.assertTrue(w["landed"])
        self.assertIn("squashed", w["landed_how"])
        self.assertEqual(w["unlanded_commits"], [])

    def test_squash_landed_then_edited_on_landing_still_counts(self):
        p = self.s.add("squash2")
        self.s.write(p, "s1.txt", "one\n")
        self.s.commit(p, "s1")
        self.s.write(p, "s1.txt", "one\nmore\n")
        self.s.commit(p, "s1 again")
        self.s.land_on_master("squash of wt/squash2", {"s1.txt": "one\nmore\n"})
        self.s.land_on_master("later edit", {"s1.txt": "one\nmore\nand later\n"})
        v, reason, w = self.verdict(p)
        self.assertEqual(v, "reap", reason)
        self.assertIn("squashed", w["landed_how"])

    def test_landed_on_a_second_landing_ref(self):
        p = self.s.add("team")
        self.s.write(p, "t.txt", "team work\n")
        self.s.commit(p, "team work")
        self.s.git(self.s.main, "branch", "team", "wt/team")
        v, _, _ = self.verdict(p, "--landing", "origin/master")
        self.assertEqual(v, "keep")
        v, _, w = self.verdict(p, "--landing", "origin/master", "--landing", "team")
        self.assertEqual(v, "reap")
        self.assertTrue(w["landed"])

    def test_prune_when_directory_is_gone(self):
        p = self.s.add("gone")
        shutil.rmtree(p)
        v, _, w = self.verdict(p)
        self.assertEqual(v, "prune")
        self.assertFalse(w["exists"])

    def test_bad_landing_ref_is_refused_not_reported_clean(self):
        r = subprocess.run([sys.executable, str(TOOL), "--repo", str(self.s.main), "--landing", "nope"],
                           capture_output=True, text=True, env=self.s.env)
        self.assertEqual(r.returncode, 2)
        r = subprocess.run([sys.executable, str(TOOL), "--repo", str(self.s.root / "missing")],
                           capture_output=True, text=True, env=self.s.env)
        self.assertEqual(r.returncode, 2)

    def test_repo_accepts_a_managed_repo_name_and_a_path_still_wins(self):
        home = self.s.root / "home"
        (home / "kb").mkdir(parents=True)
        (home / "kb" / "repos.md").write_text(
            "| Name | What it is | Remote | Hint |\n|---|---|---|---|\n| sandbox-repo | x | | |\n",
            encoding="utf-8")
        env = {k: v for k, v in self.s.env.items() if not k.startswith("YBASE_")}
        env.update(YB_ROOT=str(home), YBASE_REPO_PATH_SANDBOX_REPO=str(self.s.main))
        for repo in ("sandbox-repo", "SANDBOX-repo", str(self.s.main)):
            r = subprocess.run([sys.executable, str(TOOL), "--repo", repo, "--json"],
                               capture_output=True, text=True, env=env, cwd=str(self.s.root))
            self.assertEqual(r.returncode, 0, (repo, r.stderr))
            self.assertEqual(json.loads(r.stdout)["repo"], str(self.s.main))
        r = subprocess.run([sys.executable, str(TOOL), "--repo", "unlisted"],
                           capture_output=True, text=True, env=env, cwd=str(self.s.root))
        self.assertEqual(r.returncode, 2)


class KeepReasons(Base):
    def assertKeep(self, path, fragment, *args, cwd=None, idle="0"):
        v, reason, w = self.verdict(path, *args, cwd=cwd, idle=idle)
        self.assertEqual(v, "keep", reason)
        self.assertIn(fragment, reason)
        return w

    def test_recent_by_default(self):
        p = self.s.add("fresh")
        w = self.assertKeep(p, "recent", idle="1")
        self.assertLess(w["idle_days"], 1)
        self.assertEqual(self.verdict(p)[0], "reap")  # the same tree, once the window is zero

    def test_idle_clock_ignores_maintenance_rewriting_logs(self):
        p = self.s.add("aged")
        admin = Path(self.s.git(p, "rev-parse", "--absolute-git-dir").strip())
        old = time.time() - 10 * 86400
        for f in [p, *admin.iterdir()]:
            if f.name != "logs":
                os.utime(f, (old, old))
        log = admin / "logs" / "HEAD"
        lines = log.read_text().splitlines()
        meta, msg = lines[-1].split("\t", 1)
        parts = meta.split()
        parts[-2] = str(int(old))
        lines[-1] = " ".join(parts) + "\t" + msg
        log.write_text("\n".join(lines) + "\n")  # logs/ mtime is now: a gc pass would look like this
        v, reason, w = self.verdict(p, idle="3")
        self.assertEqual(v, "reap", reason)
        self.assertGreater(w["idle_days"], 9)

    def test_uncommitted(self):
        p = self.s.add("dirty")
        self.s.write(p, "a.txt", "changed\n")
        self.assertEqual(self.assertKeep(p, "uncommitted")["dirty"], 1)

    def test_untracked(self):
        p = self.s.add("untracked")
        self.s.write(p, "deep/dir/new.txt", "new\n")
        self.assertEqual(self.assertKeep(p, "untracked")["untracked"], 1)

    def test_unpushed_and_not_landed(self):
        p = self.s.add("local")
        self.s.write(p, "l.txt", "local\n")
        self.s.commit(p, "local only")
        w = self.assertKeep(p, "on no remote and not landed")
        self.assertEqual(w["unpushed"], 1)
        self.assertTrue(w["unlanded_commits"][0].endswith("local only"))

    def test_locked(self):
        p = self.s.add("locked")
        self.s.git(self.s.main, "worktree", "lock", str(p))
        self.assertKeep(p, "locked")

    def test_locked_and_gone_is_kept_not_pruned(self):
        p = self.s.add("removable")
        self.s.git(self.s.main, "worktree", "lock", str(p))
        shutil.rmtree(p)
        self.assertKeep(p, "locked")

    def test_current(self):
        p = self.s.add("here")
        self.assertKeep(p, "current", cwd=p / "docs")

    def test_in_use(self):
        p = self.s.add("busy")
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], cwd=str(p))
        try:
            time.sleep(0.3)
            w = self.assertKeep(p, "in use")
            self.assertTrue(any(x.startswith(f"{proc.pid} ") for x in w["in_use"]))
        finally:
            proc.kill()
            proc.wait()

    def test_broken_tree_is_not_read_through_the_parent(self):
        p = self.s.add("broken")
        (p / ".git").unlink()
        w = self.assertKeep(p, "broken")
        self.assertTrue(w["broken"])

    def test_a_failed_check_is_a_refusal(self):
        p = self.s.add("unreadable")
        (p / ".git").write_text("gitdir: /nonexistent/gitdir\n", encoding="utf-8")
        self.assertKeep(p, "could not read git status")


class Findings(Base):
    def test_each_finding_verdict(self):
        p = self.s.add("stale")
        # Master moves on after the worktree was cut.
        self.s.land_on_master("move on", {"new_on_master.txt": "fresh\n", "docs/b.md": "bravo v2\n",
                                          "renamed/a.txt": "alpha\n", "old.txt": None})
        self.s.write(p, "new_on_master.txt", "fresh\n")          # landed: same content, same path
        self.s.write(p, "copy_of_a.txt", "alpha\n")              # superseded: content at another path
        self.s.write(p, "a.txt", "alpha local edit\n")           # differs
        self.s.write(p, "old.txt", "a local edit\n")             # removed-on-landing
        self.s.write(p, "notes/idea.md", "a new idea\n")         # novel
        rep = self.s.report("--findings")
        got = {f["path"]: f["verdict"] for f in self.s.row(rep, p)["findings"]}
        self.assertEqual(got["new_on_master.txt"], "landed")
        self.assertEqual(got["copy_of_a.txt"], "superseded")
        self.assertEqual(got["a.txt"], "differs")
        self.assertEqual(got["old.txt"], "removed-on-landing")
        self.assertEqual(got["notes/idea.md"], "novel")
        self.assertTrue(rep["findings"])

    def test_older_version_of_the_same_path_is_superseded(self):
        p = self.s.add("older")
        self.s.land_on_master("v2", {"docs/b.md": "bravo v2\n"})
        self.s.land_on_master("v3", {"docs/b.md": "bravo v3\n"})
        self.s.write(p, "docs/b.md", "bravo v2\n")
        got = {f["path"]: f for f in self.s.row(self.s.report("--findings"), p)["findings"]}
        self.assertEqual(got["docs/b.md"]["verdict"], "superseded")
        self.assertIn("older version", got["docs/b.md"]["evidence"])

    def test_deletion_master_also_made_is_landed(self):
        p = self.s.add("deleter")
        self.s.land_on_master("drop old", {"old.txt": None})
        (p / "old.txt").unlink()
        (p / "a.txt").unlink()
        got = {f["path"]: f["verdict"] for f in self.s.row(self.s.report("--findings"), p)["findings"]}
        self.assertEqual(got["old.txt"], "landed")
        self.assertEqual(got["a.txt"], "differs")

    def test_stash_is_listed_and_judged(self):
        p = self.s.add("stasher")
        self.s.write(p, "a.txt", "stashed edit\n")
        self.s.write(p, "loose.txt", "loose\n")
        self.s.git(p, "stash", "push", "-q", "-u", "-m", "test-stash")
        rep = self.s.report("--findings")
        self.assertEqual(len(rep["stashes"]), 1)
        st = rep["stashes"][0]
        self.assertIn("test-stash", st["message"])
        got = {f["path"]: f["verdict"] for f in st["findings"]}
        self.assertEqual(got, {"a.txt": "differs", "loose.txt": "novel"})
        self.assertEqual(self.s.report()["stashes"][0]["findings"], [])  # listed without --findings

    def test_unregistered_directory_beside_the_worktrees(self):
        self.s.add("real")
        (self.s.wt_dir / "leftover" / "sub").mkdir(parents=True)
        rep = self.s.report()
        self.assertEqual([os.path.basename(d) for d in rep["unregistered"]], ["leftover"])


class Reap(Base):
    def test_reap_removes_only_the_safe_and_never_forces(self):
        safe = self.s.add("safe")
        self.s.write(safe, "c.txt", "charlie\n")
        self.s.commit(safe, "c")
        self.s.git(self.s.main, "merge", "-q", "--ff-only", "wt/safe")
        self.s.git(self.s.main, "push", "-q", "origin", "master")
        self.s.git(self.s.main, "fetch", "-q")
        squash = self.s.add("squashy")
        self.s.write(squash, "q1.txt", "1\n")
        self.s.commit(squash, "q1")
        self.s.write(squash, "q2.txt", "2\n")
        self.s.commit(squash, "q2")
        self.s.land_on_master("squash", {"q1.txt": "1\n", "q2.txt": "2\n"})
        dirty = self.s.add("dirty")
        self.s.write(dirty, "a.txt", "work in progress\n")
        gone = self.s.add("gone")
        shutil.rmtree(gone)
        r = subprocess.run([sys.executable, str(TOOL), "--repo", str(self.s.main), "--idle-days", "0", "--reap"],
                           capture_output=True, text=True, env=self.s.env, cwd=str(self.s.root))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(safe.exists())
        self.assertFalse(squash.exists())
        self.assertTrue((dirty / "a.txt").read_text() == "work in progress\n")
        listed = self.s.git(self.s.main, "worktree", "list", "--porcelain")
        self.assertNotIn(str(gone), listed)
        self.assertIn(str(dirty), listed)
        branches = self.s.git(self.s.main, "branch", "--format=%(refname:short)").split()
        self.assertNotIn("wt/safe", branches)      # merged: git branch -d took it
        self.assertIn("wt/squashy", branches)      # squash-landed: -d refuses, so the branch stays
        self.assertIn("wt/dirty", branches)


if __name__ == "__main__":
    unittest.main()
