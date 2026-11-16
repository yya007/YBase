#!/usr/bin/env python3
"""PreToolUse hook: refuse a Bash command that would publish a leak.

Rule 19 in docs/rules.md: everything committed is published, commit messages
included. The `leaks` check in tools/checks.py reads files and history after
the fact; this hook sits at the command that writes the text down, so the
secret, personal path, email or private term never reaches history or a PR.

REFUSES a command in whose command position (seen through env assignments,
shell keywords such as `then` or `do`, wrappers such as `timeout 60`, `nohup`,
`sudo`, `env -C dir` or `xargs`, and leading options such as `git -C dir` or
`gh -R repo`) is:
  * `git commit`: the text of `-m`/`--message` and `-F`/`--file`, plus the
    added lines of what the commit would record (`git diff --cached`, and the
    working tree too under `-a`/`--all`).
  * `gh pr create|edit|comment|review`: `--title`, `--body`, `--body-file`.
  * `git tag`: `-m`/`--message` and `-F`/`--file`.
when any of that text matches a leak pattern: every pattern in LEAK_PATTERNS in
tools/checks.py, and every private term from the `deny.list` of every knowledge
base (read for this repository and for its main checkout; a line that is not a
valid regular expression is skipped, and the `leaks` check reports it).

The rules are the same whichever repository the command targets; the hook does
not work out the target (docs/adr/0005-leak-hook-strict-everywhere.md). A
managed repo's commit that names a term on the list, the repo's own name
included, needs the ESCAPE below.

Recognition is best-effort: a `git` or `gh` run through an alias, a script, a
function or a command substitution is not seen at all, so the `leaks` check that
YBase's pre-commit hook runs remains the gate for commits, and PR text has no
second gate. The denial names the pattern and the text it matched.

A command shlex cannot split into words (a stray quote, as in a trailing
`# don't`) is scanned whole when it names git or gh.

PASSES: any other tool or command; a message composed in an editor; an
unsplittable command naming neither git nor gh; a payload the hook cannot
read; any internal error (a guard that blocks every Bash call is worse than
one unchecked surface, so it allows and says so on stderr). Cheap when
irrelevant: git runs only when the command has a commit surface.

ESCAPE: `LEAK_AUTHORIZED=1` as an environment prefix on the command
(`LEAK_AUTHORIZED=1 git commit -m ...`), so the reason is on the line a later
reader sees.

Claude Code only. Codex runs only the allow gate as a hook (.codex/hooks.json)
and reads this guard as a rule in docs/codex.md; the pre-commit hook in
.githooks/ runs the same `leaks` check on the staged files. Runnable by hand:
`python3 .claude/hooks/leak_hook.py < payload.json`.
"""
import importlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import traceback

REPO = pathlib.Path(__file__).resolve().parents[2]
ESCAPE = "LEAK_AUTHORIZED"
SEPARATORS = {";", "|", "||", "&", "&&", "(", ")", "<", ">", ">>", "<<", ">&", "<&", "\n"}
COMMANDS = {"git", "gh"}
# tools/checks.py spells the patterns out, so its own diff is exempt there and here.
SELF_EXEMPT = ("tools/checks.py",)

DENIAL = """\
Refused: this command would publish text that matches a leak pattern, in {what}:

  {hit}

Everything committed is published (docs/rules.md, rule 19). Remove the text, or
add the term to a knowledge base's deny.list if it is private and you meant
another word. {escape}=1 as a prefix on the command skips this hook for one call,
when the user said the text may ship."""


def tokenize(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars="();<>|&\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    # shlex would end a word at `#` (`owner/repo#3` loses `#3` and the rest of the line);
    # the shell starts a comment only at a word's start. Keeping comments as words only
    # adds text to inspect.
    lexer.commenters = ""
    return list(lexer)


def is_assignment(tok):
    return "=" in tok and not tok.startswith("=") and tok.split("=", 1)[0].isidentifier()


def escape_prefixed(tokens, assignment):
    """True when `assignment` (NAME=value) leads a simple command, as an env prefix does."""
    at_start = True
    for tok in tokens:
        if tok in SEPARATORS:
            at_start = True
        elif at_start and is_assignment(tok):
            if tok == assignment:
                return True
        else:
            at_start = False
    return False


# Programs that only run another command; they must not hide a git or gh call.
WRAPPERS = {"nohup", "sudo", "doas", "nice", "time", "timeout", "setsid", "command", "exec",
            "builtin", "caffeinate", "stdbuf", "xargs"}
WRAPPER_VALUE_FLAGS = {
    "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-T", "-U"},
    "doas": {"-u", "-C"},
    "nice": {"-n"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "stdbuf": {"-i", "-o", "-e"},
    "xargs": {"-I", "-n", "-L", "-P", "-s", "-d", "-E", "-a"},
}
ENV_VALUE_FLAGS = {"-u", "--unset", "-C", "--chdir", "-S", "--split-string", "-P"}
# Shell words that can lead a simple command, as in `if true; then git commit ...`.
KEYWORDS = {"{", "!", "if", "then", "elif", "else", "while", "until", "do"}
# Leading options of git or gh that take a value, before the subcommand.
GLOBAL_VALUE_FLAGS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
                      "--config-env", "-R", "--repo"}


def unwrap(tokens):
    """One simple command with env assignments and wrapper programs stripped."""
    toks = list(tokens)
    while toks:
        head = toks[0]
        if is_assignment(head):
            toks.pop(0)
            continue
        if head in KEYWORDS:
            toks.pop(0)
            continue
        if head == "env":
            toks.pop(0)
            while toks and (is_assignment(toks[0]) or toks[0].startswith("-")):
                toks = toks[2:] if toks[0] in ENV_VALUE_FLAGS else toks[1:]
            continue
        if head not in WRAPPERS:
            break
        toks.pop(0)
        values = WRAPPER_VALUE_FLAGS.get(head, set())
        while toks and toks[0].startswith("-"):
            flag = toks.pop(0)
            if flag in values and toks:
                toks.pop(0)
        if head == "timeout" and toks:
            toks.pop(0)  # the duration
    return toks


def program_name(tok):
    return tok.rsplit("/", 1)[-1]


def invocations(tokens):
    """(simple command as written, argv after the program name) for each `git` or `gh`
    in command position, seen through env assignments, shell keywords and wrappers such
    as `timeout 60` or `nohup`."""
    found, current = [], []
    for tok in tokens + [";"]:
        if tok not in SEPARATORS:
            current.append(tok)
            continue
        inner = unwrap(current)
        if inner and program_name(inner[0]) in COMMANDS:
            found.append((current, inner[1:]))
        current = []
    return found


def split_global(argv):
    """The program's own leading options as (flag, value) pairs, and the rest of argv."""
    pairs, i = [], 0
    while i < len(argv) and argv[i].startswith("-"):
        flag, value = argv[i], None
        i += 1
        if "=" in flag:
            flag, value = flag.split("=", 1)
        elif flag in GLOBAL_VALUE_FLAGS and i < len(argv):
            value = argv[i]
            i += 1
        pairs.append((flag, value))
    return pairs, argv[i:]


def subcommand(argv):
    words = []
    for tok in split_global(argv)[1]:
        if tok.startswith("-"):
            break
        words.append(tok)
    return tuple(words)


def valued(argv, names):
    """Values passed under any of `names`: `--name=x`, `--name x`, or the last
    letter of a short-flag bundle (`-am <message>`)."""
    values, skip = [], False
    for i, tok in enumerate(argv):
        if skip:
            skip = False
            continue
        if not tok.startswith("-"):
            continue
        head = tok.split("=", 1)[0]
        if head in names:
            if "=" in tok:
                values.append(tok.split("=", 1)[1])
            elif i + 1 < len(argv):
                values.append(argv[i + 1])
                skip = True
            continue
        if len(head) > 1 and not head.startswith("--") and ("-" + head[-1]) in names and i + 1 < len(argv):
            values.append(argv[i + 1])
            skip = True
    return values


def file_texts(paths, cwd):
    texts = []
    for p in paths:
        candidate = p if os.path.isabs(p) else os.path.join(cwd or ".", p)
        try:
            with open(candidate, encoding="utf-8", errors="replace") as fh:
                texts.append(fh.read())
        except OSError:
            continue
    return texts


def staged_added_lines(cwd, working_tree=False):
    """Added lines of the diff a commit would record, as one text; exempt files dropped."""
    args = ["git", "diff", "--no-color", "--no-ext-diff", "HEAD" if working_tree else "--cached"]
    try:
        res = subprocess.run(args, cwd=cwd or None, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if res.returncode != 0 and not working_tree:
        return ""
    if res.returncode != 0:
        return staged_added_lines(cwd)  # no HEAD yet: fall back to the index
    out, exempt = [], False
    for line in res.stdout.splitlines():
        if line.startswith("+++ "):
            name = line[4:].strip()
            if name.startswith("b/"):
                name = name[2:]
            exempt = name in SELF_EXEMPT
            continue
        if exempt or not line.startswith("+") or line.startswith("+++"):
            continue
        out.append(line[1:])
    return "\n".join(out)


def surfaces(argv, cwd):
    """[(what, text)] this invocation would put in front of a reader."""
    sub = subcommand(argv)
    if sub[:1] == ("commit",):
        # A leading `git -C <dir>` commits in that directory, so the diff is read there too.
        for flag, value in split_global(argv)[0]:
            if flag == "-C" and value:
                cwd = value if os.path.isabs(value) else os.path.join(cwd or ".", value)
        out = [("a commit message", t) for t in valued(argv, ("-m", "--message"))]
        out += [("a commit message file", t) for t in file_texts(valued(argv, ("-F", "--file")), cwd)]
        # `-a`, `--all` or a short bundle holding `a` (`-am`) commits the working tree too.
        working = any(a == "--all" or (a.startswith("-") and not a.startswith("--") and "a" in a[1:])
                      for a in argv)
        diff = staged_added_lines(cwd, working_tree=working)
        if diff:
            out.append(("the lines this commit would add", diff))
        return out
    if sub[:1] == ("tag",):
        out = [("a tag message", t) for t in valued(argv, ("-m", "--message"))]
        out += [("a tag message file", t) for t in file_texts(valued(argv, ("-F", "--file")), cwd)]
        return out
    if sub[:2] in (("pr", "create"), ("pr", "edit")):
        out = [("a PR title", t) for t in valued(argv, ("-t", "--title"))]
        out += [("a PR body", t) for t in valued(argv, ("-b", "--body"))]
        out += [("a PR body file", t) for t in file_texts(valued(argv, ("-F", "--body-file")), cwd)]
        return out
    if sub[:2] in (("pr", "comment"), ("pr", "review")):
        out = [("a PR comment", t) for t in valued(argv, ("-b", "--body"))]
        out += [("a PR comment file", t) for t in file_texts(valued(argv, ("-F", "--body-file")), cwd)]
        return out
    return []


def tools_module(name):
    """A module from YBase's tools/, imported only when needed so a missing file
    raises inside main(), which allows the call."""
    tools = REPO / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    return importlib.import_module(name)


def checks_module():
    return tools_module("checks")


def deny_lists(checks):
    """Every knowledge base's private terms, for this repository and its main checkout;
    checks.deny_patterns skips a line that is not a valid regular expression."""
    return checks.deny_patterns(checks.Ctx(REPO))


def unsplit(command, environ):
    """Decide a command shlex cannot split (a stray quote, as in `# don't`). Its words
    and message cannot be told apart, so if it names git or gh at all, the whole text
    is the surface."""
    if environ.get(ESCAPE) == "1" or re.match(rf"\s*(\w+=\S*\s+)*{ESCAPE}=1\s", command):
        return None
    if not re.search(r"(?<![\w.-])(git|gh)(?![\w.-])", command):
        return None
    checks = checks_module()
    hits = checks.leak_hits(command, deny_lists(checks))
    if hits:
        return DENIAL.format(what="a command the hook could not split into words",
                             hit="\n  ".join(hits[:5]), escape=ESCAPE)
    return None


def decide(payload, environ=None):
    """Return a denial reason, or None to allow."""
    environ = os.environ if environ is None else environ
    if payload.get("tool_name") != "Bash":
        return None
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not command:
        return None
    try:
        tokens = tokenize(command)
    except ValueError:
        return unsplit(command, environ)
    if escape_prefixed(tokens, ESCAPE + "=1") or environ.get(ESCAPE) == "1":
        return None
    cwd = payload.get("cwd") or os.getcwd()
    found = [pair for _, argv in invocations(tokens) for pair in surfaces(argv, cwd)]
    if not found:
        return None
    checks = checks_module()
    deny = deny_lists(checks)
    for what, text in found:
        hits = checks.leak_hits(text, deny)
        if hits:
            return DENIAL.format(what=what, hit="\n  ".join(hits[:5]), escape=ESCAPE)
    return None


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
        # A guard that cannot decide allows, out loud, so a disabled hook does
        # not read like a clean call.
        sys.stderr.write("leak_hook: allowed without checking, it raised:\n" + traceback.format_exc())
        return 0


if __name__ == "__main__":
    sys.exit(main())
