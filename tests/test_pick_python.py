"""Tests for tools/pick_python.sh: the first interpreter on PATH that meets every floor.

Interpreters are shell shims that print a version, so the outcome does not
depend on what the machine has installed. Run: python3 -m unittest discover -s tests
"""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PICK = ROOT / "tools" / "pick_python.sh"


class PickPython(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        # Only the tools the script needs, so no real interpreter leaks in from PATH.
        sysbin = self.root / "sysbin"
        sysbin.mkdir()
        for tool in ("bash", "sed", "head", "dirname"):
            os.symlink(shutil.which(tool), sysbin / tool)
        self.env = {"PATH": "%s:%s" % (self.bin, sysbin), "HOME": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def shim(self, name, version, where=None):
        path = (where or self.bin) / name
        path.write_text("#!/bin/sh\necho 'Python %s'\n" % version, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def project(self, rel, floor_line):
        d = self.root / rel
        d.mkdir(parents=True, exist_ok=True)
        (d / "pyproject.toml").write_text("[project]\nname = \"x\"\n%s\n" % floor_line, encoding="utf-8")
        return d / "pyproject.toml"

    def run_pick(self, *args, env=None):
        full = dict(self.env)
        full.update(env or {})
        res = subprocess.run(["bash", str(PICK), *args], capture_output=True, text=True, env=full, timeout=60)
        return res.returncode, res.stdout.strip(), res.stderr

    def test_prefers_python3_when_it_meets_the_floor(self):
        self.shim("python3", "3.11.2")
        self.shim("python3.12", "3.12.0")
        p = self.project("a", 'requires-python = ">=3.10"')
        rc, out, _ = self.run_pick(str(p))
        self.assertEqual(rc, 0)
        self.assertEqual(out, str(self.bin / "python3"))

    def test_falls_through_versions_in_order(self):
        self.shim("python3", "3.8.10")
        self.shim("python3.9", "3.9.1")
        self.shim("python3.11", "3.11.0")
        p = self.project("a", 'requires-python = ">=3.9, <4"')
        rc, out, _ = self.run_pick(str(p))
        self.assertEqual(rc, 0)
        self.assertEqual(out, str(self.bin / "python3.11"), "3.13 down to 3.8: 3.11 comes before 3.9")

    def test_every_floor_counts(self):
        self.shim("python3", "3.9.0")
        self.shim("python3.12", "3.12.0")
        a = self.project("a", 'requires-python = ">=3.8"')
        b = self.project("b", 'requires-python = ">=3.12"')
        rc, out, _ = self.run_pick(str(a), str(b))
        self.assertEqual(rc, 0)
        self.assertEqual(out, str(self.bin / "python3.12"))

    def test_for_path_finds_the_nearest_pyproject(self):
        self.shim("python3", "3.10.0")
        self.project("repo", 'requires-python = ">=3.10"')
        deep = self.root / "repo" / "src" / "pkg"
        deep.mkdir(parents=True)
        rc, out, _ = self.run_pick("--for-path", str(deep))
        self.assertEqual(rc, 0)
        self.assertEqual(out, str(self.bin / "python3"))
        rc, out, _ = self.run_pick("--for-path", str(deep / "mod.py"))
        self.assertEqual(rc, 0, "a file path resolves through its directory")

    def test_pick_python_override_comes_first(self):
        self.shim("python3", "3.12.0")
        custom = self.shim("mypy3", "3.13.0", where=self.root)
        p = self.project("a", 'requires-python = ">=3.9"')
        rc, out, _ = self.run_pick(str(p), env={"PICK_PYTHON": str(custom)})
        self.assertEqual(out, str(custom))
        old = self.shim("oldpy", "3.6.0", where=self.root)
        rc, out, _ = self.run_pick(str(p), env={"PICK_PYTHON": str(old)})
        self.assertEqual(out, str(self.bin / "python3"), "an override below the floor is skipped, not trusted")

    def test_none_meets_floor_exits_3_and_lists_what_it_tried(self):
        self.shim("python3", "3.8.0")
        p = self.project("a", 'requires-python = ">=3.12"')
        rc, out, err = self.run_pick(str(p))
        self.assertEqual(rc, 3)
        self.assertEqual(out, "")
        self.assertIn("no interpreter on PATH meets >=3.12", err)
        self.assertIn("tried %s: Python 3.8" % (self.bin / "python3"), err)
        self.assertIn("python3.13: not found", err)

    def test_usage_errors_exit_2(self):
        self.assertEqual(self.run_pick()[0], 2)
        self.assertEqual(self.run_pick("--for-path")[0], 2)
        self.assertEqual(self.run_pick(str(self.root / "missing.toml"))[0], 2)
        no_bound = self.project("nb", 'requires-python = "~=3.9"')
        rc, _, err = self.run_pick(str(no_bound))
        self.assertEqual(rc, 2)
        self.assertIn("no requires-python >=X.Y", err)
        rc, _, err = self.run_pick("--for-path", self.tmp.name)
        self.assertEqual(rc, 2)
        self.assertIn("no pyproject.toml", err)

    def test_unreadable_version_is_skipped(self):
        broken = self.bin / "python3"
        broken.write_text("#!/bin/sh\necho 'not a python'\nexit 1\n", encoding="utf-8")
        broken.chmod(broken.stat().st_mode | stat.S_IXUSR)
        self.shim("python3.10", "3.10.4")
        p = self.project("a", 'requires-python = ">=3.9"')
        rc, out, _ = self.run_pick(str(p))
        self.assertEqual(rc, 0)
        self.assertEqual(out, str(self.bin / "python3.10"))


if __name__ == "__main__":
    unittest.main()
