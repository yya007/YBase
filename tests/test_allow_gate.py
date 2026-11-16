"""Regression tests for .claude/hooks/allow-gate.py.

These tests document both what the allow-gate approves and specific commands
that have historically required manual approval due to gaps in the gate logic
or in an allow list. The regression tests read a fixture allow list written to
a throwaway project and home directory, never the tracked .claude/settings.json,
which ships a short reviewed list (tests/test_settings.py pins it). The tests at
the end run main() from a copy of the hook in a throwaway project holding that
real list; the gate there is opt-in, so they set YBASE_ALLOW_GATE themselves
(in the environment or a fixture .env), never through the real .env.

Regression markers:
  SHOULD_APPROVE — command should be auto-approved (fix the gate/list when failing)
  SHOULD_BLOCK   — command must NOT be silently approved (security boundary)
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import allow-gate module from its non-package location.
# ---------------------------------------------------------------------------

_CLAUDE_DIR = Path(__file__).resolve().parent.parent / ".claude"
_GATE_PATH = _CLAUDE_DIR / "hooks/allow-gate.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("allow_gate", _GATE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = _load_gate()
split_compound = gate.split_compound
segment_is_allowed = gate.segment_is_allowed
glob_to_regex = gate.glob_to_regex

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A broad personal allow list of the kind a user keeps in .claude/settings.local.json.
# The regression tests need these entries; the tracked settings never carry them.
FIXTURE_ALLOW = [
    "Bash(git status*)", "Bash(git diff*)", "Bash(git add*)", "Bash(git log*)",
    "Bash(git rev-parse*)", "Bash(cat *)", "Bash(grep *)", "Bash(head *)", "Bash(wc *)",
    "Bash(echo *)", "Bash(basename *)", "Bash(sort*)", "Bash(find *)", "Bash(xargs *)",
    "Bash(cd *)", "Bash(for *)", "Bash(python3 *)", "Bash(make *)",
    "WebSearch",
]


@pytest.fixture
def patterns(tmp_path, monkeypatch):
    """The gate's own loader, pointed at a fixture project and an empty home directory."""
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude/settings.json").write_text(json.dumps({"permissions": {"allow": FIXTURE_ALLOW}}))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(project)
    return gate.load_allow_patterns()


def test_loader_reads_project_settings_and_skips_non_bash(patterns):
    assert "git status*" in patterns
    assert "WebSearch" not in patterns
    assert len(patterns) == len(FIXTURE_ALLOW) - 1


def test_loader_adds_local_settings(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude/settings.json").write_text(json.dumps({"permissions": {"allow": ["Bash(ls *)"]}}))
    (project / ".claude/settings.local.json").write_text(json.dumps({"permissions": {"allow": ["Bash(git push*)"]}}))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(project)
    assert gate.load_allow_patterns() == ["ls *", "git push*"]


def allowed(cmd: str, pats: list[str]) -> bool:
    """Return True if the gate approves cmd against pats, as main() decides."""
    return gate.command_is_approved(cmd, pats)


# ---------------------------------------------------------------------------
# split_compound — unit tests
# ---------------------------------------------------------------------------


class TestSplitCompound:
    def test_single_command(self):
        assert split_compound("git status") == ["git status"]

    def test_and_and(self):
        assert split_compound("git add . && git status") == ["git add .", "git status"]

    def test_semicolon(self):
        assert split_compound("git add .; git status") == ["git add .", "git status"]

    def test_pipe(self):
        assert split_compound("git diff | grep foo") == ["git diff", "grep foo"]

    def test_escaped_pipe_not_split(self):
        # grep 'a\|b' — the \| is an escaped pipe inside the grep pattern, not a compound op
        segs = split_compound(r"grep 'a\|b' file.txt")
        assert len(segs) == 1

    def test_quoted_semicolon_not_split(self):
        segs = split_compound("echo 'a;b'")
        assert segs == ["echo 'a;b'"]

    def test_quoted_double_and_not_split(self):
        segs = split_compound('echo "a&&b"')
        assert segs == ['echo "a&&b"']

    def test_for_loop_inline(self):
        cmd = "for f in a b c; do echo $f; done"
        segs = split_compound(cmd)
        # header, body, done — all three should be present
        assert any("for f" in s for s in segs)
        assert any("echo $f" in s for s in segs)

    def test_for_loop_multiline_header(self):
        # Multi-line variable list in for header should NOT fragment the paths.
        cmd = "for f in /a/b\n/c/d; do echo $f; done"
        segs = split_compound(cmd)
        header = next(s for s in segs if s.startswith("for "))
        assert "/a/b" in header and "/c/d" in header

    def test_newline_separator_outside_loop(self):
        cmd = "git add foo.py\ngit status"
        assert split_compound(cmd) == ["git add foo.py", "git status"]

    def test_trailing_empty_segment_ignored(self):
        segs = split_compound("git add .; ")
        assert "" not in segs

    def test_pipeline_chain(self):
        segs = split_compound("find . | sort | xargs echo")
        assert segs == ["find .", "sort", "xargs echo"]

    def test_or_operator(self):
        segs = split_compound("git add . || echo failed")
        assert segs == ["git add .", "echo failed"]

    def test_background_ampersand_splits(self):
        # `ls & touch x` runs two commands; as one segment, "ls *" would cover both.
        assert split_compound("ls & touch pwned") == ["ls", "touch pwned"]
        assert split_compound("ls x & ") == ["ls x"]
        assert not allowed("git status && ls & touch pwned", ["git status", "ls *"])

    def test_ampersand_in_redirections_does_not_split(self):
        for cmd in ("ls 2>&1", "ls &>/dev/null", "ls >&2", "ls 1>&2 2>&1", "echo 'a & b'"):
            assert split_compound(cmd) == [cmd], cmd


# ---------------------------------------------------------------------------
# segment_is_allowed — unit tests
# ---------------------------------------------------------------------------


class TestSegmentIsAllowed:
    def test_empty_segment_allowed(self):
        assert segment_is_allowed("", []) is True

    def test_comment_declines(self):
        # Declines: an unquoted # is syntax the gate does not model (it once hid a second line).
        assert segment_is_allowed("# this is a comment", []) is False

    def test_bare_keywords_allowed(self):
        for kw in ("do", "done", "then", "else", "elif", "fi", "esac"):
            assert segment_is_allowed(kw, []) is True, f"{kw!r} should be allowed"

    def test_keyword_body_is_checked(self):
        # "do X", "then X", "else X", "elif X": X must itself match a rule.
        for kw in ("do", "then", "else", "elif"):
            assert segment_is_allowed(f"{kw} echo foo", ["echo *"]) is True, kw
            assert segment_is_allowed(f"{kw} touch pwned", ["echo *"]) is False, kw

    def test_closing_keyword_takes_only_descriptor_redirects(self):
        assert segment_is_allowed("done 2>/dev/null", []) is True
        assert segment_is_allowed("fi 2>&1", []) is True
        assert segment_is_allowed("done touch pwned", ["echo *"]) is False

    def test_glob_star_matches_args(self):
        assert segment_is_allowed("git add foo.py bar.py", ["git add*"]) is True

    def test_glob_star_matches_empty_suffix(self):
        # "git add" with no trailing args should still match "git add*"
        assert segment_is_allowed("git add", ["git add*"]) is True

    def test_exact_match_rejects_suffix(self):
        # "git status" (exact) should NOT approve "git status --short"
        assert segment_is_allowed("git status --short", ["git status"]) is False

    def test_wildcard_match_accepts_suffix(self):
        assert segment_is_allowed("git status --short", ["git status*"]) is True

    def test_sort_no_args_requires_no_space_pattern(self):
        # "sort *" (with space) rejects bare "sort"
        assert segment_is_allowed("sort", ["sort *"]) is False
        # "sort*" (no space) accepts bare "sort"
        assert segment_is_allowed("sort", ["sort*"]) is True

    def test_wc_with_flag(self):
        assert segment_is_allowed("wc -l", ["wc *"]) is True

    def test_no_matching_pattern_rejected(self):
        assert segment_is_allowed("rm -rf /", ["echo *", "git *"]) is False


class TestSubshellHandling:
    def test_simple_subshell_approved(self):
        # HASH=$(git rev-parse --short HEAD) — inner cmd covered by git rev-parse*
        seg = "HASH=$(git rev-parse --short HEAD)"
        assert segment_is_allowed(seg, ["git rev-parse*"]) is True

    def test_subshell_inner_not_covered_rejects(self):
        # $(basename $f) — basename not in patterns
        seg = 'echo "$(basename $f)"'
        assert segment_is_allowed(seg, ["echo *", "git *"]) is False

    def test_subshell_inner_covered_approves(self):
        seg = 'echo "$(basename $f)"'
        assert segment_is_allowed(seg, ["echo *", "basename *"]) is True

    def test_backtick_rejected(self):
        seg = "echo `git rev-parse HEAD`"
        assert segment_is_allowed(seg, ["echo *", "git rev-parse*"]) is False

    def test_process_substitution_rejected(self):
        seg = "diff <(git show HEAD:foo) foo"
        assert segment_is_allowed(seg, ["diff *", "git show*"]) is False

    def test_nested_subshell_allowed(self):
        # $(git rev-parse $(cat file)) — nested, both inner commands covered
        seg = "X=$(git rev-parse $(cat file))"
        # inner-inner: "cat file" covered; inner: "git rev-parse _SUBSHELL_" covered
        assert segment_is_allowed(seg, ["git rev-parse*", "cat *"]) is True

    def test_depth_cap_rejects_deep_nesting(self):
        # Artificially deep nesting exceeds _depth >= 4 cap
        seg = "A=$(B=$(C=$(D=$(E=$(echo x)))))"
        # Even if all inner cmds are covered, depth > 4 → rejected
        assert segment_is_allowed(seg, ["echo *"]) is False


# ---------------------------------------------------------------------------
# Regression tests: commands that have historically required manual approval
# ---------------------------------------------------------------------------


class TestRegressions:
    """Commands that historically required manual approval due to gate/allow-list gaps.

    All of these should now be auto-approved. Keep them as permanent regression guards.
    """

    # git status with flags (was blocked: Bash(git status) was exact, no wildcard)

    def test_git_status_short_flag(self, patterns):
        """git status --short should be approved."""
        assert segment_is_allowed("git status --short", patterns)

    def test_git_status_short_with_redirect(self, patterns):
        """git status --short 2>&1 should be approved."""
        assert segment_is_allowed("git status --short 2>&1", patterns)

    def test_compound_git_status_short(self, patterns):
        """Full compound: git diff ... | grep ... && echo ... && git status --short 2>&1"""
        cmd = 'git diff --stat 2>&1 | grep -v "^$" && echo "===" && git status --short 2>&1'
        # Declines: `$"` (from "^$") reads as locale quoting, which the gate does not model;
        # '^$' declines too (it holds `$'`). Without the anchor pattern the command passes.
        assert not allowed(cmd, patterns)
        assert allowed(cmd.replace(' | grep -v "^$"', ""), patterns)

    # basename subshell (was blocked: basename missing from allow list)

    def test_basename_subshell(self, patterns):
        """basename $f inside a subshell should be approved."""
        seg = 'echo "=== $(basename $f) ==="'
        assert segment_is_allowed(seg, patterns)

    def test_for_loop_with_basename_subshell(self, patterns):
        """for loop iterating *.md and echoing basename."""
        cmd = (
            "for f in /srv/example/project/.claude/skills/*.md; "
            'do echo "=== $(basename $f) ==="; '
            'head -5 "$f" | grep -E "^(created:|name:)"; '
            "done 2>/dev/null"
        )
        assert allowed(cmd, patterns)

    # done with trailing redirect (was blocked: _SHELL_KEYWORDS was exact-match only)

    def test_done_with_redirect(self, patterns):
        """done 2>/dev/null should be treated as the loop-closing keyword."""
        assert segment_is_allowed("done 2>/dev/null", patterns)

    # bare sort (was blocked: Bash(sort *) had literal space, bare 'sort' didn't match)

    def test_bare_sort(self, patterns):
        """sort with no arguments should be approved."""
        assert segment_is_allowed("sort", patterns)

    def test_pipeline_find_sort_xargs(self, patterns):
        """find ... | sort | xargs git add should be fully approved."""
        cmd = "find exp/ -name 'results.md' 2>/dev/null | sort | xargs git add"
        assert allowed(cmd, patterns)

    # cd (was blocked: cd missing from allow list)

    def test_cd_command(self, patterns):
        """cd into a directory should be approved."""
        assert segment_is_allowed("cd /tmp/example-fix", patterns)

    def test_compound_with_cd(self, patterns):
        """cd && git log chain should be approved."""
        cmd = (
            "cd /tmp/example-fix && "
            "git log --oneline origin/master..HEAD 2>&1 && "
            "echo '---' && "
            "git log --oneline HEAD ^origin/master 2>&1 | wc -l"
        )
        assert allowed(cmd, patterns)

    # --- Commands that already pass (ensure no regression) ---

    def test_git_add_compound(self, patterns):
        """git add && git status (bare) should be approved."""
        cmd = "git add foo.py && git status"
        assert allowed(cmd, patterns)

    def test_git_diff_pipe_grep(self, patterns):
        """git diff piped to grep should be approved."""
        cmd = "git diff --stat | grep foo"
        assert allowed(cmd, patterns)

    def test_find_pipe_xargs(self, patterns):
        """find | xargs git add (without sort) should be approved."""
        cmd = "find exp/ -name 'results.md' | xargs git add"
        assert allowed(cmd, patterns)

    def test_python3_invocation(self, patterns):
        """python3 script.py should be approved."""
        assert segment_is_allowed("python3 scripts/parse_log.py", patterns)

    def test_make_command(self, patterns):
        """make test-unit should be approved."""
        assert segment_is_allowed("make test-unit", patterns)

    def test_git_add_newline_git_status(self, patterns):
        """Two-line: git add && git status (bare, no flags)."""
        cmd = "git add foo.py\ngit status"
        # Declines: a newline is syntax the gate does not model; join commands with && instead.
        assert not allowed(cmd, patterns)
        assert allowed("git add foo.py && git status", patterns)

    def test_hash_assignment_subshell(self, patterns):
        """HASH=$(git rev-parse --short=4 HEAD) — VAR=$() pattern."""
        seg = "HASH=$(git rev-parse --short=4 HEAD)"
        assert segment_is_allowed(seg, patterns)

    def test_for_loop_simple_echo(self, patterns):
        """Simple for loop with only allowed commands."""
        cmd = "for f in a b c; do echo $f; done"
        assert allowed(cmd, patterns)


# ---------------------------------------------------------------------------
# Redirections and git difftool: declined, whatever the allow list says
# ---------------------------------------------------------------------------


class TestRedirectionsAndDifftool:
    @pytest.mark.parametrize("seg", [
        "cat /dev/null > victim.txt", "echo x >> log.txt", "echo x >out", "echo x 1> f", "ls &> f",
        "ls &>> f", "ls >| f", "ls >&f", "ls 2> err.txt", "head -c0 > .git/hooks/pre-commit",
        'echo x > "$HOME/f"', "cat <> f", "done > f", "do echo x > f",
    ])
    def test_file_redirection_is_not_approved(self, seg):
        assert segment_is_allowed(seg, ["cat *", "echo *", "ls*", "head *"]) is False

    @pytest.mark.parametrize("seg", [
        "ls 2>&1", "ls >&2", "ls 1>&2", "ls >/dev/null", "ls > /dev/null", "ls 2>/dev/null",
        "ls &>/dev/null", "ls >/dev/null 2>&1", "echo 'a > b'", 'echo "a >> b"',
        "done 2>/dev/null",
    ])
    def test_fd_duplication_and_dev_null_still_approved(self, seg):
        assert segment_is_allowed(seg, ["ls*", "echo *"]) is True

    def test_escaped_redirect_declines(self):
        # Declines: a backslash outside single quotes is syntax the gate does not model.
        assert segment_is_allowed(r"echo a \> b", ["echo *"]) is False

    def test_redirection_inside_a_subshell_is_not_approved(self):
        assert segment_is_allowed("X=$(echo x > f)", ["echo *"]) is False
        assert segment_is_allowed("X=$(echo x 2>/dev/null)", ["echo *"]) is True

    def test_git_difftool_is_not_approved(self):
        for seg in ('git difftool -y -x "touch pwned" HEAD', "git -C . difftool", "git difftool"):
            assert segment_is_allowed(seg, ["git *", "git difftool*"]) is False, seg

    def test_with_a_fixture_list(self, patterns):
        assert not allowed("git status && cat /dev/null > out.txt", patterns)
        assert allowed("git status --short 2>&1 && echo done >/dev/null", patterns)


# ---------------------------------------------------------------------------
# The gate as main() runs it: a copy of the hook, tools/envfile.py and the real
# tracked .claude/settings.json in a throwaway project, never the real .env.
# The gate is opt-in: it approves only when YBASE_ALLOW_GATE is exactly 1.
# ---------------------------------------------------------------------------

APPROVE = '{"decision": "approve"}'
PROBES = [
    'git status && git difftool -y -x "touch pwned" HEAD',
    "git status && git diff --output=victim2.txt",
    "git status; cat /dev/null > victim.txt",
    "ls x | head -c0 > .git/hooks/pre-commit",
    "git diff --output=x",
]
# Commands holding syntax the gate does not model: ANSI-C or locale quoting, a
# backslash outside single quotes, an unquoted #, a newline.
UNMODELLED_PROBES = [
    "git status && ls $'\\'' > out.txt",
    "git status && ls $'\\'' ; touch pwned",
    'git status && ls \\" ; touch pwned',
    "git status && ls \\' ; touch pwned",
    "git status && ls #'\ntouch pwned #'",
    "git status; #'\ntouch pwned #'",
    'git status && ls $"x" > out.txt',
    "git status && ls \\\\ ; touch pwned",
    'git status && ls "a\\"" ; touch pwned',
    "git status && wc -l x # ; note\ntouch pwned",
]
# Known gaps of the best-effort parser: some of these are approved when the gate is on.
GAP_PROBES = [
    "git status && ls \"'\" $(touch pwned)",
    'git status && ls "$(ls x; touch pwned)"',
    "git status && ls () ( touch pwned ) && ls",
    "git status && ls =(touch pwned)",
    "git status && ls *(e:'touch pwned':)",
    "git status && ls *(+pwn)",
    "git status && ls ${(e):-'$(touch pwned)'}",
    "git status && wc -l < /dev/tcp/example.com/80",
    "ls () for f in a; do touch pwned; done; ls",
]
# The keyword shortcut no longer approves a body: these decline when the gate is on.
KEYWORD_PROBES = [
    "ls () for f in a; do touch pwned; done; ls",
    "git status && then touch pwned",
    "git status; else touch pwned",
    "git status; elif touch pwned",
]
SHIPPED_CONTROLS = [
    "git status && ls -la 2>&1",
    "git status && ls >/dev/null",
    "git status && ls '>' x",
    "git status && wc -l 'a\\b'",
    "git status && git log",
]


@pytest.fixture
def shipped_project(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / ".claude" / "hooks").mkdir(parents=True)
    (project / "tools").mkdir()
    (project / ".claude/settings.json").write_text((_CLAUDE_DIR / "settings.json").read_text())
    (project / ".claude/hooks/allow-gate.py").write_text(_GATE_PATH.read_text())
    (project / "tools/envfile.py").write_text((_CLAUDE_DIR.parent / "tools" / "envfile.py").read_text())
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(project)
    return project


def run_gate(project, cmd, switch=None):
    """main() of the project's copy of the gate; its stdout, stripped. `switch` sets
    YBASE_ALLOW_GATE in the process environment; every other YBASE_ key is removed."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("YBASE_")}
    env["HOME"] = str(project.parent / "home")
    if switch is not None:
        env["YBASE_ALLOW_GATE"] = switch
    res = subprocess.run([sys.executable, str(project / ".claude/hooks/allow-gate.py")], cwd=project, env=env,
                         capture_output=True, text=True,
                         input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}))
    assert res.returncode == 0, res.stderr
    return res.stdout.strip()


ALL_PROBES = PROBES + UNMODELLED_PROBES + GAP_PROBES + KEYWORD_PROBES


@pytest.mark.parametrize("cmd", ALL_PROBES + SHIPPED_CONTROLS)
def test_off_by_default_prints_nothing(shipped_project, cmd):
    assert run_gate(shipped_project, cmd) == ""


@pytest.mark.parametrize("cmd", SHIPPED_CONTROLS)
def test_switch_in_the_environment_turns_it_on(shipped_project, cmd):
    assert run_gate(shipped_project, cmd, switch="1") == APPROVE


@pytest.mark.parametrize("cmd", SHIPPED_CONTROLS)
def test_switch_in_the_env_file_turns_it_on(shipped_project, cmd):
    (shipped_project / ".env").write_text("YBASE_ALLOW_GATE=1\n")
    assert run_gate(shipped_project, cmd) == APPROVE


@pytest.mark.parametrize("value", ["true", "yes", "0", " 1", "on"])
def test_only_exactly_one_turns_it_on(shipped_project, value):
    for cmd in SHIPPED_CONTROLS:
        assert run_gate(shipped_project, cmd, switch=value) == "", (value, cmd)
    (shipped_project / ".env").write_text(f"YBASE_ALLOW_GATE={value}\n")
    for cmd in SHIPPED_CONTROLS:
        assert run_gate(shipped_project, cmd) == "", (value, cmd)


def test_process_environment_wins_over_the_env_file(shipped_project):
    (shipped_project / ".env").write_text("YBASE_ALLOW_GATE=1\n")
    assert run_gate(shipped_project, SHIPPED_CONTROLS[0], switch="0") == ""


def test_unreadable_env_file_means_off(shipped_project):
    (shipped_project / ".env").mkdir()  # reading it raises, which reads as empty
    assert run_gate(shipped_project, SHIPPED_CONTROLS[0]) == ""
    (shipped_project / ".env").rmdir()
    envf = shipped_project / ".env"
    envf.write_text("YBASE_ALLOW_GATE=1\n")
    envf.chmod(0)
    try:
        if not os.access(envf, os.R_OK):
            assert run_gate(shipped_project, SHIPPED_CONTROLS[0]) == ""
    finally:
        envf.chmod(0o600)


def test_missing_envfile_module_means_off(shipped_project):
    (shipped_project / "tools/envfile.py").unlink()
    (shipped_project / ".env").write_text("YBASE_ALLOW_GATE=1\n")
    assert run_gate(shipped_project, SHIPPED_CONTROLS[0], switch="1") == ""


def test_a_linked_worktree_reads_the_main_checkouts_switch(shipped_project, tmp_path):
    main = tmp_path / "main"
    (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
    (main / ".env").write_text("YBASE_ALLOW_GATE=1\n")
    (shipped_project / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'wt'}\n")
    assert run_gate(shipped_project, SHIPPED_CONTROLS[0]) == APPROVE


# With the gate on, the hardening still holds against the shipped list.

@pytest.mark.parametrize("cmd", PROBES + UNMODELLED_PROBES + KEYWORD_PROBES)
def test_switched_on_shipped_list_declines_probe(shipped_project, cmd):
    assert run_gate(shipped_project, cmd, switch="1") == ""
    assert not allowed(cmd, gate.load_allow_patterns())


@pytest.mark.parametrize("cmd", ["ls $'x'", 'ls $"x"', "ls \\x", 'ls "a\\b"', "ls # c", "ls\nls", "ls\rls",
                                 "ls 'unclosed", 'ls "unclosed'])
def test_unmodelled_syntax_is_declined_by_the_pre_check(cmd):
    assert gate.has_unmodelled_syntax(cmd)


@pytest.mark.parametrize("cmd", ["ls 'a\\b'", "ls '#x'", 'ls "#x"', "ls 'a\"b'", "git log --format='%H %s'"])
def test_modelled_syntax_passes_the_pre_check(cmd):
    assert not gate.has_unmodelled_syntax(cmd)


def test_wildcard_does_not_span_a_newline():
    assert not re.match(glob_to_regex("ls *"), "ls x\ntouch pwned")
