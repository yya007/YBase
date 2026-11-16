"""Tests for checks.py beside this file. Each check is shown to fire on a planted defect,
not only to pass on a clean topic. Run: python3 -m unittest test_checks (from this folder)"""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Loaded under its own name: YBase's tools/checks.py is also imported as `checks` in one test run.
_spec = importlib.util.spec_from_file_location("research_topic_checks", HERE / "checks.py")
checks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checks)  # type: ignore[union-attr]

CASE_MD = """---
name: demo
summary: a demo topic
stages: [literature]
notes_dir: literature/papers
catalog: literature/CATALOG.md
note_required_keys: [title, url]
---
# Topic: demo
"""
NOTE = "---\ntitle: A paper\nurl: https://arxiv.org/abs/0000.00000\n---\n# A paper\n"


class Topic:
    """A throwaway topic folder with a valid manifest, one note and its catalog row."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "demo"
        self.write("CASE.md", CASE_MD)
        self.write("literature/papers/a-paper.md", NOTE)
        self.write("literature/CATALOG.md", "| [a-paper](papers/a-paper.md) |\n")

    def write(self, rel: str, text: str):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def run(self, fn):
        return fn(self.dir)


class CleanTopic(unittest.TestCase):
    def test_every_check_passes_on_a_clean_topic_and_scans_something(self):
        t = Topic()
        for name, fn in checks.CHECKS:
            scanned, bad = t.run(fn)
            self.assertEqual(bad, [], name)
            self.assertGreater(scanned, 0, name)

    def test_command_line_exit_codes(self):
        t = Topic()
        ok = subprocess.run([sys.executable, str(HERE / "checks.py"), str(t.dir)], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stdout)
        t.write("literature/papers/b.md", NOTE)
        bad = subprocess.run([sys.executable, str(HERE / "checks.py"), str(t.dir)], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1, bad.stdout)
        self.assertIn("FAIL catalog", bad.stdout)
        usage = subprocess.run([sys.executable, str(HERE / "checks.py")], capture_output=True, text=True)
        self.assertEqual(usage.returncode, 2)


class Fires(unittest.TestCase):
    def test_case_manifest_missing_stage(self):
        t = Topic()
        t.write("CASE.md", CASE_MD.replace("[literature]", "[literature, analysis]"))
        self.assertTrue(any("analysis" in b for b in t.run(checks.check_case_manifests)[1]))

    def test_case_manifest_wrong_name(self):
        t = Topic()
        t.write("CASE.md", CASE_MD.replace("name: demo", "name: other"))
        self.assertTrue(t.run(checks.check_case_manifests)[1])

    def test_source_note_missing_key(self):
        t = Topic()
        t.write("literature/papers/b.md", "---\ntitle: B\n---\n")
        self.assertTrue(any("url" in b for b in t.run(checks.check_source_notes)[1]))

    def test_catalog_missing_row(self):
        t = Topic()
        t.write("literature/papers/b.md", NOTE)
        self.assertTrue(any("b.md" in b for b in t.run(checks.check_catalog)[1]))


if __name__ == "__main__":
    unittest.main()
