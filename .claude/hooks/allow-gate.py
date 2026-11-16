#!/usr/bin/env python3
"""PreToolUse hook: approve a compound Bash command whose every part is already allowed.

OPT-IN. The gate ships OFF. It runs only when `YBASE_ALLOW_GATE=1` is in the
process environment or in the `.env` of YBase's main checkout, found from
this file's own location; anything else, including a missing or unreadable
`.env` or a missing `tools/envfile.py`, leaves it off, and off prints nothing.
docs/adr/0003-allow-gate-is-opt-in.md records why.

The built-in permission system matches the whole command string against each
Bash(...) allow pattern, so a compound command (&&, ||, ;, |, &, newline) never
matches a single rule and always prompts, even when every part is allowed on
its own. When on, this hook splits the command and checks each part against
the allow patterns of every active settings file: `~/.claude/settings.json`,
then `.claude/settings.json` and `.claude/settings.local.json` read from the
working directory, which the wiring sets to the project root. The tracked
`.claude/settings.json` lists `pwd`, `ls`, `wc`, `which`, the exact forms of
`git status`, `git diff`, `git log` and `git show`, `git rev-parse`, `git
ls-files`, `git branch --show-current`, `git remote -v`, and the project's own
`tools/checks.py`, `ybase check`, `doctor --dry-run` and the bare
`repos`, `kb`, `profile` and `env` listings. A user's broader approvals belong
in `.claude/settings.local.json`, which is never committed.

NOT A SECURITY BOUNDARY. The command parsing is best-effort and has known
gaps: a command substitution hidden by quoting, a function definition, zsh
process substitution (`=(...)`) and glob qualifiers, and input redirection
from a network pseudo-device such as `/dev/tcp/...`. Through any of these an
approved command can run a program that no rule lists or reach the network.
Turn the gate on only for allow lists that hold commands you are content to
run unprompted.

REFUSES: nothing. It only approves, by printing {"decision": "approve"}.

APPROVES (when on): a compound command when every part, as this parser splits
it, matches an allow pattern. Parts are split on &&, ||, ;, | and a background
&, outside quotes. A `*` in a rule matches within one line. A bare shell
keyword (do, done, then, else, fi, ...) is allowed; after do, then, else or
elif the rest of the part must match a rule itself, and after done, fi or esac
only a redirect to /dev/null or between descriptors may follow. A part holding
$(...) is approved when the text the parser extracts from each $(...) and the
outer command with each substitution replaced both match; nesting deeper than
four levels is declined.

DECLINES (says nothing, so the normal permission prompt decides): everything
while off; a single command, which the built-in system already matches; a
command holding `$'` or `$"`, a backslash outside single quotes, an unquoted
`#`, a newline or carriage return, or a quote left open, checked before any
splitting; any part no pattern covers; a part with a backtick, <(...), >(...)
or an unbalanced `$(`, as the parser sees them; a part that redirects output
to a file (`>`, `>>`, `>|`, `&>`, `>&file` or `<>` outside quotes), while
`2>&1`, `>&2` and a redirect to /dev/null are fine; a `git difftool` command,
whose `-x` runs any program; no allow patterns at all; a payload the hook
cannot read.

ESCAPE: none is needed, since it refuses nothing. To stop its approvals, leave
`YBASE_ALLOW_GATE` unset, or remove the allow entry that covers the part.

Wired in .claude/settings.json under PreToolUse matcher "Bash". The wrapper finds
this file from $CLAUDE_PROJECT_DIR, then from the git toplevel, and runs it from
the project root, since the settings files are read relative to the working
directory; when it finds no file or cannot move there, it exits 0, so a `cd`
into another repository, or Codex, which sets no CLAUDE_PROJECT_DIR, cannot
block a call (docs/adr/0001-allow-gate-cwd-robustness.md). Codex runs it too,
through .codex/hooks.json, under the same switch (docs/codex.md).
Runnable by hand: `python3 .claude/hooks/allow-gate.py < payload.json`.
"""

import importlib.util
import sys
import json
import re
from pathlib import Path
from typing import Optional

# Bare shell control-flow keywords that carry no executable payload.
_SHELL_KEYWORDS: frozenset[str] = frozenset({"do", "done", "then", "else", "elif", "fi", "esac"})
_OPENING_KEYWORDS: frozenset[str] = frozenset({"do", "then", "else", "elif"})
# What may follow a closing keyword: redirects to /dev/null or between descriptors.
_DESCRIPTOR_REDIRECTS = re.compile(r"(?:\s*(?:\d*>>?\s*/dev/null|&>>?\s*/dev/null|\d*>&(?:\d+|-)))+\s*")
# YBase's .env key that turns the gate on; anything but exactly 1 leaves it off.
SWITCH = "YBASE_ALLOW_GATE"


def gate_enabled() -> bool:
    """True only when YBASE_ALLOW_GATE is exactly 1, in the process environment or
    in the .env of YBase's main checkout (found from this file, so a linked worktree
    and a session started elsewhere both work). Any failure reads as off."""
    try:
        root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location("ybase_envfile", root / "tools" / "envfile.py")
        envfile = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(envfile)
        return envfile.switch_enabled(SWITCH, envfile.main_checkout(root))
    except Exception:
        return False


def load_allow_patterns() -> list[str]:
    """Collect all Bash(...) allow patterns from active settings files."""
    patterns: list[str] = []
    settings_files = [
        Path.home() / ".claude/settings.json",
        Path(".claude/settings.json"),
        Path(".claude/settings.local.json"),
    ]
    for f in settings_files:
        if f.exists():
            try:
                d = json.loads(f.read_text())
                for entry in d.get("permissions", {}).get("allow", []):
                    m = re.match(r"^Bash\((.+)\)$", entry)
                    if m:
                        patterns.append(m.group(1))
            except Exception:
                pass
    return patterns


def glob_to_regex(pattern: str) -> str:
    """Convert a shell-style glob pattern (as used in Bash allow rules) to regex.

    `*` and `?` never match a newline or carriage return, so one rule cannot cover
    a second line (has_unmodelled_syntax already declines any command holding one).
    """
    result = "^"
    for ch in pattern:
        if ch == "*":
            result += "[^\\n\\r]*"
        elif ch == "?":
            result += "[^\\n\\r]"
        else:
            result += re.escape(ch)
    result += "$"
    return result


def has_unmodelled_syntax(cmd: str) -> bool:
    """True when cmd holds shell syntax this gate does not model, so it must decline.

    Declines on: `$'` or `$"` (ANSI-C and locale quoting, where `\\'` is a quote);
    a newline or carriage return; a backslash outside single quotes (outside any
    quote or inside double quotes); an unquoted `#`; a quote left open. Single
    quotes have no escapes, so a backslash inside them is literal and fine.
    """
    if "$'" in cmd or '$"' in cmd or "\n" in cmd or "\r" in cmd:
        return True
    quote = ""
    for ch in cmd:
        if quote == "'":
            if ch == "'":
                quote = ""
        elif quote == '"':
            if ch == '"':
                quote = ""
            elif ch == "\\":
                return True
        elif ch in "'\"":
            quote = ch
        elif ch in "\\#":
            return True
    return quote != ""


def _has_subshell(segment: str) -> bool:
    """Return True if segment contains command/process substitution outside single quotes.

    Detects $(...), backtick `...`, <(...), >(...).
    Single-quoted regions suppress all substitution; double-quoted regions do
    NOT suppress $() or backticks, so only single-quote regions are skipped.
    """
    in_single = False
    i = 0
    while i < len(segment):
        ch = segment[i]
        if ch == "'":
            in_single = not in_single
            i += 1
            continue
        if in_single:
            i += 1
            continue
        if ch == "`":
            return True
        if ch == "$" and i + 1 < len(segment) and segment[i + 1] == "(":
            return True
        if ch in ("<", ">") and i + 1 < len(segment) and segment[i + 1] == "(":
            return True
        i += 1
    return False


def _extract_subshells(segment: str) -> Optional[tuple[list[str], str]]:
    """Extract all $(...) subshell inner commands from segment (outside single quotes).

    Returns (inner_cmds, sanitized_segment) where sanitized_segment has each
    $(...) replaced with _SUBSHELL_.  Returns None if extraction fails (backtick,
    process substitution, or unbalanced parens).

    Depth-tracks parentheses so $(...(...)...) with nested parens is handled
    correctly — e.g. $(cat <<'EOF'\\n[link](url)\\nEOF\\n) works despite the ()
    in the URL.
    """
    inner_cmds: list[str] = []
    sanitized: list[str] = []
    in_single = False
    i = 0
    while i < len(segment):
        ch = segment[i]
        if ch == "'":
            in_single = not in_single
            sanitized.append(ch)
            i += 1
            continue
        if in_single:
            sanitized.append(ch)
            i += 1
            continue
        if ch == "`":
            return None  # backtick subshell — cannot safely extract
        if ch in ("<", ">") and i + 1 < len(segment) and segment[i + 1] == "(":
            return None  # process substitution — cannot safely extract
        if ch == "$" and i + 1 < len(segment) and segment[i + 1] == "(":
            # Depth-track to find the matching closing paren.
            depth = 1
            j = i + 2
            inner: list[str] = []
            while j < len(segment) and depth > 0:
                if segment[j] == "(":
                    depth += 1
                elif segment[j] == ")":
                    depth -= 1
                if depth > 0:
                    inner.append(segment[j])
                j += 1
            if depth != 0:
                return None  # unmatched paren
            inner_cmds.append("".join(inner).strip())
            sanitized.append("_SUBSHELL_")
            i = j
            continue
        sanitized.append(ch)
        i += 1
    return inner_cmds, "".join(sanitized)


_DIFFTOOL = re.compile(r"\bgit\b.*\bdifftool\b", re.S)


def _writes_a_file(segment: str) -> bool:
    """True if segment redirects output to anything but /dev/null or another descriptor.

    Scans outside single and double quotes, skipping backslash escapes. `>`, `>>`,
    `>|`, `&>`, `<>` and `>&word` name a file; `>&2`, `2>&1` and `>&-` duplicate or
    close a descriptor. A target that is not literally /dev/null (a variable, a
    quoted word) counts as a file. `>(...)` is left to _has_subshell.
    """
    in_single = in_double = False
    i, n = 0, len(segment)
    while i < n:
        ch = segment[i]
        if ch == "\\" and not in_single:
            i += 2
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if in_single or in_double or ch != ">":
            i += 1
            continue
        j = i + 1
        if j < n and segment[j] == "(":
            i = j
            continue
        while j < n and segment[j] in ">|":
            j += 1
        if j < n and segment[j] == "&":
            k = j + 1
            while k < n and segment[k].isdigit():
                k += 1
            if k < n and segment[k] == "-":
                k += 1
            if k > j + 1 and (k == n or segment[k] in " \t\n;|&)"):
                i = k
                continue
            j += 1
        while j < n and segment[j] in " \t":
            j += 1
        k = j
        while k < n and segment[k] not in " \t\n;|&<>()":
            k += 1
        if segment[j:k] != "/dev/null":
            return True
        i = k
    return False


def segment_is_allowed(segment: str, patterns: list[str], _depth: int = 0) -> bool:
    segment = segment.strip()
    if not segment:
        return True  # empty segment (e.g. trailing ;) — harmless
    if has_unmodelled_syntax(segment):
        return False
    # Decline a write to a file, or git difftool (its -x runs any program),
    # whatever the allow list says. Checked before the keyword shortcut so
    # "done > file" is not approved either.
    if _writes_a_file(segment) or _DIFFTOOL.search(segment):
        return False
    # A bare shell keyword (do, done, then, fi, ...) carries no payload. After an
    # opening keyword (do, then, else, elif) the rest is a command and must match a
    # rule itself; after a closing one (done, fi, esac) only descriptor or /dev/null
    # redirects may follow.
    word = segment.split()[0]
    if word in _SHELL_KEYWORDS:
        rest = segment[len(word):].strip()
        if not rest:
            return True
        if word in _OPENING_KEYWORDS:
            return segment_is_allowed(rest, patterns, _depth)
        return bool(_DESCRIPTOR_REDIRECTS.fullmatch(rest))
    if _has_subshell(segment):
        # Safe subshell path: allow only when EVERY $(...) inner command is itself
        # allowed AND the outer command (with subshells replaced) matches a pattern
        # OR is a simple VAR=$(cmd) assignment.
        # Recursion depth cap: prevents pathological nesting from stalling the hook.
        if _depth >= 4:
            return False
        result = _extract_subshells(segment)
        if result is None:
            return False  # backtick / process-substitution / unbalanced — reject
        inner_cmds, sanitized = result
        # All inner commands must be individually allowed.
        if not all(segment_is_allowed(c, patterns, _depth + 1) for c in inner_cmds):
            return False
        # Outer check 1: sanitized segment matches an allow pattern.
        for pat in patterns:
            if re.match(glob_to_regex(pat), sanitized):
                return True
        # Outer check 2: VAR=_SUBSHELL_ — a simple variable-capture assignment.
        # e.g. HASH=$(git rev-parse --short=4 HEAD)
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=_SUBSHELL_$", sanitized):
            return True
        return False
    for pat in patterns:
        if re.match(glob_to_regex(pat), segment):
            return True
    return False


def split_compound(cmd: str) -> list[str]:
    """
    Split a shell command on top-level compound operators: &&, ||, ;, |, and a
    background & (not the & of a redirection such as 2>&1 or &>file).

    Quote-aware: characters inside single-quoted or double-quoted strings are
    never treated as operators.  Escaped pipes (\\|) outside quotes are also
    preserved so they are not treated as pipeline operators.

    Control-structure aware: newlines within a for/while/until loop header
    (between the keyword and the closing ;) are treated as spaces rather than
    segment separators.  This prevents multi-line `for var in a b c\\nd e f; do`
    constructs from being fragmented into unapproved path-list segments.

    This is intentionally simple — false negatives are safe: we'd just not
    approve that case, falling back to the normal permission prompt.
    """
    segments: list[str] = []
    current: list[str] = []
    i = 0
    in_single = False
    in_double = False
    in_ctrl_header = False  # True when inside a for/while/until header (before ;)

    while i < len(cmd):
        ch = cmd[i]

        # Track quoting state.
        if ch == "'" and not in_double:
            in_single = not in_single
            current.append(ch)
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            current.append(ch)
            i += 1
            continue

        # Inside a quoted string — never split.
        if in_single or in_double:
            current.append(ch)
            i += 1
            continue

        # Escaped pipe outside quotes — keep as-is.
        if ch == "\\" and i + 1 < len(cmd) and cmd[i + 1] == "|":
            current.append("\\|")
            i += 2
            continue

        # Two-character operators: &&, ||
        two = cmd[i : i + 2]
        if two in ("&&", "||"):
            in_ctrl_header = False
            seg = "".join(current).strip()
            if seg:
                segments.append(seg)
            current = []
            i += 2
            # skip whitespace after operator
            while i < len(cmd) and cmd[i] in (" ", "\t", "\n"):
                i += 1
            continue

        # A lone & (background) ends a command like ; does. The & in 2>&1, >&2,
        # <&0 and &>file belongs to a redirection and does not split.
        if ch == "&" and (i == 0 or cmd[i - 1] not in "<>") and cmd[i + 1 : i + 2] != ">":
            in_ctrl_header = False
            seg = "".join(current).strip()
            if seg:
                segments.append(seg)
            current = []
            i += 1
            while i < len(cmd) and cmd[i] in (" ", "\t", "\n"):
                i += 1
            continue

        # Semicolon ends a control-structure header.
        if ch == ";":
            in_ctrl_header = False
            seg = "".join(current).strip()
            if seg:
                segments.append(seg)
            current = []
            i += 1
            while i < len(cmd) and cmd[i] in (" ", "\t", "\n"):
                i += 1
            continue

        # Newline: if we're inside a for/while/until header, treat as a space
        # so the entire multi-line variable list is kept as one segment.
        if ch == "\n":
            current_text = "".join(current).lstrip()
            if not in_ctrl_header and re.match(r"^(for|while|until)\b", current_text):
                in_ctrl_header = True
            if in_ctrl_header:
                current.append(" ")
                i += 1
                while i < len(cmd) and cmd[i] in (" ", "\t"):
                    i += 1
                continue
            # Normal newline split.
            seg = "".join(current).strip()
            if seg:
                segments.append(seg)
            current = []
            i += 1
            while i < len(cmd) and cmd[i] in (" ", "\t", "\n"):
                i += 1
            continue

        # Pipeline operator.
        if ch == "|":
            in_ctrl_header = False
            seg = "".join(current).strip()
            if seg:
                segments.append(seg)
            current = []
            i += 1
            while i < len(cmd) and cmd[i] in (" ", "\t", "\n"):
                i += 1
            continue

        current.append(ch)
        i += 1

    seg = "".join(current).strip()
    if seg:
        segments.append(seg)
    return segments


def command_is_approved(cmd: str, patterns: list[str]) -> bool:
    """True when the gate approves cmd: nothing unmodelled in it, and every part allowed."""
    if not patterns or has_unmodelled_syntax(cmd):
        return False
    return all(segment_is_allowed(seg, patterns) for seg in split_compound(cmd))


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    # Opt-in: off unless YBASE_ALLOW_GATE=1. Off prints nothing.
    if not gate_enabled():
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    cmd = data.get("tool_input", {}).get("command", "")
    if not cmd:
        sys.exit(0)

    # Only act on compound commands — single commands are handled by the
    # built-in permission system already. The \\| check avoids false positives
    # from escaped pipes inside grep patterns (e.g. "grep 'a\\|b'" is not compound).
    if not re.search(r"&&|\|\||(?<!\\);|(?<!\\)\||\n", cmd):
        sys.exit(0)

    patterns = load_allow_patterns()
    if command_is_approved(cmd, patterns):
        print('{"decision": "approve"}')


if __name__ == "__main__":
    main()
