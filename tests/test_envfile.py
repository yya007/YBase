import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import envfile  # noqa: E402


def test_value_is_literal_after_first_equals(tmp_path):
    (tmp_path / ".env").write_text(
        "# comment\n\nYBASE_KB_PRIMARY=/Volumes/My Disk/kb=1 #x\nbad line\n", encoding="utf-8"
    )
    assert envfile.read_env(tmp_path) == {"YBASE_KB_PRIMARY": "/Volumes/My Disk/kb=1 #x"}


def test_missing_file_is_empty(tmp_path):
    assert envfile.read_env(tmp_path) == {}
    assert envfile.setting("YBASE_PROFILE", tmp_path, {}) == ""
    assert envfile.guard_enabled("PR_DRAFT", tmp_path, {}) is False


def test_unreadable_file_is_empty(tmp_path):
    (tmp_path / ".env").mkdir()
    assert envfile.read_env(tmp_path) == {}


def test_process_environment_wins(tmp_path):
    (tmp_path / ".env").write_text("YBASE_PROFILE=linux\n", encoding="utf-8")
    assert envfile.setting("YBASE_PROFILE", tmp_path, {"YBASE_PROFILE": "aws"}) == "aws"
    assert envfile.setting("YBASE_PROFILE", tmp_path, {"YBASE_PROFILE": ""}) == "linux"


def test_guard_needs_exactly_one(tmp_path):
    (tmp_path / ".env").write_text("YBASE_GUARD_PR_DRAFT=true\n", encoding="utf-8")
    assert envfile.guard_enabled("PR_DRAFT", tmp_path, {}) is False
    assert envfile.guard_enabled("PR_DRAFT", tmp_path, {"YBASE_GUARD_PR_DRAFT": "1"}) is True


def test_main_checkout_follows_a_worktree_and_leaves_other_roots_alone(tmp_path):
    main = tmp_path / "main"
    (main / ".git" / "worktrees" / "x").mkdir(parents=True)
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'x'}\n", encoding="utf-8")
    assert envfile.main_checkout(wt) == main
    assert envfile.main_checkout(main) == main  # `.git` is a directory
    assert envfile.main_checkout(tmp_path / "none") == tmp_path / "none"


def test_main_checkout_resolves_a_relative_gitdir_against_root(tmp_path, monkeypatch):
    main = tmp_path / "main"
    (main / ".git" / "worktrees" / "x").mkdir(parents=True)
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: ../main/.git/worktrees/x\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere" / "deeper"
    elsewhere.mkdir(parents=True)
    monkeypatch.chdir(elsewhere)  # a relative gitdir must not be read against the working directory
    assert envfile.main_checkout(wt) == main


def test_switch_enabled_reads_the_named_key_exactly_one(tmp_path):
    (tmp_path / ".env").write_text("YBASE_ALLOW_GATE=1\nYBASE_GUARD_ALLOW_GATE=0\n", encoding="utf-8")
    assert envfile.switch_enabled("YBASE_ALLOW_GATE", tmp_path, {}) is True
    assert envfile.switch_enabled("YBASE_ALLOW_GATE", tmp_path, {"YBASE_ALLOW_GATE": "0"}) is False
    assert envfile.switch_enabled("YBASE_ALLOW_GATE", tmp_path, {"YBASE_ALLOW_GATE": "yes"}) is False
    assert envfile.switch_enabled("YBASE_ALLOW_GATE", tmp_path / "none", {}) is False
