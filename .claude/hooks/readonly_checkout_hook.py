#!/usr/bin/env python3
"""PreToolUse hook: refuse a Write or Edit that lands in the main checkout.

Rule 15 in docs/rules.md: work in a worktree, one per unit of work, made with
`ybase wt <name>`. The main checkout stays on the default branch and is
never edited. A session's main agent follows that; a subagent inherits the
session's working directory and not the reasoning that chose it, so a dispatch
that names no path writes wherever the parent happened to stand.

OPT-IN. The guard ships OFF. It runs only when `YBASE_GUARD_READONLY_CHECKOUT=1`
is in the process environment or in YBase's `.env`; otherwise it allows
without looking further.

REFUSES (when on): Write, Edit, MultiEdit and NotebookEdit whose file lands
inside a main checkout of YBase or of a managed repo (one in the repo list
that is present on this machine). A main checkout is a repository root whose
`.git` is a DIRECTORY; a linked worktree has a `.git` FILE, so every worktree
passes by the same test with nothing to keep in sync. YBase is found from this
hook's own file location, never from the session's working directory, so the
hook works in a session started inside a managed repo.

PASSES: any other tool; a path outside those checkouts; inside YBase a path
under `.ybase/`, `tmp/` or `kb/` and the `.env` file (per-machine state that is
never committed); a payload the hook cannot read; any internal error, a missing
or unreadable `.env` included (a guard that blocks every write is worse than the
mess it prevents, so it allows, and says so on stderr).

ESCAPE: `MAIN_CHECKOUT_WRITE=1` in the environment of the session, for the
rare write the user asked for in the main checkout itself. An editing tool has
no command line to prefix, so this one is set on the process, for example
`MAIN_CHECKOUT_WRITE=1 claude`.

Blocking, unlike the advisory hooks beside it, because an advisory lands after
the write happened, and undoing it means guessing which paths in `git status`
were the agent's. Denial is exit 2 with the reason on stderr and the same
reason as JSON on stdout.

Claude Code only. Codex runs only the allow gate as a hook (.codex/hooks.json);
docs/codex.md names the
convention it follows instead. Runnable by hand:
`python3 .claude/hooks/readonly_checkout_hook.py < payload.json`.
"""
import json
import os
import pathlib
import sys
import traceback

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
GUARD = "READONLY_CHECKOUT"
# Per-machine state lives here and is gitignored; writing it in the main
# checkout is how `bin/ybase setup` and the retro tooling work.
ALLOWED_TOP_DIRS = (".ybase", "tmp", "kb")
ALLOWED_TOP_FILES = (".env",)
ESCAPE = "MAIN_CHECKOUT_WRITE"

DENIAL = """\
Refused: {path} is inside the main checkout at {root}.

The main checkout is read-only (docs/rules.md, rule 15). Every change, including
a one-line fix, is made in a worktree on its own branch:

  {command}

then re-run this edit against the copy of the file inside that worktree.

If you are a subagent, you inherited this directory from the session that
dispatched you. Say so in your report instead of writing here; the agent that
dispatched you owns creating the worktree.

{allowed} {escape}=1 in the session's
environment skips this hook when the user asked for a write here."""


def repo_root(path):
    """The nearest ancestor of `path` (inclusive) holding a `.git`, or None."""
    for parent in [path] + list(path.parents):
        if (parent / ".git").exists():
            return parent
    return None


def ybase_home():
    """YBase's main checkout, found from this file and never from the session's cwd.

    Run from a linked worktree of YBase, this file sits in the worktree; the `.env` and
    the repo list belong to the main checkout (envfile.main_checkout)."""
    root = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "tools"))
    import envfile
    return envfile.main_checkout(root)


def protected_roots(home):
    """{resolved main checkout: repo name or None for YBase}, when the guard is on, else {}."""
    sys.path.insert(0, str(home / "tools"))
    import envfile
    if not envfile.guard_enabled(GUARD, home):
        return {}
    roots = {home.resolve(): None}
    import repos
    for repo in repos.all_repos(home):
        path = repos.repo_path(repo, home)
        if (path / ".git").is_dir():
            roots.setdefault(path.resolve(), repo.name)
    return roots


def decide(payload, environ=None):
    """Return a denial reason, or None to allow."""
    environ = os.environ if environ is None else environ
    if environ.get(ESCAPE) == "1":
        return None
    if payload.get("tool_name") not in WRITE_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw, str) or not raw:
        return None
    home = ybase_home()
    protected = protected_roots(home)  # empty unless the user switched the guard on
    if not protected:
        return None
    path = pathlib.Path(raw).expanduser()
    if not path.is_absolute():
        # A relative path resolves against the session's cwd, which is the very
        # thing in question here, so resolve it the way the tool will.
        path = pathlib.Path(payload.get("cwd") or ".") / path
    try:
        path = path.resolve()
    except OSError:
        return None
    root = repo_root(path)
    if root is None or not (root / ".git").is_dir() or root not in protected:
        return None
    name = protected[root]
    rel = path.relative_to(root)
    if name is None:
        if rel.parts and rel.parts[0] in ALLOWED_TOP_DIRS:
            return None
        if rel.parts in [(f,) for f in ALLOWED_TOP_FILES]:
            return None
        command = "ybase wt <name>"
        allowed = "Paths under .ybase/, tmp/ and kb/, and .env, are allowed."
    else:
        command = f"ybase wt <name> --repo {name}"
        allowed = "Nothing in a managed repo's main checkout is exempt."
    return DENIAL.format(path=path, root=root, escape=ESCAPE, command=command, allowed=allowed)


def _run():
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        return 0
    reason = decide(payload)
    if reason is None:
        return 0
    json.dump({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}, sys.stdout)
    sys.stderr.write(reason + "\n")
    return 2


def main():
    try:
        return _run()
    except Exception:
        # A hook that cannot decide allows, out loud: exit 0 is also what a
        # clean call returns, so a silent handler would read like a clean call.
        sys.stderr.write("readonly_checkout_hook: allowed without checking, it raised:\n"
                         + traceback.format_exc())
        return 0


if __name__ == "__main__":
    sys.exit(main())
