import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The whole shipped allow list. A `*` only ever follows a space, so `git diff` never
# covers `git difftool`; git status, diff, log and show ship in their exact forms only,
# and nothing that reads an arbitrary file (cat, grep, rg, head, tail) ships at all.
SHIPPED = {
    "Bash(pwd)", "Bash(ls)", "Bash(ls *)", "Bash(wc *)", "Bash(which *)",
    "Bash(git status)", "Bash(git diff)", "Bash(git log)", "Bash(git show)",
    "Bash(git branch --show-current)", "Bash(git remote -v)", "Bash(git rev-parse *)",
    "Bash(git ls-files)", "Bash(git ls-files *)",
    "Bash(python3 tools/checks.py)", "Bash(python3 tools/checks.py *)",
    # The project's own read-only commands, in both forms: by path and through the launcher.
    "Bash(bin/ybase check)", "Bash(bin/ybase check *)", "Bash(bin/ybase doctor --dry-run)",
    "Bash(bin/ybase repos)", "Bash(bin/ybase kb)", "Bash(bin/ybase profile)", "Bash(bin/ybase env)",
    "Bash(ybase check)", "Bash(ybase check *)", "Bash(ybase doctor --dry-run)",
    "Bash(ybase repos)", "Bash(ybase kb)", "Bash(ybase profile)", "Bash(ybase env)",
}


def shipped_allow():
    return json.loads((ROOT / ".claude/settings.json").read_text())["permissions"]["allow"]


def test_shipped_permissions_are_exactly_the_reviewed_set():
    allow = shipped_allow()
    assert len(allow) == len(set(allow))
    assert set(allow) == SHIPPED


def test_no_wildcard_without_a_space_before_it():
    for entry in shipped_allow():
        assert not re.search(r"(?<! )\*", entry), entry


def test_every_hook_file_is_wired():
    hooks = json.loads((ROOT / ".claude/settings.json").read_text())["hooks"]
    text = json.dumps(hooks)
    for f in (ROOT / ".claude/hooks").glob("*.py"):
        assert f.name in text, f.name
