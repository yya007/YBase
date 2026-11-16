#!/usr/bin/env python3
"""PreToolUse hook: refuse a Bash command that puts a pull request in front of reviewers.

WHY. YBase's landing convention (`docs/rules.md`, `docs/flows.md`): work lands
through a draft PR, and only the user marks it ready or merges. A `gh` call is
never committed, so no repository check can read it; this hook reads it off
the command before it runs.

OPT-IN. The guard ships OFF. It runs only when `YBASE_GUARD_PR_DRAFT=1` is in the
process environment or in YBase's `.env` (found from this hook's own file
location, so it works in a session started inside a managed repo); otherwise it
allows without looking at the command.

WHAT IT REFUSES, each a way to open a PR for review:
  * `gh pr create` without `--draft` (or its short `-d`), or with `--draft=false`.
  * `gh pr ready` without `--undo` (`--undo` is the repair, not the violation).
  * `gh api graphql` carrying a `markPullRequestReadyForReview` mutation.
  * `gh api` on a pull request that sets `draft` to false.

WHAT PASSES. `gh pr create --draft ...`, `gh pr ready --undo`, every read
(`gh pr view`, `gh pr list`, `gh api` GETs), and a `gh` call whose subcommand
the shell builds at run time.

BLOCKING: by the time an advisory note lands, the review request is out.

ESCAPE: when the user asked for it in so many words, prefix the command with
`PR_READY_AUTHORIZED=1` (`PR_READY_AUTHORIZED=1 gh pr ready 12`). The
assignment stays on the line a reader sees later.

A hook that cannot decide allows: malformed stdin, an unparseable command and
any internal error exit 0, the last out loud on stderr. It does not see a `gh`
call inside a script the command runs, or a PR opened from the web UI. Claude
Code is the only harness that runs this hook; `docs/codex.md` carries the rule
for Codex.

Run by hand: python3 .claude/hooks/pr_draft_hook.py < payload.json
"""
import json
import os
import re
import shlex
import sys
import traceback
from pathlib import Path

GUARD = "PR_DRAFT"
ESCAPE = "PR_READY_AUTHORIZED"
OPERATORS = {";", "|", "||", "&", "&&", "(", ")", "<", ">", ">>", "<<", "\n", "|&", ";;"}
PREFIXES = {"sudo", "nohup", "nice", "time", "command", "exec", "builtin", "env",
            "timeout", "then", "do", "else", "elif", "if", "while", "until", "!",
            "{", "}"}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")

DENIAL = """\
Refused: this command would put a pull request in front of reviewers: {what}

YBase lands work through a draft PR (`docs/rules.md`, `docs/flows.md`): the
session opens it as a draft, and only the user marks it ready or merges.

{fix}

If the user asked for this in so many words, say so on the command itself:
  {escape}=1 <the same command>"""

CREATE_FIX = """Add `--draft`; the rest of the invocation is fine:
  gh pr create --draft --base <base> ...
The user flips it with `gh pr ready` when they are ready, and not before."""

READY_FIX = """Do not run it. Marking a PR ready is the user's call, not this
session's. Report that the PR is ready for their review and stop there; they
run `gh pr ready` themselves, or tell you to."""


def _guard_on():
    """True only when the user switched the guard on; any failure to find out means off."""
    try:
        home = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(home / "tools"))
        import envfile
        return envfile.guard_enabled(GUARD, envfile.main_checkout(home))
    except Exception:
        return False


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
                i += 1
            continue
        break
    return cmd[i:], escaped


def gh_invocations(tokens):
    """argv of each `gh` in command position; [] as soon as the escape is seen."""
    found = []
    for raw in _simple_commands(tokens):
        cmd, escaped = _strip_prefixes(raw)
        if escaped:
            return []
        if cmd and cmd[0].rsplit("/", 1)[-1] == "gh":
            found.append(cmd[1:])
    return found


# `gh pr create` options that take a value, so the token after them is not a flag.
CREATE_VALUE_FLAGS = {"-t", "--title", "-b", "--body", "-B", "--base", "-H", "--head", "-a", "--assignee",
                      "-r", "--reviewer", "-l", "--label", "-m", "--milestone", "-p", "--project",
                      "-F", "--body-file", "-R", "--repo", "-T", "--template"}


def _subcommand(argv):
    """The subcommand words, reading past a global `-R`/`--repo` placed before them."""
    words, skip = [], False
    for token in argv:
        if skip:
            skip = False
            continue
        if token in ("-R", "--repo"):
            skip = True
            continue
        if token.startswith("--repo="):
            continue
        if token.startswith("-"):
            break
        words.append(token)
    return tuple(words)


def _draft_requested(argv):
    """`--draft`, `--draft=true`, or the short `-d` alone or in a bundle such as `-dt`."""
    skip = False
    for token in argv:
        if skip:
            skip = False
            continue
        if token == "--draft":
            return True
        if token.startswith("--draft="):
            return token.split("=", 1)[1] not in ("false", "0")
        if token.startswith("-") and not token.startswith("--") and len(token) > 1:
            letters = token[1:]
            if "d" in letters:
                return True
            if "-" + letters[-1] in CREATE_VALUE_FLAGS:
                skip = True
        elif token in CREATE_VALUE_FLAGS:
            skip = True
    return False


def _flags(argv):
    return {token.split("=", 1)[0] for token in argv if token.startswith("-")}


def _valued(argv, name):
    """The value of `--name=x` or `--name x`, or None."""
    for i, token in enumerate(argv):
        if token == name and i + 1 < len(argv):
            return argv[i + 1]
        if token.startswith(name + "="):
            return token.split("=", 1)[1]
    return None


def _sets_draft_false(argv):
    """A REST or GraphQL call that clears draft on a pull request."""
    joined = " ".join(argv)
    if "markPullRequestReadyForReview" in joined:
        return True
    if "/pulls/" not in joined and "pullRequest" not in joined:
        return False
    for token in argv:
        stripped = token.replace(" ", "")
        if stripped in ("draft=false", "draft=False", '"draft":false') or stripped.endswith(":draft=false"):
            return True
    return False


def verdict(argv):
    """(what, fix) when this gh invocation opens a PR for review, else None."""
    sub = _subcommand(argv)
    if sub[:2] == ("pr", "create"):
        if _draft_requested(argv):
            return None
        return ("`gh pr create` with no `--draft`.", CREATE_FIX)
    if sub[:2] == ("pr", "ready"):
        if "--undo" in _flags(argv):
            return None
        return ("`gh pr ready`, which marks it ready for review.", READY_FIX)
    if sub[:1] == ("api",) and _sets_draft_false(argv):
        return ("an API call that clears the draft flag.", READY_FIX)
    return None


def _run():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    if os.environ.get(ESCAPE) or not _guard_on():
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
    for argv in gh_invocations(tokens):
        found = verdict(argv)
        if found is None:
            continue
        what, fix = found
        reason = DENIAL.format(what=what, fix=fix, escape=ESCAPE)
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
            "pr_draft_hook: DISABLED for this call, it raised before it could\n"
            "finish, so the command went unchecked:\n" + traceback.format_exc())
        return 0


if __name__ == "__main__":
    sys.exit(main())
