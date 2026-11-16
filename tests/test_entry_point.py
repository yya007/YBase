import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_entry_point_lists_engine_commands():
    out = subprocess.run(["/bin/bash", str(ROOT / "bin" / "ybase"), "help"],
                         capture_output=True, text=True).stdout
    for word in ("setup", "doctor", "profile", "wt", "worktrees", "env", "hooks", "check",
                 "publish", "absorb"):
        assert word in out
