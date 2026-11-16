#!/usr/bin/env python3
"""PreToolUse hook (advisory): say so when a git or gh write's exit status is discarded.

WHY. A pipeline reports its LAST command's status, so `git push ... | tail -1`
reports tail's success whatever git did. A command list separated by `;` or a
newline does the same, so `git push ... > log; tail -1 log` reports tail's.
Either way a failed write reads as clean, and the work looks landed when it is
not. `git add f 2>&1 | head -3; echo $?` prints 0 for an `add` that failed.

WHAT IT FLAGS, read off the token stream:
  upstream of a pipe   a pipeline segment other than the last runs a write:
                       `git add|commit|push|rebase|merge|cherry-pick|reset|...`,
                       `git worktree remove|add|prune`, `git branch -d|-D|-m`,
                       `git stash` (not `list`/`show`), or `gh pr create|merge|
                       edit|close|ready`. `|` splits a pipeline; `;`, `&&`, `||`,
                       `&` and a newline end one.
  reporter last        a list separated by `;`, `&` or a newline ends on a pure
                       reporter (`echo`, `printf`, `cat`, `tail`, `head`, `wc`,
                       `ls`, `true`, ...) while an earlier element writes. `&&`
                       and `||` are not separators here: a failure on the left
                       of `&&` short-circuits, and `||` is a deliberate fallback.

WHAT PASSES. A write in the last pipeline segment (its status is the line's),
`git push ...; rc=$?; echo done` (the next statement holds the status), a
trailing `grep` (its non-zero on no-match is itself a verdict), and the
read-only spellings: `git log | head`, `git branch | grep`, `gh pr view | cat`.

ADVISORY, never blocking: a pipe carrying a git write is sometimes exactly
what is meant. The hook exits 0 and attaches `additionalContext` that says
what the line's status will read as.

ESCAPE: none is needed, since nothing is blocked. To silence the note, hold
the status (`...; rc=$?; ...`) or do not pipe the write.

A hook that cannot decide stays silent: malformed stdin, an unparseable
command and any internal error exit 0, the last out loud on stderr. It does
not see a write inside `$(...)` or inside a script the command runs. Claude
Code is the only harness that runs this hook; `docs/codex.md` carries the rule
for Codex.

Run by hand: python3 .claude/hooks/git_write_in_pipeline_hook.py < payload.json
"""
import json
import re
import shlex
import sys
import traceback

# Git subcommands with no read-only spelling. `branch`, `tag`, `remote` and
# `config` are judged by their flags or left alone: `git tag | grep` is a read.
ALWAYS_WRITES = {"add", "am", "apply", "cherry-pick", "checkout", "clean", "commit",
                 "fetch", "init", "merge", "mv", "pull", "push", "rebase", "reset",
                 "restore", "revert", "rm", "switch"}
# Subcommands that write unless their first operand names a listing.
CONDITIONAL_WRITES = {"stash": {"list", "show"}, "worktree": {"list"}}
# Subcommands that write only with one of these flags.
FLAG_WRITES = {"branch": {"-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy"},
               "tag": {"-d", "--delete"},
               "remote": set()}  # `git remote add|remove|...` handled as operands below
REMOTE_WRITES = {"add", "remove", "rm", "rename", "set-url", "prune"}
# Global git options that take a value, so the next token is not the subcommand.
VALUE_GLOBALS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
GH_WRITES = {"pr": {"create", "merge", "edit", "close", "reopen", "ready", "comment", "review"},
             "issue": {"create", "edit", "close", "reopen", "comment", "delete"},
             "release": {"create", "edit", "delete", "upload"}}
GH_VALUE_FLAGS = {"-R", "--repo", "-q", "--jq", "--template", "-t", "--title", "-b", "--body"}
# Commands that report and do not act. `grep` is absent on purpose: it exits
# non-zero on no-match, so a trailing `grep FAIL log` is a verdict.
REPORTERS = {"echo", "printf", "cat", "tail", "head", "ls", "date", "pwd", "wc",
             "true", "basename", "dirname", "stat"}
PIPE = "|"
ENDS_PIPELINE = {";", "||", "&&", "&", "\n", "(", ")", ";;"}
ENDS_STATEMENT = {";", "&", "\n"}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")

ADVICE_PIPE = """\
Heads up: `{call}` is upstream of a pipe, so its exit status is discarded.

A pipeline reports its LAST command's status. If this call fails, the line
still reads as success and the work will look done when it is not
(`git add f 2>&1 | head -3; echo $?` prints 0 for an add that failed).

Nothing was blocked. If you meant to pipe it, read the status explicitly:

  rc from the pipeline    {call} ... | tail -1; rc=${{PIPESTATUS[0]}}; [ "$rc" = 0 ] || exit "$rc"
                          (zsh: ${{pipestatus[1]}})
  or do not pipe at all   {call} ...            # let the status reach the shell

Never chain landing work off a pipeline: `git push ... | tail -1 && echo pushed`
prints "pushed" for a push that failed."""

ADVICE_LIST = """\
Heads up: `{call}` runs earlier in this command list and `{reporter}` runs last,
so the exit status of the whole call is {reporter}'s.

A list separated by `;`, `&` or a newline reports its LAST element's status,
exactly as a pipeline does, and a reporter almost always succeeds. So `{call}`
can fail here and the call still reads as clean.

Nothing was blocked. Either hold the status before reporting:

  {call} ...; rc=$?; {reporter} ...; [ "$rc" = 0 ] || exit "$rc"

or take the verdict from the artifact itself (the pushed ref, the new commit,
the log line), since a trailing reporter leaves this call's status unread."""


def _tokenize(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def tokenize_lines(command):
    """Tokens with a "\\n" token at each line boundary (shlex drops newlines)."""
    lines = command.split("\n")
    if len(lines) == 1:
        return _tokenize(command)
    per_line = []
    for line in lines:
        try:
            per_line.append(_tokenize(line))
        except ValueError:
            return _tokenize(command)  # a quoted string spans lines
    out = []
    for i, tokens in enumerate(per_line):
        if i:
            out.append("\n")
        out.extend(tokens)
    return out


def _segments(tokens):
    """Yield (argv, is_last_of_its_pipeline) for every pipeline segment."""
    pipelines, current = [], [[]]
    for token in tokens:
        if token == PIPE or token == "|&":
            current.append([])
        elif token in ENDS_PIPELINE:
            pipelines.append(current)
            current = [[]]
        else:
            current[-1].append(token)
    pipelines.append(current)
    for pipeline in pipelines:
        for i, argv in enumerate(pipeline):
            yield argv, i == len(pipeline) - 1


def _statements(tokens):
    statements = [[]]
    for token in tokens:
        if token in ENDS_STATEMENT:
            statements.append([])
        else:
            statements[-1].append(token)
    return [s for s in statements if s]


def _last_argv(statement):
    argv = []
    for token in statement:
        if token in (PIPE, "|&", "||", "&&", "(", ")"):
            argv = []
        else:
            argv.append(token)
    return argv


def _name(token):
    return token.rsplit("/", 1)[-1]


def _strip_env_prefix(argv):
    """argv without leading `NAME=VALUE` assignments and an `env` wrapper."""
    out = list(argv)
    while out and ASSIGNMENT.match(out[0]):
        out.pop(0)
    if out and _name(out[0]) == "env":
        out.pop(0)
        while out and (ASSIGNMENT.match(out[0]) or out[0].startswith("-")):
            out.pop(0)
    return out


def git_write(argv):
    """The writing git subcommand this argv runs, or None."""
    argv = _strip_env_prefix(argv)
    if not argv or _name(argv[0]) != "git":
        return None
    rest, skip = argv[1:], False
    for i, token in enumerate(rest):
        if skip:
            skip = False
            continue
        if token in VALUE_GLOBALS:
            skip = True
            continue
        if token.startswith("-"):
            continue
        after = rest[i + 1:]
        if token in ALWAYS_WRITES:
            return token
        if token in CONDITIONAL_WRITES:
            operands = [t for t in after if not t.startswith("-")]
            if operands and operands[0] in CONDITIONAL_WRITES[token]:
                return None
            return token if not operands else token + " " + operands[0]
        if token in FLAG_WRITES:
            flags = {t.split("=", 1)[0] for t in after if t.startswith("-")}
            if flags & FLAG_WRITES[token]:
                return token + " " + sorted(flags & FLAG_WRITES[token])[0]
            if token == "remote":
                operands = [t for t in after if not t.startswith("-")]
                if operands and operands[0] in REMOTE_WRITES:
                    return "remote " + operands[0]
            return None
        return None
    return None


def gh_write(argv):
    """The writing gh subcommand this argv runs, as `gh pr create`, or None."""
    argv = _strip_env_prefix(argv)
    if not argv or _name(argv[0]) != "gh":
        return None
    operands, skip = [], False
    for token in argv[1:]:
        if skip:
            skip = False
            continue
        if token in GH_VALUE_FLAGS:
            skip = True
            continue
        if token.startswith("-"):
            continue
        operands.append(token)
    if len(operands) >= 2 and operands[1] in GH_WRITES.get(operands[0], set()):
        return "gh %s %s" % (operands[0], operands[1])
    return None


def write_call(argv):
    sub = git_write(argv)
    if sub is not None:
        return "git " + sub
    return gh_write(argv)


def _advise(text):
    json.dump({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": text,
    }}, sys.stdout)


def _run():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        return 0
    try:
        tokens = tokenize_lines(command)
    except ValueError:
        return 0

    for argv, is_last in _segments(tokens):
        if is_last:
            continue
        call = write_call(argv)
        if call is not None:
            _advise(ADVICE_PIPE.format(call=call))
            return 0

    statements = _statements(tokens)
    if len(statements) < 2:
        return 0
    final = _last_argv(statements[-1])
    if not final or _name(final[0]) not in REPORTERS:
        return 0
    for i, statement in enumerate(statements[:-1]):
        call = None
        for argv, _ in _segments(statement):
            call = write_call(argv)
            if call is not None:
                break
        if call is None:
            continue
        # `git push > log; rc=$?; tail -1 log` holds the status: that is the
        # remedy, so warning there would flag the fix. Only the statement right
        # after the write can hold it.
        if any("$?" in token for token in statements[i + 1]):
            return 0
        _advise(ADVICE_LIST.format(call=call, reporter=_name(final[0])))
        return 0
    return 0


def main():
    try:
        return _run()
    except Exception:
        # A broken hook must never break a session: stay quiet on the decision
        # but say so, because a silent exit 0 reads exactly like a clean call.
        sys.stderr.write(
            "git_write_in_pipeline_hook: DISABLED for this call, it raised before it\n"
            "could finish, so no advice was given about the command:\n"
            + traceback.format_exc())
        return 0


if __name__ == "__main__":
    sys.exit(main())
