"""Tests for the write-side hooks: readonly_checkout, moment_law, leak and
writing_style, plus the shape of .claude/settings.json. Each hook is fed a
payload on stdin through subprocess, with at least one planted violation that
must be refused and one near-miss that must pass.
Run: python3 -m unittest discover -s tests"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / ".claude" / "hooks"
sys.path.insert(0, str(ROOT / "tools"))
EM_DASH = chr(0x2014)  # spelled out so this file carries no em dash of its own


def run_hook(path, payload, env=None, cwd=None):
    """Run a hook the way the harness does: the payload as JSON on stdin."""
    full = dict(os.environ)
    for k in ("MAIN_CHECKOUT_WRITE", "LAW_SKIP", "LEAK_AUTHORIZED", "WRITING_STYLE_SKIP", "LAW_ACK_DIR"):
        full.pop(k, None)
    full.update(env or {})
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, str(path)], input=data, capture_output=True, text=True,
                          env=full, cwd=cwd, timeout=60)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


def git_repo(root):
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "config", "commit.gpgsign", "false")


def write(root, rel, text=""):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def denied(res):
    """A denial is exit 2, the reason on stderr and the deny decision on stdout."""
    if res.returncode != 2:
        return False
    out = json.loads(res.stdout)["hookSpecificOutput"]
    return out["permissionDecision"] == "deny" and bool(res.stderr.strip())


# ------------------------------------------------------------ readonly_checkout
class ReadonlyCheckout(unittest.TestCase):
    """The hook runs from a temporary copy of YBase (it finds YBase from its own
    file location), so the real checkout's `.env` never decides these tests."""
    ON = {"YBASE_GUARD_READONLY_CHECKOUT": "1"}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
        self.home = self.root / "YBase"
        for rel in (".claude/hooks/readonly_checkout_hook.py", "tools/envfile.py", "tools/repos.py"):
            (self.home / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, self.home / rel)
        git_repo(self.home)
        self.HOOK = self.home / ".claude" / "hooks" / "readonly_checkout_hook.py"

    def hook(self, payload, env=None, cwd=None):
        full = {k: "" for k in os.environ if k.startswith("YBASE_")}
        full.update(env or {})
        return run_hook(self.HOOK, payload, env=full, cwd=cwd)

    def managed_repo(self, name="other", listed=True):
        d = self.root / name
        d.mkdir()
        git_repo(d)
        if listed:
            write(self.home, "kb/repos.md",
                  f"| Name | What it is | Remote | Hint |\n|---|---|---|---|\n| {name} | x | | |\n")
        return d

    def payload(self, path, tool="Write", cwd=None):
        return {"session_id": "s", "tool_name": tool, "cwd": cwd or str(self.root),
                "tool_input": {"file_path": str(path), "content": "x"}}

    def test_readonly_guard_is_off_by_default(self):
        self.assertEqual(self.hook(self.payload(self.home / "docs" / "x.md")).returncode, 0)
        d = self.managed_repo()
        res = self.hook(self.payload(d / "x.md"))
        self.assertEqual((res.returncode, res.stdout), (0, ""))
        # Any value but exactly 1 leaves it off.
        self.assertEqual(self.hook(self.payload(self.home / "x.md"),
                                   env={"YBASE_GUARD_READONLY_CHECKOUT": "true"}).returncode, 0)

    def test_readonly_guard_on_blocks_ybase_main_checkout(self):
        res = self.hook(self.payload(self.home / "docs" / "x.md"), env=self.ON)
        self.assertTrue(denied(res), res)
        self.assertIn("ybase wt <name>", res.stderr)
        self.assertIn("ybase wt", json.loads(res.stdout)["hookSpecificOutput"]["permissionDecisionReason"])

    def test_switch_in_env_file_turns_it_on(self):
        write(self.home, ".env", "YBASE_GUARD_READONLY_CHECKOUT=1\n")
        self.assertTrue(denied(self.hook(self.payload(self.home / "docs" / "x.md"))))

    def test_readonly_guard_on_blocks_managed_repo_main_checkout(self):
        d = self.managed_repo()
        res = self.hook(self.payload(d / "src" / "x.py"), env=self.ON, cwd=str(d))
        self.assertTrue(denied(res), res)
        self.assertIn("ybase wt <name> --repo other", res.stderr)
        # An unlisted repository is not protected.
        stranger = self.managed_repo("stranger", listed=False)
        self.assertEqual(self.hook(self.payload(stranger / "x.py"), env=self.ON).returncode, 0)

    def test_readonly_guard_on_blocks_each_write_tool(self):
        for tool in ("Edit", "MultiEdit", "NotebookEdit"):
            self.assertTrue(denied(self.hook(self.payload(self.home / "README.md", tool), env=self.ON)), tool)

    def test_resolves_a_relative_path_against_cwd(self):
        res = self.hook(self.payload("docs/x.md", cwd=str(self.home)), env=self.ON)
        self.assertTrue(denied(res), res)

    def test_readonly_guard_on_allows_kb_and_env(self):
        for rel in (".ybase/MACHINE.md", ".ybase/retro/inbox/x.md", "tmp/scratch.txt",
                    "kb/notes/x.md", "kb/repos.md", ".env"):
            res = self.hook(self.payload(self.home / rel), env=self.ON)
            self.assertEqual(res.returncode, 0, (rel, res.stderr))
            self.assertEqual(res.stdout, "")
        self.assertTrue(denied(self.hook(self.payload(self.home / "docs" / ".env"), env=self.ON)))

    def test_readonly_guard_allows_when_env_file_unreadable(self):
        (self.home / ".env").mkdir()  # a directory where the file should be: unreadable as a file
        res = self.hook(self.payload(self.home / "docs" / "x.md"))
        self.assertEqual((res.returncode, res.stdout), (0, ""))

    def test_allows_when_the_support_modules_are_missing(self):
        (self.home / "tools" / "envfile.py").unlink()
        res = self.hook(self.payload(self.home / "docs" / "x.md"), env=self.ON)
        self.assertEqual(res.returncode, 0)
        self.assertIn("allowed without checking", res.stderr)

    def test_allows_a_linked_worktree(self):
        git(self.home, "add", ".")
        git(self.home, "commit", "-q", "-m", "init")
        wt = self.root / "wt"
        git(self.home, "worktree", "add", "-q", str(wt), "-b", "wt/x")
        self.assertTrue((wt / ".git").is_file())
        res = self.hook(self.payload(wt / "docs" / "x.md"), env=self.ON)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_a_hook_run_from_a_worktree_still_protects_the_main_checkout(self):
        write(self.home, ".env", "YBASE_GUARD_READONLY_CHECKOUT=1\n")
        git(self.home, "add", ".")
        git(self.home, "commit", "-q", "-m", "init")
        wt = self.root / "wt"
        git(self.home, "worktree", "add", "-q", str(wt), "-b", "wt/x")
        hook = wt / ".claude" / "hooks" / "readonly_checkout_hook.py"
        env = {k: "" for k in os.environ if k.startswith("YBASE_")}
        self.assertTrue(denied(run_hook(hook, self.payload(self.home / "docs" / "x.md"), env=env)))
        self.assertEqual(run_hook(hook, self.payload(wt / "docs" / "x.md"), env=env).returncode, 0)

    def test_allows_a_path_outside_git(self):
        self.assertEqual(self.hook(self.payload(self.root / "loose.md"), env=self.ON).returncode, 0)

    def test_allows_other_tools(self):
        self.assertEqual(self.hook(self.payload(self.home / "x.md", tool="Read"), env=self.ON).returncode, 0)

    def test_escape(self):
        res = self.hook(self.payload(self.home / "x.md"), env={**self.ON, "MAIN_CHECKOUT_WRITE": "1"})
        self.assertEqual(res.returncode, 0)

    def test_malformed_stdin_allows(self):
        self.assertEqual(self.hook("not json", env=self.ON).returncode, 0)
        self.assertEqual(self.hook('{"tool_name": "Write", "tool_input": "oops"}', env=self.ON).returncode, 0)


# ------------------------------------------------------------------ moment_law
class MomentLawTable(unittest.TestCase):
    """The table, read in-process: which command or path reaches which moment."""

    @classmethod
    def setUpClass(cls):
        cls.mod = load(HOOKS / "moment_law_hook.py", "moment_law_hook_under_test")

    def bash(self, cmd):
        return self.mod.moment_for("Bash", {"command": cmd}, environ={})

    KBS = [Path("/work/kb"), Path("/work/extra-kb")]

    def path(self, p):
        return self.mod.moment_for("Write", {"file_path": p}, cwd="/work/repo", environ={}, kb_roots=self.KBS)

    def test_commands_reach_their_moment(self):
        cases = {
            "git commit -m 'x'": "commit",
            "FOO=1 git commit -am x": "commit",
            "git push origin HEAD": "push",
            "ls && git push": "push",
            "ls\ngit push": "push",
            "env -u X git push": "push",
            "git worktree add ../x -b y": "worktree",
            "git worktree remove ../x": "worktree",
            "git worktree prune": "worktree",
            "ybase wt feature": "worktree",
            "bin/ybase wt feature": "worktree",
            "./bin/ybase wt feature": "worktree",
            "bash /somewhere/bin/ybase wt feature": "worktree",
            "ybase worktrees --reap": "worktree",
            "gh pr create --draft --title t --body b": "pr",
            "gh pr edit 3 --body x": "pr",
            "gh pr ready 3": "pr",
            "gh pr merge 3": "pr",
            "gh pr close 3": "pr",
            "gh pr review 3 --approve": "review",
            "gh pr comment 3 --body hi": "review",
            "gh api repos/o/r/pulls/3/reviews": "review",
            "gh api -X POST repos/o/r/pulls/3/comments -f body=x": "review",
            "sleep 30": "watch",
            "until test -f done; do sleep 1; done": "watch",
            "while true; do date; done": "watch",
            "wait 1234": "watch",
            "timeout 60 python3 x.py": "watch",
            "tail -f log.txt": "watch",
            "tail -n 20 -f log.txt": "watch",
            "tail --follow log.txt": "watch",
            "watch -n 5 ls": "watch",
        }
        for cmd, want in cases.items():
            self.assertEqual(self.bash(cmd), want, cmd)

    def test_near_misses_reach_nothing(self):
        for cmd in ("echo 'git commit -m x'", "git log --oneline", "git status", "git worktree list",
                    "ybase worktrees", "ybase worktrees --findings", "ybase check",
                    "gh pr view 3", "gh pr list", "gh api repos/o/r/pulls/3", "gh api repos/o/r/issues/3/comments",
                    "tail -n 5 log.txt", "grep sleep x.py", "python3 -c 'import time; time.sleep(1)'",
                    "echo done | tail -n 1", "git commit -m 'unterminated"):
            self.assertIsNone(self.bash(cmd), cmd)

    def test_escape_on_the_line_and_in_the_environment(self):
        self.assertIsNone(self.bash("LAW_SKIP=1 git push"))
        self.assertEqual(self.mod.moment_for("Bash", {"command": "echo LAW_SKIP=1; git push"}, environ={}), "push")
        self.assertIsNone(self.mod.moment_for("Bash", {"command": "git push"}, environ={"LAW_SKIP": "1"}))
        self.assertIsNone(self.mod.moment_for("Agent", {"prompt": "x"}, environ={"LAW_SKIP": "1"}))

    def test_agent_is_the_delegate_moment(self):
        self.assertEqual(self.mod.moment_for("Agent", {"prompt": "do a thing"}, environ={}), "delegate")

    def test_paths_reach_their_moment(self):
        cases = {
            "tools/checks.py": "checks", "tests/test_x.py": "checks", ".githooks/pre-commit": "checks",
            "docs/rules.md": "docs", "docs/law/commit.md": "docs",
        }
        for rel, want in cases.items():
            self.assertEqual(self.path("/work/repo/" + rel), want, rel)
            self.assertEqual(self.path(rel), want, rel)
        for rel in ("README.md", "memory/git.md", "worklog/2026-W01.md", "research/t/analysis/x.md",
                    "cases/c/analysis/x.md", "bin/ybase", "profiles/aws/NOTES.md", "mytools/x.py"):
            self.assertIsNone(self.path("/work/repo/" + rel), rel)
            self.assertIsNone(self.path(rel), rel)
        self.assertIsNone(self.mod.moment_for("Read", {"file_path": "/work/repo/docs/x.md"}, environ={}))

    def test_kb_documents_reach_the_docs_moment(self):
        for p in ("/work/kb/research/topic/analysis/x.md", "/work/kb/memory/git.md",
                  "/work/extra-kb/worklog/2026-W01.md", "/work/kb/research/topic/../topic/README.md"):
            self.assertEqual(self.path(p), "docs", p)
        self.assertEqual(self.mod.moment_for("Write", {"file_path": "../kb/memory/x.md"}, cwd="/work/repo",
                                             environ={}, kb_roots=self.KBS), "docs")
        for p in ("/work/kb/rules.md", "/work/kb/deny.list", "/work/kb/notes/x.md", "/work/kb-other/memory/x.md",
                  "/work/kb/memory"):
            self.assertIsNone(self.path(p), p)
        self.assertIsNone(self.mod.moment_for("Write", {"file_path": "/work/kb/memory/x.md"}, cwd="/work/repo",
                                              environ={}, kb_roots=[]))

    def test_wrapped_and_flagged_commands_reach_their_moments(self):
        cases = {
            "timeout 60 git push": ["push", "watch"],
            "timeout -s KILL 30 git commit -m x": ["commit", "watch"],
            "nohup git commit -m x": ["commit"],
            "sudo -u someone git push origin HEAD": ["push"],
            "nice -n 5 gh pr create --draft": ["pr"],
            "git -C /tmp/elsewhere commit -m x": ["commit"],
            "git --no-pager -c user.name=x push": ["push"],
            "gh -R owner/repo pr create --draft": ["pr"],
            "gh --repo owner/repo api repos/o/r/pulls/3/reviews": ["review"],
            "command -v git": [],
            "timeout 5 ls": ["watch"],
        }
        for cmd, want in cases.items():
            self.assertEqual(self.mod.moments_for("Bash", {"command": cmd}, environ={}), want, cmd)

    def test_every_moment_has_its_law_file_here(self):
        for m in self.mod.moments():
            self.assertTrue((ROOT / "docs" / "law" / (m + ".md")).is_file(), m)


class MomentLawHook(unittest.TestCase):
    """The deny-once flow, through a copy of the hook in a fixture repository."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
        self.hook = self.root / ".claude" / "hooks" / "moment_law_hook.py"
        self.hook.parent.mkdir(parents=True)
        shutil.copy(HOOKS / "moment_law_hook.py", self.hook)
        self.mod = load(self.hook, "moment_law_fixture")
        for m in self.mod.moments():
            if m != "push":  # push.md is left missing on purpose
                write(self.root, f"docs/law/{m}.md", f"# Law: {m}\n\nThe {m} rule body.\n")

    def payload(self, cmd, session="sess-1", tool="Bash"):
        inp = {"command": cmd} if tool == "Bash" else {"file_path": cmd}
        return {"session_id": session, "tool_name": tool, "cwd": str(self.root), "tool_input": inp}

    def test_denies_once_with_the_law_then_passes(self):
        first = run_hook(self.hook, self.payload("git commit -m x"))
        self.assertTrue(denied(first), first)
        self.assertIn("docs/law/commit.md", first.stderr)
        self.assertIn("The commit rule body.", first.stderr)
        self.assertIn("The commit rule body.",
                      json.loads(first.stdout)["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertTrue((self.root / ".ybase" / "law-ack" / "sess-1" / "commit").is_file())
        second = run_hook(self.hook, self.payload("git commit -m y"))
        self.assertEqual(second.returncode, 0, second.stderr)
        # Another moment in the same session, and the same moment in another session, both fire.
        self.assertTrue(denied(run_hook(self.hook, self.payload("gh pr create --draft"))))
        self.assertTrue(denied(run_hook(self.hook, self.payload("git commit -m z", session="sess-2"))))

    def test_two_moments_in_one_command_are_shown_together(self):
        first = run_hook(self.hook, self.payload("timeout 60 git commit -m x"))
        self.assertTrue(denied(first), first)
        self.assertIn("docs/law/commit.md", first.stderr)
        self.assertIn("docs/law/watch.md", first.stderr)
        self.assertIn("The watch rule body.", first.stderr)
        for m in ("commit", "watch"):
            self.assertTrue((self.root / ".ybase" / "law-ack" / "sess-1" / m).is_file(), m)
        self.assertEqual(run_hook(self.hook, self.payload("timeout 60 git commit -m y")).returncode, 0)

    def test_missing_law_file_allows_silently(self):
        res = run_hook(self.hook, self.payload("git push"))
        self.assertEqual((res.returncode, res.stdout), (0, ""))
        self.assertFalse((self.root / ".ybase" / "law-ack" / "sess-1" / "push").exists())

    def test_near_miss_and_escape_pass(self):
        self.assertEqual(run_hook(self.hook, self.payload("echo 'git commit'")).returncode, 0)
        self.assertEqual(run_hook(self.hook, self.payload("LAW_SKIP=1 git commit -m x")).returncode, 0)
        self.assertTrue(denied(run_hook(self.hook, self.payload("git commit -m x"))))

    def test_write_path_and_agent_fire(self):
        res = run_hook(self.hook, self.payload(str(self.root / "tools" / "new.py"), tool="Write"))
        self.assertTrue(denied(res), res)
        self.assertIn("docs/law/checks.md", res.stderr)
        res = run_hook(self.hook, {"session_id": "sess-1", "tool_name": "Agent", "cwd": str(self.root),
                                   "tool_input": {"prompt": "go"}})
        self.assertTrue(denied(res), res)
        self.assertIn("docs/law/delegate.md", res.stderr)

    def test_session_id_is_sanitized_into_the_sentinel_path(self):
        res = run_hook(self.hook, self.payload("git commit -m x", session="../evil/../id"))
        self.assertTrue(denied(res))
        acks = list((self.root / ".ybase" / "law-ack").iterdir())
        self.assertEqual(len(acks), 1)
        self.assertNotIn("/", acks[0].name)
        self.assertNotIn("..", acks[0].name)

    def test_sentinel_lands_in_the_main_checkout_from_a_worktree(self):
        main = self.root / "main"
        (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
        wt = self.root / "wt"
        hook = wt / ".claude" / "hooks" / "moment_law_hook.py"
        hook.parent.mkdir(parents=True)
        shutil.copy(HOOKS / "moment_law_hook.py", hook)
        write(wt, ".git", f"gitdir: {main / '.git' / 'worktrees' / 'wt'}\n")
        write(wt, "docs/law/commit.md", "# commit\n")
        res = run_hook(hook, {"session_id": "s", "tool_name": "Bash", "cwd": str(wt),
                              "tool_input": {"command": "git commit -m x"}})
        self.assertTrue(denied(res), res)
        self.assertTrue((main / ".ybase" / "law-ack" / "s" / "commit").is_file())
        self.assertFalse((wt / ".ybase").exists())

    def test_malformed_stdin_allows(self):
        self.assertEqual(run_hook(self.hook, "{").returncode, 0)
        self.assertEqual(run_hook(self.hook, '{"tool_name": "Bash", "tool_input": null}').returncode, 0)

    def kb_fixture(self):
        """A KB outside the fixture repository, named by the fixture's `.env`."""
        kb_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(kb_tmp.cleanup)
        kb = Path(kb_tmp.name).resolve()
        write(self.root, ".env", f"YBASE_KB_PRIMARY={kb}\n")
        env = {k: "" for k in os.environ if k.startswith("YBASE_")}
        return kb, env

    def test_kb_document_fires_the_docs_moment(self):
        (self.root / "tools").mkdir()
        shutil.copy(ROOT / "tools" / "envfile.py", self.root / "tools" / "envfile.py")
        kb, env = self.kb_fixture()
        res = run_hook(self.hook, self.payload(str(kb / "memory" / "x.md"), tool="Write"), env=env)
        self.assertTrue(denied(res), res)
        self.assertIn("docs/law/docs.md", res.stderr)
        res = run_hook(self.hook, self.payload(str(kb / "rules.md"), session="sess-2", tool="Write"), env=env)
        self.assertEqual((res.returncode, res.stdout), (0, ""))

    def test_kb_paths_unknown_means_no_kb_moment_and_no_crash(self):
        kb, env = self.kb_fixture()  # no tools/envfile.py beside this copy of the hook
        res = run_hook(self.hook, self.payload(str(kb / "memory" / "x.md"), tool="Write"), env=env)
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, "", ""))
        res = run_hook(self.hook, self.payload(str(self.root / "docs" / "x.md"), tool="Write"), env=env)
        self.assertTrue(denied(res), res)


# ------------------------------------------------------------------------ leak
# Planted values are built by concatenation so this file does not trip the repo's own leak scan.
KEY = "AKIA" + "ABCDEFGHIJKLMNOP"
MAIL = "bob" + "@corp.io"


def ybase_fixture(root, kb=None):
    """A git repository holding a copy of the leak hook and the tools it imports, so that,
    to that copy, the fixture is YBase. With `kb`, its `.env` names that knowledge base."""
    hook = root / ".claude" / "hooks" / "leak_hook.py"
    hook.parent.mkdir(parents=True)
    shutil.copy(HOOKS / "leak_hook.py", hook)
    (root / "tools").mkdir()
    for name in ("checks.py", "envfile.py"):
        shutil.copy(ROOT / "tools" / name, root / "tools" / name)
    if kb is not None:
        write(root, ".env", f"YBASE_KB_PRIMARY={kb}\n")
    git_repo(root)
    write(root, "clean.md", "nothing to see\n")
    git(root, "add", "clean.md", ".claude", "tools")
    git(root, "commit", "-qm", "init")
    return hook


NO_YBASE_ENV = {k: "" for k in os.environ if k.startswith("YBASE_")}


class Leak(unittest.TestCase):
    """Commands that target YBase itself: every pattern applies."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
        self.HOOK = ybase_fixture(self.repo)

    def payload(self, cmd):
        return {"session_id": "s", "tool_name": "Bash", "cwd": str(self.repo), "tool_input": {"command": cmd}}

    def run_cmd(self, cmd, env=None):
        return run_hook(self.HOOK, self.payload(cmd), env={**NO_YBASE_ENV, **(env or {})})

    def test_refuses_a_commit_message_with_a_key_and_names_the_pattern(self):
        res = self.run_cmd(f'git commit -m "rotate {KEY} later"')
        self.assertTrue(denied(res), res)
        self.assertIn("AWS access key id", res.stderr)
        self.assertIn(KEY, res.stderr)
        self.assertIn("a commit message", res.stderr)

    def test_message_forms(self):
        for cmd in (f"git commit --message='{MAIL}'", f"git commit -am '{MAIL}'",
                    f'git commit -m "$(cat <<\'EOF\'\nsubject\n\nmail {MAIL}\nEOF\n)"'):
            self.assertTrue(denied(self.run_cmd(cmd)), cmd)
        write(self.repo, "msg.txt", f"subject\n\ncontact {MAIL}\n")
        self.assertTrue(denied(self.run_cmd("git commit -F msg.txt")))

    def test_refuses_a_staged_line_with_a_leak(self):
        write(self.repo, "notes.md", f"written by {MAIL}\n")
        git(self.repo, "add", "notes.md")
        res = self.run_cmd('git commit -m "add notes"')
        self.assertTrue(denied(res), res)
        self.assertIn("email address", res.stderr)
        self.assertIn("lines this commit would add", res.stderr)

    def test_working_tree_change_counts_only_under_dash_a(self):
        write(self.repo, "clean.md", f"now with {KEY}\n")  # tracked, modified, not staged
        self.assertEqual(self.run_cmd('git commit -m "msg"').returncode, 0)
        self.assertTrue(denied(self.run_cmd('git commit -am "msg"')))
        self.assertTrue(denied(self.run_cmd('git commit --all -m "msg"')))

    def test_wrapped_and_flagged_invocations_are_inspected(self):
        self.assertTrue(denied(self.run_cmd(f'timeout 60 git commit -m "rotate {KEY}"')))
        self.assertTrue(denied(self.run_cmd(f'nohup gh -R owner/repo pr create --draft --body "{MAIL}"')))
        self.assertTrue(denied(self.run_cmd(f'git --no-pager commit --message "{KEY}"')))
        # `commit -C <commit>` reuses a message; it is not a directory and must not move the cwd.
        self.assertEqual(self.run_cmd('git commit -C HEAD --allow-empty').returncode, 0)
        # `git -C <repo>` from another directory reads that repository's index, not the cwd's.
        write(self.repo, "notes.md", f"written by {MAIL}\n")
        git(self.repo, "add", "notes.md")
        payload = self.payload(f'git -C "{self.repo}" commit -m "add notes"')
        payload["cwd"] = str(self.repo.parent)
        res = run_hook(self.HOOK, payload, env=NO_YBASE_ENV)
        self.assertTrue(denied(res), res)
        self.assertIn("lines this commit would add", res.stderr)

    def test_near_misses_pass(self):
        for cmd in ('git commit -m "thanks you@example.com"',
                    f'echo "{KEY}"',  # not a publishing surface
                    f'git log --grep "{KEY}"',
                    f'gh pr view 3 --json body -q "{KEY}"'):
            res = self.run_cmd(cmd)
            self.assertEqual(res.returncode, 0, (cmd, res.stderr))

    def test_an_unterminated_quote_is_scanned_whole(self):
        self.assertTrue(denied(self.run_cmd(f"git commit -m 'unterminated {KEY}")))
        self.assertEqual(self.run_cmd("git commit -m 'unterminated").returncode, 0)

    def test_pr_surfaces(self):
        self.assertTrue(denied(self.run_cmd(f'gh pr create --draft --title "x" --body "{KEY}"')))
        self.assertTrue(denied(self.run_cmd(f'gh pr edit 3 --title "{MAIL}"')))
        self.assertTrue(denied(self.run_cmd(f'gh pr comment 3 -b "{KEY}"')))
        write(self.repo, "body.md", f"## Review\n{MAIL}\n")
        self.assertTrue(denied(self.run_cmd("gh pr review 3 --comment --body-file body.md")))
        self.assertEqual(self.run_cmd('gh pr create --draft --title "clean" --body "fine"').returncode, 0)

    def test_tag_message(self):
        self.assertTrue(denied(self.run_cmd(f'git tag -a v1 -m "{KEY}"')))
        self.assertEqual(self.run_cmd('git tag -a v1 -m "release"').returncode, 0)

    def test_chained_command_and_env_prefix(self):
        self.assertTrue(denied(self.run_cmd(f'cd x && GIT_AUTHOR_NAME=t git commit -m "{KEY}"')))

    def test_deny_local_private_term(self):
        import checks
        hits = checks.leak_hits("made at SecretCo", [__import__("re").compile("(?i)secretco")])
        self.assertTrue(hits)  # the hook defers to checks.leak_hits; the term list is per machine

    def test_escape(self):
        self.assertEqual(self.run_cmd(f'LEAK_AUTHORIZED=1 git commit -m "{KEY}"').returncode, 0)
        self.assertEqual(self.run_cmd(f'git commit -m "{KEY}"', env={"LEAK_AUTHORIZED": "1"}).returncode, 0)
        # The escape is a prefix, not a word somewhere on the line.
        self.assertTrue(denied(self.run_cmd(f'echo LEAK_AUTHORIZED=1; git commit -m "{KEY}"')))

    def test_malformed_stdin_and_other_tools_allow(self):
        self.assertEqual(run_hook(self.HOOK, "nope").returncode, 0)
        self.assertEqual(run_hook(self.HOOK, {"tool_name": "Write", "tool_input": {"file_path": KEY}}).returncode, 0)


class LeakScope(unittest.TestCase):
    """Every pattern and every private term applies whichever repository the command
    targets (ADR 0005); the hook does not work out the target."""

    TOKEN = "gh" + "p_" + "A" * 36

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
        self.home = base / "YBase"
        self.kb = base / "kb"
        write(self.kb, "deny.list", "(?i)secretco\n")
        self.hook = ybase_fixture(self.home, kb=self.kb)
        self.other = base / "secretco-app"
        self.other.mkdir()
        git_repo(self.other)
        write(self.other, "a.md", "a\n")
        git(self.other, "add", "a.md")
        git(self.other, "commit", "-qm", "init")

    def run_in(self, cwd, cmd, env=None):
        payload = {"session_id": "s", "tool_name": "Bash", "tool_input": {"command": cmd}}
        if cwd is not None:
            payload["cwd"] = str(cwd)
        # An empty value counts as unset, so a GH_REPO in the developer's shell cannot leak in.
        quiet = {**NO_YBASE_ENV, "GH_REPO": "", "GH_HOST": ""}
        return run_hook(self.hook, payload, env={**quiet, **(env or {})}, cwd=str(self.other))

    def test_a_private_term_in_a_managed_repo_commit_is_refused(self):
        res = self.run_in(self.other, 'git commit -m "Fix SecretCo startup"')
        self.assertTrue(denied(res), res)
        self.assertIn("private term (deny.list)", res.stderr)
        res = self.run_in(self.home, f'git -C "{self.other}" commit -m "Fix SecretCo startup"')
        self.assertTrue(denied(res), res)

    def test_the_escape_prefix_allows_it_in_a_managed_repo(self):
        res = self.run_in(self.other, 'LEAK_AUTHORIZED=1 git commit -m "Fix SecretCo startup"')
        self.assertEqual((res.returncode, res.stdout), (0, ""), res.stderr)

    def test_the_same_message_targeting_ybase_is_refused(self):
        res = self.run_in(self.home, 'git commit -m "Fix SecretCo startup"')
        self.assertTrue(denied(res), res)
        self.assertIn("private term (deny.list)", res.stderr)
        res = self.run_in(self.other, f'git -C "{self.home}" commit -m "Fix SecretCo startup"')
        self.assertTrue(denied(res), res)

    def test_a_ybase_worktree_counts_as_ybase(self):
        wt = self.home.parent / "wt"
        git(self.home, "worktree", "add", "-q", str(wt))
        res = self.run_in(wt, 'git commit -m "Fix SecretCo startup"')
        self.assertTrue(denied(res), res)

    def test_a_token_in_a_managed_repo_commit_is_still_refused(self):
        res = self.run_in(self.other, f'git commit -m "use {self.TOKEN}"')
        self.assertTrue(denied(res), res)
        self.assertIn("GitHub token", res.stderr)

    def test_a_staged_email_in_a_managed_repo_is_refused(self):
        write(self.other, "authors.md", f"written by {MAIL}\n")
        git(self.other, "add", "authors.md")
        res = self.run_in(self.other, 'git commit -m "add authors"')
        self.assertTrue(denied(res), res)
        self.assertIn("lines this commit would add", res.stderr)
        res = self.run_in(self.home, f'git -C "{self.other}" commit -m "add authors"')
        self.assertTrue(denied(res), res)

    def test_a_target_the_hook_cannot_see_is_refused(self):
        cmd = 'git commit -m "Fix SecretCo startup"'
        self.assertTrue(denied(self.run_in(None, cmd)))  # no cwd in the payload
        self.assertTrue(denied(self.run_in(self.home.parent, cmd)))  # cwd is not in a repository
        self.assertTrue(denied(self.run_in(self.other, f'cd "{self.home}" && {cmd}')))  # moves first
        self.assertTrue(denied(self.run_in(self.other, 'gh -R o/r pr create --title "Fix SecretCo startup"')))
        self.assertTrue(denied(self.run_in(self.other, f'GIT_DIR="{self.home}/.git" {cmd}')))

    # A stray quote in a trailing comment is legal shell that shlex cannot split.
    UNSPLITTABLE = 'git commit -m "Fix SecretCo startup" # don\'t'

    def test_a_command_that_cannot_be_split_is_scanned_whole(self):
        res = self.run_in(self.home, self.UNSPLITTABLE)
        self.assertTrue(denied(res), res)
        self.assertIn("private term (deny.list)", res.stderr)
        self.assertTrue(denied(self.run_in(self.other, self.UNSPLITTABLE)))
        self.assertTrue(denied(self.run_in(self.home, 'gh pr create --title "SecretCo" # it\'s')))

    def test_an_unsplittable_command_without_a_leak_is_allowed(self):
        res = self.run_in(self.home, 'git commit -m "Fix startup" # don\'t')
        self.assertEqual((res.returncode, res.stdout), (0, ""), res.stderr)

    def test_an_unsplittable_command_that_names_neither_git_nor_gh_is_allowed(self):
        for cmd in ('echo "SecretCo" # don\'t', 'cat github.md "SecretCo" # don\'t'):
            res = self.run_in(self.home, cmd)
            self.assertEqual((res.returncode, res.stdout), (0, ""), (cmd, res.stderr))

    def test_the_escape_prefix_covers_an_unsplittable_command(self):
        res = self.run_in(self.home, "LEAK_AUTHORIZED=1 " + self.UNSPLITTABLE)
        self.assertEqual((res.returncode, res.stdout), (0, ""), res.stderr)
        res = self.run_in(self.home, self.UNSPLITTABLE, env={"LEAK_AUTHORIZED": "1"})
        self.assertEqual((res.returncode, res.stdout), (0, ""), res.stderr)

    def test_a_repo_selector_a_move_or_a_wrapper_changes_nothing(self):
        msg, home = "Fix SecretCo startup", self.home
        url = "https://github.com/owner/YBase/pull/3"
        cmds = (
            f'gh pr create --title "{msg}" -R owner/YBase',
            f'gh pr create --repo owner/YBase --title "{msg}"',
            f'gh pr create --repo=owner/YBase --title "{msg}"',
            f'gh pr create -Rowner/YBase --title "{msg}"',
            f'GH_REPO=owner/YBase gh pr create --title "{msg}"',
            f'gh pr comment {url} --body "{msg}"',
            f'gh pr edit {url} --title "{msg}"',
            f'gh pr comment owner/YBase#3 --body "{msg}"',
            f'{{ cd "{home}"; }}; git commit -m "{msg}"',
            f'if true; then cd "{home}"; git commit -m "{msg}"; fi',
            f'while true; do cd "{home}"; git commit -m "{msg}"; done',
            f'sudo -D "{home}" git commit -m "{msg}"',
            f'GIT_COMMON_DIR="{home}/.git" git commit -m "{msg}"',
            f'GIT_DIR="{home}/.git" git commit -m "{msg}"',
            f'env -C "{home}" git commit -m "{msg}"',
            f'time git -C "{home}" commit -m "{msg}"',
            f'git --work-tree="{home}" commit -m "{msg}"',
            f'git -c core.worktree="{home}" commit -m "{msg}"',
            f'nohup git commit -m "{msg}"',
            f'command git commit -m "{msg}"',
            f'printf x | xargs git commit -m "{msg}"',
        )
        for cmd in cmds:
            with self.subTest(cmd=cmd):
                self.assertTrue(denied(self.run_in(self.other, cmd)), cmd)

    def test_a_repo_set_in_the_process_environment_changes_nothing(self):
        cmd = 'gh pr create --title "Fix SecretCo startup"'
        for name in ("GH_REPO", "GH_HOST"):
            with self.subTest(name=name):
                res = self.run_in(self.other, cmd, env={name: "owner/YBase"})
                self.assertTrue(denied(res), res)

    def test_plain_commands_in_another_repo_are_refused_too(self):
        msg = "Fix SecretCo startup"
        for cwd, cmd in ((self.other, f'git commit -m "{msg} fix"'),
                         (self.home, f'git -C "{self.other}" commit -m "{msg} fix"'),
                         (self.other, f'gh pr create --title "{msg}"'),
                         (self.other, f'git tag -a v1 -m "{msg}"')):
            with self.subTest(cmd=cmd):
                self.assertTrue(denied(self.run_in(cwd, cmd)), cmd)

    def test_a_clean_message_in_another_repo_is_allowed(self):
        res = self.run_in(self.other, 'git commit -m "Fix startup"')
        self.assertEqual((res.returncode, res.stdout), (0, ""), res.stderr)

    def test_a_token_in_a_pr_for_another_repo_is_still_refused(self):
        res = self.run_in(self.other, f'gh pr create --title "use {self.TOKEN}"')
        self.assertTrue(denied(res), res)
        self.assertIn("GitHub token", res.stderr)

    def test_escape_still_works(self):
        res = self.run_in(self.home, 'LEAK_AUTHORIZED=1 git commit -m "Fix SecretCo startup"')
        self.assertEqual(res.returncode, 0)
        res = self.run_in(self.other, f'LEAK_AUTHORIZED=1 sudo -D "{self.home}" git commit -m "Fix SecretCo startup"')
        self.assertEqual(res.returncode, 0)


class LeakDenyList(unittest.TestCase):
    """The deny list as the hook reads it, through a copy of the hook and its tools in a
    fixture repository whose `.env` names a fixture knowledge base."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
        self.repo = base / "repo"
        self.hook = self.repo / ".claude" / "hooks" / "leak_hook.py"
        self.hook.parent.mkdir(parents=True)
        shutil.copy(HOOKS / "leak_hook.py", self.hook)
        (self.repo / "tools").mkdir()
        for name in ("checks.py", "envfile.py"):
            shutil.copy(ROOT / "tools" / name, self.repo / "tools" / name)
        self.kb = base / "kb"
        write(self.kb, "deny.list", "# private terms\n(unclosed\n(?i)secretco\n")
        write(self.repo, ".env", f"YBASE_KB_PRIMARY={self.kb}\n")
        git_repo(self.repo)
        write(self.repo, "clean.md", "nothing to see\n")
        git(self.repo, "add", "clean.md")
        git(self.repo, "commit", "-qm", "init")
        self.env = {k: "" for k in os.environ if k.startswith("YBASE_")}

    def test_a_malformed_line_is_skipped_and_the_rest_still_refuse(self):
        res = run_hook(self.hook, {"session_id": "s", "tool_name": "Bash", "cwd": str(self.repo),
                                   "tool_input": {"command": 'git commit -m "made at SecretCo"'}}, env=self.env)
        self.assertTrue(denied(res), res)
        self.assertIn("private term (deny.list): SecretCo", res.stderr)
        self.assertNotIn("allowed without checking", res.stderr)

    def test_a_line_that_overflows_the_compiler_is_skipped_too(self):
        # re.compile raises OverflowError here, not re.error.
        write(self.kb, "deny.list", "a{99999999999999999999}\n(?i)secretco\n")
        res = run_hook(self.hook, {"session_id": "s", "tool_name": "Bash", "cwd": str(self.repo),
                                   "tool_input": {"command": 'git commit -m "made at SecretCo"'}}, env=self.env)
        self.assertTrue(denied(res), res)
        self.assertIn("private term (deny.list): SecretCo", res.stderr)
        self.assertNotIn("allowed without checking", res.stderr)


# --------------------------------------------------------------- writing_style
class WritingStyle(unittest.TestCase):
    HOOK = HOOKS / "writing_style_hook.py"

    def setUp(self):
        # Inside the repository (the hook only advises on its own repo), under the ignored tmp/.
        self.dir = ROOT / "tmp" / f"hooks-write-test-{uuid.uuid4().hex[:8]}"
        self.dir.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.dir, True)

    def payload(self, path, tool="Write"):
        return {"session_id": "s", "tool_name": tool, "cwd": str(ROOT),
                "tool_input": {"file_path": str(path), "content": ""}, "tool_response": {}}

    def context(self, res):
        self.assertEqual(res.returncode, 0, res.stderr)
        out = json.loads(res.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PostToolUse")
        return out["additionalContext"]

    def test_reports_em_dash_and_broken_link_plus_the_five_judgment_checks(self):
        p = write(self.dir, "x.md", "# T\n\nfirst " + EM_DASH + " second\n\nsee [gone](missing.md)\n")
        ctx = self.context(run_hook(self.HOOK, self.payload(p)))
        self.assertIn("em dash", ctx)
        self.assertIn("broken link -> missing.md", ctx)
        self.assertIn("x.md:3:", ctx)
        self.assertEqual(len([ln for ln in ctx.splitlines() if ln.strip()[:2] in ("1.", "2.", "3.", "4.", "5.")]), 5)
        for word in ("Lead with the answer", "One fact per sentence", "label", "outside reader", "end state"):
            self.assertIn(word, ctx)

    def test_clean_file_earns_silence(self):
        p = write(self.dir, "y.md", "# T\n\nPlain text, see [self](y.md).\n")
        res = run_hook(self.HOOK, self.payload(p, tool="Edit"))
        self.assertEqual((res.returncode, res.stdout), (0, ""))

    def test_silent_for_non_markdown_outside_repo_missing_file_and_escape(self):
        p = write(self.dir, "z.py", "x = 1\n")
        self.assertEqual((run_hook(self.HOOK, self.payload(p)).returncode, run_hook(self.HOOK, self.payload(p)).stdout), (0, ""))
        with tempfile.TemporaryDirectory() as t:
            q = write(t, "out.md", "a " + EM_DASH + " b\n")
            res = run_hook(self.HOOK, self.payload(q))
            self.assertEqual((res.returncode, res.stdout), (0, ""))
        res = run_hook(self.HOOK, self.payload(self.dir / "never.md"))
        self.assertEqual((res.returncode, res.stdout), (0, ""))
        p = write(self.dir, "w.md", "a " + EM_DASH + " b\n")
        res = run_hook(self.HOOK, self.payload(p), env={"WRITING_STYLE_SKIP": "1"})
        self.assertEqual((res.returncode, res.stdout), (0, ""))

    def test_always_exit_zero(self):
        self.assertEqual(run_hook(self.HOOK, "garbage").returncode, 0)
        self.assertEqual(run_hook(self.HOOK, '{"tool_input": 3}').returncode, 0)


# ------------------------------------------------------------------- settings
HOOK_NAMES = {
    "filesystem_scan_hook.py", "self_matching_pgrep_hook.py", "zsh_word_split_hook.py", "pr_draft_hook.py",
    "git_write_in_pipeline_hook.py", "python_floor_hook.py", "readonly_checkout_hook.py", "moment_law_hook.py",
    "leak_hook.py", "writing_style_hook.py", "session_end_distil_hook.py", "tool_load_hook.py",
}
ADVISORY = {"git_write_in_pipeline_hook.py", "writing_style_hook.py", "tool_load_hook.py", "session_end_distil_hook.py"}
# YBase's own guards: the allow gate reads settings files relative to its working directory
# (docs/adr/0001-allow-gate-cwd-robustness.md), so its wrapper also moves to the project root.
OWN_WIRING = {"allow-gate.py", "file-guard.py"}


def own_wiring_commands():
    """(file, hook name, command) for the allow gate and file guard, in both wiring files."""
    claude = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    codex = json.loads((ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    for label, data in ((".claude/settings.json", claude), (".codex/hooks.json", codex)):
        for groups in data["hooks"].values():
            for g in groups:
                for h in g["hooks"]:
                    m = re.search(r"\.claude/hooks/(allow-gate\.py|file-guard\.py)", h["command"])
                    if m:
                        yield label, m.group(1), h["command"]


def run_wired(cmd, cwd, payload, project_dir=None, extra=None):
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    if project_dir:
        env["CLAUDE_PROJECT_DIR"] = project_dir
    env.update(extra or {})
    return subprocess.run(["/bin/sh", "-c", cmd], input=json.dumps(payload), capture_output=True,
                          text=True, cwd=cwd, env=env, timeout=60)


class OwnWiring(unittest.TestCase):
    """The allow gate and file guard fail open like the other hooks: Codex sets no
    CLAUDE_PROJECT_DIR, and a session may sit outside any repository."""

    def test_both_files_wire_both_guards(self):
        found = {(label, name) for label, name, _ in own_wiring_commands()}
        self.assertEqual(found, {(".claude/settings.json", "allow-gate.py"), (".claude/settings.json", "file-guard.py"),
                                 (".codex/hooks.json", "allow-gate.py")})

    def test_outside_any_repository_without_project_dir_exits_zero_silently(self):
        payloads = {"allow-gate.py": {"tool_name": "Bash", "tool_input": {"command": "ls"}},
                    "file-guard.py": {"tool_name": "Write", "tool_input": {"file_path": "/x/.env"}}}
        with tempfile.TemporaryDirectory() as t:
            for label, name, cmd in own_wiring_commands():
                res = run_wired(cmd, t, payloads[name])
                self.assertEqual((res.returncode, res.stdout, res.stderr), (0, "", ""), (label, name))

    def test_allow_gate_reads_the_project_settings_from_another_directory(self):
        # The gate reads .claude/settings.json relative to its working directory, so the
        # wrapper must move to the project root before running it.
        payload = {"tool_name": "Bash", "tool_input": {"command": "ls && pwd"}}
        with tempfile.TemporaryDirectory() as t:
            for label, name, cmd in own_wiring_commands():
                if name == "allow-gate.py":
                    res = run_wired(cmd, t, payload, project_dir=str(ROOT), extra={"YBASE_ALLOW_GATE": "1"})
                    self.assertEqual(res.returncode, 0, (label, res.stderr))
                    self.assertIn("approve", res.stdout, label)

    def test_file_guard_still_blocks_when_wired_normally(self):
        cmd = next(c for _, name, c in own_wiring_commands() if name == "file-guard.py")
        res = run_wired(cmd, str(ROOT), {"tool_name": "Write", "tool_input": {"file_path": str(ROOT / ".env")}},
                        project_dir=str(ROOT))
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertIn("file-guard", res.stderr)
        with tempfile.TemporaryDirectory() as t:  # from another directory, through CLAUDE_PROJECT_DIR
            res = run_wired(cmd, t, {"tool_name": "Write", "tool_input": {"file_path": str(ROOT / ".env")}},
                            project_dir=str(ROOT))
        self.assertEqual(res.returncode, 2, res.stderr)


class Settings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))

    def entries(self):
        for event, groups in self.settings["hooks"].items():
            for g in groups:
                for h in g["hooks"]:
                    name = re.search(r"\.claude/hooks/([A-Za-z0-9_.-]+\.py)", h["command"]).group(1)
                    yield event, g.get("matcher"), name, h

    def test_every_hook_is_wired_and_nothing_else(self):
        self.assertEqual({e[2] for e in self.entries()}, HOOK_NAMES | OWN_WIRING)
        self.assertNotIn("env", self.settings)

    def test_matchers(self):
        wiring = {}
        for event, matcher, name, _ in self.entries():
            wiring.setdefault((event, matcher), set()).add(name)
        self.assertEqual(wiring[("PreToolUse", "Bash|Glob|Grep")], {"filesystem_scan_hook.py"})
        self.assertEqual(wiring[("PreToolUse", "Bash")],
                         {"allow-gate.py", "self_matching_pgrep_hook.py", "zsh_word_split_hook.py",
                          "python_floor_hook.py", "pr_draft_hook.py", "leak_hook.py",
                          "git_write_in_pipeline_hook.py", "moment_law_hook.py"})
        self.assertEqual(wiring[("PreToolUse", "Write|Edit|NotebookEdit")], {"file-guard.py"})
        self.assertEqual(wiring[("PreToolUse", "Write|Edit|MultiEdit|NotebookEdit")],
                         {"readonly_checkout_hook.py", "moment_law_hook.py"})
        self.assertEqual(wiring[("PreToolUse", "Agent")], {"moment_law_hook.py"})
        self.assertEqual(wiring[("PostToolUse", "Write|Edit")], {"writing_style_hook.py"})
        self.assertEqual(wiring[("PostToolUse", ".*")], {"tool_load_hook.py"})
        self.assertEqual(wiring[("SessionEnd", None)], {"session_end_distil_hook.py"})

    def test_wrapper_shape_and_timeouts(self):
        for event, matcher, name, h in self.entries():
            if name in OWN_WIRING:
                continue
            cmd = h["command"]
            self.assertEqual(h["type"], "command")
            self.assertEqual(h["timeout"], 20, name)
            self.assertTrue(cmd.startswith(f'h="$CLAUDE_PROJECT_DIR/.claude/hooks/{name}"; [ -f "$h" ] || '
                                           f'h="$(git rev-parse --show-toplevel 2>/dev/null)/.claude/hooks/{name}"; '), name)
            self.assertTrue(cmd.endswith("exit 0"), name)
            if name in ADVISORY:
                self.assertTrue(cmd.endswith('[ -f "$h" ] && python3 "$h"; exit 0'), name)
            else:
                self.assertTrue(cmd.endswith('[ -f "$h" ] || exit 0; python3 "$h"; [ $? = 2 ] && exit 2; exit 0'), name)

    def test_wrapper_exits_zero_when_the_hook_file_is_missing(self):
        """The resolving wrapper degrades to silence, never to a fake failure."""
        cmd = next(h["command"] for _, _, name, h in self.entries() if name == "writing_style_hook.py")
        with tempfile.TemporaryDirectory() as t:
            res = subprocess.run(["bash", "-c", cmd], input="{}", capture_output=True, text=True, cwd=t,
                                 env={**os.environ, "CLAUDE_PROJECT_DIR": t})
        self.assertEqual(res.returncode, 0, res.stderr)


if __name__ == "__main__":
    unittest.main()
