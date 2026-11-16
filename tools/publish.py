"""Publish this clone to a public repository, and take public contributions back.

    python3 tools/publish.py publish [--dry-run] [--skip-tests]
    python3 tools/publish.py absorb

Run through `ybase publish` and `ybase absorb`. The public repository is the
machine setting YBASE_PUBLIC_REPO: a GitHub `owner/name`, or any git URL or path.

publish
    Exports the committed tree at HEAD, less the paths in `.publishignore`, into a clone
    of the public repository and runs the gate there: the check registry with this
    machine's deny lists, the publication checks below, and the test suite. Only when all
    pass does it commit one snapshot and push it as branch `sync/<short rev>`, then open
    a pull request (GitHub `owner/name` only). The first publish to an empty repository
    pushes the default branch itself, because a pull request needs a base. No private
    commit, message or author leaves: the public history is made of snapshots.
    `--dry-run` runs the gate and pushes nothing. `--skip-tests` leaves the test suite out
    and says so in the pull request.

absorb
    Fetches the public default branch and cherry-picks, onto the current branch, every
    public commit that is neither a snapshot from here nor already absorbed. The
    contributor stays the author. Run it in a worktree, then run the gate before landing.

Publication checks: LICENSE, README.md, CONTRIBUTING.md and SECURITY.md exist; the licence
is the one named in LICENSE_NAME; no ignored path survived the export; no symlink leaves
the tree; no file is larger than MAX_BYTES; no `.env` file is present; `gitleaks` finds
nothing when it is installed (skipped, and reported as skipped, when it is not).

Standard library only.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import envfile  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
IGNORE_FILE = ".publishignore"
LICENSE_NAME = "PolyForm Noncommercial License 1.0.0"
REQUIRED = ("LICENSE", "README.md", "CONTRIBUTING.md", "SECURITY.md")
MAX_BYTES = 1_000_000
TRAILER = "Upstream-Rev"
PICKED = "cherry picked from commit "


class Refused(Exception):
    """The command stops and nothing is pushed."""


# The branch a first publish creates in an empty public repository.
FIRST_BRANCH = "master"

def git(cwd: Path, *args: str, check: bool = True, env: dict | None = None) -> str:
    res = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=env)
    if check and res.returncode != 0:
        raise Refused(f"git {' '.join(args[:2])} failed: {res.stderr.strip()[:300]}")
    return res.stdout.strip()


def public_url(root: Path) -> tuple[str, str]:
    """(git URL, GitHub slug or '') from YBASE_PUBLIC_REPO."""
    value = envfile.setting("YBASE_PUBLIC_REPO", envfile.main_checkout(root))
    if not value:
        raise Refused("YBASE_PUBLIC_REPO is not set in .env; set it to owner/name or a git URL")
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value) and not Path(value).exists():
        return "git" f"@github.com:{value}.git", value
    return value, ""


def ignored(root: Path) -> list[str]:
    """Paths left out of the export: the lines of .publishignore, and the file itself.
    A line ending in `/` names a folder."""
    lines = [IGNORE_FILE]
    try:
        text = (root / IGNORE_FILE).read_text(encoding="utf-8")
    except OSError:
        return lines
    lines += [s for s in (line.strip() for line in text.splitlines()) if s and not s.startswith("#")]
    return lines


def export_tree(root: Path, rev: str, dest: Path) -> list[str]:
    """Write the tree at `rev`, less the ignored paths, into `dest`. Returns those paths."""
    dest.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(["git", "-C", str(root), "archive", rev], capture_output=True, check=True)
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True)
    drop = ignored(root)
    for rel in drop:
        target = dest / rel.rstrip("/")
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        elif target.exists() or target.is_symlink():
            target.unlink()
    return drop


def publication_findings(tree: Path, drop: list[str]) -> tuple[list[str], list[str]]:
    """(findings, notes) from the publication checks over the files in `tree`."""
    bad: list[str] = []
    notes: list[str] = []
    for name in REQUIRED:
        if not (tree / name).is_file():
            bad.append(f"{name} is missing")
    licence = tree / "LICENSE"
    if licence.is_file() and LICENSE_NAME not in licence.read_text(encoding="utf-8", errors="replace"):
        bad.append(f"LICENSE is not the {LICENSE_NAME}")
    for rel in drop:
        if (tree / rel.rstrip("/")).exists():
            bad.append(f"{rel} is in {IGNORE_FILE} but is still in the export")
    real = tree.resolve()
    for p in sorted(tree.rglob("*")):
        rel = p.relative_to(tree).as_posix()
        if rel == ".git" or rel.startswith(".git/"):
            continue
        if p.is_symlink():
            if real not in p.resolve().parents and p.resolve() != real:
                bad.append(f"{rel} is a symlink that leaves the tree")
            continue
        if not p.is_file():
            continue
        if p.name == ".env" or (p.name.startswith(".env.") and p.name != ".env.example"):
            bad.append(f"{rel} is an environment file")
        if p.stat().st_size > MAX_BYTES:
            bad.append(f"{rel} is larger than {MAX_BYTES} bytes")
    if shutil.which("gitleaks"):
        res = subprocess.run(["gitleaks", "dir", str(tree), "--no-banner", "--redact"],
                             capture_output=True, text=True)
        if res.returncode != 0:
            bad.append("gitleaks reported findings: " + (res.stdout + res.stderr).strip()[-300:])
    else:
        notes.append("gitleaks is not installed, so the second secret scan was skipped")
    return bad, notes


def run_gate(root: Path, clone: Path, drop: list[str], skip_tests: bool) -> tuple[list[str], list[str]]:
    """(findings, notes): every reason the export in `clone` may not be published."""
    bad, notes = publication_findings(clone, drop)
    env = dict(os.environ, YB_ROOT=str(clone))
    main = envfile.main_checkout(root)
    for key in ("YBASE_KB_PRIMARY", "YBASE_KB_PATHS"):
        value = envfile.setting(key, main)
        if value:
            env[key] = value
    checks = clone / "tools" / "checks.py"
    if checks.is_file():
        res = subprocess.run([sys.executable, str(checks)], capture_output=True, text=True, env=env)
        deny = re.search(r"deny list: (\d+) terms", res.stdout)
        if res.returncode != 0:
            bad.append("the check registry failed on the export:\n" + res.stdout.strip()[-1500:])
        if not deny or deny.group(1) == "0":
            bad.append("the leak scan ran with no deny-list terms; set the knowledge base in .env")
    else:
        bad.append("tools/checks.py is missing from the export")
    if skip_tests:
        notes.append("the test suite was skipped (--skip-tests)")
    elif not bad:
        if not shutil.which("uv"):
            bad.append("uv is not installed, so the export's tests cannot run")
        else:
            # The tests see no machine settings: they must pass for a stranger.
            clean = {k: v for k, v in os.environ.items()
                     if not k.startswith(("YBASE_", "YB_")) and k != "PYTHONDONTWRITEBYTECODE"}
            res = subprocess.run(["uv", "run", "--extra", "dev", "pytest", "-q", "-x"],
                                 cwd=clone, capture_output=True, text=True, env=clean)
            if res.returncode != 0:
                bad.append("the export's own tests failed:\n" + res.stdout.strip()[-1500:])
            else:
                notes.append("tests: " + res.stdout.strip().splitlines()[-1])
    return bad, notes


def replace_tree(clone: Path, export: Path) -> None:
    for child in clone.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    shutil.copytree(export, clone, symlinks=True, dirs_exist_ok=True)


def publish(root: Path, dry_run: bool, skip_tests: bool) -> int:
    url, slug = public_url(root)
    if git(root, "status", "--porcelain", "--untracked-files=no"):
        raise Refused("tracked files have uncommitted changes; publish exports the committed tree")
    rev = git(root, "rev-parse", "HEAD")
    upstream = git(root, "rev-parse", "--verify", "--quiet", "@{u}", check=False)
    if not dry_run and upstream and upstream != rev:
        raise Refused("HEAD is not the pushed upstream tip; push or pull first, publish only ships what is pushed")

    with tempfile.TemporaryDirectory(prefix="ybase-publish-") as scratch:
        work = Path(scratch)
        export, clone = work / "export", work / "public"
        drop = export_tree(root, rev, export)
        git(work, "clone", "--quiet", url, str(clone))
        first = not git(clone, "rev-parse", "--verify", "--quiet", "HEAD", check=False)
        if not first:
            waiting = unabsorbed(root, url)
            if waiting:
                raise Refused(f"{len(waiting)} public commit(s) are not absorbed yet (first: {waiting[0][:10]}); "
                              "run ybase absorb and land it, or this snapshot would undo them")
        base = FIRST_BRANCH if first else git(clone, "symbolic-ref", "--short", "HEAD")
        branch = base if first else f"sync/{rev[:10]}"
        git(clone, "checkout", "--quiet", "-B", branch)
        replace_tree(clone, export)
        git(clone, "add", "-A")
        if not first and not git(clone, "status", "--porcelain"):
            print("nothing to publish: the public repository already has this tree")
            return 0

        # Commit in the scratch clone first: the gate reads the commit it would push, and
        # the tests clone it. Nothing leaves until the gate passes.
        git(clone, "commit", "--quiet", "-m", f"Sync from upstream\n\n{TRAILER}: {rev}")
        bad, notes = run_gate(root, clone, drop, skip_tests)
        for note in notes:
            print(f"note: {note}")
        if bad:
            for b in bad:
                print(f"REFUSED: {b}", file=sys.stderr)
            return 1
        if git(clone, "status", "--porcelain"):
            raise Refused("the gate changed files in the export; nothing was pushed")
        print("first publish" if first else git(clone, "show", "--stat", "--format=", "HEAD").splitlines()[-1])
        if dry_run:
            print("dry run: the gate passed and nothing was pushed")
            return 0

        git(clone, "push", "--quiet", "origin", f"HEAD:refs/heads/{branch}")
        if first:
            print(f"published the first snapshot to {base}")
        elif slug:
            body = "Snapshot from upstream.\n\nGate: check registry, publication checks" + \
                   ("".join(f"\n- {n}" for n in notes))
            res = subprocess.run(["gh", "pr", "create", "--repo", slug, "--base", base, "--head", branch,
                                  "--title", "Sync from upstream", "--body", body],
                                 capture_output=True, text=True)
            if res.returncode != 0:
                raise Refused(f"pushed {branch}, but gh could not open the pull request: {res.stderr.strip()[:300]}")
            print(res.stdout.strip())
        else:
            print(f"pushed {branch}; open a pull request into {base}")
    return 0


def unabsorbed(root: Path, url: str) -> list[str]:
    """Public commits, oldest first, that are neither a snapshot from here nor absorbed."""
    git(root, "fetch", "--quiet", url, "HEAD")
    tip = git(root, "rev-parse", "FETCH_HEAD")
    out = []
    for sha in git(root, "rev-list", "--reverse", "--no-merges", tip).splitlines():
        if re.search(rf"^{TRAILER}: ", git(root, "log", "-1", "--format=%B", sha), re.M):
            continue
        if git(root, "log", "--all", "--fixed-strings", f"--grep={PICKED}{sha}", "--format=%H", "-1"):
            continue
        out.append(sha)
    return out


def absorb(root: Path) -> int:
    url, _ = public_url(root)
    if git(root, "status", "--porcelain", "--untracked-files=no"):
        raise Refused("tracked files have uncommitted changes; commit them first")
    taken = 0
    for sha in unabsorbed(root, url):
        # An empty pick is kept, so every public commit has a record here.
        res = subprocess.run(["git", "-C", str(root), "cherry-pick", "-x", "--allow-empty",
                              "--keep-redundant-commits", sha], capture_output=True, text=True)
        if res.returncode != 0:
            unmerged = git(root, "diff", "--name-only", "--diff-filter=U").split()
            raise Refused(f"{sha[:10]} does not apply cleanly ({unmerged[0] if unmerged else 'see git status'}); "
                          "resolve it, then run git cherry-pick --continue and absorb again")
        taken += 1
        print(f"absorbed {sha[:10]} {git(root, 'log', '-1', '--format=%an: %s', sha)}")
    print(f"{taken} public commit(s) absorbed; run the gate before landing them")
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help") or argv[0] not in ("publish", "absorb"):
        print(__doc__)
        return 0 if argv and argv[0] in ("-h", "--help") else 2
    root = Path(os.environ.get("YB_ROOT", ROOT))
    flags = set(argv[1:])
    unknown = flags - {"--dry-run", "--skip-tests"}
    if unknown or (argv[0] == "absorb" and flags):
        print(f"unknown option(s): {' '.join(sorted(unknown or flags))}", file=sys.stderr)
        return 2
    try:
        if argv[0] == "publish":
            return publish(root, "--dry-run" in flags, "--skip-tests" in flags)
        return absorb(root)
    except Refused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
