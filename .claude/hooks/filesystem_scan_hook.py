#!/usr/bin/env python3
"""PreToolUse hook: refuse a recursive filesystem walk rooted too high.

WHAT IT REFUSES. A recursive walk whose root is `/`, `/home`, `/Users`, `/mnt`,
`/Volumes`, `$HOME`, a user home directly under `/home` or `/Users`, a whole
volume directly under `/mnt` or `/Volumes`, or the root of the network mount
(NFS, CIFS, FUSE and the like) that holds the session's working directory. The
walkers it knows: `find`, `bfs`, `fd`, `rg`, `grep -r`, `tree`, `du`, `ls -R`,
and the Glob and Grep tools through their `path`. A relative root is read against
the session cwd and any `cd` earlier in the same command, so `cd / && find .`
is caught too. A `bash -c '...'` string is read the same way, three levels deep.

WHY. Every one of these walks every directory under its root before a pattern
filters anything, so the cost is the size of the tree, not the size of the
answer. On a shared or network filesystem that cost lands on everyone who uses
it, and a search started by mistake can run for days.

WHAT PASSES. Any root below those, which is where a search belongs: the repo,
one virtualenv, one run directory. A `find`/`bfs` with `-maxdepth` <= 3, an
`rg`/`fd` with `--max-depth` <= 3, a `tree -L` <= 3, and `find / -xdev`, which
stays on the local root filesystem.

BLOCKING: a warning after the walk has started is worth nothing.

ESCAPE: prefix the command with `SCAN_WIDE=1` when the wide walk is what you
mean (`SCAN_WIDE=1 find /mnt/data -name x`). Setting `SCAN_WIDE` in the
session's environment has the same effect.

A hook that cannot decide allows: malformed stdin, a root built by shell
expansion, an unparseable command, and any internal error all exit 0, the last
out loud on stderr. It does not see a walk inside a script the command runs or
an `os.walk` in `python -c`. Claude Code is the only harness that runs this
hook; `docs/codex.md` carries the rule for Codex.

Run by hand: python3 .claude/hooks/filesystem_scan_hook.py < payload.json
"""
import json
import os
import re
import shlex
import subprocess
import sys
import traceback

ESCAPE = "SCAN_WIDE"
MAX_DEPTH = 3
BROAD = ("/", "/home", "/Users", "/mnt", "/Volumes")
HOME_PARENTS = ("/home", "/Users")
VOLUME_PARENTS = ("/mnt", "/Volumes")
NETWORK_TYPES = {"nfs", "nfs4", "cifs", "smbfs", "smb3", "afpfs", "webdav",
                 "lustre", "glusterfs", "ceph", "9p", "afs", "sshfs"}
OPERATORS = {";", "|", "||", "&", "&&", "(", ")", ";;", "|&"}
REDIRECTS = {"<", ">", ">>", "<<", "<<<", ">&", "<&", "&>", "2>", "2>>"}
GLOB_CHARS = "*?["
# Words that may stand before the command they run.
PREFIXES = {"sudo", "nohup", "nice", "time", "command", "exec", "builtin", "env",
            "timeout", "ionice", "stdbuf", "setsid", "xargs", "then", "do", "else",
            "elif", "if", "while", "until", "!", "{", "}"}
# Prefix options that consume the next token.
PREFIX_VALUE_OPTS = {"sudo": {"-u", "-g"}, "nice": {"-n"}, "timeout": {"-s", "-k"},
                     "ionice": {"-c", "-n"},
                     "xargs": {"-I", "-n", "-P", "-d", "-L", "-s", "-a", "-E"}}
SHELLS = {"bash", "sh", "zsh", "dash"}
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")

DENIAL = """\
Refused: `{what}` walks {root}, which is {why}.

A recursive walk visits every directory under its root before any pattern
filters it, so its cost is the size of the tree, not the size of the answer.
On a shared or network filesystem that load lands on everyone using it.

Search where the answer is instead:

  inside the repo            rg -l PATTERN <repo>   or Grep/Glob with path=<repo>
  one known tree             find <that dir> -name X   (a venv, a run dir, a cache)
  a bounded look at a root   find {root} -maxdepth {depth} -name X
  the local disk only        find / -xdev -name X
  where a package lives      python3 -c 'import pkg; print(pkg.__file__)'
  where a binary lives       command -v NAME

If the wide walk is what you mean:  {escape}=1 <the same command>"""


# ----------------------------------------------------------------- mounts
def parse_proc_mounts(text):
    """[(mount point, fstype)] from the text of /proc/mounts."""
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        # /proc/mounts escapes a space in a path as \040.
        point = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), parts[1])
        out.append((point, parts[2]))
    return out


def parse_mount_output(text):
    """[(mount point, fstype)] from BSD/macOS `mount` output: `dev on /p (type, ...)`."""
    out = []
    for line in text.splitlines():
        m = re.match(r"^.*? on (/.*?) \(([^,)]+)", line)
        if m:
            out.append((m.group(1), m.group(2).strip()))
    return out


def mounts():
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/mounts", encoding="utf-8", errors="replace") as fh:
                return parse_proc_mounts(fh.read())
        if sys.platform == "darwin":
            res = subprocess.run(["mount"], capture_output=True, text=True, timeout=5)
            return parse_mount_output(res.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return []


def is_network_type(fstype):
    return fstype in NETWORK_TYPES or fstype.startswith("fuse")


def network_root(path, table):
    """The mount point of the network filesystem holding `path`, or None."""
    path = os.path.normpath(path)
    best = None
    for point, fstype in table:
        point_n = os.path.normpath(point)
        if path == point_n or path.startswith(point_n.rstrip("/") + "/"):
            if best is None or len(point_n) > len(best[0]):
                best = (point_n, fstype)
    if best is not None and is_network_type(best[1]):
        return best[0]
    return None


# ------------------------------------------------------------------ roots
def _home():
    return os.path.normpath(os.environ.get("HOME") or os.path.expanduser("~"))


def broad_reason(path, home=None, net_root=None):
    """Why `path` is too broad to walk, or None when it is fine."""
    p = os.path.normpath(path)
    home = home or _home()
    if p == "/":
        return "the whole machine"
    if p in BROAD:
        return "every home or volume on the machine"
    if net_root is not None and p == net_root:
        return "the root of the network mount this session works on"
    if p == home:
        return "your whole home directory"
    if os.path.dirname(p) in HOME_PARENTS:
        return "a whole home directory"
    if os.path.dirname(p) in VOLUME_PARENTS:
        return "a whole mounted volume"
    return None


def resolve(token, cwd):
    """The directory a path operand walks, or None when the shell decides it."""
    if token.startswith("~"):
        if token != "~" and not token.startswith("~/"):
            return None  # ~user
        token = _home() + token[1:]
    for spelling in ("${HOME}", "$HOME"):
        if token.startswith(spelling):
            token = _home() + token[len(spelling):]
            break
    if "$" in token or "`" in token:
        return None
    cut = min((token.find(c) for c in GLOB_CHARS if c in token), default=-1)
    if cut >= 0:
        # A glob walks whatever it expands to, so judge the literal part.
        token = token[:cut]
        token = token if token.endswith("/") else os.path.dirname(token) or "."
    if not os.path.isabs(token):
        token = os.path.join(cwd, token)
    return os.path.normpath(token)


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _split_opts(argv, value_short="", value_long=(), stop=()):
    """(options as (flag, value) pairs, operands). Handles -abc and --x=y."""
    opts, operands, i = [], [], 0
    while i < len(argv):
        tok = argv[i]
        if tok in stop:
            break
        if tok == "--":
            operands.extend(argv[i + 1:])
            break
        if tok.startswith("--"):
            name, eq, val = tok.partition("=")
            if not eq and name in value_long and i + 1 < len(argv):
                val = argv[i + 1]
                i += 1
            opts.append((name, val))
        elif tok.startswith("-") and len(tok) > 1:
            for j, ch in enumerate(tok[1:], start=1):
                if ch in value_short:
                    val = tok[j + 1:]
                    if not val and i + 1 < len(argv):
                        val = argv[i + 1]
                        i += 1
                    opts.append(("-" + ch, val))
                    break
                opts.append(("-" + ch, ""))
        else:
            operands.append(tok)
        i += 1
    return opts, operands


def _depth(opts, names):
    for name, val in opts:
        if name in names and _int(val) is not None:
            return _int(val)
    return None


def _find(argv):
    """-> (roots, maxdepth or None, stays on one filesystem) for find and bfs."""
    roots, i = [], 0
    while i < len(argv) and argv[i] in ("-H", "-L", "-P", "-E", "-X", "-s", "-x"):
        i += 1
    while i < len(argv):
        tok = argv[i]
        if re.fullmatch(r"-(O|j)\d+", tok):
            i += 1
        elif tok in ("-D", "-S", "-j", "-O"):
            i += 2
        else:
            break
    while i < len(argv) and not argv[i].startswith("-") and argv[i] not in ("(", "!", ","):
        roots.append(argv[i])
        i += 1
    rest = argv[i:]
    depth = None
    for k, tok in enumerate(rest):
        if tok == "-maxdepth" and k + 1 < len(rest):
            depth = _int(rest[k + 1])
    local = "-xdev" in rest or "-mount" in rest
    return roots or ["."], depth, local


RG_VALUE_LONG = {
    "--regexp", "--file", "--glob", "--iglob", "--type", "--type-not", "--max-depth",
    "--maxdepth", "--max-count", "--after-context", "--before-context", "--context",
    "--threads", "--max-columns", "--replace", "--encoding", "--max-filesize",
    "--type-add", "--ignore-file", "--pre", "--pre-glob", "--sort", "--sortr",
    "--color", "--colors", "--engine"}
GREP_VALUE_LONG = {"--regexp", "--file", "--include", "--exclude", "--exclude-dir"}
PATTERN_OPTS = {"-e", "-f", "--regexp", "--file"}


def _search_roots(opts, operands):
    """Path operands of a grep-like call: the first operand is the pattern
    unless -e or -f supplied it, or rg is listing files."""
    names = {n for n, _ in opts}
    if not names & PATTERN_OPTS and "--files" not in names:
        operands = operands[1:]
    return operands or ["."]


def roots_of(tool, argv):
    """-> [(root operand, bounded)] for one invocation; [] when it does not walk."""
    if tool in ("find", "bfs"):
        roots, depth, local = _find(argv)
        bounded = depth is not None and depth <= MAX_DEPTH
        return [(r, bounded or (local and os.path.normpath(r) == "/")) for r in roots]
    if tool == "rg":
        opts, operands = _split_opts(argv, "ABCdefgjmMrtTE", RG_VALUE_LONG)
        depth = _depth(opts, ("-d", "--max-depth", "--maxdepth"))
        bounded = depth is not None and depth <= MAX_DEPTH
        return [(r, bounded) for r in _search_roots(opts, operands)]
    if tool in ("grep", "egrep", "fgrep", "ugrep"):
        opts, operands = _split_opts(argv, "ABCdDefm", GREP_VALUE_LONG)
        if not {n for n, _ in opts} & {"-r", "-R", "--recursive", "--dereference-recursive"}:
            return []
        return [(r, False) for r in _search_roots(opts, operands)]
    if tool in ("fd", "fdfind"):
        opts, operands = _split_opts(argv, "dEetjcSo", {"--max-depth", "--exclude",
                                                        "--extension", "--type"},
                                     stop=("-x", "-X", "--exec", "--exec-batch"))
        depth = _depth(opts, ("-d", "--max-depth"))
        bounded = depth is not None and depth <= MAX_DEPTH
        return [(r, bounded) for r in operands[1:] or ["."]]
    if tool == "du":
        _, operands = _split_opts(argv, "BdtX", {"--max-depth", "--block-size",
                                                 "--threshold", "--exclude"})
        # --max-depth only trims the report; du still walks everything.
        return [(r, False) for r in operands or ["."]]
    if tool == "tree":
        opts, operands = _split_opts(argv, "LPIoH")
        depth = _depth(opts, ("-L",))
        bounded = depth is not None and depth <= MAX_DEPTH
        return [(r, bounded) for r in operands or ["."]]
    if tool == "ls":
        opts, operands = _split_opts(argv, "IwT")
        if not {n for n, _ in opts} & {"-R", "--recursive"}:
            return []
        return [(r, False) for r in operands or ["."]]
    return []


# ---------------------------------------------------------------- commands
def _strip_heredocs(command):
    """Drop heredoc bodies (data, not commands) and end each line with `;`."""
    out, delim = [], None
    for line in command.replace("\\\n", " ").split("\n"):
        if delim is not None:
            if line.strip() == delim:
                delim = None
            continue
        m = re.search(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", line)
        if m:
            delim = m.group(1)
        out.append(line)
    return " ;\n".join(out)


def _tokenize(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>")
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
        base = tok.rsplit("/", 1)[-1]
        if ASSIGNMENT.match(tok):
            name, _, value = tok.partition("=")
            if name == ESCAPE and value:
                escaped = True
            i += 1
            continue
        if base in PREFIXES:
            i += 1
            takes = PREFIX_VALUE_OPTS.get(base, set())
            while i < len(cmd) and cmd[i].startswith("-"):
                i += 2 if cmd[i] in takes else 1
            if base == "timeout" and i < len(cmd):
                i += 1  # the duration
            continue
        break
    return cmd[i:], escaped


def _drop_redirects(cmd):
    """The words without redirections: the operator, its target and a leading fd digit
    (`2>/dev/null` tokenizes as `2`, `>`, `/dev/null`), so `> /mnt/out.txt` is never a root."""
    out, i = [], 0
    while i < len(cmd):
        if cmd[i] in REDIRECTS:
            if out and len(out[-1]) == 1 and out[-1].isdigit():
                out.pop()
            i += 2
            continue
        out.append(cmd[i])
        i += 1
    return out


def scans(command, cwd, net_root=None, nesting=0):
    """Yield (invocation text, root) for every too-broad walk in a command."""
    try:
        tokens = _tokenize(_strip_heredocs(command))
    except ValueError:
        return
    for raw in _simple_commands(tokens):
        cmd, escaped = _strip_prefixes(raw)
        cmd = _drop_redirects(cmd)
        if not cmd or escaped:
            continue
        tool = cmd[0].rsplit("/", 1)[-1]
        argv = cmd[1:]
        if tool == "cd":
            cwd = (resolve(argv[0], cwd) if argv else _home()) or cwd
            continue
        if tool in SHELLS and "-c" in argv and nesting < 3:
            k = argv.index("-c")
            if k + 1 < len(argv):
                for hit in scans(argv[k + 1], cwd, net_root, nesting + 1):
                    yield hit
            continue
        for operand, bounded in roots_of(tool, argv):
            if bounded:
                continue
            root = resolve(operand, cwd)
            if root and broad_reason(root, net_root=net_root):
                yield " ".join(cmd)[:120], root


def tool_root(tool, tool_input, cwd):
    """The directory a Glob or Grep tool call walks."""
    path = tool_input.get("path")
    base = resolve(path, cwd) if isinstance(path, str) and path else cwd
    pattern = tool_input.get("pattern")
    if tool == "Glob" and isinstance(pattern, str) and pattern.startswith("/"):
        base = resolve(pattern, cwd) or base
    return base


def _deny(what, root, net_root):
    reason = DENIAL.format(what=what, root=root, why=broad_reason(root, net_root=net_root),
                           depth=MAX_DEPTH, escape=ESCAPE)
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
    if not isinstance(payload, dict):
        return 0
    if os.environ.get(ESCAPE):
        return 0
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    cwd = payload.get("cwd")
    cwd = os.path.normpath(cwd) if isinstance(cwd, str) and cwd else os.getcwd()
    net_root = network_root(cwd, mounts())

    if tool in ("Glob", "Grep"):
        root = tool_root(tool, tool_input, cwd)
        if root and broad_reason(root, net_root=net_root):
            return _deny("%s(%r)" % (tool, tool_input.get("pattern")), root, net_root)
        return 0
    if tool != "Bash":
        return 0
    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        return 0
    for what, root in scans(command, cwd, net_root):
        return _deny(what, root, net_root)
    return 0


def main():
    try:
        return _run()
    except Exception:
        # A broken hook must never break a session: allow, and say so, because
        # a silent exit 0 reads exactly like a clean call.
        sys.stderr.write(
            "filesystem_scan_hook: DISABLED for this call, it raised before it could\n"
            "finish, so the command was not checked for a whole-filesystem walk:\n"
            + traceback.format_exc())
        return 0


if __name__ == "__main__":
    sys.exit(main())
