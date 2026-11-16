#!/usr/bin/env python3
"""worktrees.py: inventory every linked worktree of a repository, and reap the safe ones.

    python3 tools/worktrees.py                 report, for this repository
    python3 tools/worktrees.py --repo X        report for another repository: a path, or the
                                               name of a managed repo from the repo list
    python3 tools/worktrees.py --landing REF   the ref that counts as landed; repeat it when
                                               work can land on more than one (landed on any)
    python3 tools/worktrees.py --findings      also judge every uncommitted, untracked and
                                               stashed path, and every unlanded commit
    python3 tools/worktrees.py --idle-days N   keep anything git acted in within N days (default 1)
    python3 tools/worktrees.py --json          machine-readable report
    python3 tools/worktrees.py --reap          remove every worktree whose verdict is `reap`

For each worktree it measures, rather than guesses:
  dirty      tracked files with uncommitted changes
  untracked  files git does not track and does not ignore
  ignored    ignored paths; `git worktree remove` deletes them with the tree
  unpushed   commits reachable from HEAD and from no remote ref
  behind     commits on the landing ref that HEAD lacks
  landed     every commit on the branch is in a landing ref by patch (`git cherry`),
             or the branch's whole change is: a squash landing still counts
  idle_days  since git last acted in it: its admin files and its last reflog entry,
             not the mtime of logs/, which `git gc` rewrites for every worktree at once
  locked     `git worktree lock` was set
  current    this process is running inside it
  in_use     a live process has its working directory inside it
  broken     the directory exists but its `.git` is gone (a removal stopped part-way)

Verdicts:
  keep    something would be lost, someone is using it, or a check could not run;
          the reason says which
  reap    every check ran and was clear: no dirty or untracked files, nothing
          unpushed or everything landed, not locked, not current, not in use,
          idle longer than --idle-days
  prune   the directory is gone and not locked; only git's registration remains
  main    the main checkout, never touched

--findings judges each path by content against the landing refs, never by path
alone, because a rebase rewrites every sha and a reorganization every path:
  landed              identical content at this path (or deleted on both sides)
  superseded          identical content at another path, or an older version of
                      this same path: nothing here is newer than the landing ref
  differs             the landing ref has this path with other content
  removed-on-landing  the landing ref deleted or moved this path on purpose
  novel               neither the path nor the content is on any landing ref
  unknown             the content could not be read
It also lists the stash, which every worktree shares, judged the same way, and
directories beside the worktrees that no registration names.

`--reap` runs `git worktree remove` (never --force), `git worktree prune` for
gone registrations, and deletes a branch only with `git branch -d`, which refuses
an unmerged branch. Nothing else writes. Stdlib only; runs on Linux and macOS.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EMPTY_BLOBS = {"e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
               "473a0f4c3be8a93681a267e3b1e9a7dcda1185436fe141f7749120a303721813"}
MAX_PATHSPEC = 1000  # paths per git call, well under ARG_MAX on Linux and macOS


def run(repo: Path, *args: str, stdin: str | None = None, env: dict | None = None) -> tuple[int, str, str]:
    r = subprocess.run(["git", "-C", str(repo), *args], input=stdin, capture_output=True, text=True,
                       env={**os.environ, **env} if env else None)
    return r.returncode, r.stdout, r.stderr.strip()


def git(repo: Path, *args: str, check: bool = True) -> str:
    rc, out, err = run(repo, *args)
    if check and rc != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {repo}: {err}")
    return out


def chunks(xs: list[str], n: int = MAX_PATHSPEC):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


LITERAL = {"GIT_LITERAL_PATHSPECS": "1"}


@dataclass
class Worktree:
    path: str
    head: str = ""
    branch: str = ""
    main: bool = False
    exists: bool = True
    broken: bool = False
    locked: bool = False
    current: bool = False
    dirty: int = 0
    untracked: int = 0
    ignored: int = 0
    unpushed: int = 0
    behind: int = 0
    idle_days: float = -1.0
    landed: bool = False
    landed_how: str = ""
    in_use: list[str] = field(default_factory=list)
    unlanded_commits: list[str] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    verdict: str = ""
    reason: str = ""


def list_worktrees(repo: Path) -> list[Worktree]:
    out = git(repo, "worktree", "list", "--porcelain")
    res: list[Worktree] = []
    cur: Worktree | None = None
    for line in out.splitlines() + [""]:
        if line.startswith("worktree "):
            cur = Worktree(path=line[len("worktree "):])
        elif cur is None:
            continue
        elif line.startswith("HEAD "):
            cur.head = line[5:]
        elif line.startswith("branch "):
            ref = line[len("branch "):]
            cur.branch = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
        elif line.startswith("locked"):
            cur.locked = True
        elif line == "":
            res.append(cur)
            cur = None
    if res:
        res[0].main = True  # git always lists the main worktree first
    return res


def landing_refs(repo: Path, explicit: list[str] | None) -> list[str]:
    if explicit:
        return explicit
    sym = git(repo, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD", check=False).strip()
    if sym:
        return [sym]
    for cand in ("origin/master", "origin/main", "master", "main"):
        if git(repo, "rev-parse", "-q", "--verify", cand, check=False).strip():
            return [cand]
    return ["HEAD"]


# ---------------------------------------------------------------- processes
def is_inside(child: str, parent: str) -> bool:
    return child == parent or child.startswith(parent.rstrip(os.sep) + os.sep)


def scan_processes() -> tuple[list[tuple[str, str, str]] | None, int | None]:
    """(pid, command, cwd) for every process whose cwd we can read, and how many of
    our own processes we could not read. None for the list means the scan could not run."""
    me = str(os.getpid())
    found: list[tuple[str, str, str]] = []
    proc = Path("/proc")
    if proc.is_dir() and (proc / "self" / "cwd").exists():
        uid, opaque = os.getuid(), 0
        for p in proc.iterdir():
            if not p.name.isdigit() or p.name == me:
                continue
            try:
                cwd = os.readlink(p / "cwd")
                cmd = (p / "comm").read_text().strip()
            except PermissionError:
                try:
                    opaque += p.stat().st_uid == uid
                except OSError:
                    pass
                continue
            except OSError:
                continue
            found.append((p.name, cmd, cwd))
        return found, opaque
    # macOS and other BSDs: no /proc; lsof reports each process's cwd.
    try:
        r = subprocess.run(["lsof", "-a", "-d", "cwd", "-Fpcn"], capture_output=True, text=True)
    except OSError:
        return None, None
    pid = cmd = ""
    for line in r.stdout.splitlines():
        tag, val = line[:1], line[1:]
        if tag == "p":
            pid = val
        elif tag == "c":
            cmd = val
        elif tag == "n" and pid != me:
            found.append((pid, cmd, val))
    return found, None


# ---------------------------------------------------------------- content
class Landing:
    """Every blob on the landing refs, by path and by content."""

    def __init__(self, repo: Path, refs: list[str]):
        self.repo, self.refs = repo, refs
        self.at: dict[str, set[str]] = {}
        self.where: dict[str, str] = {}
        for ref in refs:
            for rec in git(repo, "ls-tree", "-r", "-z", ref).split("\0"):
                if not rec:
                    continue
                meta, path = rec.split("\t", 1)
                _mode, typ, sha = meta.split()
                if typ == "blob":
                    self.at.setdefault(path, set()).add(sha)
                    self.where.setdefault(sha, path)

    def classify(self, path: str, blob: str | None) -> tuple[str, str]:
        """blob None = deleted here; "" = a directory git does not descend into."""
        if blob is None:
            if path not in self.at:
                return "landed", "deleted here, and absent from the landing ref too"
            return "differs", "deleted here; the landing ref still has it"
        if blob == "":
            return "novel", "a directory git does not descend into (a nested repository?)"
        if blob in self.at.get(path, ()):
            return "landed", "identical content at this path"
        if blob not in EMPTY_BLOBS:
            if blob in self.where:
                return "superseded", f"identical content at {self.where[blob]}"
            for ref in self.refs:
                rc, c, _ = run(self.repo, "log", "-1", "--format=%h", f"--find-object={blob}", ref, "--", path,
                               env=LITERAL)
                c = c.strip()
                if rc == 0 and c:
                    return "superseded", f"an older version of this path on {ref} ({c})"
        if path in self.at:
            return "differs", "the landing ref has this path with other content"
        for ref in self.refs:
            rc, out, _ = run(self.repo, "log", "-1", "--format=%h %s", ref, "--", path, env=LITERAL)
            if rc == 0 and out.strip():
                return "removed-on-landing", f"{ref} removed or moved it in {out.strip()}"
        return "novel", "neither the path nor the content is on any landing ref"


def finding(landing: Landing, path: str, status: str, blob: str | None, note: str = "") -> dict:
    if note:
        verdict, evidence = "unknown", note
    else:
        verdict, evidence = landing.classify(path, blob)
    return {"path": path, "status": status, "blob": blob or "", "verdict": verdict, "evidence": evidence}


def hash_files(wt: Path, paths: list[str]) -> dict[str, tuple[str, str]]:
    """path -> (blob, error). Regular files go through clean filters as `git add` would."""
    res: dict[str, tuple[str, str]] = {}
    plain = []
    for p in paths:
        full = wt / p
        if full.is_symlink():
            rc, out, err = run(wt, "hash-object", "--stdin", stdin=os.readlink(full))
            res[p] = (out.strip(), "") if rc == 0 else ("", err)
        elif "\n" in p:
            rc, out, err = run(wt, "hash-object", "--", p)
            res[p] = (out.strip(), "") if rc == 0 else ("", err)
        else:
            plain.append(p)
    for batch in chunks(plain):
        rc, out, err = run(wt, "hash-object", "--stdin-paths", stdin="\n".join(batch) + "\n")
        shas = out.split()
        if rc == 0 and len(shas) == len(batch):
            res.update({p: (s, "") for p, s in zip(batch, shas)})
            continue
        for p in batch:  # one unreadable file must not hide the rest
            rc, out, err = run(wt, "hash-object", "--", p)
            res[p] = (out.strip(), "") if rc == 0 else ("", err or "could not hash")
    return res


def parse_status(out: str) -> list[tuple[str, str]]:
    return [(rec[:2], rec[3:]) for rec in out.split("\0") if len(rec) > 3]


def worktree_findings(wt: Path, entries: list[tuple[str, str]], landing: Landing) -> list[dict]:
    want, kinds = [], {}
    for xy, path in entries:
        p = path.rstrip("/")
        full = wt / p
        if not os.path.lexists(full):
            kinds[path] = (p, None)
        elif full.is_dir() and not full.is_symlink():
            kinds[path] = (p, "")
        else:
            want.append(p)
            kinds[path] = (p, "hash")
    blobs = hash_files(wt, want)
    out = []
    for xy, path in entries:
        p, kind = kinds[path]
        if kind == "hash":
            blob, err = blobs.get(p, ("", "not hashed"))
            out.append(finding(landing, p, xy, blob, err))
        else:
            out.append(finding(landing, p, xy, kind))
    return out


def stash_entries(repo: Path, landing: Landing | None) -> list[dict]:
    rc, out, _ = run(repo, "stash", "list", "--format=%H%x1f%gd%x1f%gs%x1f%ci")
    res = []
    for line in out.splitlines() if rc == 0 else []:
        sha, ref, msg, date = (line.split("\x1f") + ["", "", ""])[:4]
        item = {"sha": sha, "ref": ref, "message": msg, "date": date, "findings": []}
        if landing is not None:
            tree = {}
            for rec in git(repo, "ls-tree", "-r", "-z", sha).split("\0"):
                if rec:
                    meta, path = rec.split("\t", 1)
                    tree[path] = meta.split()[2]
            parts = git(repo, "diff-tree", "-r", "-z", "--no-renames", "--name-status", f"{sha}^1", sha).split("\0")
            for st, path in zip(parts[0::2], parts[1::2]):
                if st:
                    item["findings"].append(finding(landing, path, st, None if st == "D" else tree.get(path)))
            if git(repo, "rev-parse", "-q", "--verify", f"{sha}^3", check=False).strip():
                for rec in git(repo, "ls-tree", "-r", "-z", f"{sha}^3").split("\0"):
                    if rec:
                        meta, path = rec.split("\t", 1)
                        item["findings"].append(finding(landing, path, "??", meta.split()[2]))
        res.append(item)
    return res


# ---------------------------------------------------------------- landing
def squash_landed(repo: Path, head: str, ref: str) -> bool:
    """The branch's whole change, taken as one patch, is already on `ref`."""
    rc, mb, _ = run(repo, "merge-base", ref, head)
    if rc != 0:
        return False
    mb = mb.strip()
    rc, names, _ = run(repo, "diff", "--name-only", "-z", "--no-renames", mb, head)
    paths = [p for p in names.split("\0") if p]
    if rc != 0 or not paths:
        return rc == 0
    # The ref holds the branch's content at every path the branch touched.
    if all(run(repo, "diff", "--quiet", head, ref, "--", *b, env=LITERAL)[0] == 0 for b in chunks(paths)):
        return True
    # Or one landing commit carries the same patch, even if the ref has moved on since.
    if len(paths) > MAX_PATHSPEC:
        return False
    rc, diff, _ = run(repo, "diff", "--no-renames", mb, head)
    rc2, pid, _ = run(repo, "patch-id", "--stable", stdin=diff)
    if rc or rc2 or not pid.split():
        return False
    rc, log, _ = run(repo, "log", "-p", "--no-merges", "--no-renames", f"{mb}..{ref}", "--", *paths, env=LITERAL)
    rc2, ids, _ = run(repo, "patch-id", "--stable", stdin=log)
    return rc == 0 and rc2 == 0 and pid.split()[0] in {ln.split()[0] for ln in ids.splitlines() if ln.split()}


def branch_landing(repo: Path, head: str, refs: list[str]) -> tuple[bool, str, list[str]] | None:
    """(landed, how, unlanded 'sha subject' lines), or None if a check failed."""
    plus_sets = []
    for ref in refs:
        rc, out, _ = run(repo, "cherry", "-v", ref, head)
        if rc != 0:
            return None
        plus_sets.append([ln[2:] for ln in out.splitlines() if ln.startswith("+ ")])
    shas = [{c.split()[0] for c in s} for s in plus_sets]
    common = [c for c in plus_sets[0] if all(c.split()[0] in s for s in shas[1:])]
    if not common:
        return True, "by commit", []
    for ref in refs:
        if squash_landed(repo, head, ref):
            return True, f"squashed into {ref}", []
    return False, "", [c.split(" ", 1)[0][:12] + " " + c.partition(" ")[2] for c in common]


# ---------------------------------------------------------------- verdicts
def last_used(p: Path) -> float | None:
    """When git last acted in this worktree: the newest of its directory, its admin files and
    the time written inside its last reflog entry. The mtime of logs/ is skipped on purpose:
    `git gc` and `git reflog expire` rewrite every worktree's logs in one pass, so that date
    belongs to the maintenance, not to the user."""
    try:
        text = (p / ".git").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text.startswith("gitdir:"):
        return None
    admin = Path(text[len("gitdir:"):].strip())
    if not admin.is_absolute():
        admin = (p / admin).resolve()
    if not admin.is_dir():
        return None
    times = [p.stat().st_mtime]
    for f in admin.iterdir():
        if f.name != "logs":
            try:
                times.append(f.stat().st_mtime)
            except OSError:
                pass
    try:
        last = (admin / "logs" / "HEAD").read_text(encoding="utf-8", errors="replace").splitlines()[-1]
        times.append(float(last.split("\t", 1)[0].split()[-2]))
    except (OSError, IndexError, ValueError):
        pass
    return max(times)


def inspect(repo: Path, wt: Worktree, refs: list[str], procs, cwd: str, landing: Landing | None,
            idle_days: float = 1.0) -> Worktree:
    if wt.main:
        wt.verdict, wt.reason = "main", "the main checkout"
        return wt
    p = Path(wt.path)
    if not p.is_dir():
        wt.exists = False
        if wt.locked:
            wt.verdict = "keep"
            wt.reason = "locked; the directory is not present (removable or unmounted storage?)"
        else:
            wt.verdict, wt.reason = "prune", "directory is gone; run: git worktree prune"
        return wt
    real = os.path.realpath(wt.path)
    wt.current = is_inside(cwd, real)
    if procs is not None:
        wt.in_use = [f"{pid} {cmd}" for pid, cmd, c in procs if is_inside(c, real)]

    reasons = []
    if wt.locked:
        reasons.append("locked")
    if wt.current:
        reasons.append("current: this command runs inside it")
    if procs is None:
        reasons.append("could not check for processes using it")
    elif wt.in_use:
        reasons.append(f"in use by {len(wt.in_use)} process(es)")
    if not (p / ".git").exists():
        # Without its .git, git -C would climb into the parent repository and answer for that.
        wt.broken = True
        reasons.append("broken: the directory has no .git, so an earlier removal stopped part-way")
        wt.verdict, wt.reason = "keep", "; ".join(reasons)
        return wt

    # --no-optional-locks: the sweep must not refresh the index, which would reset the idle clock.
    rc, out, err = run(p, "--no-optional-locks", "status", "--porcelain=v1", "-z", "-uall", "--no-renames",
                       "--ignored=matching")
    entries = parse_status(out) if rc == 0 else []
    if rc != 0:
        reasons.append(f"could not read git status: {err.splitlines()[0] if err else rc}")
    wt.ignored = sum(1 for xy, _ in entries if xy == "!!")
    entries = [e for e in entries if e[0] != "!!"]
    wt.untracked = sum(1 for xy, _ in entries if xy == "??")
    wt.dirty = len(entries) - wt.untracked
    if wt.dirty:
        reasons.append(f"{wt.dirty} uncommitted change(s)")
    if wt.untracked:
        reasons.append(f"{wt.untracked} untracked file(s)")

    if wt.head:
        rc, out, _ = run(repo, "rev-list", wt.head, "--not", "--remotes")
        if rc != 0:
            reasons.append("could not count unpushed commits")
        wt.unpushed = len(out.split())
        rc, out, _ = run(repo, "rev-list", "--count", f"{wt.head}..{refs[0]}")
        wt.behind = int(out.strip() or 0) if rc == 0 else 0
        got = branch_landing(repo, wt.head, refs)
        if got is None:
            reasons.append("could not check whether the branch landed")
        else:
            wt.landed, wt.landed_how, wt.unlanded_commits = got
    if wt.unpushed and not wt.landed:
        reasons.append(f"{wt.unpushed} commit(s) on no remote and not landed")
    if landing is not None and entries:
        wt.findings = worktree_findings(p, entries, landing)
    used = last_used(p)
    if used is None:
        reasons.append("could not tell when it was last used")
    else:
        wt.idle_days = round(max(0.0, time.time() - used) / 86400, 2)
        if wt.idle_days < idle_days:
            reasons.append(f"recent: last used {wt.idle_days} day(s) ago, under --idle-days {idle_days:g}")

    if reasons:
        wt.verdict, wt.reason = "keep", "; ".join(reasons)
    else:
        wt.verdict = "reap"
        wt.reason = f"landed in {', '.join(refs)} {wt.landed_how}" if wt.landed else "everything is pushed"
        if wt.ignored:
            wt.reason += f"; {wt.ignored} ignored path(s) are deleted with it"
    return wt


def unregistered(wts: list[Worktree]) -> list[str]:
    """Directories beside the linked worktrees that no registration names: often what an
    interrupted removal leaves once git has already dropped the registration."""
    if not wts:
        return []
    registered = {os.path.realpath(w.path) for w in wts}
    skip = {os.path.dirname(os.path.realpath(wts[0].path)), os.path.realpath(os.path.expanduser("~"))}
    parents = {os.path.dirname(os.path.realpath(w.path)) for w in wts if not w.main} - skip
    found = []
    for parent in sorted(parents):
        try:
            names = sorted(os.listdir(parent))
        except OSError:
            continue
        for n in names:
            d = os.path.join(parent, n)
            if not os.path.isdir(d) or os.path.islink(d) or os.path.realpath(d) in registered:
                continue
            dotgit = os.path.join(d, ".git")
            if os.path.isdir(dotgit):
                continue  # a repository of its own
            if os.path.isfile(dotgit):
                try:
                    gitdir = open(dotgit, encoding="utf-8").read().strip().split("gitdir:", 1)[-1].strip()
                except OSError:
                    gitdir = ""
                if gitdir and os.path.isdir(os.path.join(d, gitdir)):
                    continue  # a worktree some other repository still registers
            found.append(d)
    return found


def reap(repo: Path, wts: list[Worktree]) -> int:
    rc = 0
    if any(w.verdict == "prune" for w in wts):
        git(repo, "worktree", "prune")
        for w in wts:
            if w.verdict == "prune":
                print(f"pruned registration: {w.path}")
    for wt in wts:
        if wt.verdict != "reap":
            continue
        r = subprocess.run(["git", "-C", str(repo), "worktree", "remove", wt.path], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"REFUSED {wt.path}: {r.stderr.strip()}", file=sys.stderr)
            rc = 1
            continue
        still = os.path.realpath(wt.path) in {os.path.realpath(w.path) for w in list_worktrees(repo)}
        if still or os.path.exists(wt.path):
            print(f"INCOMPLETE {wt.path}: registration {'kept' if still else 'gone'}, "
                  f"directory {'survived' if os.path.exists(wt.path) else 'gone'}", file=sys.stderr)
            rc = 1
            continue
        print(f"removed: {wt.path}")
        if wt.branch and wt.landed:
            b = subprocess.run(["git", "-C", str(repo), "branch", "-d", wt.branch], capture_output=True, text=True)
            print(f"  branch {wt.branch}: " + ("deleted" if b.returncode == 0 else "kept (" + b.stderr.strip() + ")"))
    return rc


NEEDS_EYES = ("differs", "removed-on-landing", "novel", "unknown")


def print_findings(items: list[dict], indent: str) -> None:
    counts: dict[str, int] = {}
    for f in items:
        counts[f["verdict"]] = counts.get(f["verdict"], 0) + 1
    print(indent + "findings: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    for f in items:
        if f["verdict"] in NEEDS_EYES:
            print(f"{indent}  {f['verdict']:18} {f['status']:2} {f['path']}   ({f['evidence']})")


def resolve_repo(arg: str) -> Path:
    """An existing directory wins; otherwise a managed repo's name from the repo list."""
    if Path(arg).is_dir():
        return Path(arg)
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import repos
        home = Path(os.environ.get("YB_ROOT") or ROOT)
        found = repos.find(arg, home)
        return repos.repo_path(found, home) if found else Path(arg)
    except Exception:
        return Path(arg)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=os.environ.get("YB_ROOT", str(ROOT)))
    ap.add_argument("--landing", action="append",
                    help="ref that counts as landed; repeatable (default: origin/HEAD, then origin/master)")
    ap.add_argument("--findings", action="store_true", help="judge every unlanded path and commit by content")
    ap.add_argument("--idle-days", type=float, default=1.0,
                    help="keep a worktree git acted in more recently than this (default 1)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--reap", action="store_true", help="remove worktrees whose verdict is reap")
    ap.add_argument("--all", action="store_true",
                    help="report on YBase and every managed repo from the repo list")
    ap.add_argument("--done", metavar="BRANCH",
                    help="remove the one worktree on BRANCH, and its branch, when nothing in it would be lost")
    a = ap.parse_args(argv)
    if a.all and (a.done or a.reap):
        ap.error("--all only reports; name one repo with --repo to remove anything")
    targets: list[tuple[str, Path]] = [("", resolve_repo(a.repo))]
    if a.all:
        targets = [("", Path(os.environ.get("YB_ROOT") or ROOT))] + managed_repos()
    rc, payloads = 0, []
    for name, repo in targets:
        if name and not repo.is_dir():
            if a.json:
                payloads.append({"repo": str(repo), "name": name, "cloned": False})
            else:
                print(f"repo {repo}   {name}: not cloned on this machine")
            continue
        one, payload = report(repo, a)
        rc = max(rc, one)
        if payload is not None:
            payloads.append(payload)
    if a.json and payloads:
        print(json.dumps(payloads if a.all else payloads[0], indent=2))
    return rc


def managed_repos() -> list[tuple[str, Path]]:
    """(name, path) for every repo in the repo list, cloned or not."""
    sys.path.insert(0, str(ROOT / "tools"))
    import repos
    home = Path(os.environ.get("YB_ROOT") or ROOT)
    return [(r.name, repos.repo_path(r, home)) for r in repos.all_repos(home)]


def done(repo: Path, wts: list[Worktree], branch: str) -> int:
    """Remove the one linked worktree on `branch` when its verdict is reap; otherwise say why it stays."""
    linked = [w for w in wts if not w.main]
    mine = [w for w in linked if w.branch == branch]
    if not mine:
        print(f"no worktree of {repo} is on branch {branch}", file=sys.stderr)
        for w in linked:
            print(f"  {w.branch or '(detached)'}  {w.path}", file=sys.stderr)
        return 1
    wt = mine[0]
    if wt.verdict not in ("reap", "prune"):
        print(f"kept {wt.path}: {wt.reason}", file=sys.stderr)
        return 1
    return reap(repo, [wt])


def report(repo: Path, a: argparse.Namespace) -> tuple[int, dict | None]:
    if run(repo, "rev-parse", "--git-dir")[0] != 0:
        print(f"not a git repository: {repo}", file=sys.stderr)
        return 2, None
    refs = landing_refs(repo, a.landing)
    for ref in refs:
        if run(repo, "rev-parse", "-q", "--verify", f"{ref}^{{commit}}")[0] != 0:
            print(f"landing ref does not resolve in {repo}: {ref}", file=sys.stderr)
            return 2, None
    landing = Landing(repo, refs) if a.findings else None
    procs, opaque = scan_processes()
    cwd = os.path.realpath(os.getcwd())
    wts = [inspect(repo, w, refs, procs, cwd, landing, 0.0 if a.done else a.idle_days) for w in list_worktrees(repo)]
    stashes = stash_entries(repo, landing)
    extra = unregistered(wts)
    if a.done:
        return done(repo, wts, a.done), None
    payload = None
    if a.json:
        payload = ({"repo": str(repo), "landing": refs[0], "landing_refs": refs,
                          "processes_unreadable": opaque, "findings": bool(a.findings),
                          "worktrees": [asdict(w) for w in wts], "stashes": stashes,
                          "unregistered": extra})
    else:
        counts: dict[str, int] = {}
        for w in wts:
            counts[w.verdict] = counts.get(w.verdict, 0) + 1
        print(f"repo {repo}   landing {', '.join(refs)}   {len(wts)} worktree(s): "
              + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        if procs is None:
            print("NOT CHECKED: processes (no /proc and no lsof); every worktree is kept")
        elif opaque:
            print(f"NOT CHECKED: {opaque} of your own processes whose working directory could not be read")
        if not a.findings:
            print("not judged: paths and commits by content (pass --findings)")
        for w in wts:
            print(f"{w.verdict:6} {w.branch or '(detached)':28} {w.path}")
            print(f"       {w.reason}")
            if w.behind or w.unlanded_commits:
                print(f"       behind {w.behind}; unlanded commits {len(w.unlanded_commits)}")
                for c in w.unlanded_commits:
                    print(f"         + {c}")
            if w.findings:
                print_findings(w.findings, "       ")
        for s in stashes:
            print(f"stash  {s['ref']:28} {s['sha'][:12]} {s['date']}  {s['message']}")
            if s["findings"]:
                print_findings(s["findings"], "       ")
        for d in extra:
            print(f"unregistered directory (no worktree registration names it): {d}")
    if a.reap:
        return reap(repo, wts), payload
    return 0, payload


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
