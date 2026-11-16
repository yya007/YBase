#!/usr/bin/env python3
"""PostToolUse hook: record host load after each tool call, for the retro's wait analysis.

Refuses: nothing. It appends one tab-separated sample per call and exits 0; on any problem
(malformed stdin, a missing field, no load average on this platform, an unwritable
directory) it is a silent no-op, because a recording hook must never slow or break a session.

Sample: `ts, session_id, tool_use_id, tool_name, load1, load5, load15, ncpu`, appended in one
write to `.ybase/retro/load/<session_id>.tsv` under the MAIN checkout, which the repo
gitignores. The main checkout is resolved from this file's own location, never from cwd.
`tools/retro.py distill` joins the samples to the tool waits it finds in the transcript, by
`tool_use_id`, so a slow call can be told apart from a loaded host. An absent file means
NOT MEASURED, never zero load.

Escape: `YBASE_RETRO_OFF=1` in the harness environment makes it a no-op. Claude Code only:
Codex runs no PostToolUse hook (it runs only the allow gate, before a call), so its records
carry no load samples.

    python3 .claude/hooks/tool_load_hook.py < payload.json
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def main_checkout():
    """Walk up from this file to `.git`; a `.git` file names the main checkout's worktree entry."""
    d = HERE
    while True:
        dotgit = os.path.join(d, ".git")
        if os.path.isdir(dotgit):
            return d
        if os.path.isfile(dotgit):
            with open(dotgit, encoding="utf-8") as fh:
                target = fh.read().strip().partition("gitdir:")[2].strip()
            target = os.path.realpath(os.path.join(d, target))
            if os.path.basename(os.path.dirname(target)) == "worktrees":
                return os.path.dirname(os.path.dirname(os.path.dirname(target)))
            return os.path.dirname(target)
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def main():
    try:
        if os.environ.get("YBASE_RETRO_OFF"):
            return 0
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        fields = [payload.get(k) for k in ("session_id", "tool_use_id", "tool_name")]
        if any(not isinstance(f, str) or not f or "\t" in f or "\n" in f or os.sep in f for f in fields):
            return 0
        main_dir = main_checkout()
        if main_dir is None:
            return 0
        load1, load5, load15 = os.getloadavg()
        ncpu = os.cpu_count()
        if not isinstance(ncpu, int) or ncpu <= 0:
            return 0
        load_dir = os.path.join(main_dir, ".ybase", "retro", "load")
        os.makedirs(load_dir, exist_ok=True)
        line = "%.3f\t%s\t%s\t%s\t%.2f\t%.2f\t%.2f\t%d\n" % (
            time.time(), fields[0], fields[1], fields[2], load1, load5, load15, ncpu)
        with open(os.path.join(load_dir, fields[0] + ".tsv"), "a", encoding="utf-8") as fh:
            fh.write(line)  # one write, so concurrent appenders never interleave a row
    except Exception:  # noqa: BLE001  a recording hook never breaks the call it records
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
