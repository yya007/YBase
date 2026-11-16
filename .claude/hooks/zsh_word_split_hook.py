#!/usr/bin/env python3
"""PreToolUse hook: refuse a bare `$VAR` where zsh will not word-split it.

WHY. When the Bash tool's shell is zsh, an unquoted parameter expansion is NOT
split on whitespace, unlike bash. So `for item in $ITEMS` iterates once over
the whole string and `set -- $spec` sets one positional argument, and both look
successful while passing one value where several were meant.

WHAT IT REFUSES. At the top level of the command, a bare `$NAME` or `${NAME}`
in the list of a `for NAME in ...` or directly after `set --`.

WHAT PASSES. Everything when the shell is not zsh. `${=VAR}` and `${(f)VAR}`,
which ask zsh to split. A real array (`for x in "${arr[@]}"`). `"$VAR"`, which
asks for one item on purpose. `$(...)`, which splits in zsh too. Any `$VAR`
inside quotes, a command substitution, backticks or a heredoc body: those are
masked before tokenizing, so shell text handed to `bash -c '...'` is not read
as zsh text. A command zsh itself rejects (`zsh -n`) when zsh is on PATH.

WHEN IT FIRES. Only when the tool's shell is zsh, decided from
`$CLAUDE_CODE_SHELL` when set, else from the basename of `$SHELL`. Otherwise it
allows without looking.

BLOCKING: the failure is silent by construction, so a note after the fact is
too late. The refusal names the fixes.

ESCAPE: prefix the command with `WORD_SPLIT_OK=1` when the single-item
behaviour is what you mean.

A hook that cannot decide allows: malformed stdin, an unbalanced quote or
heredoc, a command the tokenizer cannot read and any internal error exit 0,
the last out loud on stderr. Claude Code is the only harness that runs this
hook; `docs/codex.md` carries the rule for Codex.

Run by hand: python3 .claude/hooks/zsh_word_split_hook.py < payload.json
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import traceback

ESCAPE = "WORD_SPLIT_OK"
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
BARE_PARAMETER = re.compile(r"^(?:\$[A-Za-z_][A-Za-z0-9_]*|\$\{[A-Za-z_][A-Za-z0-9_]*\})$")
COMMAND_START_WORDS = {"do", "then", "else", "elif", "if", "while", "until"}
COMMAND_START_TOKENS = {"&", "&&", "|", "||", "(", ")", "{", "}"}

DENIAL = """\
Refused: `{expansion}` relies on bash word splitting, but this Bash tool runs
under zsh. zsh does not split an unquoted `$VAR` or `${{VAR}}` unless a split
flag is explicit, so this {context} receives one item instead of the list
stored in the variable.

Use one of these forms instead:

  ask zsh to split on IFS          for item in ${{=ITEMS}}; do ...; done
  split a newline-separated list   for item in ${{(f)ITEMS}}; do ...; done
  use a real array                 items=(a b c); for item in "${{items[@]}}"; do ...; done
  produce the words directly       for item in $(printf '%s\\n' ...); do ...; done
  run bash syntax explicitly       bash -c 'for item in $ITEMS; do ...; done'

Quoted `"$VAR"` is still right when one item is deliberate.

If one item is what you mean here:  {escape}=1 <the same command>"""


def shell_is_zsh(environ=None):
    """Whether the Bash tool's shell is zsh, from CLAUDE_CODE_SHELL, else SHELL."""
    env = os.environ if environ is None else environ
    for var in ("CLAUDE_CODE_SHELL", "SHELL"):
        value = env.get(var)
        if value:
            return os.path.basename(value.strip()) == "zsh"
    return False


def _syntax_is_valid(command):
    """Whether zsh accepts the text. No zsh on PATH means no opinion (True)."""
    zsh = shutil.which("zsh")
    if zsh is None:
        return True
    try:
        res = subprocess.run([zsh, "-n", "-c", command], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return res.returncode == 0


# ------------------------------------------------------------------ masking
def _quoted_end(text, start, quote):
    """Index after a shell quote, or None when the quote is unbalanced."""
    i = start + 1
    while i < len(text):
        if quote == "'":
            if text[i] == "'":
                return i + 1
            i += 1
            continue
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    return None


def _backtick_end(text, start):
    i = start + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == "`":
            return i + 1
        i += 1
    return None


def _paren_end(text, start):
    """Index after a balanced `$(`, `<(` or `>(` region, or None."""
    depth, i = 1, start + 2
    while i < len(text):
        ch = text[i]
        if ch in "'\"":
            end = _quoted_end(text, i, ch)
            if end is None:
                return None
            i = end
            continue
        if ch == "`":
            end = _backtick_end(text, i)
            if end is None:
                return None
            i = end
            continue
        if text.startswith("<<", i) and not text.startswith("<<<", i):
            return None  # a heredoc inside a substitution needs a real parser
        if ch == "\\":
            i += 2
            continue
        if i + 1 < len(text) and ch in "$<>" and text[i + 1] == "(":
            depth += 1
            i += 2
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def _heredoc_word(text, start):
    """(index after the delimiter word, quote-removed delimiter), or None."""
    i = start
    while i < len(text) and text[i] in " \t":
        i += 1
    if i >= len(text) or text[i] in "\r\n;|&()<>":
        return None
    delimiter = []
    while i < len(text) and text[i] not in " \t\r\n;|&()<>":
        ch = text[i]
        if ch in "'\"":
            end = _quoted_end(text, i, ch)
            if end is None:
                return None
            j = i + 1
            while j < end - 1:
                if ch == '"' and text[j] == "\\" and j + 1 < end - 1:
                    j += 1
                delimiter.append(text[j])
                j += 1
            i = end
            continue
        if ch == "\\":
            if i + 1 >= len(text) or text[i + 1] == "\n":
                return None
            delimiter.append(text[i + 1])
            i += 2
            continue
        delimiter.append(ch)
        i += 1
    if not delimiter:
        return None
    return i, "".join(delimiter)


def _comment_starts(text, index):
    if text[index] != "#":
        return False
    return index == 0 or text[index - 1].isspace() or text[index - 1] in ";|&()<>"


def mask_ignored(command):
    """Replace quoted strings, substitutions, comments and heredoc bodies with
    placeholders so only top-level shell words remain. None means undecidable."""
    out, pending, i = [], [], 0
    while i < len(command):
        ch = command[i]
        if ch == "\n":
            out.append("\n")
            i += 1
            while pending:
                delimiter, strip_tabs = pending.pop(0)
                found = False
                while i <= len(command):
                    end = command.find("\n", i)
                    has_newline = end != -1
                    if not has_newline:
                        end = len(command)
                    line = command[i:end]
                    candidate = line.lstrip("\t") if strip_tabs else line
                    if candidate == delimiter:
                        if has_newline:
                            out.append("\n")
                        i = end + (1 if has_newline else 0)
                        found = True
                        break
                    if has_newline:
                        out.append("\n")
                        i = end + 1
                    else:
                        i = end
                        break
                if not found:
                    return None
            continue
        if _comment_starts(command, i):
            end = command.find("\n", i)
            out.append("#")
            if end == -1:
                break
            i = end
            continue
        if ch in "'\"":
            end = _quoted_end(command, i, ch)
            if end is None:
                return None
            out.append(ch + "Q" + ch)
            i = end
            continue
        if ch == "`":
            end = _backtick_end(command, i)
            if end is None:
                return None
            out.append("CMDSUB")
            i = end
            continue
        if i + 1 < len(command) and ch in "$<>" and command[i + 1] == "(":
            end = _paren_end(command, i)
            if end is None:
                return None
            out.append("CMDSUB")
            i = end
            continue
        if command.startswith("<<", i) and not command.startswith("<<<", i):
            strip_tabs = command.startswith("<<-", i)
            op_end = i + (3 if strip_tabs else 2)
            parsed = _heredoc_word(command, op_end)
            if parsed is None:
                return None
            pending.append((parsed[1], strip_tabs))
            out.append(command[i:op_end])
            i = op_end
            continue
        if ch == "\\":
            if i + 1 >= len(command):
                return None
            if command[i + 1] != "\n":
                out.append("ESC")
            i += 2
            continue
        out.append(ch)
        i += 1
    if pending:
        return None
    return "".join(out)


def _tokenize(command):
    masked = mask_ignored(command)
    if masked is None:
        return None
    try:
        lexer = shlex.shlex(masked, posix=True, punctuation_chars=";&|()<>\n")
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return None


# ------------------------------------------------------------------ verdict
def _after_boundary(tokens, index):
    if index == 0:
        return True
    prev = tokens[index - 1]
    return (prev in COMMAND_START_WORDS or prev in COMMAND_START_TOKENS
            or ";" in prev or "\n" in prev)


def _list_ends(token):
    return token == "do" or ";" in token or "\n" in token


def find_unsafe(tokens):
    """(expansion, context) for the first bare parameter zsh would not split."""
    for i, token in enumerate(tokens):
        if token == "for" and _after_boundary(tokens, i):
            if i + 2 >= len(tokens) or not IDENT.fullmatch(tokens[i + 1]) or tokens[i + 2] != "in":
                continue
            for item in tokens[i + 3:]:
                if _list_ends(item):
                    break
                if BARE_PARAMETER.fullmatch(item):
                    return item, "for-list"
        if token == "set" and _after_boundary(tokens, i):
            if i + 2 < len(tokens) and tokens[i + 1] == "--" and BARE_PARAMETER.fullmatch(tokens[i + 2]):
                return tokens[i + 2], "`set --` argument list"
    return None


def _escaped(tokens):
    return any(t.startswith(ESCAPE + "=") and len(t) > len(ESCAPE) + 1 for t in tokens)


def _run():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    if os.environ.get(ESCAPE) or not shell_is_zsh():
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        return 0
    tokens = _tokenize(command)
    if tokens is None or _escaped(tokens):
        return 0
    unsafe = find_unsafe(tokens)
    if unsafe is None or not _syntax_is_valid(command):
        return 0
    expansion, context = unsafe
    reason = DENIAL.format(expansion=expansion, context=context, escape=ESCAPE)
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
        # A broken hook must never break a session: allow, and say so, because
        # a silent exit 0 reads exactly like a clean call.
        sys.stderr.write(
            "zsh_word_split_hook: DISABLED for this call, it raised before it could\n"
            "finish, so no word-splitting check was made for the command:\n"
            + traceback.format_exc())
        return 0


if __name__ == "__main__":
    sys.exit(main())
