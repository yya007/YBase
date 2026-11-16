#!/usr/bin/env python3
"""session_inventory.py: the machine side of what a session owns, as facts.

    python3 tools/session_inventory.py                     report for the checkout you stand in
    python3 tools/session_inventory.py --touched B         also adjudicate branch B as this session's
    python3 tools/session_inventory.py --env-key K=V       join processes whose environment carries K=V
    python3 tools/session_inventory.py --json              machine-readable report

It reads, and never writes:
  identity   repository, the worktree you stand in, branch, HEAD, upstream and
             ahead/behind, the landing ref, and how old the last fetch is
  profile    name, scratch directory, whether scratch is durable, the worktree
             directory, and the scratch footprint (files and bytes)
  worktrees  `tools/worktrees.py --json`, unchanged, plus each worktree's
             in-progress git state (index.lock, a paused rebase or merge) and
             whether it sits on non-durable storage
  branches   every local branch: commits on no remote ref, and where it is
             checked out; the namespace is counted, only owned rows are listed
  processes  processes of this unix user whose working directory is inside a
             worktree of this repository or the profile scratch, or whose
             environment carries --env-key; this process and its ancestors
             (the harness that ran it) are left out
  gaps       what this run could not see

It assigns no ownership tier and no write class: those are judgements, and the
session-scope skill makes them from these facts. Exit 2 outside a git checkout.
Stdlib only; Linux reads /proc, macOS and other BSDs use ps and lsof.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GIT_OPS = ("index.lock", "HEAD.lock", "rebase-merge", "rebase-apply", "MERGE_HEAD",
           "CHERRY_PICK_HEAD", "REVERT_HEAD", "BISECT_LOG")
COMMON_LOCKS = ("packed-refs.lock", "config.lock", "shallow.lock")


def git(repo: str, *args: str) -> tuple[int, str]:
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def real(p: str) -> str:
    return os.path.realpath(p)


def inside(child: str, parent: str) -> bool:
    return child == parent or child.startswith(parent.rstrip(os.sep) + os.sep)


# ---------------------------------------------------------------- identity
def identity(cwd: str) -> dict | None:
    rc, top = git(cwd, "rev-parse", "--show-toplevel")
    if rc != 0:
        return None
    _, common = git(cwd, "rev-parse", "--git-common-dir")
    common = os.path.join(cwd, common)  # relative on older git; join leaves an absolute path alone
    _, branch = git(cwd, "symbolic-ref", "-q", "--short", "HEAD")
    _, head = git(cwd, "rev-parse", "-q", "--verify", "HEAD")
    rc, upstream = git(cwd, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    ahead = behind = None
    if rc == 0 and upstream:
        _, counts = git(cwd, "rev-list", "--left-right", "--count", "@{u}...HEAD")
        if counts:
            behind, ahead = (int(x) for x in counts.split())
    else:
        upstream = ""
    fetch_head = Path(common) / "FETCH_HEAD"
    fetched = int(time.time() - fetch_head.stat().st_mtime) if fetch_head.exists() else None
    return {"worktree": real(top), "common_dir": real(common), "branch": branch, "head": head,
            "upstream": upstream, "ahead": ahead, "behind": behind, "last_fetch_s": fetched}


# ---------------------------------------------------------------- profile
def profile(yb_root: Path) -> dict:
    script = ('set -eu; YB_ROOT="$1"; export YB_ROOT; . "$1/tools/profile.sh"; yb_load_profile; '
              'printf "%s\\n%s\\n%s\\n%s\\n" "$PROFILE_NAME" "$PROFILE_SCRATCH" '
              '"$PROFILE_SCRATCH_DURABLE" "$PROFILE_WORKTREES"')
    r = subprocess.run(["bash", "-c", script, "_", str(yb_root)], capture_output=True, text=True)
    lines = r.stdout.splitlines()
    if r.returncode != 0 or len(lines) < 4:
        return {"name": "", "scratch": "", "durable": "unknown", "worktrees_dir": "",
                "error": r.stderr.strip() or "profile did not load"}
    out = {"name": lines[0], "scratch": lines[1], "durable": lines[2] or "unknown", "worktrees_dir": lines[3]}
    files = size = 0
    if os.path.isdir(out["scratch"]):
        for d, _, names in os.walk(out["scratch"]):
            for n in names:
                try:
                    size += os.lstat(os.path.join(d, n)).st_size
                    files += 1
                except OSError:
                    pass
    out["footprint"] = {"files": files, "bytes": size}
    return out


# ---------------------------------------------------------------- worktrees and branches
def worktrees(repo: str) -> dict:
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "worktrees.py"), "--repo", repo, "--json"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return {"landing": "", "worktrees": [], "error": r.stderr.strip()}
    data = json.loads(r.stdout)
    for w in data["worktrees"]:
        w["git_ops"] = []
        if os.path.isdir(w["path"]):
            rc, gd = git(w["path"], "rev-parse", "--absolute-git-dir")
            if rc == 0:
                w["git_ops"] = [n for n in GIT_OPS if os.path.exists(os.path.join(gd, n))]
    return data


def common_locks(common_dir: str) -> list[str]:
    return [n for n in COMMON_LOCKS if os.path.exists(os.path.join(common_dir, n))]


def branches(repo: str, wts: list[dict]) -> list[dict]:
    _, out = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    at = {w["branch"]: real(w["path"]) for w in wts if w.get("branch")}
    res = []
    for b in out.splitlines():
        _, n = git(repo, "rev-list", "--count", "refs/heads/" + b, "--not", "--remotes")
        res.append({"branch": b, "unpushed": int(n or 0), "checked_out_at": at.get(b, "")})
    return res


# ---------------------------------------------------------------- processes
def ancestors() -> set[int]:
    """This process and every ancestor: the harness that ran the inventory is not a finding."""
    table = {p["pid"]: p["ppid"] for p in _ps_table()}
    seen, pid = set(), os.getpid()
    while pid and pid not in seen:
        seen.add(pid)
        pid = table.get(pid, 0)
    return seen


def _ps_table() -> list[dict]:
    r = subprocess.run(["ps", "-axo", "pid=,ppid=,uid=,comm="], capture_output=True, text=True)
    rows = []
    for line in r.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4 and parts[0].isdigit():
            rows.append({"pid": int(parts[0]), "ppid": int(parts[1]), "uid": int(parts[2]), "comm": parts[3]})
    return rows


def processes(env_key: str | None) -> tuple[list[dict], int, bool]:
    """(rows, unreadable count, env join available) for this unix user's processes."""
    uid, rows, unreadable = os.getuid(), [], 0
    proc = Path("/proc")
    if (proc / "self" / "cwd").exists():
        for p in proc.iterdir():
            if not p.name.isdigit():
                continue
            try:
                st = dict(ln.split(":", 1) for ln in (p / "status").read_text().splitlines() if ":" in ln)
                if int(st["Uid"].split()[0]) != uid:
                    continue
                row = {"pid": int(p.name), "ppid": int(st["PPid"]), "comm": (p / "comm").read_text().strip()}
            except (OSError, KeyError, ValueError):
                continue
            try:
                row["cwd"] = real(os.readlink(p / "cwd"))
            except OSError:
                row["cwd"], unreadable = None, unreadable + 1
            row["env_match"] = None
            if env_key:
                try:
                    row["env_match"] = env_key.encode() in (p / "environ").read_bytes().split(b"\0")
                except OSError:
                    unreadable += 1
            rows.append(row)
        return rows, unreadable, True
    cwds: dict[int, str] = {}
    r = subprocess.run(["lsof", "-a", "-u", str(uid), "-d", "cwd", "-Fpn"], capture_output=True, text=True)
    pid = 0
    for line in r.stdout.splitlines():
        if line[:1] == "p" and line[1:].isdigit():
            pid = int(line[1:])
        elif line[:1] == "n" and pid:
            cwds[pid] = real(line[1:])
    for row in _ps_table():
        if row["uid"] != uid:
            continue
        cwd = cwds.get(row["pid"])
        unreadable += cwd is None
        rows.append({"pid": row["pid"], "ppid": row["ppid"], "comm": row["comm"], "cwd": cwd, "env_match": None})
    return rows, unreadable, False


def place(cwd: str | None, wt_paths: list[str], scratch: str) -> str:
    if not cwd:
        return ""
    hits = [w for w in wt_paths if inside(cwd, w)]
    if hits:
        return max(hits, key=len)
    if scratch and inside(cwd, real(scratch)):
        return "scratch"
    return ""


# ---------------------------------------------------------------- the report
def inventory(cwd: str, touched: list[str], env_key: str | None) -> dict | None:
    ident = identity(cwd)
    if ident is None:
        return None
    prof = profile(ROOT)
    wt = worktrees(ident["worktree"])
    wts = wt.get("worktrees", [])
    owned_branches = {b for b in [ident["branch"], *touched] if b}
    ephemeral_roots = [real(d) for d in (prof.get("scratch"), prof.get("worktrees_dir")) if d and os.path.isabs(d)]
    for w in wts:
        w["owned"] = real(w["path"]) == ident["worktree"] or w.get("branch") in owned_branches
        w["ephemeral"] = prof["durable"] == "no" and any(inside(real(w["path"]), r) for r in ephemeral_roots)
        if w.get("main") and w["owned"]:
            # worktrees.py leaves the main checkout uninspected; a session standing in it still owes the counts.
            _, st = git(w["path"], "status", "--porcelain")
            lines = st.splitlines()
            w["untracked"] = sum(1 for s in lines if s.startswith("??"))
            w["dirty"] = len(lines) - w["untracked"]
            if w.get("head"):
                _, n = git(w["path"], "rev-list", "--count", w["head"], "--not", "--remotes")
                w["unpushed"] = int(n or 0)
            w["reason"] = (f"the main checkout: {w['dirty']} uncommitted, {w['untracked']} untracked, "
                           f"{w.get('unpushed', 0)} commit(s) on no remote")
    brs = branches(ident["worktree"], wts)
    for b in brs:
        b["owned"] = b["branch"] in owned_branches
    skip = ancestors()
    rows, unreadable, env_ok = processes(env_key)
    wt_paths = [real(w["path"]) for w in wts if w.get("exists", True)]
    procs = []
    for r in rows:
        if r["pid"] in skip:
            continue
        r["where"] = place(r["cwd"], wt_paths, prof.get("scratch", ""))
        if r["where"] or r["env_match"]:
            r["detached"] = r["ppid"] == 1
            procs.append(r)
    gaps = [
        "harness rows (background tasks, monitors, scheduled wake-ups, subagents) are not processes this "
        "tool can attribute; list them from the harness",
        "other machines and other unix users: anything they hold on these branches is invisible here",
        f"{unreadable} process field(s) of this user could not be read",
    ]
    if ident["last_fetch_s"] is None:
        gaps.append("remote refs were never fetched here: 'unpushed' is measured against stale or absent refs")
    elif ident["last_fetch_s"] > 3600:
        gaps.append(f"remote refs last fetched {ident['last_fetch_s'] // 60} min ago: fetch before trusting 'unpushed'")
    if env_key and not env_ok:
        gaps.append("--env-key join is unavailable on this platform (no /proc): processes are joined by cwd only")
    if not env_key:
        gaps.append("no --env-key given: processes are joined by cwd only, so none is proven this session's")
    if prof["durable"] == "unknown":
        gaps.append("scratch durability unknown: " + prof.get("error", "the profile did not say"))
    if wt.get("error"):
        gaps.append("tools/worktrees.py failed: " + wt["error"])
    return {"identity": ident, "landing": wt.get("landing", ""), "profile": prof, "worktrees": wts,
            "common_locks": common_locks(ident["common_dir"]), "branches": brs, "processes": procs,
            "gaps": gaps}


def render(inv: dict) -> str:
    i, p = inv["identity"], inv["profile"]
    up = f"upstream {i['upstream']} ahead {i['ahead']} behind {i['behind']}" if i["upstream"] else "no upstream"
    fp = p.get("footprint", {"files": 0, "bytes": 0})
    out = [f"IDENTITY   worktree {i['worktree']}",
           f"           branch {i['branch'] or '(detached)'}  head {i['head'][:12]}  {up}  landing {inv['landing']}",
           f"PROFILE    {p['name'] or '?'}  scratch {p['scratch']}  durable {p['durable']}  "
           f"footprint {fp['files']} file(s), {fp['bytes'] // 1024} KiB"]
    owned = [w for w in inv["worktrees"] if w["owned"]]
    out.append(f"WORKTREES  {len(inv['worktrees'])} registered, {len(owned)} this session's")
    for w in owned:
        flags = [f for f, on in (("EPHEMERAL", w["ephemeral"]), ("LOCKED", w.get("locked"))) if on]
        flags += w["git_ops"]
        out.append(f"  {w['verdict']:6} {w.get('branch') or '(detached)'}  {w['path']}  {' '.join(flags)}".rstrip())
        out.append(f"         {w['reason']}")
    if inv["common_locks"]:
        out.append("  repository locks: " + " ".join(inv["common_locks"]))
    unp = [b for b in inv["branches"] if b["unpushed"]]
    out.append(f"BRANCHES   namespace: {len(inv['branches'])} local, {len(unp)} with commits on no remote "
               "(a fact about the repo, not about this session)")
    for b in (b for b in inv["branches"] if b["owned"]):
        where = b["checked_out_at"] or "no worktree"
        out.append(f"  owned {b['branch']}: {b['unpushed']} commit(s) on no remote; checked out at {where}")
    out.append(f"PROCESSES  {len(inv['processes'])} of this user in a worktree, the scratch, or the env join")
    for r in inv["processes"]:
        tag = " detached" if r["detached"] else ""
        tag += " env-match" if r["env_match"] else ""
        out.append(f"  {r['pid']:>7} ppid {r['ppid']:<7} {r['comm'][:24]:24} {r['where'] or r['cwd'] or '?'}{tag}")
    out.append("GAPS")
    out += ["  " + g for g in inv["gaps"]]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=os.getcwd(), help="a path inside the checkout (default: cwd)")
    ap.add_argument("--touched", action="append", default=[], help="a branch this session worked on (repeatable)")
    ap.add_argument("--env-key", help="NAME=VALUE that marks this session's processes in their environment")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    inv = inventory(a.repo, a.touched, a.env_key)
    if inv is None:
        print(f"not inside a git checkout: {a.repo}", file=sys.stderr)
        return 2
    print(json.dumps(inv, indent=2) if a.json else render(inv))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
