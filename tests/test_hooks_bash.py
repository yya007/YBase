"""Tests for the PreToolUse Bash guards in .claude/hooks/ and tools/hooks_install.py.

Each hook is run as Claude Code runs it: a JSON payload on stdin, the verdict
in the exit status (2 = deny, 0 = allow or advise). Every hook gets at least
one planted violation that must be refused and one near-miss that must pass.
Run: python3 -m unittest discover -s tests
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / ".claude" / "hooks"
sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(ROOT / "tools"))

import filesystem_scan_hook as scan  # noqa: E402
import hooks_install  # noqa: E402


def run_hook(name, payload, env=None, cwd=None):
    """-> (returncode, stdout, stderr) of one hook run on a payload."""
    full_env = dict(os.environ)
    for key in ("SCAN_WIDE", "PGREP_SELF_OK", "WORD_SPLIT_OK", "PR_READY_AUTHORIZED",
                "PYTHON_FLOOR_OK", "CLAUDE_CODE_SHELL"):
        full_env.pop(key, None)
    if env:
        full_env.update(env)
    data = payload if isinstance(payload, str) else json.dumps(payload)
    res = subprocess.run([sys.executable, str(HOOKS / name)], input=data, capture_output=True,
                         text=True, env=full_env, cwd=cwd or str(ROOT), timeout=60)
    return res.returncode, res.stdout, res.stderr


def bash(command, cwd="/tmp", **extra):
    payload = {"session_id": "t", "transcript_path": "/dev/null", "cwd": cwd,
               "hook_event_name": "PreToolUse", "tool_name": "Bash",
               "tool_input": {"command": command}}
    payload.update(extra)
    return payload


def denied(stdout):
    return json.loads(stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


class HookContract(unittest.TestCase):
    """Every hook allows on what it cannot decide, and documents itself."""

    NAMES = ["filesystem_scan_hook.py", "self_matching_pgrep_hook.py", "zsh_word_split_hook.py",
             "pr_draft_hook.py", "git_write_in_pipeline_hook.py", "python_floor_hook.py"]

    def test_malformed_stdin_allows(self):
        for name in self.NAMES:
            for raw in ("", "not json", "[]", '{"tool_name": "Bash"}', '{"tool_name":"Bash","tool_input":"x"}'):
                rc, out, err = run_hook(name, raw)
                self.assertEqual(rc, 0, (name, raw, err))

    def test_other_tools_allow(self):
        for name in self.NAMES:
            rc, _, _ = run_hook(name, {"tool_name": "Write", "tool_input": {"file_path": "/x"}})
            self.assertEqual(rc, 0, name)

    def test_docstring_names_refusal_pass_and_escape(self):
        for name in self.NAMES:
            text = (HOOKS / name).read_text(encoding="utf-8")
            self.assertTrue(text.startswith("#!/usr/bin/env python3\n\"\"\""), name)
            for word in ("PASS", "ESCAPE", "Run by hand"):
                self.assertIn(word, text, (name, word))
            self.assertTrue("REFUSE" in text or "FLAGS" in text, name)
            self.assertNotIn("\u2014", text, name)


class FilesystemScan(unittest.TestCase):
    H = "filesystem_scan_hook.py"

    def deny(self, command, cwd="/tmp", **env):
        rc, out, err = run_hook(self.H, bash(command, cwd), env=env or None)
        self.assertEqual(rc, 2, (command, err))
        self.assertTrue(denied(out))
        self.assertIn("Refused", err)

    def allow(self, command, cwd="/tmp", **env):
        rc, out, err = run_hook(self.H, bash(command, cwd), env=env or None)
        self.assertEqual(rc, 0, (command, err))
        self.assertEqual(out, "")

    def test_refuses_walks_from_broad_roots(self):
        self.deny("find / -name x")
        self.deny("rg -l pattern /home")
        self.deny("grep -r pattern /Users")
        self.deny("fd x /mnt")
        self.deny("du -sh /Volumes")
        self.deny("tree /")
        self.deny("ls -R /")
        self.deny("find $HOME -name '*.py'")
        self.deny("find ~ -name x")
        self.deny("find /home/someone -name x")
        self.deny("find /mnt/data -name x")

    def test_resolves_cd_and_relative_roots(self):
        self.deny("cd / && find . -name x")
        self.deny("rg pattern .", cwd="/")
        self.deny("cd .. && find . -name x", cwd="/home/someone")
        self.deny("bash -c 'find / -name x'")

    def test_passes_bounded_or_narrow_walks(self):
        self.allow("find / -maxdepth 2 -name x")
        self.allow("find / -xdev -name x")
        self.allow("rg --max-depth 3 pattern /")
        self.allow("tree -L 2 /")
        self.allow("find /tmp/project -name x")
        self.allow("rg pattern .", cwd="/tmp/project")
        self.allow("grep pattern /etc/hosts")          # no -r
        self.allow("ls -la /")                         # no -R
        self.allow("du -sh /tmp/project")
        self.allow("find $SOMEWHERE -name x")          # shell builds the root
        self.allow("cd /home/U1/repo && rg x .")
        # A redirect target is not a root, whatever directory it lands in.
        self.allow("rg pattern /tmp/project > /mnt/out.txt")
        self.allow("grep -r pattern /tmp/project 2>/dev/null >> /home/out.txt")
        self.allow("ls -R /tmp/project 2>&1 | tail -3")
        self.deny("find / -name x > /tmp/out.txt")

    def test_maxdepth_above_bound_still_refuses(self):
        self.deny("find / -maxdepth 8 -name x")

    def test_escape_prefix_and_env(self):
        self.allow("SCAN_WIDE=1 find / -name x")
        self.allow("find / -name x", SCAN_WIDE="1")

    def test_glob_and_grep_tools(self):
        payload = {"tool_name": "Grep", "cwd": "/tmp", "tool_input": {"pattern": "x", "path": "/home"}}
        rc, out, err = run_hook(self.H, payload)
        self.assertEqual(rc, 2, err)
        payload = {"tool_name": "Glob", "cwd": "/tmp", "tool_input": {"pattern": "**/*.py", "path": "/tmp/repo"}}
        rc, _, _ = run_hook(self.H, payload)
        self.assertEqual(rc, 0)
        payload = {"tool_name": "Glob", "cwd": "/", "tool_input": {"pattern": "**/*.py"}}
        rc, _, _ = run_hook(self.H, payload)
        self.assertEqual(rc, 2)

    def test_network_mount_root_from_proc_mounts(self):
        table = scan.parse_proc_mounts(
            "sysfs /sys sysfs rw 0 0\n"
            "/dev/nvme0n1p1 / ext4 rw 0 0\n"
            "fs-1.example.com:/ /net/shared\\040drive nfs4 rw 0 0\n"
            "/dev/nvme1n1 /data ext4 rw 0 0\n")
        self.assertEqual(scan.network_root("/net/shared drive/me/repo", table), "/net/shared drive")
        self.assertIsNone(scan.network_root("/data/repo", table))
        self.assertIsNone(scan.network_root("/net/other", table))
        self.assertEqual(scan.broad_reason("/net/shared drive", net_root="/net/shared drive"),
                         "the root of the network mount this session works on")
        self.assertIsNone(scan.broad_reason("/net/shared drive/me/repo", net_root="/net/shared drive"))

    def test_network_mount_root_from_bsd_mount_output(self):
        table = scan.parse_mount_output(
            "/dev/disk3s1 on / (apfs, local, journaled)\n"
            "//user@server/share on /Volumes/share (smbfs, nodev, nosuid)\n"
            "map auto_home on /System/Volumes/Data/home (autofs, automounted)\n")
        self.assertEqual(scan.network_root("/Volumes/share/x", table), "/Volumes/share")
        self.assertIsNone(scan.network_root("/Users/me", table))

    def test_broad_reasons(self):
        self.assertEqual(scan.broad_reason("/", home="/h/me"), "the whole machine")
        self.assertIsNotNone(scan.broad_reason("/h/me", home="/h/me"))
        self.assertIsNotNone(scan.broad_reason("/Users/me", home="/h/x"))
        self.assertIsNotNone(scan.broad_reason("/Volumes/ext", home="/h/x"))
        self.assertIsNone(scan.broad_reason("/Users/U1/repo", home="/h/x"))
        self.assertIsNone(scan.broad_reason("/opt/venv", home="/h/x"))


class SelfMatchingPgrep(unittest.TestCase):
    H = "self_matching_pgrep_hook.py"

    def test_refuses_self_matching_waiter_and_kill(self):
        for command in ("until ! pgrep -f train.py; do sleep 20; done",
                        "pkill -f 'run_eval --job 7'",
                        "pgrep -u someone -f train.py",
                        "sudo pkill --full train.py",
                        "sleep 1; pgrep -fl train.py"):
            rc, out, err = run_hook(self.H, bash(command))
            self.assertEqual(rc, 2, (command, err))
            self.assertTrue(denied(out))
            self.assertIn("[t]rain" if "train" in command else "[r]un", err)

    def test_passes_bracketed_name_match_and_expansions(self):
        for command in ("pgrep -f '[t]rain.py'",
                        "pgrep train",                       # no -f: name match
                        "pgrep -f \"$PATTERN\"",             # shell builds it
                        "pgrep -f 'tra[i]n.py' | xargs kill"):
            rc, out, err = run_hook(self.H, bash(command))
            self.assertEqual(rc, 0, (command, err))
        rc, _, _ = run_hook(self.H, bash("pgrep -f 'train.py'; echo other"))
        self.assertEqual(rc, 2, "quoting does not help: the literal pattern is still in the command")

    def test_pattern_only_as_argument_elsewhere_is_not_a_matcher(self):
        rc, _, _ = run_hook(self.H, bash("grep pgrep notes.md; echo 'pgrep -f x'"))
        self.assertEqual(rc, 0)

    def test_escape(self):
        rc, _, _ = run_hook(self.H, bash("PGREP_SELF_OK=1 pgrep -f train.py"))
        self.assertEqual(rc, 0)
        rc, _, _ = run_hook(self.H, bash("pgrep -f train.py"), env={"PGREP_SELF_OK": "1"})
        self.assertEqual(rc, 0)


class ZshWordSplit(unittest.TestCase):
    H = "zsh_word_split_hook.py"
    ZSH = {"CLAUDE_CODE_SHELL": "/bin/zsh"}

    def test_refuses_bare_parameter_in_for_list_and_set(self):
        for command in ("for f in $FILES; do echo $f; done",
                        "FILES=\"a b\"\nfor f in ${FILES}; do echo $f; done",
                        "set -- $SPEC; echo $1",
                        "cd /tmp && for f in $FILES; do echo $f; done"):
            rc, out, err = run_hook(self.H, bash(command), env=self.ZSH)
            self.assertEqual(rc, 2, (command, err))
            self.assertTrue(denied(out))
            self.assertIn("${=", err)

    def test_passes_split_forms_arrays_and_quoted(self):
        for command in ("for f in ${=FILES}; do echo $f; done",
                        "for f in ${(f)FILES}; do echo $f; done",
                        "for f in \"${arr[@]}\"; do echo $f; done",
                        "for f in $(ls); do echo $f; done",
                        "for f in \"$FILE\"; do echo $f; done",
                        "for f in a b c; do echo $f; done",
                        "set -- \"$ONE\"; echo $1",
                        "echo \"for f in $FILES\"",
                        "bash -c 'for f in $FILES; do echo $f; done'",
                        "cat <<'EOF'\nfor f in $FILES; do echo $f; done\nEOF\n"):
            rc, _, err = run_hook(self.H, bash(command), env=self.ZSH)
            self.assertEqual(rc, 0, (command, err))

    def test_only_fires_under_zsh(self):
        command = "for f in $FILES; do echo $f; done"
        rc, _, _ = run_hook(self.H, bash(command), env={"CLAUDE_CODE_SHELL": "/bin/bash"})
        self.assertEqual(rc, 0)
        rc, _, _ = run_hook(self.H, bash(command), env={"CLAUDE_CODE_SHELL": "/bin/bash", "SHELL": "/bin/zsh"})
        self.assertEqual(rc, 0, "CLAUDE_CODE_SHELL wins over SHELL")
        rc, _, _ = run_hook(self.H, bash(command), env={"SHELL": "/usr/bin/zsh"})
        self.assertEqual(rc, 2)
        rc, _, _ = run_hook(self.H, bash(command), env={"SHELL": ""})
        self.assertEqual(rc, 0)

    def test_escape(self):
        rc, _, _ = run_hook(self.H, bash("WORD_SPLIT_OK=1 for f in $FILES; do echo $f; done"), env=self.ZSH)
        self.assertEqual(rc, 0)


class PrDraft(unittest.TestCase):
    H = "pr_draft_hook.py"
    ON = {"YBASE_GUARD_PR_DRAFT": "1"}

    def try_command(self, command, env=None):
        return run_hook(self.H, bash(command), env={**self.ON, **(env or {})})

    def test_refuses_ready_for_review_forms(self):
        for command in ("gh pr create --title t --body b",
                        "gh pr create --draft=false --fill",
                        "git push -u origin x && gh pr create --fill",
                        "gh pr ready 12",
                        "gh api graphql -f query='mutation { markPullRequestReadyForReview(input: {pullRequestId: \"x\"}) { clientMutationId } }'",
                        "gh api -X PATCH repos/o/r/pulls/12 -F draft=false",
                        "gh -R o/r pr create --fill",
                        "gh --repo o/r pr ready 12",
                        "gh pr create -t t -b '-d'"):        # the -d is the body, not the flag
            rc, out, err = self.try_command(command)
            self.assertEqual(rc, 2, (command, err))
            self.assertTrue(denied(out))
            self.assertIn("draft", err)

    def test_passes_draft_and_reads(self):
        for command in ("gh pr create --draft --title t --body b",
                        "gh pr create --fill --draft=true",
                        "gh pr create -d -t t -b b",
                        "gh pr create -dt t -b b",
                        "gh -R o/r pr create -d --fill",
                        "gh pr ready --undo 12",
                        "gh pr view 12 --json isDraft",
                        "gh pr list",
                        "gh api repos/o/r/pulls/12",
                        "gh api graphql -f query='{ repository(owner:\"o\", name:\"r\") { id } }'",
                        "echo 'gh pr create'",
                        "gh $SUB create"):
            rc, _, err = self.try_command(command)
            self.assertEqual(rc, 0, (command, err))

    def test_escape(self):
        rc, _, _ = self.try_command("PR_READY_AUTHORIZED=1 gh pr ready 12")
        self.assertEqual(rc, 0)
        rc, _, _ = self.try_command("gh pr ready 12", env={"PR_READY_AUTHORIZED": "1"})
        self.assertEqual(rc, 0)

    def test_pr_draft_guard_is_off_by_default(self):
        """Run from a temporary YBase with no `.env`: the real checkout's settings do not count."""
        with tempfile.TemporaryDirectory() as t:
            home = Path(t).resolve()
            for rel in (".claude/hooks/pr_draft_hook.py", "tools/envfile.py"):
                (home / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / rel, home / rel)
            hook = home / ".claude" / "hooks" / "pr_draft_hook.py"
            clean = {k: v for k, v in os.environ.items() if not k.startswith("YBASE_")}
            payload = json.dumps(bash("gh pr create --title t --body b"))

            def run(extra=None):
                return subprocess.run([sys.executable, str(hook)], input=payload, capture_output=True,
                                      text=True, env={**clean, **(extra or {})}, cwd=t, timeout=60)

            off = run()
            self.assertEqual((off.returncode, off.stdout), (0, ""), off.stderr)
            (home / ".env").write_text("YBASE_GUARD_PR_DRAFT=1\n", encoding="utf-8")
            self.assertEqual(run().returncode, 2)
            (home / ".env").unlink()
            self.assertEqual(run({"YBASE_GUARD_PR_DRAFT": "1"}).returncode, 2)
            shutil.rmtree(home / "tools")  # cannot find out: allows
            self.assertEqual(run({"YBASE_GUARD_PR_DRAFT": "1"}).returncode, 0)


class GitWriteInPipeline(unittest.TestCase):
    H = "git_write_in_pipeline_hook.py"

    def advice(self, command):
        rc, out, err = run_hook(self.H, bash(command))
        self.assertEqual(rc, 0, (command, err))
        if not out:
            return None
        data = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(data["hookEventName"], "PreToolUse")
        self.assertNotIn("permissionDecision", data)
        return data["additionalContext"]

    def test_advises_on_write_upstream_of_pipe(self):
        for command, call in (("git push origin x 2>&1 | tail -1", "git push"),
                              ("git commit -m msg | cat", "git commit"),
                              ("TMPDIR=/tmp git merge --ff-only x 2>&1 | tail -5", "git merge"),
                              ("git -C /tmp/repo add -A | head", "git add"),
                              ("git worktree remove ../wt 2>&1 | tail -3", "git worktree remove"),
                              ("git branch -d topic | cat", "git branch -d"),
                              ("gh pr create --draft --fill 2>&1 | tail -1", "gh pr create"),
                              ("gh pr merge 12 --squash | cat", "gh pr merge")):
            text = self.advice(command)
            self.assertIsNotNone(text, command)
            self.assertIn("upstream of a pipe", text)
            self.assertIn("`%s`" % call, text)

    def test_advises_on_trailing_reporter(self):
        for command, reporter in (("git push origin x > log 2>&1; tail -1 log", "tail"),
                                  ("git commit -qm msg\necho committed", "echo"),
                                  ("git rebase origin/main; echo rebased; true", "true")):
            text = self.advice(command)
            self.assertIsNotNone(text, command)
            self.assertIn("runs last", text)
            self.assertIn("exit status of the whole call is %s's" % reporter, text)

    def test_quiet_on_reads_and_held_status(self):
        for command in ("git log --oneline | head -3",
                        "git branch | grep topic",
                        "git worktree list | cat",
                        "git stash list | wc -l",
                        "gh pr view 12 | cat",
                        "git push origin x",
                        "git push origin x && echo pushed",
                        "git push origin x || echo failed",
                        "git push origin x > log; rc=$?; tail -1 log; exit $rc",
                        "echo 'git push | tail'",
                        "git push origin x; grep -q error log",
                        "tail -1 log | git commit -F -"):
            self.assertIsNone(self.advice(command), command)


class PythonFloor(unittest.TestCase):
    H = "python_floor_hook.py"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proj = Path(self.tmp.name) / "proj"
        (self.proj / "tests").mkdir(parents=True)
        (self.proj / "tests" / "test_x.py").write_text("def test_x(): pass\n", encoding="utf-8")
        (self.proj / "run.py").write_text("print(1)\n", encoding="utf-8")
        self.bin = Path(self.tmp.name) / "bin"
        self.bin.mkdir()
        self.shim(self.bin / "python3", "3.7.9")
        # Only what pick_python.sh needs, so no real interpreter leaks in from PATH.
        sysbin = Path(self.tmp.name) / "sysbin"
        sysbin.mkdir()
        for tool in ("bash", "sed", "head", "dirname"):
            os.symlink(shutil.which(tool), sysbin / tool)
        self.env = {"PATH": "%s:%s" % (self.bin, sysbin)}

    def tearDown(self):
        self.tmp.cleanup()

    def shim(self, path, version):
        path.write_text("#!/bin/sh\necho 'Python %s'\n" % version, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def floor(self, text):
        (self.proj / "pyproject.toml").write_text(text, encoding="utf-8")

    def run_cmd(self, command, cwd=None, env=None):
        full = dict(self.env)
        full.update(env or {})
        return run_hook(self.H, bash(command, cwd or str(self.proj)), env=full)

    def test_refuses_interpreter_below_floor(self):
        self.floor('[project]\nname = "x"\nrequires-python = ">=3.9,<4"\n')
        for command in ("python3 -m pytest tests", "python3 -m unittest discover",
                        "python3 -c 'import x'", "python3 run.py", "cd proj && python3 -m pytest"):
            cwd = str(self.proj.parent) if command.startswith("cd ") else None
            rc, out, err = self.run_cmd(command, cwd=cwd)
            self.assertEqual(rc, 2, (command, err))
            self.assertTrue(denied(out))
            self.assertIn("Python 3.7", err)
            self.assertIn(">= 3.9", err)
            self.assertIn("pick_python.sh", err)

    def test_names_an_interpreter_that_meets_the_floor(self):
        self.floor('requires-python = ">=3.9"\n')
        self.shim(self.bin / "python3.12", "3.12.1")
        rc, _, err = self.run_cmd("python3 -m pytest")
        self.assertEqual(rc, 2, err)
        self.assertIn(str(self.bin / "python3.12"), err)

    def test_passes_when_floor_met_or_unknown(self):
        self.floor('requires-python = ">=3.9"\n')
        self.shim(self.bin / "python3", "3.9.0")
        rc, _, err = self.run_cmd("python3 -m pytest tests")
        self.assertEqual(rc, 0, err)
        self.shim(self.bin / "python3", "3.7.9")
        self.floor('requires-python = "~=3.9"\n')          # no >= bound: uncertain
        self.assertEqual(self.run_cmd("python3 -m pytest")[0], 0)
        (self.proj / "pyproject.toml").unlink()             # no project at all
        self.assertEqual(self.run_cmd("python3 -m pytest")[0], 0)

    def test_passes_commands_that_run_no_project_code(self):
        self.floor('requires-python = ">=3.9"\n')
        for command in ("python3 --version", "python3 -m venv .venv", "python3 -m pip install x",
                        "echo python3 -m pytest", "pytest tests", "python3 $SCRIPT"):
            rc, _, err = self.run_cmd(command)
            self.assertEqual(rc, 0, (command, err))
        rc, _, _ = self.run_cmd("cd $DIR && python3 -m pytest")
        self.assertEqual(rc, 0, "a cd the shell builds is undecidable")

    def test_escape(self):
        self.floor('requires-python = ">=3.9"\n')
        self.assertEqual(self.run_cmd("PYTHON_FLOOR_OK=1 python3 -m pytest")[0], 0)
        self.assertEqual(self.run_cmd("python3 -m pytest", env={"PYTHON_FLOOR_OK": "1"})[0], 0)


class HooksInstall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name) / "cfg"
        self.settings = self.cfg / "settings.json"
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.cfg))

    def tearDown(self):
        self.tmp.cleanup()

    def run_install(self, *args):
        res = subprocess.run([sys.executable, str(ROOT / "tools" / "hooks_install.py"), "install-user", *args],
                             capture_output=True, text=True, env=self.env, timeout=60)
        return res.returncode, res.stdout.splitlines(), res.stderr

    def names(self):
        return [n for n, _ in hooks_install.BLOCKING_HOOKS]

    def test_dry_run_writes_nothing(self):
        rc, lines, _ = self.run_install("--dry-run")
        self.assertEqual(rc, 0)
        self.assertEqual(lines, ["add %s" % n for n in self.names()])
        self.assertFalse(self.settings.exists())

    def test_install_is_idempotent_and_keeps_other_settings(self):
        self.cfg.mkdir()
        other_hook = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo mine"}]}
        self.settings.write_text(json.dumps({
            "model": "opus", "permissions": {"allow": ["Bash(ls:*)"]},
            "hooks": {"PreToolUse": [other_hook], "Stop": [{"hooks": [{"type": "command", "command": "x"}]}]},
        }), encoding="utf-8")
        rc, lines, _ = self.run_install()
        self.assertEqual(rc, 0)
        self.assertEqual(lines, ["add %s" % n for n in self.names()])
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(data["model"], "opus")
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls:*)"]})
        self.assertEqual(data["hooks"]["Stop"], [{"hooks": [{"type": "command", "command": "x"}]}])
        self.assertEqual(data["hooks"]["PreToolUse"][0], other_hook)
        self.assertEqual(len(data["hooks"]["PreToolUse"]), 1 + len(self.names()))
        for group in data["hooks"]["PreToolUse"][1:]:
            cmd = group["hooks"][0]["command"]
            self.assertIn('$CLAUDE_PROJECT_DIR/.claude/hooks/', cmd)
            self.assertIn(str(HOOKS), cmd)
            self.assertTrue(cmd.endswith('[ $? = 2 ] && exit 2; exit 0'))
        scan_group = [g for g in data["hooks"]["PreToolUse"] if "filesystem_scan" in g["hooks"][0]["command"]][0]
        self.assertEqual(scan_group["matcher"], "Bash|Glob|Grep")
        # Second run: everything ok, file unchanged.
        before = self.settings.read_text(encoding="utf-8")
        rc, lines, _ = self.run_install()
        self.assertEqual(lines, ["ok %s" % n for n in self.names()])
        self.assertEqual(self.settings.read_text(encoding="utf-8"), before)

    def test_update_replaces_a_stale_entry_in_place(self):
        settings = {}
        hooks_install.apply(settings)
        group = settings["hooks"]["PreToolUse"][1]
        group["hooks"][0]["command"] = group["hooks"][0]["command"].replace(str(ROOT), "/old/clone")
        actions = hooks_install.apply(settings)
        self.assertEqual([a for a, _ in actions], ["ok", "update"] + ["ok"] * (len(self.names()) - 2))
        self.assertEqual(len(settings["hooks"]["PreToolUse"]), len(self.names()))
        self.assertIn(str(ROOT), settings["hooks"]["PreToolUse"][1]["hooks"][0]["command"])

    def test_the_leak_guard_follows_a_session_started_outside_ybase(self):
        self.assertIn("leak_hook.py", self.names())
        settings = {}
        hooks_install.apply(settings)
        cmd = [g for g in settings["hooks"]["PreToolUse"]
               if "leak_hook" in g["hooks"][0]["command"]][0]["hooks"][0]["command"]
        home_path = "/Us" + "ers/someone/notes.txt"
        payload = json.dumps(bash("git commit --allow-empty -m 'see %s'" % home_path))
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.tmp.name)
        env.pop("LEAK_AUTHORIZED", None)
        res = subprocess.run(["bash", "-c", cmd], input=payload, capture_output=True, text=True,
                             env=env, cwd=self.tmp.name, timeout=60)
        self.assertEqual(res.returncode, 2, res.stderr)

    def test_remove_leaves_only_what_was_there(self):
        self.cfg.mkdir()
        self.settings.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
        self.run_install()
        rc, lines, _ = self.run_install("--remove")
        self.assertEqual(rc, 0)
        self.assertEqual(lines, ["remove %s" % n for n in self.names()])
        self.assertEqual(json.loads(self.settings.read_text(encoding="utf-8")), {"theme": "dark"})
        rc, lines, _ = self.run_install("--remove")
        self.assertEqual(lines, ["ok %s" % n for n in self.names()])

    def test_installed_command_passes_deny_through_and_defers_to_project_copy(self):
        settings = {}
        hooks_install.apply(settings)
        cmd = [g for g in settings["hooks"]["PreToolUse"]
               if "pr_draft_hook" in g["hooks"][0]["command"]][0]["hooks"][0]["command"]
        payload = json.dumps(bash("gh pr create --fill"))
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.tmp.name, YBASE_GUARD_PR_DRAFT="1")
        env.pop("PR_READY_AUTHORIZED", None)
        res = subprocess.run(["bash", "-c", cmd], input=payload, capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertTrue(denied(res.stdout))
        env["CLAUDE_PROJECT_DIR"] = str(ROOT)  # the project has its own copy: defer
        res = subprocess.run(["bash", "-c", cmd], input=payload, capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout, "")

    def test_unparseable_settings_are_never_overwritten(self):
        self.cfg.mkdir()
        self.settings.write_text("{not json", encoding="utf-8")
        rc, _, err = self.run_install()
        self.assertEqual(rc, 1)
        self.assertIn("nothing written", err)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), "{not json")

    def test_cli_dispatch(self):
        res = subprocess.run(["bash", str(ROOT / "bin" / "ybase"), "hooks", "install-user", "--dry-run"],
                             capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("add filesystem_scan_hook.py", res.stdout)
        self.assertIn("hooks install-user", subprocess.run(
            ["bash", str(ROOT / "bin" / "ybase"), "help"], capture_output=True, text=True).stdout)


if __name__ == "__main__":
    unittest.main()
