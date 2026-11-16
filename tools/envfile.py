"""Read YBase's machine settings from the repo-root `.env`.

Format: one KEY=VALUE per line. The value is everything after the first `=`,
taken literally (no quotes, escapes or inline comments). Blank lines and lines
starting with `#` are ignored, as is any line whose key is not [A-Z][A-Z0-9_]*.
The file is parsed, never sourced. A missing or unreadable file reads as empty.
Standard library only.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path

_KEY = re.compile(r"[A-Z][A-Z0-9_]*\Z")


def read_env(root: Path) -> dict[str, str]:
    try:
        text = (Path(root) / ".env").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if _KEY.match(key):
            values[key] = value
    return values


def setting(key: str, root: Path, environ: Mapping[str, str] | None = None) -> str:
    """The process environment's value when non-empty, else the file's, else ''."""
    env = os.environ if environ is None else environ
    return env.get(key) or read_env(root).get(key, "")


def main_checkout(root: Path) -> Path:
    """The main checkout that `root` belongs to. A linked worktree has no `.env` of its own;
    its `.git` file names the main checkout's git directory (`<main>/.git/worktrees/<name>`),
    absolute or relative to `root`. Any other root, or one that cannot be read, is returned
    unchanged."""
    root = Path(root)
    try:
        gitdir = Path((root / ".git").read_text(encoding="utf-8").split(":", 1)[1].strip())
    except (OSError, UnicodeDecodeError, IndexError):
        return root
    if not gitdir.is_absolute():
        gitdir = Path(os.path.normpath(root / gitdir))
    if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
        return gitdir.parent.parent.parent
    return root


def switch_enabled(key: str, root: Path, environ: Mapping[str, str] | None = None) -> bool:
    """True when the setting `key` is exactly `1` (process environment first, then `.env`)."""
    return setting(key, root, environ) == "1"


def guard_enabled(name: str, root: Path, environ: Mapping[str, str] | None = None) -> bool:
    return switch_enabled(f"YBASE_GUARD_{name}", root, environ)


def kb_roots(root: Path, environ: Mapping[str, str] | None = None) -> list[Path]:
    """Knowledge-base roots, primary first: YBASE_KB_PRIMARY (default `<root>/kb`), then
    the `:`-separated YBASE_KB_PATHS. Duplicates are dropped; a root need not exist."""
    primary = setting("YBASE_KB_PRIMARY", root, environ) or str(Path(root) / "kb")
    extras = setting("YBASE_KB_PATHS", root, environ).split(":")
    roots: list[Path] = []
    for raw in [primary, *extras]:
        if raw and Path(raw) not in roots:
            roots.append(Path(raw))
    return roots
