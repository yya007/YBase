"""No tracked file names a private term.

The terms themselves can never be written into a tracked file, so the test reads
them from YBASE_TEST_DENY (terms separated by `|`) and is skipped without it.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

EXCLUDED: list[str] = []


def test_no_private_terms_in_tracked_files():
    deny = os.environ.get("YBASE_TEST_DENY", "")
    if not deny:
        pytest.skip("YBASE_TEST_DENY is not set")
    out = subprocess.run(
        ["git", "-C", str(ROOT), "grep", "-n", "-i", "-E", deny, "--", ".", *EXCLUDED],
        capture_output=True,
        text=True,
    ).stdout
    assert out == ""
