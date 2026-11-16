#!/usr/bin/env python3
"""PreToolUse hook: refuse a `pgrep -f` or `pkill -f` whose pattern matches itself.

WHY. The Bash tool runs the whole command as one `<shell> -c '<command>'`
argument, so the command text is the argument vector of the shell running it.
`pgrep -f` and `pkill -f` match against full argument vectors, which means a
literal pattern written in the command always finds that shell. Two failures
follow, both silent: a waiter such as `until ! pgrep -f PAT; do sleep 20; done`
never sees its condition go false, and `pkill -f PAT` kills the shell issuing
it, so every later command on the line is skipped.

WHAT IT REFUSES. A `pgrep`/`pkill` in command position carrying `-f` (or
`--full`) whose pattern, read as the regular expression pgrep applies, matches
the command text it sits in. That is the same test pgrep runs against the
wrapper's argument vector, so it decides rather than guesses.

WHAT PASSES. The bracket spelling `pgrep -f '[p]attern'`: the command holds
`[p]attern` and the expression wants `pattern`, so it cannot match itself.
A name match without `-f`. A pattern the shell builds (`$VAR`, backticks),
an expression the `re` module rejects, and a pattern that simply does not occur
in the command.

BLOCKING: an advisory note arrives after the waiter is already armed.

ESCAPE: prefix the command with `PGREP_SELF_OK=1` when you know what you are
doing (`PGREP_SELF_OK=1 pgrep -f pattern`). The bracket spelling is the usual
fix and needs no escape.

A hook that cannot decide allows: malformed stdin, an unparseable command and
any internal error exit 0, the last out loud on stderr. It does not see a
match made inside a script the command runs, or a `ps | grep` written by hand.
Claude Code is the only harness that runs this hook; `docs/codex.md` carries
the rule for Codex.

Run by hand: python3 .claude/hooks/self_matching_pgrep_hook.py < payload.json
"""
import json
import os
import re
import shlex
import sys
import traceback

ESCAPE = "PGREP_SELF_OK"
MATCHERS = ("pgrep", "pkill")
# Short options that consume the next token: without these, the value of `-u`
# in `pgrep -u NAME -f pat` reads as the pattern operand.
VALUE_SHORT = set("dgGPstuUF")
VALUE_LONG = {"--delimiter", "--pgroup", "--group", "--parent", "--session",
              "--terminal", "--euid", "--uid", "--pidfile", "--ns", "--nslist",
              "--signal"}
EXPANSION = ("$", "`")
OPERATORS = {";", "|", "||", "&", "&&", "(", ")", "<", ">", ">>", "\n", "|&", ";;"}
# Words that may stand before the command they run.
PREFIXES = {"sudo", "nohup", "nice", "time", "command", "exec", "builtin", "env",
            "timeout", "then", "do", "else", "elif", "if", "while", "until", "!",
            "{", "}"}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")

DENIAL = """\
Refused: `{tool} -f {pattern}` matches the shell running this very command.

A Bash tool call runs as `<shell> -c '<the whole command>'`, so the command
text is that shell's argument vector, and `-f` matches against it. The
pattern {pattern} occurs in this command, so {tool} finds the wrapper itself.

  as a waiter   `until ! pgrep -f ...` never goes false and spins until killed
  as a kill     `pkill -f ...` kills this shell and skips the rest of the line

Use one of these instead:

  wait on a pid you captured       PID=$!; until ! kill -0 "$PID"; do sleep 20; done
  wait on the artifact             until [ -s run.log ]; do sleep 20; done
  match without matching yourself  {tool} -f '{bracketed}'
  kill by reviewed pid             pgrep -f '{bracketed}'   # read the list, then kill <pid>

Give any waiter a wall-clock cap; a loop with none cannot tell a finished job
from a wedged one. On a shared machine, attribute a pid before killing it
(`ps -o user=,command= -p <pid>`) and prefer `kill <pid>` to `pkill -f`.

If the self-match is intended:  {escape}=1 <the same command>"""


def _bracketed(pattern):
    """The same pattern rewritten so it cannot match its own command line."""
    for i, ch in enumerate(pattern):
        if ch.isalnum():
            return pattern[:i] + "[" + ch + "]" + pattern[i + 1:]
    return pattern


def _tokenize(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def _simple_commands(tokens):
    cmd = []
    for tok in tokens:
        if tok in OPERATORS:
            if cmd:
                yield cmd
            cmd = []
        else:
            cmd.append(tok)
    if cmd:
        yield cmd


def _strip_prefixes(cmd):
    """-> (command without assignments and wrapper words, escaped)."""
    i, escaped = 0, False
    while i < len(cmd):
        tok = cmd[i]
        if ASSIGNMENT.match(tok):
            name, _, value = tok.partition("=")
            if name == ESCAPE and value:
                escaped = True
            i += 1
            continue
        if tok.rsplit("/", 1)[-1] in PREFIXES:
            i += 1
            while i < len(cmd) and cmd[i].startswith("-"):
                i += 1
            if tok == "timeout" and i < len(cmd):
                i += 1  # the duration
            continue
        break
    return cmd[i:], escaped


def _invocations(tokens):
    """(tool, argv) for each pgrep or pkill in command position; stops at an escape."""
    found = []
    for raw in _simple_commands(tokens):
        cmd, escaped = _strip_prefixes(raw)
        if escaped:
            return []
        if cmd and cmd[0].rsplit("/", 1)[-1] in MATCHERS:
            found.append((cmd[0].rsplit("/", 1)[-1], cmd[1:]))
    return found


def _pattern_of(argv):
    """The pattern operand of a full-match invocation, or None when undecidable."""
    full = False
    operands = []
    skip = False
    for token in argv:
        if skip:
            skip = False
            continue
        if token.startswith("--"):
            name = token.split("=", 1)[0]
            if name == "--full":
                full = True
            elif name in VALUE_LONG and "=" not in token:
                skip = True
            continue
        if token.startswith("-") and len(token) > 1:
            letters = token[1:]
            if "f" in letters:
                full = True
            if letters[-1] in VALUE_SHORT:
                skip = True
            continue
        operands.append(token)
    if not full or len(operands) != 1:
        return None
    return operands[0]


def _self_matches(pattern, command):
    if any(marker in pattern for marker in EXPANSION):
        return False
    try:
        return re.search(pattern, command) is not None
    except re.error:
        return False


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
    try:
        tokens = _tokenize(command)
    except ValueError:
        return 0

    for tool, argv in _invocations(tokens):
        pattern = _pattern_of(argv)
        if pattern is None or not _self_matches(pattern, command):
            continue
        reason = DENIAL.format(tool=tool, pattern=pattern,
                               bracketed=_bracketed(pattern), escape=ESCAPE)
        json.dump({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}, sys.stdout)
        sys.stderr.write(reason + "\n")
        return 2
    return 0


def main():
    try:
        return _run()
    except Exception:
        # A broken hook must never break a session: allow, and say so, because
        # a silent exit 0 reads exactly like a clean call.
        sys.stderr.write(
            "self_matching_pgrep_hook: DISABLED for this call, it raised before it could\n"
            "finish, so the command was not checked for a self-matching pattern:\n"
            + traceback.format_exc())
        return 0


if __name__ == "__main__":
    sys.exit(main())
