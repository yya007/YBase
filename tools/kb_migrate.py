#!/usr/bin/env python3
"""kb_migrate: bring a knowledge base's layout up to the version this YBase knows.

    kb_migrate.py [PATH] [--dry-run]

A KB's `VERSION` file holds an integer layout version. `MIGRATIONS` maps a
from-version to (description, step); each step moves a KB from that version to the
next. `VERSION` is rewritten after each finished step, so a failure leaves it at the
last step that completed. This does no git work and never downgrades a KB.
"""
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURRENT: int = int((ROOT / "templates" / "kb" / "VERSION").read_text(encoding="utf-8").strip())
# from-version -> (one-line description, step). The layout is at version 1: no steps yet.
MIGRATIONS: dict[int, tuple[str, Callable[[Path], None]]] = {}


def read_version(kb: Path) -> int | None:
    try:
        return int((kb / "VERSION").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def plan(kb: Path) -> list[tuple[int, str]]:
    """Steps still to run as (from-version, description). Raises ValueError if it cannot."""
    if not kb.is_dir():
        raise ValueError(
            f'{kb} is missing (an unmounted disk, or a branch not merged yet?); check the path, '
            "or set the right primary with `ybase kb primary PATH`"
        )
    version = read_version(kb)
    if not (kb / "memory" / "INDEX.md").is_file():
        hint = f'; to create one run `ybase kb init "{kb}"`' if version is None else ""
        raise ValueError(f"{kb} does not look like a knowledge base (needs VERSION and memory/INDEX.md){hint}")
    if version is None:
        raise ValueError(f'{kb} has no readable VERSION file; run `ybase kb init "{kb}"`')
    if version > CURRENT:
        raise ValueError(
            f"{kb} is at layout version {version} but this YBase knows {CURRENT}; "
            "update YBase (`ybase update`) rather than migrating"
        )
    steps = []
    for frm in range(version, CURRENT):
        if frm not in MIGRATIONS:
            raise ValueError(f"no migration from layout version {frm} to {frm + 1}; nothing was changed")
        steps.append((frm, MIGRATIONS[frm][0]))
    return steps


def migrate(kb: Path, dry_run: bool) -> int:
    try:
        steps = plan(kb)
    except ValueError as err:
        print(f"kb migrate: {err}", file=sys.stderr)
        return 1
    if not steps:
        print(f"kb migrate: {kb} is up to date (layout version {CURRENT})")
        return 0
    for frm, description in steps:
        print(f"{'would run' if dry_run else 'running'} {frm} -> {frm + 1}: {description}")
    if dry_run:
        return 0
    for frm, description in steps:
        try:
            MIGRATIONS[frm][1](kb)
        except Exception as err:  # a step may fail any way; stop at the last finished version
            print(f"kb migrate: step {frm} -> {frm + 1} failed ({err}); "
                  f"{kb} stays at layout version {frm}", file=sys.stderr)
            return 1
        (kb / "VERSION").write_text(f"{frm + 1}\n", encoding="utf-8")
    print(f"kb migrate: {kb} is now at layout version {CURRENT}")
    return 0


def main(argv: list[str]) -> int:
    usage = "usage: ybase kb migrate [PATH] [--dry-run]"
    if any(a in ("-h", "--help") for a in argv):
        print(usage)
        return 0
    dry_run = "--dry-run" in argv
    rest = [a for a in argv if a != "--dry-run"]
    paths = [a for a in rest if not a.startswith("-")]
    if len(paths) != 1 or len(paths) != len(rest):
        print(usage, file=sys.stderr)
        return 2
    return migrate(Path(paths[0]), dry_run)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
