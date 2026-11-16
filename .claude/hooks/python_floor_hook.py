#!/usr/bin/env python3
"""PreToolUse hook: refuse a Python command running below the project's declared floor.

WHY. Below `requires-python`, imports and test collection fail before the code
under test runs, and the failure reads like a defect in the code. On a machine
with several interpreters, the bare `python3` on PATH is often the oldest.

WHAT IT REFUSES. A Bash command that runs `python`, `python3` or `python3.X`
in command position as `-m pytest`, `-m unittest`, `-c CODE` or `script.py`,
when the nearest `pyproject.toml` at or above the working directory (after any
`cd` earlier in the command), the script, or a pytest path operand declares
`requires-python = ">=X.Y"` and the interpreter the command would run is older
than X.Y. The refusal names an interpreter that meets the floor, found by
`tools/pick_python.sh --for-path <dir>`.

WHAT PASSES. An interpreter at or above the floor. Any uncertainty: no
`pyproject.toml`, no `>=` lower bound, an interpreter not on PATH, a version
probe that fails, a `cd` to a path the shell builds, an unparseable command.
Commands that do not run project code (`python3 --version`, `python3 -m venv`).

BLOCKING: the wrong-interpreter failure costs a debugging detour every time.

ESCAPE: prefix the command with `PYTHON_FLOOR_OK=1` when running below the
floor is the point (a compatibility check, for example).

A hook that cannot decide allows: malformed stdin and any internal error exit
0, the last out loud on stderr. It does not see Python started by a script the
command runs, or by `uv run`, `tox` or `make`. Claude Code is the only harness
that runs this hook; `docs/codex.md` carries the rule for Codex.

Run by hand: python3 .claude/hooks/python_floor_hook.py < payload.json
"""
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import traceback

ESCAPE = "PYTHON_FLOOR_OK"
INTERPRETER = re.compile(r"^python(?:3(?:\.\d+)?)?$")
VERSION = re.compile(r"Python\s+(\d+)\.(\d+)")
FLOOR = re.compile(r"^\s*requires-python\s*=.*?>=\s*(\d+)\.(\d+)", re.MULTILINE)
OPERATORS = {";", "&&", "||", "|", "&", "(", ")", "|&", ";;"}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
# Interpreter options that consume the next token.
PY_VALUE_OPTS = {"-W", "-X", "--check-hash-based-pycs"}
PICKER = pathlib.Path(__file__).resolve().parents[2] / "tools" / "pick_python.sh"

DENIAL = """\
Refused: {interpreter} is Python {have}, but the nearest pyproject.toml
({project}) declares requires-python >= {floor}.

Below the declared floor, imports and test collection can fail before the
code under test runs, and the failure reads like a defect in the code.

{advice}

If running below the floor is the point:  {escape}=1 <the same command>"""


def _resolve_interpreter(token):
    base = token.rsplit("/", 1)[-1]
    if not INTERPRETER.match(base):
        return None
    if "/" in token:
        path = os.path.expanduser(token)
        return path if os.path.isfile(path) and os.access(path, os.X_OK) else None
    return shutil.which(token)


def python_version(interpreter):
    try:
        res = subprocess.run([interpreter, "--version"], capture_output=True, text=True,
                             timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    m = VERSION.search(res.stdout + res.stderr)
    return (int(m.group(1)), int(m.group(2))) if m else None


def nearest_floor(path):
    """(pyproject path, (major, minor)) for the nearest declared floor, or None."""
    candidate = pathlib.Path(path)
    if not candidate.exists() or candidate.is_file():
        candidate = candidate.parent
    try:
        candidate = candidate.resolve()
    except OSError:
        return None
    for directory in (candidate, *candidate.parents):
        pyproject = directory / "pyproject.toml"
        if not pyproject.is_file():
            continue
        try:
            text = pyproject.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        m = FLOOR.search(text)
        if not m:
            return None  # the nearest project has no lower bound: uncertain, allow
        return pyproject, (int(m.group(1)), int(m.group(2)))
    return None


def _tokens(command):
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return None


def _simple_commands(tokens):
    cmd = []
    for token in tokens:
        if token in OPERATORS:
            if cmd:
                yield cmd
            cmd = []
        else:
            cmd.append(token)
    if cmd:
        yield cmd


def command_contexts(command, session_cwd):
    """[(words, cwd)] for each simple command, following `cd`; None if undecidable."""
    tokens = _tokens(command)
    if tokens is None:
        return None
    cwd = pathlib.Path(session_cwd)
    found = []
    for words in _simple_commands(tokens):
        if words[0] == "cd":
            if len(words) != 2 or "$" in words[1] or "`" in words[1]:
                return None
            target = pathlib.Path(os.path.expanduser(words[1]))
            cwd = target if target.is_absolute() else cwd / target
            continue
        found.append((words, cwd))
    return found


def _strip_env_prefix(words):
    """-> (words without assignments and `env`, escaped)."""
    escaped = False
    while words and ASSIGNMENT.match(words[0]):
        name, _, value = words[0].partition("=")
        if name == ESCAPE and value:
            escaped = True
        words = words[1:]
    if words and words[0] == "env":
        words = words[1:]
        while words and (words[0].startswith("-") or ASSIGNMENT.match(words[0])):
            if words[0].startswith(ESCAPE + "=") and len(words[0]) > len(ESCAPE) + 1:
                escaped = True
            words = words[1:]
    return words, escaped


def _pytest_paths(args, cwd):
    paths = []
    for token in args:
        if token.startswith("-"):
            continue
        target = token.split("::", 1)[0]
        path = pathlib.Path(os.path.expanduser(target))
        path = path if path.is_absolute() else cwd / path
        if path.exists() or "/" in target or target.endswith(".py"):
            paths.append(path)
    return paths


def relevant(words, cwd):
    """(interpreter, [paths whose project floor applies]) or None when not a trigger."""
    words, escaped = _strip_env_prefix(words)
    if escaped or not words:
        return None
    interpreter = _resolve_interpreter(words[0])
    if interpreter is None:
        return None
    args = words[1:]
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "-m":
            module = args[i + 1] if i + 1 < len(args) else None
            if module == "pytest":
                return interpreter, [cwd] + _pytest_paths(args[i + 2:], cwd)
            if module == "unittest":
                return interpreter, [cwd]
            return None
        if tok == "-c":
            return (interpreter, [cwd]) if i + 1 < len(args) else None
        if tok == "-":
            return None
        if tok.startswith("-"):
            i += 2 if tok in PY_VALUE_OPTS else 1
            continue
        if tok.endswith(".py"):
            script = pathlib.Path(os.path.expanduser(tok))
            script = script if script.is_absolute() else cwd / script
            return interpreter, [cwd, script]
        return None
    return None


def replacement(project_dir):
    """An interpreter meeting the floor, via tools/pick_python.sh, or None."""
    try:
        res = subprocess.run(["bash", str(PICKER), "--for-path", str(project_dir)],
                             capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0 or not res.stdout.strip():
        return None
    return res.stdout.strip().splitlines()[-1]


def _deny(interpreter, have, floor, pyproject, picked):
    expr = "$(bash %s --for-path %s)" % (shlex.quote(str(PICKER)), shlex.quote(str(pyproject.parent)))
    if picked is None:
        advice = ("No interpreter on PATH meets >= %d.%d; `%s` lists what it tried. Install one "
                  "(for example `uv python install %d.%d` or a venv built from one), or set "
                  "PICK_PYTHON to its path, then run the command with:\n\n  %s"
                  % (floor[0], floor[1], expr[2:-1], floor[0], floor[1], expr))
    else:
        advice = ("Run the command with this interpreter instead:\n\n  %s ...\n\n"
                  "That expression currently resolves to %s." % (expr, picked))
    reason = DENIAL.format(interpreter=interpreter, have="%d.%d" % have, project=pyproject,
                           floor="%d.%d" % floor, advice=advice, escape=ESCAPE)
    json.dump({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}, sys.stdout)
    sys.stderr.write(reason + "\n")
    return 2


def _run():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    if os.environ.get(ESCAPE):
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        return 0
    session_cwd = payload.get("cwd")
    if not isinstance(session_cwd, str) or not session_cwd:
        session_cwd = os.getcwd()
    contexts = command_contexts(command, session_cwd)
    if contexts is None:
        return 0
    for words, cwd in contexts:
        found = relevant(words, cwd)
        if found is None:
            continue
        interpreter, paths = found
        have = python_version(interpreter)
        if have is None:
            continue
        for path in paths:
            project = nearest_floor(path)
            if project is None:
                continue
            pyproject, floor = project
            if have >= floor:
                continue
            # The version verdict is certain; a missing replacement changes the advice only.
            return _deny(interpreter, have, floor, pyproject, replacement(pyproject.parent))
    return 0


def main():
    try:
        return _run()
    except Exception:
        # A broken hook must never break a session: allow, and say so, because
        # a silent exit 0 reads exactly like a clean call.
        sys.stderr.write(
            "python_floor_hook: DISABLED for this call, it raised before it could\n"
            "finish, so no Python-floor check was made for the command:\n"
            + traceback.format_exc())
        return 0


if __name__ == "__main__":
    sys.exit(main())
