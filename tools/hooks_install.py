#!/usr/bin/env python3
"""hooks_install.py: register YBase's blocking Bash guards in the user's Claude Code settings.

    ybase hooks install-user [--dry-run] [--remove]

Claude Code runs a project's `.claude/settings.json` hooks only when the
session starts inside that project. A session started elsewhere (a managed
repo, a scratch directory) gets none of them. This command merges one
entry per BLOCKING hook into the user-level settings file, which applies to
every session on this machine:

    $CLAUDE_CONFIG_DIR/settings.json      when CLAUDE_CONFIG_DIR is set
    ~/.claude/settings.json               otherwise

Each entry's command first looks for the same hook in the current project
(`$CLAUDE_PROJECT_DIR/.claude/hooks/<name>`) and exits 0 when it is there, so
the project copy wins and a YBase session does not run each guard twice.
Otherwise it runs this clone's copy by absolute path and passes through only
exit 2 (deny); anything else allows.

Idempotent: entries are keyed by hook filename, every other key and hook in the
file is kept, and one line is printed per hook: `ok|add|update|remove <name>`.
`--dry-run` prints the lines and writes nothing. `--remove` deletes the entries.
Stdlib only; Python 3.8+.
"""
import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOKS_DIR = ROOT / ".claude" / "hooks"
# (hook filename, tool matcher). Only the blocking guards: an advisory hook
# outside its project has no project context to advise on.
BLOCKING_HOOKS = [
    ("filesystem_scan_hook.py", "Bash|Glob|Grep"),
    ("self_matching_pgrep_hook.py", "Bash"),
    ("zsh_word_split_hook.py", "Bash"),
    ("pr_draft_hook.py", "Bash"),
    ("leak_hook.py", "Bash"),
]
EVENT = "PreToolUse"


def settings_path():
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    base_path = pathlib.Path(base) if base else pathlib.Path.home() / ".claude"
    return base_path / "settings.json"


def hook_command(name):
    local = HOOKS_DIR / name
    return ('h="$CLAUDE_PROJECT_DIR/.claude/hooks/%s"; [ -f "$h" ] && exit 0; '
            'python3 "%s"; [ $? = 2 ] && exit 2; exit 0' % (name, local))


def marker(name):
    """The substring that identifies our entry for `name`, whatever clone wrote it."""
    return "/.claude/hooks/%s\"" % name


def load(path):
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("%s: top level is not a JSON object" % path)
    return data


def find_entry(groups, name):
    """(group index, hook index) of our entry for `name`, or None."""
    for gi, group in enumerate(groups):
        hooks = group.get("hooks") if isinstance(group, dict) else None
        if not isinstance(hooks, list):
            continue
        for hi, hook in enumerate(hooks):
            if isinstance(hook, dict) and marker(name) in str(hook.get("command", "")):
                return gi, hi
    return None


def apply(settings, remove=False):
    """Mutate `settings` in place; return [(action, name)]."""
    actions = []
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
        settings["hooks"] = hooks
    groups = hooks.get(EVENT)
    if not isinstance(groups, list):
        groups = []
        hooks[EVENT] = groups
    for name, matcher in BLOCKING_HOOKS:
        found = find_entry(groups, name)
        want = {"type": "command", "command": hook_command(name)}
        if remove:
            if found is None:
                actions.append(("ok", name))
                continue
            gi, hi = found
            del groups[gi]["hooks"][hi]
            if not groups[gi]["hooks"]:
                del groups[gi]
            actions.append(("remove", name))
            continue
        if found is None:
            groups.append({"matcher": matcher, "hooks": [want]})
            actions.append(("add", name))
            continue
        gi, hi = found
        group = groups[gi]
        if group["hooks"][hi] == want and group.get("matcher") == matcher and len(group["hooks"]) == 1:
            actions.append(("ok", name))
            continue
        if len(group["hooks"]) == 1:
            group["matcher"] = matcher
            group["hooks"][hi] = want
        else:
            # Our hook shares a group with someone else's: leave theirs alone.
            del group["hooks"][hi]
            groups.append({"matcher": matcher, "hooks": [want]})
        actions.append(("update", name))
    if remove:
        if not hooks.get(EVENT):
            hooks.pop(EVENT, None)
        if not hooks:
            settings.pop("hooks", None)
    return actions


def write(path, settings):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".settings.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def install_user(argv):
    dry_run = "--dry-run" in argv
    remove = "--remove" in argv
    unknown = [a for a in argv if a not in ("--dry-run", "--remove")]
    if unknown:
        print("hooks install-user: unknown argument(s): %s" % " ".join(unknown), file=sys.stderr)
        return 2
    missing = [n for n, _ in BLOCKING_HOOKS if not (HOOKS_DIR / n).is_file()]
    if missing and not remove:
        print("hooks install-user: missing in %s: %s" % (HOOKS_DIR, ", ".join(missing)), file=sys.stderr)
        return 1
    path = settings_path()
    try:
        settings = load(path)
    except ValueError as exc:
        print("hooks install-user: cannot parse %s (%s); nothing written" % (path, exc), file=sys.stderr)
        return 1
    actions = apply(settings, remove=remove)
    for action, name in actions:
        print("%s %s" % (action, name))
    changed = any(a != "ok" for a, _ in actions)
    if dry_run:
        print("dry run: %s not written" % path, file=sys.stderr)
    elif changed:
        write(path, settings)
        print("wrote %s" % path, file=sys.stderr)
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0 if argv else 2
    if argv[0] == "install-user":
        return install_user(argv[1:])
    print("hooks: unknown subcommand %r (try install-user)" % argv[0], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
