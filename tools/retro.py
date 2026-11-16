#!/usr/bin/env python3
"""retro.py: the mechanical half of the retro skill (.claude/skills/retro/SKILL.md).

    python3 tools/retro.py paths                      where this machine's retro state lives and whether git ignores it
    python3 tools/retro.py distill [--days N] [--only TRANSCRIPT] [--closed] [--out DIR] [--prefix DIR]...
                                                      one JSON record per session in scope, with line numbers
    python3 tools/retro.py turns TRANSCRIPT           every accepted human turn as JSON, with its correction label
    python3 tools/retro.py rank [--top N]             distilled sessions not yet examined, by evidence
    python3 tools/retro.py span TRANSCRIPT START END [START END ...]
                                                      the lines START..END of a transcript, flattened
    python3 tools/retro.py covered                    what memory/ and docs/rules.md already cover

Transcripts: Claude Code keeps them under `$CLAUDE_CONFIG_DIR` (default `~/.claude`)
`/projects/**/*.jsonl`, Codex under `$CODEX_HOME` (default `~/.codex`) `/sessions/**/*.jsonl`.
Both trees are walked following symlinks. A session is in scope when the cwd recorded inside
its transcript is the main checkout, one of its live worktrees or a `--prefix` directory: an
exact directory match (the directory itself or a path below it), never a name prefix.

Transcripts can hold private material, so everything this tool writes goes under the
gitignored `.ybase/retro/` of the main checkout (`distill/`, `load/`, `inbox/`, `done/`).
`--out` may point elsewhere, but never at a path git tracks or could track: the tool asks
`git check-ignore` and refuses with exit 2 when the answer is no. The main checkout is
derived from this file's location (`git rev-parse --git-common-dir`), or from `--repo`.

Each record carries the transcript line numbers of its signals, so later stages cite lines
instead of rereading files: `corrections` (human turns that open with a correction word, a
heuristic and therefore `[A]`), `interrupts`, `errors` (tool results that failed), `waits`
(tool calls that took longer than WAIT_S seconds, joined to the host-load samples that
`.claude/hooks/tool_load_hook.py` writes to `.ybase/retro/load/<session_id>.tsv` when
they exist), and `tokens` when the transcript carries usage fields. Codex runs no
load-sampling hook, so its records never carry load samples; its interrupts come from
`turn_aborted` events.

Stdlib only, Python 3.8+.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RETRO_SUBDIR = os.path.join(".ybase", "retro")

# Human turns that open with one of these words are counted as corrections. [A]: a
# heuristic; the `turns` subcommand shows the text so a reader can judge each one.
CORR = re.compile(r"^\W*(no\b|nope|don'?t|do not|stop|wrong|not what|that'?s not|why did you"
                  r"|you didn'?t|actually|instead|again|undo|revert)", re.I)
# A Codex tool output that reports a failure. Claude marks its failures with `is_error`.
ERR = re.compile(r'"exit_code":\s*[1-9]|exited with code [1-9]|Exit code:? [1-9]|Script failed')
INTERRUPT_PREFIX = "[Request interrupted"
# A tool call that took at least this long is recorded as a wait. [A]
WAIT_S = 30.0
# Above one runnable process per core a CPU-bound tool starts queueing for the processor. [A]
LOAD_PER_CORE_BUSY = 1.0
MAX_WAITS = 200
EXAMINED_RE = re.compile(r"## Sessions examined\s*`{3}\w*\n(.*?)`{3}", re.S)
TRIGGERS_RE = re.compile(r"<!-- BEGIN TRIGGERS -->(.*?)<!-- END TRIGGERS -->", re.S)
RULE_RE = re.compile(r"^[0-9]+\. ")


# ---------------------------------------------------------------- places
def git(cwd: str, *args: str) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return r.returncode, r.stdout.strip()


def main_checkout(repo: str | None = None) -> str:
    """The main checkout of the repository holding `repo` (default: this file), real path."""
    start = os.path.realpath(repo or ROOT)
    rc, common = git(start, "rev-parse", "--git-common-dir")
    if rc == 0 and common:
        if not os.path.isabs(common):
            common = os.path.join(start, common)
        return os.path.realpath(os.path.dirname(os.path.realpath(common)))
    # No git on PATH: walk up to a `.git` directory, or a `.git` file naming one.
    d = start
    while True:
        dotgit = os.path.join(d, ".git")
        if os.path.isdir(dotgit):
            return d
        if os.path.isfile(dotgit):
            with open(dotgit, encoding="utf-8") as fh:
                target = fh.read().strip().partition("gitdir:")[2].strip()
            if target:
                target = os.path.realpath(os.path.join(d, target))
                if os.path.basename(os.path.dirname(target)) == "worktrees":
                    return os.path.dirname(os.path.dirname(os.path.dirname(target)))
                return os.path.dirname(target)
        parent = os.path.dirname(d)
        if parent == d:
            return start
        d = parent


def worktree_dirs(main: str) -> list[str]:
    """The main checkout and every live linked worktree, as recorded by git."""
    rc, out = git(main, "worktree", "list", "--porcelain")
    dirs = [line[len("worktree "):] for line in out.splitlines() if line.startswith("worktree ")]
    return dirs if rc == 0 and dirs else [main]


def retro_dir(main: str) -> str:
    return os.path.join(main, RETRO_SUBDIR)


def transcript_roots() -> list[tuple[str, str]]:
    cdir = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "projects")
    xdir = os.path.join(os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex"), "sessions")
    return [("claude", cdir), ("codex", xdir)]


def is_ignored(path: str) -> bool | None:
    """True when git ignores `path`, False when the repo holding it would track it, None outside any repo."""
    probe = os.path.abspath(path)
    anc = probe
    while not os.path.isdir(anc):
        parent = os.path.dirname(anc)
        if parent == anc:
            return None
        anc = parent
    rc, top = git(anc, "rev-parse", "--show-toplevel")
    if rc != 0 or not top:
        return None
    rc, _ = git(top, "check-ignore", "-q", probe)
    return rc == 0


def refuse_unless_ignored(out: str) -> None:
    if is_ignored(out) is False:
        sys.exit("retro: refusing to write under %s: git does not ignore it, and transcript content "
                 "never goes in a tracked path (default: <main checkout>/.ybase/retro/)" % out)


def scope_prefixes(main: str, extra: list[str]) -> list[str]:
    """Each scope directory in both spellings, raw and real, with no trailing slash."""
    seen: list[str] = []
    for d in worktree_dirs(main) + list(extra):
        for p in (d, os.path.realpath(d)):
            p = p.rstrip(os.sep) or os.sep
            if p not in seen:
                seen.append(p)
    return seen


def in_scope(cwd: str | None, prefixes: list[str]) -> bool:
    """`cwd` is a scope directory or a path below one. A sibling that shares a name prefix is not."""
    if not cwd:
        return False
    for c in {cwd.rstrip(os.sep) or os.sep, os.path.realpath(cwd)}:
        for p in prefixes:
            if c == p or c.startswith(p + os.sep):
                return True
    return False


# ---------------------------------------------------------------- transcript reading
def parse_ts(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value:
        return None
    s = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        dt = datetime.datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.timestamp()


def iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return " ".join(b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") in ("text", "input_text"))


def flat(x) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        return " ".join(flat(b) for b in x)
    if not isinstance(x, dict):
        return ""
    if x.get("type") in ("tool_use", "function_call", "custom_tool_call"):
        return "[call %s] %s" % (x.get("name"), json.dumps(x.get("input") or x.get("arguments"))[:200])
    return flat(x.get("text") or x.get("content") or x.get("output") or x.get("message") or "")


def accepted_text(t: str) -> bool:
    """A human turn worth counting: not an injected file, not a harness wrapper."""
    return bool(t) and not t.startswith(("<", "# AGENTS.md"))


def harness_of(path: str) -> str:
    for harness, top in transcript_roots():
        real_top = os.path.realpath(top)
        for candidate in (os.path.abspath(path), os.path.realpath(path)):
            if candidate.startswith(top.rstrip(os.sep) + os.sep) or candidate.startswith(real_top + os.sep):
                return harness
    return "codex" if os.path.basename(path).startswith("rollout-") else "claude"


def iter_lines(path: str):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for n, line in enumerate(fh, 1):
            try:
                yield n, json.loads(line)
            except ValueError:
                yield n, None


def human_turns(path: str, harness: str):
    """Yield (line, ts, text, is_interrupt) for every human turn the distiller accepts."""
    for n, r in iter_lines(path):
        if not isinstance(r, dict):
            continue
        ts = parse_ts(r.get("timestamp"))
        if harness == "claude":
            if r.get("type") != "user" or r.get("isSidechain") or r.get("isMeta") or r.get("isCompactSummary"):
                continue
            c = (r.get("message") or {}).get("content")
            if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                continue
            t = text_of(c).strip()
        else:
            pl = r.get("payload") if isinstance(r.get("payload"), dict) else {}
            if pl.get("type") != "message" or pl.get("role") != "user":
                continue
            t = text_of(pl.get("content")).strip()
        if not accepted_text(t):
            continue
        yield n, ts, t, t.startswith(INTERRUPT_PREFIX)


def read_load_samples(path: str) -> dict[str, tuple[float, int]] | None:
    """tool_use_id -> (load1, ncpu) from one sidecar, or None when there is no sidecar."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    samples: dict[str, tuple[float, int]] = {}
    for line in lines:
        f = line.split("\t")
        if len(f) != 8 or not f[2]:
            continue
        try:
            load1, ncpu = float(f[4]), int(f[7])
        except ValueError:
            continue
        if ncpu > 0 and load1 == load1:
            samples[f[2]] = (load1, ncpu)
    return samples


def claude_usage(message, seen_ids: set) -> dict[str, int] | None:
    """Usage of one assistant message, once per message id (a message spans several lines)."""
    if not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
        return None
    if message.get("id") is not None:
        if message["id"] in seen_ids:
            return None
        seen_ids.add(message["id"])
    u = message["usage"]

    def count(name):
        v = u.get(name)
        return v if isinstance(v, int) and v >= 0 else 0
    return {"input": count("input_tokens"), "cache_read": count("cache_read_input_tokens"),
            "cache_write": count("cache_creation_input_tokens"), "output": count("output_tokens")}


def codex_usage(usage) -> dict[str, int] | None:
    """Codex's cumulative counter, in Claude's shape: `input` means uncached input in both."""
    if not isinstance(usage, dict):
        return None

    def count(name):
        v = usage.get(name)
        return v if isinstance(v, int) and v >= 0 else 0
    cached = count("cached_input_tokens")
    return {"input": max(count("input_tokens") - cached, 0), "cache_read": cached,
            "cache_write": count("cache_write_input_tokens"), "output": count("output_tokens")}


def token_block(totals: dict[str, int] | None, samples: int) -> dict | None:
    if not totals or not samples:
        return None
    out = dict(totals)
    out["total"] = sum(totals.values())
    out["samples"] = samples
    return out


def distill_one(path: str, harness: str, load_dir: str) -> dict:
    st = os.stat(path)
    s: dict = dict(harness=harness, path=path, bytes=st.st_size, mtime=int(st.st_mtime), id=None,
                   cwd=None, branch=None, started_at=None, ended_at=None, closed=False, turns=0,
                   corrections=[], interrupts=[], calls=0, errors=[], waits=[], unparsed=0,
                   tokens=None, load=None)
    first_ts = last_ts = None
    pending: dict[str, tuple[float | None, str, int]] = {}
    load_samples: dict[str, tuple[float, int]] | None = None
    joined: list[float] = []
    token_totals: dict[str, int] | None = None
    token_samples = 0
    seen_msg_ids: set = set()

    def note_wait(call_id, ts, line):
        p = pending.pop(str(call_id), None)
        if p is None or p[0] is None or ts is None:
            return
        gap = ts - p[0]
        if gap < WAIT_S:
            return
        w = {"line": line, "call_line": p[2], "tool": p[1], "s": round(gap, 1), "id": str(call_id)}
        if load_samples and str(call_id) in load_samples:
            load1, ncpu = load_samples[str(call_id)]
            w["load_per_core"] = round(load1 / max(ncpu, 1), 3)
            joined.append(w["load_per_core"])
        if len(s["waits"]) < MAX_WAITS:
            s["waits"].append(w)

    for n, r in iter_lines(path):
        if not isinstance(r, dict):
            s["unparsed"] += 1
            continue
        ts = parse_ts(r.get("timestamp"))
        if ts is not None:
            first_ts = ts if first_ts is None else min(first_ts, ts)
            last_ts = ts if last_ts is None else max(last_ts, ts)
        pl = r.get("payload") if isinstance(r.get("payload"), dict) else {}
        if harness == "claude":
            if s["id"] is None and r.get("sessionId"):
                s["id"] = r.get("sessionId")
                if load_samples is None and load_dir:
                    load_samples = read_load_samples(os.path.join(load_dir, "%s.tsv" % s["id"]))
            s["cwd"] = s["cwd"] or r.get("cwd")
            s["branch"] = s["branch"] or r.get("gitBranch")
            msg = r.get("message") if isinstance(r.get("message"), dict) else {}
            if r.get("type") == "assistant":
                u = claude_usage(msg, seen_msg_ids)
                if u:
                    token_totals = {k: (token_totals or {}).get(k, 0) + v for k, v in u.items()}
                    token_samples += 1
                for b in msg.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id"):
                        pending[str(b["id"])] = (ts, str(b.get("name")), n)
                continue
            if r.get("type") != "user" or r.get("isSidechain") or r.get("isMeta") or r.get("isCompactSummary"):
                continue
            c = msg.get("content")
            res = [b for b in (c if isinstance(c, list) else []) if isinstance(b, dict) and b.get("type") == "tool_result"]
            if res:
                s["calls"] += len(res)
                s["errors"] += [n for b in res if b.get("is_error")]
                for b in res:
                    note_wait(b.get("tool_use_id"), ts, n)
                continue
            t = text_of(c).strip()
        else:
            kind = pl.get("type")
            if r.get("type") == "session_meta":
                s["id"], s["cwd"] = pl.get("id") or pl.get("session_id"), pl.get("cwd")
                continue
            if r.get("type") == "event_msg":
                if kind == "token_count":
                    u = codex_usage((pl.get("info") or {}).get("total_token_usage") if isinstance(pl.get("info"), dict) else None)
                    if u:
                        token_totals, token_samples = u, token_samples + 1  # cumulative: last wins
                elif kind == "turn_aborted":
                    s["interrupts"].append(n)
                continue
            if isinstance(kind, str) and kind.endswith("_call") and pl.get("call_id"):
                pending[str(pl["call_id"])] = (ts, str(pl.get("name")), n)
                continue
            if isinstance(kind, str) and kind.endswith("call_output"):
                s["calls"] += 1
                output = pl.get("output")
                if ERR.search(output if isinstance(output, str) else json.dumps(output)):
                    s["errors"].append(n)
                note_wait(pl.get("call_id"), ts, n)
                continue
            t = text_of(pl.get("content")).strip() if kind == "message" and pl.get("role") == "user" else ""
        if not accepted_text(t):
            continue
        if t.startswith(INTERRUPT_PREFIX):
            s["interrupts"].append(n)
            continue
        s["turns"] += 1
        if CORR.match(t[:200]):
            s["corrections"].append(n)

    s["started_at"], s["ended_at"] = iso(first_ts), iso(last_ts)
    s["tokens"] = token_block(token_totals, token_samples)
    if load_samples is not None:
        s["load"] = {"samples": len(load_samples), "joined": len(joined),
                     "under_load": sum(1 for x in joined if x > LOAD_PER_CORE_BUSY),
                     "load_per_core_max": max(joined) if joined else 0.0}
    return s


# ---------------------------------------------------------------- subcommands
def cmd_paths(args) -> int:
    main = main_checkout(args.repo)
    r = retro_dir(main)
    ignored = is_ignored(os.path.join(r, "inbox", "probe.md"))
    print("main: %s" % main)
    print("retro: %s" % r)
    print("ignored: %s" % {True: "yes", False: "NO: stop, .ybase/ must be gitignored", None: "outside any repo"}[ignored])
    for d in worktree_dirs(main):
        print("scope: %s" % d)
    for harness, top in transcript_roots():
        print("%s: %s (%s)" % (harness, top, "present" if os.path.isdir(top) else "absent"))
    return 0 if ignored else 1


def cmd_distill(args) -> int:
    main = main_checkout(args.repo)
    out = os.path.abspath(args.out or os.path.join(retro_dir(main), "distill"))
    refuse_unless_ignored(out)
    os.makedirs(out, exist_ok=True)
    load_dir = os.path.join(retro_dir(main), "load")
    prefixes = scope_prefixes(main, args.prefix)
    cutoff = time.time() - args.days * 86400
    if args.only:
        paths = [(harness_of(args.only), os.path.abspath(args.only))]
    else:
        paths = []
        for harness, top in transcript_roots():
            for d, _, fs in os.walk(top, followlinks=True):
                if "subagents" in d.split(os.sep):
                    continue
                paths += [(harness, os.path.join(d, f)) for f in sorted(fs) if f.endswith(".jsonl")]
    print("scope: main %s; %d scope dirs; window %g days; out %s" % (main, len(worktree_dirs(main)) + len(args.prefix), args.days, out))
    written = skipped = 0
    for harness, p in paths:
        try:
            if not args.only and os.stat(p).st_mtime < cutoff:
                continue
            s = distill_one(p, harness, load_dir)
        except OSError as exc:
            print("skip %s: %s" % (p, exc))
            skipped += 1
            continue
        if not s["id"]:
            print("skip %s: no session id read (format mismatch, %d unparsed lines)" % (p, s["unparsed"]))
            skipped += 1
            continue
        if not in_scope(s["cwd"], prefixes):
            if args.only:
                print("skip %s %s: cwd %s is outside this checkout and its worktrees" % (harness, s["id"], s["cwd"]))
            skipped += 1
            continue
        target = os.path.join(out, "%s-%s.json" % (harness, s["id"]))
        if args.closed:
            s["closed"] = True
        elif os.path.isfile(target):
            try:
                with open(target, encoding="utf-8") as fh:
                    old = json.load(fh)
                s["closed"] = bool(old.get("closed")) and old.get("mtime") == s["mtime"]
            except (OSError, ValueError):
                pass
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(s, fh, sort_keys=True)
        os.replace(tmp, target)
        written += 1
        print("%s %s turns %d corr %d intr %d calls %d err %d waits %d unparsed %d tokens %s closed %s" % (
            harness, s["id"], s["turns"], len(s["corrections"]), len(s["interrupts"]), s["calls"],
            len(s["errors"]), len(s["waits"]), s["unparsed"], (s["tokens"] or {}).get("total", "-"), s["closed"]))
    print("distilled: %d written, %d skipped" % (written, skipped))
    return 0


def cmd_turns(args) -> int:
    path = os.path.abspath(args.transcript)
    harness = args.harness or harness_of(path)
    after_interruption = False
    for n, ts, t, interrupt in human_turns(path, harness):
        if interrupt:
            after_interruption = True
            continue
        m = CORR.match(t[:200])
        print(json.dumps({"line": n, "ts": iso(ts), "text": t[:args.chars],
                          "correction_label": m.group(1).lower() if m else None,
                          "after_interruption": after_interruption}, ensure_ascii=False))
        after_interruption = False
    return 0


def examined_ids(r: str) -> set[str]:
    seen: set[str] = set()
    for f in glob.glob(os.path.join(r, "inbox", "*.md")) + glob.glob(os.path.join(r, "done", "*.md")):
        try:
            with open(f, encoding="utf-8") as fh:
                m = EXAMINED_RE.search(fh.read())
        except OSError:
            continue
        if m:
            seen |= set(m.group(1).split())
    return seen


def cmd_rank(args) -> int:
    main = main_checkout(args.repo)
    r = retro_dir(main)
    seen = examined_ids(r)
    rows, skip = [], {"examined": 0, "gone": 0, "unread": 0}
    for f in glob.glob(os.path.join(r, "distill", "*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                s = json.load(fh)
        except (OSError, ValueError):
            skip["unread"] += 1
            continue
        key = "%s:%s" % (s.get("harness"), s.get("id"))
        if key in seen:
            skip["examined"] += 1
            continue
        if not os.path.exists(s.get("path", "")):
            skip["gone"] += 1
            continue
        c, i, e = len(s.get("corrections", [])), len(s.get("interrupts", [])), len(s.get("errors", []))
        score = 3 * c + 2 * i + min(e, 20)
        rows.append((score, c, i, e, s))
    rows.sort(key=lambda x: (-x[0], -x[4].get("mtime", 0)))
    print("scope: %d unexamined and readable; skipped %s; score = 3*corr + 2*intr + min(err, 20), weights [A]"
          % (len(rows), json.dumps(skip, sort_keys=True)))
    for score, c, i, e, s in rows[:args.top]:
        tokens = (s.get("tokens") or {}).get("total")
        print("score %d = 3*%d + 2*%d + min(%d, 20)  turns %d  calls %d  waits %d  tokens %s  live %s  closed %s  %s:%s"
              % (score, c, i, e, s.get("turns", 0), s.get("calls", 0), len(s.get("waits", [])),
                 tokens if tokens is not None else "-", time.time() - s.get("mtime", 0) < 3600,
                 s.get("closed", False), s.get("harness"), s.get("id")))
    return 0


def cmd_span(args) -> int:
    if len(args.bounds) % 2:
        sys.exit("retro span: give START END pairs")
    spans = [(args.bounds[k], args.bounds[k + 1]) for k in range(0, len(args.bounds), 2)]
    hit = {sp: 0 for sp in spans}
    for n, r in iter_lines(os.path.abspath(args.transcript)):
        for sp in spans:
            if sp[0] <= n <= sp[1]:
                hit[sp] += 1
        if not any(a <= n <= b for a, b in spans):
            continue
        if r is None:
            print("L%d unparsed" % n)
            continue
        body = r.get("message") or r.get("payload") or {}
        role = body.get("role") if isinstance(body, dict) else None
        text = " ".join(flat(body.get("content", body) if isinstance(body, dict) else body).split())
        print("L%d %s: %s" % (n, role or r.get("type"), text[:args.chars]))
    for sp in spans:
        if not hit[sp]:
            print("L%d-L%d: no such lines" % sp)
    return 0


def cmd_covered(args) -> int:
    main = main_checkout(args.repo)
    n = 0
    for f in sorted(glob.glob(os.path.join(main, "memory", "*.md"))):
        with open(f, encoding="utf-8") as fh:
            for block in TRIGGERS_RE.findall(fh.read()):
                for line in block.splitlines():
                    if line.startswith("- `"):
                        print("memory/%s: %s" % (os.path.basename(f), line))
                        n += 1
    rules = os.path.join(main, "docs", "rules.md")
    if os.path.isfile(rules):
        with open(rules, encoding="utf-8") as fh:
            for line in fh:
                if RULE_RE.match(line):
                    print("docs/rules.md: %s" % line.rstrip())
                    n += 1
    print("covered: %d lines" % n, file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    sub.required = True

    def common(p):
        p.add_argument("--repo", help="a checkout of the repository (default: the one holding this file)")
        return p

    common(sub.add_parser("paths", help="where retro state lives and whether git ignores it")).set_defaults(fn=cmd_paths)
    d = common(sub.add_parser("distill", help="one JSON record per session in scope"))
    d.add_argument("--days", type=float, default=14, help="window by transcript mtime (default 14)")
    d.add_argument("--only", metavar="TRANSCRIPT", help="distil this one transcript, whatever its age")
    d.add_argument("--closed", action="store_true", help="mark the record closed (the session has ended)")
    d.add_argument("--out", metavar="DIR", help="record directory (default <main>/.ybase/retro/distill/; must be gitignored)")
    d.add_argument("--prefix", metavar="DIR", action="append", default=[],
                   help="an extra directory to treat as in scope, such as a removed worktree")
    d.set_defaults(fn=cmd_distill)
    t = common(sub.add_parser("turns", help="every accepted human turn as JSON"))
    t.add_argument("transcript")
    t.add_argument("--chars", type=int, default=400, help="characters of text per turn (default 400)")
    t.add_argument("--harness", choices=("claude", "codex"), help="override the harness guessed from the path")
    t.set_defaults(fn=cmd_turns)
    rk = common(sub.add_parser("rank", help="unexamined distilled sessions by evidence"))
    rk.add_argument("--top", type=int, default=3)
    rk.set_defaults(fn=cmd_rank)
    sp = sub.add_parser("span", help="lines START..END of a transcript, flattened")
    sp.add_argument("transcript")
    sp.add_argument("bounds", type=int, nargs="+", metavar="N")
    sp.add_argument("--chars", type=int, default=400)
    sp.set_defaults(fn=cmd_span)
    common(sub.add_parser("covered", help="trigger lines and rules already recorded")).set_defaults(fn=cmd_covered)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
