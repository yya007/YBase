"""Tests for tools/retro.py, run against fixture transcripts in a temp directory.
Both harness formats are planted, with the signals the distiller must find and the
near-misses it must leave alone. Run: python3 -m unittest discover -s tests"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "tools" / "retro.py"
ENV_GIT = dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
SID = "11111111-2222-4333-8444-555555555555"
SID_WT = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
SID_DECOY = "99999999-8888-4777-8666-555555555555"
CID = "0199aaaa-bbbb-7ccc-8ddd-eeeeeeeeeeee"
T0 = 1_790_000_000.0


def git(cwd, *args):
    env = dict(os.environ, **ENV_GIT)
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, env=env).stdout


def ts(offset):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(T0 + offset))


def claude_lines(sid, cwd):
    """A Claude Code transcript. Returns (lines, expected) where expected names line numbers."""
    def user(text, offset, **extra):
        d = {"type": "user", "sessionId": sid, "cwd": cwd, "gitBranch": "main", "timestamp": ts(offset),
             "message": {"role": "user", "content": [{"type": "text", "text": text}]}}
        d.update(extra)
        return d

    lines = [
        {"type": "mode", "mode": "x"},                                                        # 1
        user("please clean up the worktrees", 0),                                             # 2 turn
        {"type": "assistant", "sessionId": sid, "cwd": cwd, "timestamp": ts(1),               # 3
         "message": {"id": "msg_1", "role": "assistant",
                     "usage": {"input_tokens": 10, "cache_read_input_tokens": 100,
                               "cache_creation_input_tokens": 20, "output_tokens": 5},
                     "content": [{"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "ls"}}]}},
        {"type": "assistant", "sessionId": sid, "cwd": cwd, "timestamp": ts(1),               # 4 same message id: usage counted once
         "message": {"id": "msg_1", "role": "assistant",
                     "usage": {"input_tokens": 10, "cache_read_input_tokens": 100,
                               "cache_creation_input_tokens": 20, "output_tokens": 5},
                     "content": [{"type": "text", "text": "running"}]}},
        {"type": "user", "sessionId": sid, "cwd": cwd, "timestamp": ts(46),                   # 5 error, 45 s wait
         "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1",
                                                  "is_error": True, "content": "boom"}]}},
        user("<system-reminder>injected</system-reminder>", 47),                               # 6 not a turn
        user("no meta", 48, isMeta=True),                                                      # 7 not a turn
        user("no sidechain", 49, isSidechain=True),                                            # 8 not a turn
        user("[Request interrupted by user]", 50),                                             # 9 interrupt
        user("no, not that directory", 51),                                                    # 10 correction
        {"type": "assistant", "sessionId": sid, "cwd": cwd, "timestamp": ts(52),              # 11
         "message": {"id": "msg_2", "role": "assistant",
                     "usage": {"input_tokens": 1, "cache_read_input_tokens": 0,
                               "cache_creation_input_tokens": 0, "output_tokens": 2},
                     "content": [{"type": "tool_use", "id": "toolu_2", "name": "Read", "input": {}}]}},
        {"type": "user", "sessionId": sid, "cwd": cwd, "timestamp": ts(53),                   # 12 fast, ok
         "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_2", "content": "x"}]}},
        user("Nothing wrong here, carry on", 54),                                              # 13 near-miss: not a correction
    ]
    expected = dict(turns=3, corrections=[10], interrupts=[9], errors=[5], calls=2,
                    tokens={"input": 11, "cache_read": 100, "cache_write": 20, "output": 7, "total": 138, "samples": 2})
    return lines, expected


def codex_lines(cid, cwd):
    lines = [
        {"type": "session_meta", "timestamp": ts(0), "payload": {"id": cid, "cwd": cwd}},             # 1
        {"type": "response_item", "timestamp": ts(1),                                                 # 2 turn
         "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "please run it"}]}},
        {"type": "response_item", "timestamp": ts(2),                                                 # 3
         "payload": {"type": "function_call", "call_id": "call_1", "name": "exec", "arguments": "{}"}},
        {"type": "response_item", "timestamp": ts(42),                                                # 4 error, 40 s wait
         "payload": {"type": "function_call_output", "call_id": "call_1", "output": "{\"exit_code\": 1, \"output\": \"bad\"}"}},
        {"type": "event_msg", "timestamp": ts(43),                                                    # 5
         "payload": {"type": "token_count", "info": {"total_token_usage": {
             "input_tokens": 100, "cached_input_tokens": 60, "cache_write_input_tokens": 5, "output_tokens": 7}}}},
        {"type": "event_msg", "timestamp": ts(44), "payload": {"type": "turn_aborted"}},               # 6 interrupt
        {"type": "response_item", "timestamp": ts(45),                                                # 7 correction
         "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "stop, wrong file"}]}},
        {"type": "response_item", "timestamp": ts(46),                                                # 8 not a turn
         "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "<environment_context/>"}]}},
    ]
    expected = dict(turns=2, corrections=[7], interrupts=[6], errors=[4], calls=1,
                    tokens={"input": 40, "cache_read": 60, "cache_write": 5, "output": 7, "total": 112, "samples": 1})
    return lines, expected


def write_jsonl(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")


class Fixture:
    """A repo with one linked worktree, a decoy sibling sharing its name prefix, and transcripts of both harnesses."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.repo, self.wt, self.decoy = base / "repo", base / "repo-wt" / "one", base / "repo-other"
        self.claude_home, self.codex_home = base / "claude", base / "codex"
        self.repo.mkdir()
        self.decoy.mkdir()
        git(self.repo, "init", "-q")
        (self.repo / ".gitignore").write_text(".ybase/\n")
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "rules.md").write_text("# Rules\n\n1. **Verify before you assert.** Read it.\n\nprose\n2. **Label every number.**\n")
        (self.repo / "memory").mkdir()
        (self.repo / "memory" / "publishing.md").write_text(
            "# publishing\n\n<!-- BEGIN TRIGGERS -->\n- `a-slug` - when this applies.\n<!-- END TRIGGERS -->\n\n## a-slug\n- `not-a-trigger` outside the block\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "init")
        self.wt.parent.mkdir(parents=True)
        git(self.repo, "worktree", "add", "-q", "-b", "work", str(self.wt))
        # Claude: one session in the repo, one in the worktree (a subdirectory of it), one in the decoy.
        lines, self.claude_expected = claude_lines(SID, str(self.repo))
        self.claude_path = self.claude_home / "projects" / "-repo" / (SID + ".jsonl")
        write_jsonl(self.claude_path, lines)
        write_jsonl(self.claude_home / "projects" / "-wt" / (SID_WT + ".jsonl"), claude_lines(SID_WT, str(self.wt / "sub"))[0])
        write_jsonl(self.claude_home / "projects" / "-decoy" / (SID_DECOY + ".jsonl"), claude_lines(SID_DECOY, str(self.decoy))[0])
        # Codex: one session in the repo.
        lines, self.codex_expected = codex_lines(CID, str(self.repo))
        self.codex_path = self.codex_home / "sessions" / "2026" / "01" / "02" / ("rollout-2026-01-02T00-00-00-" + CID + ".jsonl")
        write_jsonl(self.codex_path, lines)
        # A load sample for the slow Claude call: 8 runnable on 4 cores.
        load = self.repo / ".ybase" / "retro" / "load"
        load.mkdir(parents=True)
        (load / (SID + ".tsv")).write_text("%.3f\t%s\ttoolu_1\tBash\t8.00\t7.00\t6.00\t4\n%.3f\t%s\ttoolu_2\tRead\t0.50\t0.50\t0.50\t4\n"
                                           % (T0 + 46, SID, T0 + 53, SID))
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.claude_home), CODEX_HOME=str(self.codex_home))

    def run(self, *args, check=True):
        r = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, env=self.env)
        if check and r.returncode != 0:
            raise AssertionError("retro.py %s failed (%d): %s%s" % (args, r.returncode, r.stdout, r.stderr))
        return r

    def distill_dir(self):
        return self.repo / ".ybase" / "retro" / "distill"

    def record(self, harness, sid):
        return json.loads((self.distill_dir() / ("%s-%s.json" % (harness, sid))).read_text())


class Distill(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.tmp.cleanup)

    def test_scope_is_an_exact_directory_match_over_the_checkout_and_its_worktrees(self):
        out = self.f.run("distill", "--repo", str(self.f.repo)).stdout
        names = sorted(p.name for p in self.f.distill_dir().iterdir())
        self.assertEqual(names, sorted(["claude-%s.json" % SID, "claude-%s.json" % SID_WT, "codex-%s.json" % CID]))
        self.assertNotIn(SID_DECOY, out, "a sibling directory that shares the name prefix is out of scope")
        self.assertIn("distilled: 3 written", out)

    def test_claude_record_carries_line_numbers_tokens_and_the_load_join(self):
        self.f.run("distill", "--repo", str(self.f.repo))
        s, e = self.f.record("claude", SID), self.f.claude_expected
        for k in ("turns", "corrections", "interrupts", "errors", "calls", "tokens"):
            self.assertEqual(s[k], e[k], k)
        self.assertEqual(s["cwd"], str(self.f.repo))
        self.assertEqual(s["branch"], "main")
        self.assertFalse(s["closed"])
        self.assertEqual((s["started_at"], s["ended_at"]), (ts(0), ts(54)))
        self.assertEqual([(w["tool"], w["line"], w["call_line"], w["s"]) for w in s["waits"]], [("Bash", 5, 3, 45.0)])
        self.assertEqual(s["waits"][0]["load_per_core"], 2.0)
        self.assertEqual(s["load"], {"samples": 2, "joined": 1, "under_load": 1, "load_per_core_max": 2.0})

    def test_a_session_without_load_samples_reads_not_measured(self):
        self.f.run("distill", "--repo", str(self.f.repo))
        self.assertIsNone(self.f.record("claude", SID_WT)["load"])

    def test_codex_record(self):
        self.f.run("distill", "--repo", str(self.f.repo))
        s, e = self.f.record("codex", CID), self.f.codex_expected
        for k in ("turns", "corrections", "interrupts", "errors", "calls", "tokens"):
            self.assertEqual(s[k], e[k], k)
        self.assertEqual([(w["tool"], w["s"]) for w in s["waits"]], [("exec", 40.0)])
        self.assertIsNone(s["load"], "Codex has no load hook")

    def test_window_by_mtime(self):
        old = time.time() - 30 * 86400
        os.utime(self.f.codex_path, (old, old))
        self.f.run("distill", "--repo", str(self.f.repo))
        self.assertFalse((self.f.distill_dir() / ("codex-%s.json" % CID)).exists())
        self.f.run("distill", "--repo", str(self.f.repo), "--days", "60")
        self.assertTrue((self.f.distill_dir() / ("codex-%s.json" % CID)).exists())

    def test_only_and_closed(self):
        old = time.time() - 30 * 86400
        os.utime(self.f.claude_path, (old, old))
        out = self.f.run("distill", "--repo", str(self.f.repo), "--only", str(self.f.claude_path), "--closed").stdout
        self.assertIn("1 written", out)
        self.assertTrue(self.f.record("claude", SID)["closed"])
        # A later window run keeps `closed` while the transcript is unchanged.
        self.f.run("distill", "--repo", str(self.f.repo), "--days", "60")
        self.assertTrue(self.f.record("claude", SID)["closed"])
        # --only on an out-of-scope transcript says so and writes nothing.
        decoy = self.f.claude_home / "projects" / "-decoy" / (SID_DECOY + ".jsonl")
        out = self.f.run("distill", "--repo", str(self.f.repo), "--only", str(decoy), "--closed").stdout
        self.assertIn("outside this checkout", out)
        self.assertFalse((self.f.distill_dir() / ("claude-%s.json" % SID_DECOY)).exists())

    def test_prefix_adds_a_directory_to_the_scope(self):
        self.f.run("distill", "--repo", str(self.f.repo), "--prefix", str(self.f.decoy))
        self.assertTrue((self.f.distill_dir() / ("claude-%s.json" % SID_DECOY)).exists())

    def test_refuses_an_out_directory_git_would_track(self):
        tracked = self.f.repo / "notes" / "distill"
        r = self.f.run("distill", "--repo", str(self.f.repo), "--out", str(tracked), check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("refusing", r.stderr)
        self.assertFalse(tracked.exists())
        self.assertFalse(list((self.f.repo / ".ybase" / "retro").glob("distill/*")))

    def test_accepts_an_ignored_out_directory_and_one_outside_any_repo(self):
        other = self.f.repo / ".ybase" / "elsewhere"
        self.f.run("distill", "--repo", str(self.f.repo), "--out", str(other))
        self.assertTrue((other / ("claude-%s.json" % SID)).exists())
        spool = Path(self.f.tmp.name) / "spool"
        self.f.run("distill", "--repo", str(self.f.repo), "--out", str(spool))
        self.assertTrue((spool / ("codex-%s.json" % CID)).exists())


class Turns(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.tmp.cleanup)

    def test_claude_turns(self):
        out = self.f.run("turns", str(self.f.claude_path), "--chars", "12").stdout
        rows = [json.loads(line) for line in out.splitlines()]
        self.assertEqual([r["line"] for r in rows], [2, 10, 13])
        self.assertEqual([r["correction_label"] for r in rows], [None, "no", None])
        self.assertEqual([r["after_interruption"] for r in rows], [False, True, False])
        self.assertEqual(rows[0]["ts"], ts(0))
        self.assertTrue(all(len(r["text"]) <= 12 for r in rows))

    def test_codex_turns(self):
        rows = [json.loads(line) for line in self.f.run("turns", str(self.f.codex_path)).stdout.splitlines()]
        self.assertEqual([(r["line"], r["correction_label"]) for r in rows], [(2, None), (7, "stop")])


class RankSpanCovered(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.addCleanup(self.f.tmp.cleanup)
        self.f.run("distill", "--repo", str(self.f.repo))

    def test_rank_skips_examined_sessions_and_labels_the_weights(self):
        out = self.f.run("rank", "--repo", str(self.f.repo), "--top", "5").stdout
        self.assertIn("weights [A]", out)
        self.assertIn("3 unexamined", out)
        self.assertIn("score 6 = 3*1 + 2*1 + min(1, 20)", out)
        inbox = self.f.repo / ".ybase" / "retro" / "inbox"
        inbox.mkdir(parents=True)
        (inbox / "2026-01-03-1.md").write_text("# run\n\n## Sessions examined\n\n```\nclaude:%s\ncodex:%s\n```\n" % (SID, CID))
        out = self.f.run("rank", "--repo", str(self.f.repo)).stdout
        self.assertIn("1 unexamined", out)
        self.assertIn('"examined": 2', out)
        self.assertIn(SID_WT, out)
        self.assertNotIn(CID, out)

    def test_rank_skips_a_record_whose_transcript_is_gone(self):
        self.f.codex_path.unlink()
        out = self.f.run("rank", "--repo", str(self.f.repo)).stdout
        self.assertIn('"gone": 1', out)
        self.assertNotIn(CID, out)

    def test_span_prints_the_requested_lines_and_names_a_missing_span(self):
        out = self.f.run("span", str(self.f.claude_path), "2", "3", "10", "10", "900", "901", "--chars", "60").stdout
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("L2 user: please clean up"), lines[0])
        self.assertTrue(lines[1].startswith("L3 assistant: [call Bash]"), lines[1])
        self.assertTrue(lines[2].startswith("L10 user: no, not that directory"), lines[2])
        self.assertEqual(lines[3], "L900-L901: no such lines")
        self.assertEqual(len(lines), 4)

    def test_span_refuses_an_odd_number_of_bounds(self):
        r = self.f.run("span", str(self.f.claude_path), "2", check=False)
        self.assertNotEqual(r.returncode, 0)

    def test_covered_lists_trigger_lines_and_numbered_rules_only(self):
        r = self.f.run("covered", "--repo", str(self.f.repo))
        self.assertEqual(r.stdout.splitlines(), [
            "memory/publishing.md: - `a-slug` - when this applies.",
            "docs/rules.md: 1. **Verify before you assert.** Read it.",
            "docs/rules.md: 2. **Label every number.**",
        ])
        self.assertIn("covered: 3 lines", r.stderr)

    def test_paths_reports_the_main_checkout_and_its_worktrees(self):
        out = self.f.run("paths", "--repo", str(self.f.wt)).stdout
        self.assertIn("main: %s" % self.f.repo, out)
        self.assertIn("ignored: yes", out)
        self.assertIn("scope: %s" % self.f.wt, out)


if __name__ == "__main__":
    unittest.main()
