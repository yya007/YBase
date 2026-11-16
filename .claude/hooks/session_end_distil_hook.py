#!/usr/bin/env python3
"""SessionEnd hook: distil the session that just closed, so a retro can cite its record.

Refuses: nothing. A session end cannot be refused, so this hook always exits 0, prints
nothing on stdout and never raises into a terminal that is closing. A failure is one line in
`.ybase/retro/closed.log`.

What it does: validates the payload (`session_id` is a session id and `transcript_path` is
that session's own `<session_id>.jsonl`, so a malformed payload cannot point the distiller
at another session's file), appends `{session_id, transcript_path, ended_at}` to
`.ybase/retro/closed.jsonl`, and starts `python3 tools/retro.py distill --only
<transcript_path> --closed` DETACHED (its own session, stdout and stderr to
`.ybase/retro/closed.log`) and returns at once. A long transcript takes seconds to parse
and the harness is shutting down. A resumed session appends to the same transcript, and its
next end distils it again.

Where it writes: `.ybase/retro/` of the MAIN checkout, which the repo gitignores. The
main checkout is resolved from this file's own location (`git rev-parse --git-common-dir`),
never from the hook's cwd, so a hook fired from a worktree still feeds the one inbox. The
distiller itself refuses a destination git does not ignore.

Escape: `YBASE_RETRO_OFF=1` in the harness environment makes it a no-op. `YBASE_RETRO_DRY_RUN=1`
prints the distiller argv as JSON instead of starting it (for tests). Claude Code only: Codex
has no session hooks, so its sessions are distilled by the next `tools/retro.py distill` run.

    python3 .claude/hooks/session_end_distil_hook.py < payload.json
"""
import datetime
import json
import os
import re
import subprocess
import sys

SESSION_ID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
HERE = os.path.dirname(os.path.abspath(__file__))


def main_checkout():
    """The main checkout of the repository holding this file, or None outside one."""
    checkout = os.path.dirname(os.path.dirname(HERE))
    try:
        r = subprocess.run(["git", "-C", HERE, "rev-parse", "--git-common-dir"],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    common = r.stdout.strip()
    if r.returncode != 0 or not common:
        return None
    if not os.path.isabs(common):
        common = os.path.join(HERE, common)
    main = os.path.dirname(os.path.realpath(common))
    return main if os.path.isdir(main) else checkout


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(retro, line):
    try:
        os.makedirs(retro, exist_ok=True)
        with open(os.path.join(retro, "closed.log"), "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (now(), line))
    except OSError:
        pass


def plan(payload, main):
    """(argv, note) for this payload, or (None, why it was skipped)."""
    sid = str(payload.get("session_id") or "")
    transcript = str(payload.get("transcript_path") or "")
    if not SESSION_ID.fullmatch(sid):
        return None, "skip: %r is not a session id" % sid[:40]
    if os.path.basename(transcript) != sid + ".jsonl" or not os.path.isfile(transcript):
        return None, "skip %s: transcript_path is not this session's file or is missing" % sid
    for checkout in (os.path.dirname(os.path.dirname(HERE)), main):
        tool = os.path.join(checkout, "tools", "retro.py")
        if os.path.isfile(tool):
            return [sys.executable, tool, "distill", "--only", transcript, "--closed"], "distil %s" % sid
    return None, "skip %s: tools/retro.py not found beside this hook" % sid


def main():
    if os.environ.get("YBASE_RETRO_OFF"):
        return 0
    main_dir = main_checkout()
    if main_dir is None:
        return 0
    retro = os.path.join(main_dir, ".ybase", "retro")
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        argv, note = plan(payload, main_dir)
        log(retro, note)
        if argv is None:
            return 0
        with open(os.path.join(retro, "closed.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"session_id": payload["session_id"],
                                 "transcript_path": payload["transcript_path"],
                                 "ended_at": now()}, sort_keys=True) + "\n")
        if os.environ.get("YBASE_RETRO_DRY_RUN"):
            print(json.dumps(argv))
            return 0
        with open(os.path.join(retro, "closed.log"), "a", encoding="utf-8") as logf:
            subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=logf, stderr=logf,
                             start_new_session=True, close_fds=True)
    except Exception as exc:  # noqa: BLE001  a session end is not the moment to raise
        log(retro, "error: %s: %s" % (type(exc).__name__, exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
