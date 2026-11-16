#!/usr/bin/env python3
"""The managed repo list: parse `repos.md` from the knowledge base, resolve local paths
from `.env`, and write the pointer file every session loads (`.ybase/REPOS.md`).

  repos.py                list repos: name, path, present|missing
  repos.py render         write .ybase/REPOS.md
  repos.py path NAME      print the repo's local path
  repos.py clone NAME     clone the remote to the path when the path is absent

Standard library only.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import envfile  # noqa: E402

POINTER_LIMIT = 20
HEADER = ("Name", "What it is", "Remote", "Hint")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_SEPARATOR = re.compile(r"\|?(\s*:?-+:?\s*\|)+\s*:?-*:?\s*\Z")


class Repo(NamedTuple):
    name: str
    what: str
    remote: str
    hint: str
    area: str


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_row(line: str) -> bool:
    return line.strip().startswith("|")


def _is_separator(line: str) -> bool:
    return _is_row(line) and bool(_SEPARATOR.match(line.strip()))


def _parse_file(path: Path, area: str) -> list[Repo]:
    """Rows of every table headed by HEADER. The `|---|` separator after the header is
    skipped when present. Blank lines inside the body (left, for example, by a removed HTML
    comment) do not end the table; a line that is neither a row nor blank does, and so does
    the header of another table (a row followed by a separator)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    lines = _COMMENT.sub("", text).splitlines()
    found: list[Repo] = []
    i = 0
    while i < len(lines):
        if not (_is_row(lines[i]) and tuple(_cells(lines[i])) == HEADER):
            i += 1
            continue
        i += 1
        if i < len(lines) and _is_separator(lines[i]):
            i += 1
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            if not _is_row(line) or (i + 1 < len(lines) and _is_separator(lines[i + 1])):
                break
            cells = _cells(line) + [""] * 4
            if cells[0] and not _is_separator(line):
                found.append(Repo(cells[0], cells[1], cells[2], cells[3], area))
            i += 1
    return found


def parse_repos(kb_root: Path) -> list[Repo]:
    kb_root = Path(kb_root)
    found = _parse_file(kb_root / "repos.md", "")
    areas = sorted((kb_root / "repos").glob("*.md")) if (kb_root / "repos").is_dir() else []
    for f in areas:
        found += _parse_file(f, f.stem)
    return found


def all_repos(root: Path, environ: Mapping[str, str] | None = None) -> list[Repo]:
    """Repos from every KB root, primary first; a name seen earlier wins."""
    seen: set[str] = set()
    merged: list[Repo] = []
    for kb in envfile.kb_roots(root, environ):
        for r in parse_repos(kb):
            if r.name.lower() not in seen:
                seen.add(r.name.lower())
                merged.append(r)
    return merged


def env_key(name: str) -> str:
    return "YBASE_REPO_PATH_" + re.sub(r"[^A-Z0-9]", "_", name.upper())


def repo_path(repo: Repo, root: Path, environ: Mapping[str, str] | None = None) -> Path:
    override = envfile.setting(env_key(repo.name), root, environ)
    if override:
        return Path(override)
    base = envfile.setting("YBASE_REPOS_ROOT", root, environ)
    return (Path(base) if base else Path(root).parent) / repo.name


def find(name: str, root: Path, environ: Mapping[str, str] | None = None) -> Repo | None:
    for kb in envfile.kb_roots(root, environ):
        for r in parse_repos(kb):
            if r.name.lower() == name.lower():
                return r
    return None


def _area_file(area: str, root: Path, environ: Mapping[str, str] | None) -> Path:
    roots = envfile.kb_roots(root, environ)
    for kb in roots:
        if (kb / "repos" / f"{area}.md").is_file():
            return kb / "repos" / f"{area}.md"
    return roots[0] / "repos" / f"{area}.md"


def _line(r: Repo, root: Path, environ: Mapping[str, str] | None) -> str:
    path = repo_path(r, root, environ)
    if path.exists():
        state = "present"
    elif r.remote:
        state = f"missing; clone: `{r.remote}`"
    else:
        state = "missing; no remote recorded"
    text = f"- **{r.name}**: {r.what}. Path: `{path}` ({state})."
    return f"{text} {r.hint}" if r.hint else text


def render_pointers(repos: list[Repo], root: Path, environ: Mapping[str, str] | None = None) -> str:
    out = [
        "# Managed repos (generated; edit `repos.md` in the primary KB)",
        "",
        "If a path is present, work there. If it is missing, clone the remote to that path first.",
        "",
    ]
    collapse = len(repos) > POINTER_LIMIT and any(r.area for r in repos)
    areas: dict[str, int] = {}
    for r in repos:
        if collapse and r.area:
            areas[r.area] = areas.get(r.area, 0) + 1
        else:
            out.append(_line(r, root, environ))
    for area, n in areas.items():
        out.append(f"- Area **{area}**: {n} repos, listed in `{_area_file(area, root, environ)}`")
    return "\n".join(out) + "\n"


def _root() -> Path:
    return Path(os.environ.get("YB_ROOT") or Path(__file__).resolve().parent.parent)


def main(argv: list[str]) -> int:
    root = _root()
    cmd = argv[0] if argv else "list"
    if cmd == "list":
        for r in all_repos(root):
            p = repo_path(r, root)
            print(f"{r.name}\t{p}\t{'present' if p.exists() else 'missing'}")
        return 0
    if cmd == "render":
        out = root / ".ybase" / "REPOS.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_pointers(all_repos(root), root), encoding="utf-8")
        print("wrote .ybase/REPOS.md")
        return 0
    if cmd in ("path", "clone") and len(argv) == 2:
        r = find(argv[1], root)
        if r is None:
            print(f"repos: unknown repo '{argv[1]}' (see 'ybase repos')", file=sys.stderr)
            return 1
        p = repo_path(r, root)
        if cmd == "path":
            print(p)
            return 0
        if not r.remote:
            print(f"repos: '{r.name}' has no remote recorded; add one to repos.md", file=sys.stderr)
            return 1
        if p.exists():
            print(f"{p} already present")
            return 0
        try:
            return subprocess.run(["git", "clone", "--", r.remote, str(p)]).returncode
        except OSError as e:
            print(f"repos: cannot run git ({e.strerror}); install git and retry", file=sys.stderr)
            return 1
    print("usage: repos [render | path NAME | clone NAME]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
