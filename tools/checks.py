#!/usr/bin/env python3
"""checks.py: the one registry of YBase checks, and their runner.

Every consumer (the pre-commit hook, CI, `ybase check`) runs this file,
so a check is declared exactly once: in CHECKS at the bottom.

    python3 tools/checks.py            run every check
    python3 tools/checks.py --list     list checks
    python3 tools/checks.py links leaks
                                       run only the named checks

Each check returns (scanned, findings). A pass reports what it scanned, so a
check that silently scanned nothing is visible as "scanned 0".
Stdlib only: this must run unchanged on every machine profile.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import envfile  # noqa: E402
MAX_SHOWN = 25
# Never scanned by any check: working documents kept out of the published tree.
EXCLUDE_PREFIXES = ("docs/superpowers/",)
LEAKS_BASELINE = ".leaks-baseline"


def under(rel: str, prefixes: tuple[str, ...]) -> bool:
    """True when `rel` is one of `prefixes`, inside one that ends in "/", or starts
    with one that ends in "*" (less the "*")."""
    return any(rel == p or (p.endswith("/") and rel.startswith(p))
               or (p.endswith("*") and rel.startswith(p[:-1])) for p in prefixes)


# ---------------------------------------------------------------- context
@dataclass
class Ctx:
    root: Path

    def files(self) -> list[Path]:
        """Tracked plus untracked-but-not-ignored files; a plain walk outside git."""
        try:
            out = subprocess.run(
                ["git", "-C", str(self.root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                capture_output=True, check=True,
            ).stdout.decode()
            paths = [self.root / p for p in out.split("\0") if p]
        except (subprocess.CalledProcessError, FileNotFoundError):
            paths = [p for p in self.root.rglob("*") if p.is_file() and ".git" not in p.parts]
        return sorted(p for p in paths
                      if p.is_file() and not under(p.relative_to(self.root).as_posix(), EXCLUDE_PREFIXES))

    def text_files(self, suffixes: tuple[str, ...] | None = None) -> list[Path]:
        res = []
        for p in self.files():
            if suffixes and p.suffix not in suffixes:
                continue
            try:
                p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            res.append(p)
        return res

    def rel(self, p: Path) -> str:
        return str(p.relative_to(self.root))

    def in_git(self) -> bool:
        return subprocess.run(["git", "-C", str(self.root), "rev-parse", "--git-dir"],
                              capture_output=True).returncode == 0


def frontmatter(text: str) -> dict[str, object]:
    """Parse the small YAML subset YBase uses: `key: value` and `key: [a, b]`."""
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    meta: dict[str, object] = {}
    for line in text[4:end].splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val.startswith("[") and val.endswith("]"):
            meta[key] = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
        else:
            meta[key] = val.strip("'\"")
    return meta


# ---------------------------------------------------------------- checks
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def links_in_file(p: Path, rel: str) -> tuple[int, list[str]]:
    """(links scanned, findings) for the relative markdown links in one file, labelled `rel`."""
    scanned, bad = 0, []
    text = p.read_text(encoding="utf-8")
    # Ignore links inside fenced code blocks and inline code.
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)
    for m in LINK_RE.finditer(text):
        target = m.group(1).split("#", 1)[0]
        if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith(("{", "<")):
            continue
        scanned += 1
        if not (p.parent / target).exists():
            bad.append(f"{rel}: broken link -> {target}")
    return scanned, bad


def check_links(ctx: Ctx):
    """Relative markdown links resolve to a file or directory in the repo."""
    scanned, bad = 0, []
    for p in ctx.text_files((".md",)):
        n, b = links_in_file(p, ctx.rel(p))
        scanned += n
        bad += b
    return scanned, bad


LEAK_PATTERNS = [
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("AWS account in an ARN", re.compile(r"arn:aws:[a-z0-9-]+::\d{12}:")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("API secret key", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{32,}\b")),
    ("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("absolute home path", re.compile(r"(?<![\w.])/(?:home|Users)/[a-z][a-z0-9._-]+/")),
    ("email address", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
]
EMAIL_ALLOW = re.compile(r"@(?:example\.(?:com|org|net)|users\.noreply\.github\.com)$|^noreply@anthropic\.com$")


@dataclass
class DenySources:
    """The private terms the leak scan applies, where they came from, and what kept any
    from loading."""
    patterns: list[re.Pattern]
    findings: list[str]
    kbs: int = 0  # knowledge bases configured or defaulted
    supplied: int = 0  # of those, how many supplied a readable deny.list

    def summary(self) -> str:
        return (f"deny list: {len(self.patterns)} terms from {self.supplied} of {self.kbs} "
                "knowledge bases")


def deny_sources(ctx: Ctx) -> DenySources:
    """Private terms from `deny.list` in every knowledge base. The knowledge bases are those
    named by the root's settings and, when the root is a linked worktree, by its main
    checkout's settings too: a worktree has no `.env`.

    Each of these is a finding, since it silently narrows the scan: a `.env` that exists but
    cannot be read; a knowledge base named in `.env` or the environment
    (YBASE_KB_PRIMARY, YBASE_KB_PATHS) that is missing; a `deny.list` that exists but
    cannot be read or decoded; a line that is not a valid regular expression (skipped, and
    never repeated, since it is private). The default `kb/` when nothing names it, and a
    knowledge base with no `deny.list`, are not findings."""
    roots = [ctx.root]
    main = envfile.main_checkout(ctx.root)
    if main != ctx.root:
        roots.append(main)
    bad: list[str] = []
    kbs: list[Path] = []
    named: set[Path] = set()
    for r in roots:
        env = r / ".env"
        if env.exists():
            try:
                env.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                bad.append(f"{env}: cannot be read ({getattr(e, 'strerror', None) or e.__class__.__name__}), "
                           "so the knowledge bases it names were not loaded")
        explicit = [envfile.setting("YBASE_KB_PRIMARY", r), *envfile.setting("YBASE_KB_PATHS", r).split(":")]
        named |= {Path(x) for x in explicit if x}
        kbs += [kb for kb in envfile.kb_roots(r) if kb not in kbs]
    out = DenySources([], bad, kbs=len(kbs))
    for kb in kbs:
        if kb in named and not kb.is_dir():
            bad.append(f"{kb}: a knowledge base named in the settings is missing, so its deny list "
                       "was not loaded")
            continue
        path = kb / "deny.list"
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            bad.append(f"{path}: cannot be read ({getattr(e, 'strerror', None) or e.__class__.__name__}), "
                       "so its terms were not loaded")
            continue
        out.supplied += 1
        for i, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                out.patterns.append(re.compile(line))
            except (re.error, OverflowError, RecursionError, ValueError) as e:
                # re.error for bad syntax; OverflowError for a huge repeat count and
                # RecursionError for deep nesting come from the compiler itself.
                bad.append(f"{path}:{i}: not a valid regular expression "
                           f"({getattr(e, 'msg', str(e))}), "
                           "so the leak scan skips this line")
    return out


def deny_list(ctx: Ctx) -> tuple[list[re.Pattern], list[str]]:
    """(private terms, findings) as `deny_sources` reads them."""
    d = deny_sources(ctx)
    return d.patterns, d.findings


def deny_patterns(ctx: Ctx) -> list[re.Pattern]:
    """Private terms from `deny.list` in every knowledge base: never part of this repository.
    A line that is not a valid regular expression is skipped (`deny_list` reports it)."""
    return deny_list(ctx)[0]


def leak_hits(text: str, deny: list[re.Pattern]) -> list[str]:
    """Leak findings in `text`: every LEAK_PATTERNS match and every `deny` match."""
    hits = []
    for name, pat in LEAK_PATTERNS:
        for m in pat.finditer(text):
            if name == "email address" and EMAIL_ALLOW.search(m.group(0)):
                continue
            hits.append(f"{name}: {m.group(0)[:60]}")
    for pat in deny:
        for m in pat.finditer(text):
            hits.append(f"private term (deny.list): {m.group(0)[:60]}")
    return hits


def log_range(ctx: Ctx) -> tuple[list[str], list[str]]:
    """(git log revisions, findings): the commits after the hash in .leaks-baseline, else every commit."""
    f = ctx.root / LEAKS_BASELINE
    base = f.read_text(encoding="utf-8").strip() if f.is_file() else ""
    if not base:
        return ["--all"], []
    known = subprocess.run(["git", "-C", str(ctx.root), "rev-parse", "-q", "--verify", f"{base}^{{commit}}"],
                           capture_output=True).returncode == 0
    if not known:
        return ["--all"], [f"{LEAKS_BASELINE}: {base[:40]} is not a commit here, so every message was read"]
    return [f"{base}..HEAD"], []


def check_leaks(ctx: Ctx):
    """No secrets, personal paths, emails or private terms in files or commit messages."""
    sources = deny_sources(ctx)
    deny, bad = sources.patterns, sources.findings
    scanned = 0
    for p in ctx.text_files():
        if p.name == "checks.py" and p.parent.name == "tools":
            continue  # this file spells the patterns out
        scanned += 1
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for h in leak_hits(line, deny):
                bad.append(f"{ctx.rel(p)}:{i}: {h}")
    if ctx.in_git():
        revs, found = log_range(ctx)
        bad += found
        log = subprocess.run(["git", "-C", str(ctx.root), "log", *revs, "--format=%H%x00%B%x01"],
                             capture_output=True, text=True).stdout
        for entry in filter(None, (e.strip() for e in log.split("\x01"))):
            sha, _, body = entry.partition("\x00")
            scanned += 1
            for h in leak_hits(body, deny):
                bad.append(f"commit {sha[:10]} message: {h}")
        # Identities are deliberate, so only the private-term list applies to them.
        ids = subprocess.run(["git", "-C", str(ctx.root), "log", *revs, "--format=%an <%ae>%n%cn <%ce>"],
                             capture_output=True, text=True).stdout
        for ident in sorted(set(ids.splitlines())):
            for pat in deny:
                if pat.search(ident):
                    bad.append(f"commit identity matches deny.list: {ident}")
    return f"{scanned}; {sources.summary()}", bad


TRIG_BLOCK = re.compile(r"<!-- BEGIN TRIGGERS -->(.*?)<!-- END TRIGGERS -->", re.S)


def check_casebook_router(ctx: Ctx):
    """docs/casebook/INDEX.md routes every group file, and each file's triggers match its entries."""
    book = ctx.root / "docs" / "casebook"
    if not book.is_dir():
        return 0, []
    scanned, bad = 0, []
    index = book / "INDEX.md"
    routed = set()
    if index.is_file():
        routed = {t for t in LINK_RE.findall(index.read_text(encoding="utf-8")) if t.endswith(".md")}
    for t in sorted(routed):
        if not (book / t).is_file():
            bad.append(f"docs/casebook/INDEX.md routes to missing {t}")
    for f in sorted(book.glob("*.md")):
        if f.name in ("README.md", "INDEX.md"):
            continue
        scanned += 1
        if f.name not in routed:
            bad.append(f"docs/casebook/{f.name}: not routed from docs/casebook/INDEX.md")
        text = f.read_text(encoding="utf-8")
        m = TRIG_BLOCK.search(text)
        if not m:
            bad.append(f"docs/casebook/{f.name}: no trigger block")
            continue
        triggers = set(re.findall(r"^- `([a-z0-9-]+)`", m.group(1), re.M))
        entries = set(re.findall(r"^## ([a-z0-9-]+)\s*$", text[m.end():], re.M))
        for s in sorted(triggers - entries):
            bad.append(f"docs/casebook/{f.name}: trigger `{s}` has no `## {s}` entry")
        for s in sorted(entries - triggers):
            bad.append(f"docs/casebook/{f.name}: entry `{s}` has no trigger line")
    return scanned, bad


KB_TRACKED = ("kb/README.md", "kb/.gitignore")


def check_no_tracked_state(ctx: Ctx):
    """Per-machine state (.env, .ybase/, tmp/) and knowledge-base content (kb/) is never tracked."""
    if not ctx.in_git():
        return 0, []
    out = subprocess.run(["git", "-C", str(ctx.root), "ls-files", "--cached"],
                         capture_output=True, text=True).stdout.splitlines()
    bad = [f"{p}: private or per-machine state is tracked; git rm --cached it" for p in out
           if p.startswith((".ybase/", "tmp/")) or p in (".env", "MACHINE.md")
           or (p.startswith("kb/") and p not in KB_TRACKED)]
    return len(out), bad


def is_framework_prose(rel: str) -> bool:
    """Framework docs, as opposed to case content imported from elsewhere."""
    if not rel.endswith(".md"):
        return False
    parts = rel.split("/")
    if parts[0] != "cases":
        return True
    return len(parts) == 2 or parts[1] == "_template" or parts[-1] in ("CASE.md",)


def em_dashes_in_file(p: Path, rel: str) -> list[str]:
    """Findings for every em dash (U+2014) in one file, labelled `rel`."""
    return [f"{rel}:{i}: em dash; use a comma, colon, semicolon or a new sentence"
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if "—" in line]


def check_framework_style(ctx: Ctx):
    """Framework prose uses no em dash (U+2014); plain ASCII punctuation reads the same everywhere."""
    scanned, bad = 0, []
    for p in ctx.text_files((".md",)):
        rel = ctx.rel(p)
        if not is_framework_prose(rel):
            continue
        scanned += 1
        bad += em_dashes_in_file(p, rel)
    return scanned, bad


def check_file(path: Path, root: Path | None = None) -> list[str]:
    """`links` and `framework-style` findings for ONE markdown file, for the editor-side hook.

    The registry is untouched: the checks above still scan the whole tree. `root` defaults
    to the enclosing repository, which decides the file's repo-relative label."""
    path = Path(path).resolve()
    if path.suffix != ".md" or not path.is_file():
        return []
    if root is None:
        root = next((d for d in [path.parent] + list(path.parents) if (d / ".git").exists()), path.parent)
    try:
        rel = str(path.relative_to(Path(root).resolve()))
    except ValueError:
        rel = path.name
    bad = links_in_file(path, rel)[1]
    if is_framework_prose(rel):
        bad += em_dashes_in_file(path, rel)
    return bad


def check_skills(ctx: Ctx):
    """Each skill has a SKILL.md naming it, a one-line description and a contract row; .agents/skills resolves."""
    sk = ctx.root / ".claude" / "skills"
    if not sk.is_dir():
        return 0, []
    scanned, bad = 0, []
    readme = sk / "README.md"
    contract = readme.read_text(encoding="utf-8") if readme.is_file() else ""
    for d in sorted(p for p in sk.iterdir() if p.is_dir()):
        scanned += 1
        f = d / "SKILL.md"
        if not f.is_file():
            bad.append(f".claude/skills/{d.name}/: no SKILL.md")
            continue
        fm = frontmatter(f.read_text(encoding="utf-8"))
        if fm.get("name") != d.name:
            bad.append(f".claude/skills/{d.name}/SKILL.md: frontmatter name is {fm.get('name')!r}, expected {d.name!r}")
        desc = fm.get("description")
        if not isinstance(desc, str) or len(desc) < 20 or desc.startswith((">", "|")):
            bad.append(f".claude/skills/{d.name}/SKILL.md: description must be one line saying when to invoke it")
        elif " #" in desc or ": " in desc:
            # Unquoted YAML: " #" starts a comment that silently truncates the description,
            # and ": " inside a plain scalar is rejected by strict parsers.
            bad.append(f".claude/skills/{d.name}/SKILL.md: description contains ' #' or ': ', which YAML misreads")
        if f"`{d.name}/`" not in contract:
            bad.append(f".claude/skills/README.md: no contract row for `{d.name}/`")
    view = ctx.root / ".agents" / "skills"
    if not view.is_symlink() or view.resolve() != sk.resolve():
        bad.append(".agents/skills must be a symlink to ../.claude/skills (the Codex view)")
    return scanned, bad


HOOK_REF_RE = re.compile(r"\.claude/hooks/([A-Za-z0-9_.-]+\.py)")


def check_hooks(ctx: Ctx):
    """Every .claude/hooks/*.py is wired in .claude/settings.json, every wired hook exists, and each has a docstring."""
    hooks = ctx.root / ".claude" / "hooks"
    settings = ctx.root / ".claude" / "settings.json"
    present = {p.name for p in hooks.glob("*.py")} if hooks.is_dir() else set()
    if not present and not settings.is_file():
        return 0, []
    scanned, bad = 0, []
    referenced: set[str] = set()
    if settings.is_file():
        text = settings.read_text(encoding="utf-8")
        try:
            json.loads(text)
        except ValueError as e:
            bad.append(f".claude/settings.json: not valid JSON ({e})")
        referenced = set(HOOK_REF_RE.findall(text))
    elif present:
        bad.append(".claude/settings.json: missing, so no hook under .claude/hooks/ is wired")
    for name in sorted(present):
        scanned += 1
        if name not in referenced:
            bad.append(f".claude/hooks/{name}: not referenced by .claude/settings.json")
        try:
            doc = ast.get_docstring(ast.parse((hooks / name).read_text(encoding="utf-8")))
        except SyntaxError as e:
            bad.append(f".claude/hooks/{name}: does not parse ({e.msg}, line {e.lineno})")
            continue
        if not doc:
            bad.append(f".claude/hooks/{name}: no module docstring saying what it refuses, what passes and the escape")
    for name in sorted(referenced - present):
        scanned += 1
        bad.append(f".claude/settings.json: wires .claude/hooks/{name}, which does not exist")
    return scanned, bad


def law_moments(ctx: Ctx) -> list[str] | None:
    """The moments .claude/hooks/moment_law_hook.py fires, read from the hook itself; None if absent."""
    hook = ctx.root / ".claude" / "hooks" / "moment_law_hook.py"
    if not hook.is_file():
        return None
    spec = importlib.util.spec_from_file_location("ybase_moment_law_hook", hook)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return list(mod.moments())


def check_law(ctx: Ctx):
    """Every moment in moment_law_hook.py has docs/law/<moment>.md, and every law file but README is a moment."""
    law = ctx.root / "docs" / "law"
    try:
        moments = law_moments(ctx)
    except Exception as e:  # a hook that does not import is a finding, not a crash
        return 1, [f".claude/hooks/moment_law_hook.py: cannot be imported ({e!r})"]
    if moments is None and not law.is_dir():
        return 0, []
    scanned, bad = 0, []
    files = {p.stem for p in law.glob("*.md") if p.name != "README.md"} if law.is_dir() else set()
    for m in moments or []:
        scanned += 1
        if m not in files:
            bad.append(f"docs/law/{m}.md: missing, and moment_law_hook.py fires the `{m}` moment")
    for f in sorted(files - set(moments or [])):
        scanned += 1
        bad.append(f"docs/law/{f}.md: no moment in .claude/hooks/moment_law_hook.py fires it")
    return scanned, bad


ALWAYS_ON = ("AGENTS.md", "docs/rules.md")
ALWAYS_ON_LIMIT = 1500
RULE_LIMIT = 50
RULE_START = re.compile(r"^(\d+)\.\s")


def numbered_rules(text: str) -> list[tuple[str, int]]:
    """(rule number, word count) for each rule: from a `<n>. ` line to the next rule, heading or blank line."""
    rules: list[tuple[str, int]] = []
    open_rule = False
    for line in text.splitlines():
        m = RULE_START.match(line)
        if m:
            rules.append((m.group(1), len(line[m.end():].split())))
            open_rule = True
        elif not line.strip() or line.startswith("#"):
            open_rule = False
        elif open_rule:
            n, w = rules[-1]
            rules[-1] = (n, w + len(line.split()))
    return rules


def check_always_on_budget(ctx: Ctx):
    """AGENTS.md plus docs/rules.md total at most 1,500 words; each numbered rule is at most 50."""
    scanned, bad, total = 0, [], 0
    for rel in ALWAYS_ON:
        p = ctx.root / rel
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        total += len(text.split())
        scanned += 1
        if rel == "docs/rules.md":
            for n, w in numbered_rules(text):
                scanned += 1
                if w > RULE_LIMIT:
                    bad.append(f"docs/rules.md: rule {n} has {w} words, limit {RULE_LIMIT}")
    if total > ALWAYS_ON_LIMIT:
        bad.insert(0, f"{' + '.join(ALWAYS_ON)}: {total} words, limit {ALWAYS_ON_LIMIT}")
    return scanned, bad


# ---------------------------------------------------------------- registry
@dataclass
class Check:
    name: str
    # (scanned, findings); scanned is a count, or a count followed by what it drew on.
    fn: Callable[[Ctx], tuple[int | str, list[str]]]

    @property
    def doc(self) -> str:
        return (self.fn.__doc__ or "").strip().splitlines()[0]


CHECKS = [
    Check("links", check_links),
    Check("leaks", check_leaks),
    Check("casebook-router", check_casebook_router),
    Check("skills", check_skills),
    Check("no-tracked-state", check_no_tracked_state),
    Check("framework-style", check_framework_style),
    Check("hooks", check_hooks),
    Check("law", check_law),
    Check("always-on-budget", check_always_on_budget),
]


def run(names: list[str], root: Path = ROOT) -> int:
    ctx = Ctx(root)
    selected = [c for c in CHECKS if not names or c.name in names]
    unknown = set(names) - {c.name for c in CHECKS}
    if unknown:
        print(f"unknown check(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    failed = 0
    for c in selected:
        scanned, bad = c.fn(ctx)
        if bad:
            failed += 1
            print(f"FAIL {c.name}: {len(bad)} finding(s), scanned {scanned}")
            for b in bad[:MAX_SHOWN]:
                print(f"     {b}")
            if len(bad) > MAX_SHOWN:
                print(f"     ... and {len(bad) - MAX_SHOWN} more")
        else:
            print(f"pass {c.name}: scanned {scanned}")
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    if "--list" in argv:
        for c in CHECKS:
            print(f"{c.name:18} {c.doc}")
        return 0
    root = Path(os.environ.get("YB_ROOT", ROOT))
    return run([a for a in argv if not a.startswith("-")], root)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
