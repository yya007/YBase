#!/usr/bin/env python3
"""checks.py: content checks for one research topic laid out from this template.

    python3 checks.py <topic-dir> [more topic dirs...]

A topic dir holds a CASE.md whose frontmatter is the manifest: `name`, `summary`,
`stages`, and for a literature stage `notes_dir`, `catalog` and `note_required_keys`.
Three checks read it:

    case-manifests   the manifest names the topic and lists stages that exist
    source-notes     every source note carries the frontmatter keys the manifest requires
    catalog          every source note has a row in the catalog

Each check returns (scanned, findings), as in YBase's check registry.
Stdlib only, so a knowledge base can run it without YBase.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

STAGES = ("literature", "understanding", "analysis", "opportunities", "projects")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
MAX_SHOWN = 25


def frontmatter(text: str) -> dict[str, object]:
    """Parse the small YAML subset a manifest uses: `key: value` and `key: [a, b]`."""
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    meta: dict[str, object] = {}
    for line in text[4:end].splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val.startswith("[") and val.endswith("]"):
            meta[key] = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
        else:
            meta[key] = val.strip("'\"")
    return meta


def manifest(d: Path) -> dict[str, object]:
    f = d / "CASE.md"
    return frontmatter(f.read_text(encoding="utf-8")) if f.is_file() else {}


def rel(p: Path, d: Path) -> str:
    return str(p.relative_to(d.parent))


def check_case_manifests(d: Path):
    """The topic has a CASE.md whose frontmatter names it and lists stages that exist."""
    name = d.name
    if not (d / "CASE.md").is_file():
        return 1, [f"{name}/CASE.md: missing"]
    meta = manifest(d)
    bad = []
    if meta.get("name") != name:
        bad.append(f"{name}/CASE.md: frontmatter name is {meta.get('name')!r}, expected {name!r}")
    if not meta.get("summary"):
        bad.append(f"{name}/CASE.md: missing summary")
    stages = meta.get("stages")
    if not isinstance(stages, list) or not stages:
        bad.append(f"{name}/CASE.md: stages must be a non-empty list")
        return 1, bad
    for s in stages:
        if s not in STAGES:
            bad.append(f"{name}/CASE.md: unknown stage {s!r} (known: {', '.join(STAGES)})")
        elif not (d / s).is_dir():
            bad.append(f"{name}/CASE.md: stage {s!r} listed but {name}/{s}/ is missing")
    return 1, bad


def case_notes(d: Path, meta: dict[str, object]) -> list[Path]:
    nd = meta.get("notes_dir")
    if not isinstance(nd, str) or not (d / nd).is_dir():
        return []
    return sorted(p for p in (d / nd).glob("*.md") if p.name not in ("README.md", "CATALOG.md"))


def check_source_notes(d: Path):
    """Every source note carries the frontmatter keys the manifest requires."""
    meta = manifest(d)
    keys = meta.get("note_required_keys") or []
    scanned, bad = 0, []
    for note in case_notes(d, meta):
        scanned += 1
        fm = frontmatter(note.read_text(encoding="utf-8"))
        missing = [k for k in keys if not fm.get(k)]
        if missing:
            bad.append(f"{rel(note, d)}: missing frontmatter {', '.join(missing)}")
    return scanned, bad


def check_catalog(d: Path):
    """Every source note has a row in the topic's catalog, and no row points at a missing note."""
    meta = manifest(d)
    cat = meta.get("catalog")
    if not isinstance(cat, str):
        return 0, []
    cat_path = d / cat
    if not cat_path.is_file():
        return 0, [f"{d.name}: catalog {cat} not found"]
    text = cat_path.read_text(encoding="utf-8")
    linked = {(cat_path.parent / t.split("#")[0]).resolve() for t in LINK_RE.findall(text)}
    scanned, bad = 0, []
    for note in case_notes(d, meta):
        scanned += 1
        if note.resolve() not in linked:
            bad.append(f"{rel(note, d)}: no row in {rel(cat_path, d)}")
    return scanned, bad


CHECKS = [
    ("case-manifests", check_case_manifests),
    ("source-notes", check_source_notes),
    ("catalog", check_catalog),
]


def main(argv: list[str]) -> int:
    if not argv or "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0 if argv else 2
    failed = 0
    for arg in argv:
        d = Path(arg).resolve()
        if not d.is_dir():
            print(f"not a directory: {arg}", file=sys.stderr)
            return 2
        for name, fn in CHECKS:
            scanned, bad = fn(d)
            if bad:
                failed += 1
                print(f"FAIL {name} ({d.name}): {len(bad)} finding(s), scanned {scanned}")
                for b in bad[:MAX_SHOWN]:
                    print(f"     {b}")
                if len(bad) > MAX_SHOWN:
                    print(f"     ... and {len(bad) - MAX_SHOWN} more")
            else:
                print(f"pass {name} ({d.name}): scanned {scanned}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
