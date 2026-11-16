#!/usr/bin/env python3
"""PreToolUse hook: load the law for a moment the first time a session reaches it.

A rule that binds when you commit, push, open a PR, review, poll, delegate or
edit the checks does not need to sit in every session's context: the command
announces the moment. This hook matches the command (or, for Write and Edit,
the path) against the table below and, on the FIRST match per session and
moment, denies the call with `docs/law/<moment>.md` as the reason. It writes a
sentinel keyed by session and moment under `<main checkout>/.ybase/law-ack/`
(gitignored per-machine state), so the retry passes.

REFUSES, once per session and moment: a Bash command whose command position
reaches a moment in MOMENTS (decided from the shlex token stream, so a decoy in
an argument or a quoted string does not fire; env assignments, wrappers such as
`timeout 60`, `nohup` or `sudo`, and a program's own leading options such as
`git -C dir` or `gh -R repo` are seen through); an Agent dispatch (the delegate
moment); a Write or Edit whose path falls under a moment's path pattern, or, for
the docs moment, under the `research/`, `memory/` or `worklog/` folder of a
knowledge base named by this repository's or its main checkout's settings. A
command that reaches several moments gets one denial naming all of them.

PASSES: the retry (the sentinel exists); a moment whose law file is missing,
silently, since the law files and this table may land separately; a KB path
when the KB roots cannot be read (no KB paths, never a crash); a command shlex
cannot parse; a payload the hook cannot read; any internal error.

ESCAPE: `LAW_SKIP=1` as an environment prefix on the command (`LAW_SKIP=1 git
push`), or in the process environment for Write, Edit and Agent, which have no
command line.

Deny first rather than advise: a PreToolUse advisory lands beside the tool
result, after the command ran, which is one call too late for a rule about the
act. The deny costs one retry and happens once per session per moment.

Claude Code only. Codex runs only the allow gate as a hook (.codex/hooks.json);
docs/codex.md lists the same law files to read at the same moments. Runnable by
hand:
`python3 .claude/hooks/moment_law_hook.py < payload.json`.
"""
import importlib.util
import json
import os
import pathlib
import re
import shlex
import sys
import traceback

REPO = pathlib.Path(__file__).resolve().parents[2]
LAW = REPO / "docs" / "law"
ESCAPE = "LAW_SKIP"

# (moment, decides a simple command's tokens, pattern over a repo-relative Write/Edit path).
# The moment names the file docs/law/<moment>.md; the `law` check in tools/checks.py keeps
# this table and that folder equal.
_REVIEW_API = re.compile(r"(^|/)pulls/[^/\s]+/(reviews|comments)(/|$|\?)")
_YBASE = re.compile(r"(^|/)ybase$")


def _is(tokens, *words):
    return tuple(tokens[:len(words)]) == words


# Programs that only run another command. They must not hide that command from the
# table: `timeout 60 git push` is a push (and a wait), `nohup git commit` is a commit.
_WRAPPERS = {"nohup", "sudo", "nice", "time", "timeout", "setsid", "command", "exec",
             "builtin", "caffeinate", "stdbuf"}
_WRAPPER_VALUE_FLAGS = {
    "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-T", "-U"},
    "nice": {"-n"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "stdbuf": {"-i", "-o", "-e"},
}
# A program's own options that take a value and may precede its subcommand.
_GIT_VALUE_FLAGS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
                    "--config-env"}
_GH_VALUE_FLAGS = {"-R", "--repo"}


def unwrap(tokens):
    """One simple command with its env assignments and wrapper programs stripped."""
    toks = list(tokens)
    while toks:
        head = toks[0]
        if _ENV_ASSIGN.match(head):
            toks.pop(0)
            continue
        if head == "env":
            toks.pop(0)
            while toks and (_ENV_ASSIGN.match(toks[0]) or toks[0] in ("-u", "-i", "-0", "--ignore-environment")):
                toks = toks[2:] if toks[0] == "-u" else toks[1:]
            continue
        if head not in _WRAPPERS:
            break
        toks.pop(0)
        values = _WRAPPER_VALUE_FLAGS.get(head, set())
        while toks and toks[0].startswith("-"):
            flag = toks.pop(0)
            if flag in values and toks:
                toks.pop(0)
        if head == "timeout" and toks:
            toks.pop(0)  # the duration
    return toks


def _after_global_flags(tokens, program, value_flags):
    """The words after `program` and its own leading options, or [] when it is not `program`."""
    if not tokens or tokens[0] != program:
        return []
    out = list(tokens[1:])
    while out and out[0].startswith("-"):
        flag = out.pop(0)
        if "=" not in flag and flag in value_flags and out:
            out.pop(0)
    return out


def _git_words(tokens):
    return _after_global_flags(tokens, "git", _GIT_VALUE_FLAGS)


def _gh_words(tokens):
    return _after_global_flags(tokens, "gh", _GH_VALUE_FLAGS)


def _git(tokens, *subs):
    words = _git_words(tokens)
    return bool(words) and words[0] in subs


def _gh(tokens, group, *subs):
    words = _gh_words(tokens)
    return len(words) >= 2 and words[0] == group and words[1] in subs


def _ybase(tokens, sub):
    toks = list(tokens)
    if toks and toks[0] in ("bash", "sh"):
        toks = toks[1:]
    return len(toks) >= 2 and bool(_YBASE.search(toks[0])) and toks[1] == sub


def _commit(t):
    return _git(t, "commit")


def _push(t):
    return _git(t, "push")


def _worktree(t):
    words = _git_words(t)
    if len(words) >= 2 and words[0] == "worktree" and words[1] in ("add", "remove", "prune"):
        return True
    if _ybase(t, "wt"):
        return True
    return _ybase(t, "worktrees") and "--reap" in t


def _pr(t):
    return _gh(t, "pr", "create", "edit", "ready", "merge", "close")


def _review(t):
    if _gh(t, "pr", "review", "comment"):
        return True
    words = _gh_words(t)
    return bool(words) and words[0] == "api" and any(_REVIEW_API.search(x) for x in words[1:])


def _watch(t):
    if not t:
        return False
    if t[0] in ("sleep", "until", "while", "wait", "timeout", "watch"):
        return True
    if t[0] == "tail":
        return any(x == "--follow" or (x.startswith("-") and not x.startswith("--") and "f" in x) for x in t[1:])
    return False


MOMENTS = [
    ("commit", _commit, None),
    ("push", _push, None),
    ("worktree", _worktree, None),
    ("pr", _pr, None),
    ("review", _review, None),
    ("watch", _watch, None),
    ("delegate", None, None),
    ("checks", None, re.compile(r"^(tools|tests|\.githooks|\.claude/hooks)/")),
    ("docs", None, re.compile(r"^docs/")),
]
# The docs moment also fires for a file under one of these folders of any configured KB root.
KB_DOC_MOMENT = "docs"
KB_DOC_DIRS = ("research", "memory", "worklog")
TOOL_MOMENTS = {"Agent": "delegate"}
PATH_TOOLS = {"Write", "Edit", "MultiEdit"}

_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", "\n"}


def moments():
    """Every moment name this hook can fire; the `law` check reads it."""
    return [m for m, _, _ in MOMENTS]


def tokenize(command):
    """Shell words with `;`, `&&`, `|`, `&`, parentheses and newlines as separate tokens."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars="();<>|&\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    return list(lexer)


def escape_prefixed(tokens, assignment):
    """True when `assignment` (NAME=value) leads a simple command, as an env prefix does."""
    at_start = True
    for t in tokens:
        if t in _SEPARATORS:
            at_start = True
        elif at_start and _ENV_ASSIGN.match(t):
            if t == assignment:
                return True
        else:
            at_start = False
    return False


def simple_commands(tokens):
    """Each simple command's tokens, with leading env assignments and `env` stripped."""
    out, cur = [], []
    for t in tokens + [";"]:
        if t not in _SEPARATORS:
            cur.append(t)
            continue
        while cur and _ENV_ASSIGN.match(cur[0]):
            cur.pop(0)
        if cur and cur[0] == "env":
            cur.pop(0)
            while cur and (_ENV_ASSIGN.match(cur[0]) or cur[0] == "-u"):
                if cur[0] == "-u":
                    cur = cur[2:]
                else:
                    cur.pop(0)
        if cur:
            out.append(cur)
        cur = []
    return out


def relative_path(raw, cwd):
    """`raw` relative to the repository this hook lives in, else to cwd, else as given."""
    path = pathlib.Path(raw).expanduser()
    if not path.is_absolute():
        return path.as_posix()
    for base in (REPO, pathlib.Path(cwd or ".")):
        try:
            return path.resolve().relative_to(pathlib.Path(base).resolve()).as_posix()
        except (ValueError, OSError):
            continue
    return path.as_posix()


def configured_kb_roots(environ=None):
    """The KB roots named by this repository's settings and its main checkout's
    (tools/envfile.py, loaded from beside this hook). Any failure means no KB roots."""
    try:
        spec = importlib.util.spec_from_file_location("ybase_envfile", REPO / "tools" / "envfile.py")
        envfile = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(envfile)
        roots = []
        for base in (REPO, main_checkout(REPO)):
            for kb in envfile.kb_roots(base, environ):
                if kb not in roots:
                    roots.append(kb)
        return roots
    except Exception:
        return []


def in_kb_documents(raw, cwd, kb_roots):
    """True when `raw` names a file under `research/`, `memory/` or `worklog/` of a KB root."""
    path = pathlib.Path(raw).expanduser()
    if not path.is_absolute():
        path = pathlib.Path(cwd or ".") / path
    for kb in kb_roots:
        kb = pathlib.Path(kb)
        for p, k in ((pathlib.Path(os.path.normpath(path)), pathlib.Path(os.path.normpath(kb))),
                     (path.resolve(), kb.resolve())):
            try:
                parts = p.relative_to(k).parts
            except ValueError:
                continue
            if len(parts) > 1 and parts[0] in KB_DOC_DIRS:
                return True
    return False


def moments_for(tool_name, tool_input, cwd=None, environ=None, kb_roots=None):
    """Every moment this call reaches, in table order. A command is read both as
    written and unwrapped, so `timeout 60 git push` is a wait and a push. A path is
    matched against the table and against the KB roots (`configured_kb_roots()` when
    `kb_roots` is None)."""
    environ = os.environ if environ is None else environ
    if environ.get(ESCAPE) == "1":
        return []
    if tool_name == "Bash":
        cmd = tool_input.get("command") or ""
        if not isinstance(cmd, str):
            return []
        try:
            tokens = tokenize(cmd)
        except ValueError:
            return []
        if escape_prefixed(tokens, ESCAPE + "=1"):
            return []
        hit = set()
        for simple in simple_commands(tokens):
            inner = unwrap(simple)
            for moment, decide, _ in MOMENTS:
                if decide and (decide(simple) or decide(inner)):
                    hit.add(moment)
        return [m for m, _, _ in MOMENTS if m in hit]
    if tool_name in TOOL_MOMENTS:
        return [TOOL_MOMENTS[tool_name]]
    if tool_name in PATH_TOOLS:
        raw = tool_input.get("file_path")
        if not isinstance(raw, str) or not raw:
            return []
        rel = relative_path(raw, cwd)
        hit = {moment for moment, _, ppat in MOMENTS if ppat and ppat.search(rel)}
        if KB_DOC_MOMENT not in hit:
            roots = configured_kb_roots(environ) if kb_roots is None else kb_roots
            if in_kb_documents(raw, cwd, roots):
                hit.add(KB_DOC_MOMENT)
        return [m for m, _, _ in MOMENTS if m in hit]
    return []


def moment_for(tool_name, tool_input, cwd=None, environ=None, kb_roots=None):
    """The first moment in table order, or None. `moments_for` gives all of them."""
    found = moments_for(tool_name, tool_input, cwd, environ, kb_roots)
    return found[0] if found else None


def main_checkout(root):
    """The main working tree of the repository at `root`: `root` itself unless
    `.git` is a worktree pointer file."""
    dotgit = root / ".git"
    if dotgit.is_file():
        try:
            text = dotgit.read_text(encoding="utf-8").strip()
        except OSError:
            return root
        if text.startswith("gitdir:"):
            gitdir = pathlib.Path(text.split(":", 1)[1].strip())
            if not gitdir.is_absolute():
                gitdir = root / gitdir
            # <main>/.git/worktrees/<name>
            if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
                return gitdir.parent.parent.parent
    return root


def ack_dir():
    override = os.environ.get("LAW_ACK_DIR")
    if override:
        return pathlib.Path(override)
    return main_checkout(REPO) / ".ybase" / "law-ack"


def _run():
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    found = moments_for(payload.get("tool_name") or "", tool_input, payload.get("cwd"))
    if not found:
        return 0
    session = re.sub(r"[^A-Za-z0-9_-]", "_", str(payload.get("session_id") or "nosession"))
    due = []
    for moment in found:
        law = LAW / (moment + ".md")
        sentinel = ack_dir() / session / moment
        if law.is_file() and not sentinel.exists():
            due.append((moment, law, sentinel))
    if not due:
        return 0
    # One denial covers every moment the call reaches, so the retry passes in one step.
    for _, _, sentinel in due:
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("read\n", encoding="utf-8")
    names = ", ".join("docs/law/%s.md" % m for m, _, _ in due)
    reason = ("Before this call, read the law for %s, %s, printed below; "
              "then re-run the same call, which passes for the rest of this session "
              "(%s=1 on the line skips this hook for one call).\n\n%s"
              % ("this moment" if len(due) == 1 else "these moments", names, ESCAPE,
                 "\n\n".join(law.read_text(encoding="utf-8") for _, law, _ in due)))
    sys.stderr.write(reason + "\n")
    json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                      "permissionDecision": "deny",
                                      "permissionDecisionReason": reason}}, sys.stdout)
    return 2


def main():
    try:
        return _run()
    except Exception:
        # A guard that can fail on its own bug must not stop all work: allow, out loud.
        sys.stderr.write("moment_law_hook: allowed without checking, it raised:\n"
                         + traceback.format_exc())
        return 0


if __name__ == "__main__":
    sys.exit(main())
