"""Tests for the two session hooks that feed the retro: session_end_distil_hook.py and
tool_load_hook.py. Each hook is copied into a throwaway repository and run from a linked
worktree of it, so the test shows that the hook resolves the MAIN checkout from its own
location and never from cwd. Payloads arrive on stdin as the harness sends them.
Run: python3 -m unittest discover -s tests"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / ".claude" / "hooks"
ENV_GIT = dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
SID = "12345678-1234-4123-8123-123456789abc"


def git(cwd, *args):
    env = dict(os.environ, **ENV_GIT)
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, env=env).stdout


class Fixture:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.repo, self.wt, self.claude_home = base / "repo", base / "wt", base / "claude"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        (self.repo / ".gitignore").write_text(".ybase/\n")
        (self.repo / "tools").mkdir()
        shutil.copy(ROOT / "tools" / "retro.py", self.repo / "tools" / "retro.py")
        (self.repo / ".claude" / "hooks").mkdir(parents=True)
        for name in ("session_end_distil_hook.py", "tool_load_hook.py"):
            shutil.copy(HOOKS / name, self.repo / ".claude" / "hooks" / name)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "init")
        git(self.repo, "worktree", "add", "-q", "-b", "work", str(self.wt))
        self.transcript = self.claude_home / "projects" / "-repo" / (SID + ".jsonl")
        self.transcript.parent.mkdir(parents=True)
        self.transcript.write_text(json.dumps({
            "type": "user", "sessionId": SID, "cwd": str(self.repo), "timestamp": "2026-01-02T03:04:05Z",
            "message": {"role": "user", "content": [{"type": "text", "text": "hello"}]}}) + "\n")
        self.retro = self.repo / ".ybase" / "retro"
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.claude_home), CODEX_HOME=str(base / "codex"))
        self.env.pop("YBASE_RETRO_OFF", None)
        self.env.pop("YBASE_RETRO_DRY_RUN", None)

    def run_hook(self, name, stdin, cwd=None, **env):
        """Run the WORKTREE's copy of the hook, from an unrelated cwd, as the harness would."""
        r = subprocess.run([sys.executable, str(self.wt / ".claude" / "hooks" / name)], input=stdin, text=True,
                           capture_output=True, cwd=str(cwd or self.tmp.name), env=dict(self.env, **env), timeout=60)
        return r

    def session_end_payload(self, **over):
        p = {"session_id": SID, "transcript_path": str(self.transcript), "hook_event_name": "SessionEnd",
             "cwd": str(self.wt), "reason": "exit"}
        p.update(over)
        return json.dumps(p)

    def tool_payload(self, **over):
        p = {"session_id": "abc", "transcript_path": str(self.transcript), "tool_use_id": "toolu_1",
             "tool_name": "Bash", "hook_event_name": "PostToolUse", "cwd": str(self.wt),
             "tool_input": {"command": "ls"}, "tool_response": {"stdout": ""}}
        p.update(over)
        return json.dumps(p)


class SessionEnd(unittest.TestCase):
    HOOK = "session_end_distil_hook.py"

    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.tmp.cleanup)

    def test_records_the_close_in_the_main_checkout_and_plans_a_closed_distil(self):
        r = self.f.run_hook(self.HOOK, self.f.session_end_payload(), YBASE_RETRO_DRY_RUN="1")
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        argv = json.loads(r.stdout)
        self.assertEqual(argv[1:], [str(self.f.wt / "tools" / "retro.py"), "distill", "--only", str(self.f.transcript), "--closed"])
        rows = [json.loads(x) for x in (self.f.retro / "closed.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["session_id"], SID)
        self.assertEqual(rows[0]["transcript_path"], str(self.f.transcript))
        self.assertRegex(rows[0]["ended_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertIn("distil " + SID, (self.f.retro / "closed.log").read_text())
        self.assertFalse((self.f.wt / ".ybase").exists(), "state goes to the main checkout, not the worktree the hook ran from")

    def test_the_detached_distiller_writes_a_closed_record_after_the_hook_has_returned(self):
        started = time.time()
        r = self.f.run_hook(self.HOOK, self.f.session_end_payload())
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertLess(time.time() - started, 30, "the hook must return without waiting for the distiller")
        record = self.f.retro / "distill" / ("claude-%s.json" % SID)
        deadline = time.time() + 60
        while not record.exists() and time.time() < deadline:
            time.sleep(0.2)
        self.assertTrue(record.exists(), (self.f.retro / "closed.log").read_text() if (self.f.retro / "closed.log").exists() else "no log")
        for _ in range(50):  # the rename is atomic; wait for the distiller's summary line too
            if "1 written" in (self.f.retro / "closed.log").read_text():
                break
            time.sleep(0.2)
        s = json.loads(record.read_text())
        self.assertTrue(s["closed"])
        self.assertEqual(s["id"], SID)
        self.assertIn("1 written", (self.f.retro / "closed.log").read_text())

    def test_a_transcript_that_is_not_this_sessions_file_is_skipped(self):
        other = self.f.transcript.with_name("00000000-0000-4000-8000-000000000000.jsonl")
        shutil.copy(self.f.transcript, other)
        r = self.f.run_hook(self.HOOK, self.f.session_end_payload(transcript_path=str(other)), YBASE_RETRO_DRY_RUN="1")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertFalse((self.f.retro / "closed.jsonl").exists())
        self.assertIn("skip %s" % SID, (self.f.retro / "closed.log").read_text())

    def test_a_bad_session_id_or_missing_transcript_is_skipped(self):
        for payload in (self.f.session_end_payload(session_id="not-an-id"),
                        self.f.session_end_payload(transcript_path=str(self.f.transcript) + ".missing")):
            r = self.f.run_hook(self.HOOK, payload, YBASE_RETRO_DRY_RUN="1")
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertFalse((self.f.retro / "closed.jsonl").exists())

    def test_malformed_stdin_and_the_escape_are_silent_noops(self):
        for stdin, env in (("not json", {}), ("[1, 2]", {}), (self.f.session_end_payload(), {"YBASE_RETRO_OFF": "1"})):
            r = self.f.run_hook(self.HOOK, stdin, YBASE_RETRO_DRY_RUN="1", **env)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertFalse((self.f.retro / "closed.jsonl").exists())
        self.assertFalse((self.f.retro / "distill").exists())

    def test_outside_a_repository_it_does_nothing(self):
        loose = Path(self.f.tmp.name) / "loose"
        loose.mkdir()
        shutil.copy(HOOKS / self.HOOK, loose / self.HOOK)
        r = subprocess.run([sys.executable, str(loose / self.HOOK)], input=self.f.session_end_payload(), text=True,
                           capture_output=True, cwd=str(loose), env=dict(self.f.env, YBASE_RETRO_DRY_RUN="1",
                                                                         GIT_CEILING_DIRECTORIES=str(self.f.tmp.name)))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertFalse(list(loose.glob("**/closed.jsonl")))


class ToolLoad(unittest.TestCase):
    HOOK = "tool_load_hook.py"

    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.tmp.cleanup)

    def tsv(self, sid="abc"):
        return self.f.retro / "load" / (sid + ".tsv")

    def test_appends_one_sample_per_call_under_the_main_checkout(self):
        r = self.f.run_hook(self.HOOK, self.f.tool_payload())
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        r = self.f.run_hook(self.HOOK, self.f.tool_payload(tool_use_id="toolu_2", tool_name="Read"))
        self.assertEqual(r.returncode, 0)
        rows = [line.split("\t") for line in self.tsv().read_text().splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertEqual([len(row) for row in rows], [8, 8])
        self.assertEqual([row[1:4] for row in rows], [["abc", "toolu_1", "Bash"], ["abc", "toolu_2", "Read"]])
        for row in rows:
            float(row[0])
            for v in row[4:7]:
                float(v)
            self.assertGreater(int(row[7]), 0)
        self.assertFalse((self.f.wt / ".ybase").exists())

    def test_the_distiller_joins_the_sample_to_the_wait(self):
        lines = [
            {"type": "user", "sessionId": SID, "cwd": str(self.f.repo), "timestamp": "2026-01-02T03:04:05Z",
             "message": {"role": "user", "content": [{"type": "text", "text": "go"}]}},
            {"type": "assistant", "sessionId": SID, "cwd": str(self.f.repo), "timestamp": "2026-01-02T03:04:06Z",
             "message": {"id": "m1", "role": "assistant", "content": [{"type": "tool_use", "id": "toolu_9", "name": "Bash", "input": {}}]}},
            {"type": "user", "sessionId": SID, "cwd": str(self.f.repo), "timestamp": "2026-01-02T03:05:06Z",
             "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_9", "content": "ok"}]}},
        ]
        self.f.transcript.write_text("".join(json.dumps(x) + "\n" for x in lines))
        self.assertEqual(self.f.run_hook(self.HOOK, self.f.tool_payload(session_id=SID, tool_use_id="toolu_9")).returncode, 0)
        subprocess.run([sys.executable, str(self.f.repo / "tools" / "retro.py"), "distill", "--only", str(self.f.transcript)],
                       check=True, capture_output=True, env=self.f.env)
        s = json.loads((self.f.retro / "distill" / ("claude-%s.json" % SID)).read_text())
        self.assertEqual(s["load"]["samples"], 1)
        self.assertEqual(s["load"]["joined"], 1)
        self.assertEqual(s["waits"][0]["id"], "toolu_9")
        self.assertIn("load_per_core", s["waits"][0])

    def test_bad_input_is_a_silent_noop(self):
        cases = [
            "not json",
            self.f.tool_payload(session_id="../escape"),      # a path-shaped id never leaves the load directory
            self.f.tool_payload(session_id=""),
            json.dumps({"session_id": "abc", "tool_name": "Bash"}),  # no tool_use_id
            self.f.tool_payload(tool_name="Bash\tevil"),       # a tab would corrupt the row
        ]
        for stdin in cases:
            r = self.f.run_hook(self.HOOK, stdin)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""), stdin)
        self.assertFalse((self.f.retro / "load").exists())
        self.assertFalse(list(Path(self.f.tmp.name).glob("**/escape.tsv")))

    def test_the_escape_disables_recording(self):
        r = self.f.run_hook(self.HOOK, self.f.tool_payload(), YBASE_RETRO_OFF="1")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertFalse(self.tsv().exists())


if __name__ == "__main__":
    unittest.main()
