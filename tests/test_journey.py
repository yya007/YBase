"""Whole user journeys across ybase commands, judged by what the user sees or has afterwards.

Everything lives in tmp_path and uses local git repos only (no network). Each journey builds
one set-up clone and asserts many things against it."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Same import syntax as Claude Code: a path ends at the first unescaped whitespace.
IMPORT = re.compile(r"(?:^|\s)@((?:[^\s\\]|\\ )+)")

# Built by concatenation so this file never contains the joined term.
TERM = "zq" + "priv" + "term"

TABLE_HEAD = "| Name | What it is | Remote | Hint |\n|---|---|---|---|\n"


def _env(home):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("YBASE_", "GH_", "GIT_")) and k not in ("CI", "YB_CI", "RUNNER_TEMP")}
    env.update(
        HOME=str(home), YBASE_PROFILE="linux",
        GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
        GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com",
    )
    return env


def sh(cwd, *cmd, env, stdin=None, check=True):
    res = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, input=stdin, capture_output=True,
                         text=True, stdin=None if stdin is not None else subprocess.DEVNULL, timeout=300)
    if check:
        assert res.returncode == 0, f"{cmd}\n{res.stdout}\n{res.stderr}"
    return res


def git(cwd, *args, env):
    return sh(cwd, "git", "-c", "commit.gpgsign=false", *args, env=env).stdout.strip()


def yb(clone, env, *args, check=False):
    res = sh(clone, "/bin/bash", clone / "bin" / "ybase", *args, env=env, check=False)
    if check:
        assert res.returncode == 0, f"ybase {args}\n{res.stdout}\n{res.stderr}"
    return res


def out(res):
    return res.stdout + res.stderr


def make_repo(path, env):
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main", env=env)
    (path / "README.md").write_text("hello\n")
    git(path, "add", "README.md", env=env)
    git(path, "commit", "-q", "-m", "init", env=env)
    return path


def clone_root(dest, env):
    """A clone of this checkout's committed tree. A detached or branchless ROOT is fine."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    sh(dest.parent, "git", "clone", "--quiet", ROOT, dest, env=env)
    return dest


def imports_of(doc):
    found = []
    for m in IMPORT.findall(doc.read_text()):
        imp = m.replace("\\ ", " ")
        target = Path(imp)
        found.append((imp, target if target.is_absolute() else doc.parent / imp))
    return found


@pytest.fixture
def world(tmp_path):
    """notes repo with a KB folder (path has a space), alpha-tool present, beta-site remote only,
    and a YBase clone set up against them."""
    (tmp_path / "fake-home").mkdir()
    env = _env(tmp_path / "fake-home")
    notes = make_repo(tmp_path / "notes", env)
    kb = notes / "Home KB"
    root = tmp_path / "repos"
    root.mkdir()
    alpha = make_repo(root / "alpha-tool", env)
    seed = make_repo(tmp_path / "beta-seed", env)
    bare = tmp_path / "beta-site.git"
    sh(tmp_path, "git", "clone", "--quiet", "--bare", seed, bare, env=env)
    clone = clone_root(tmp_path / "yb" / "YBase", env)
    res = yb(clone, env, "setup", "--non-interactive", "--kb", kb, "--repos-root", root)
    assert res.returncode == 0, out(res)
    return dict(tmp=tmp_path, env=env, notes=notes, kb=kb, root=root, alpha=alpha, bare=bare, clone=clone)


def write_repos(w):
    (w["kb"] / "repos.md").write_text(
        "# Repos\n\n" + TABLE_HEAD
        + "| alpha-tool | a command-line tool | | read its README first |\n"
        + f"| beta-site | a website | {w['bare']} | |\n")


def test_first_day_with_an_external_kb_and_two_repos(world):
    w = world
    clone, env, kb, root = w["clone"], w["env"], w["kb"], w["root"]
    assert (kb / "rules.md").is_file() and (kb / "memory" / "INDEX.md").is_file()
    assert (kb / "VERSION").read_text().strip() == "1"

    write_repos(w)
    assert yb(clone, env, "repos", "render").returncode == 0
    lines = [ln for ln in (clone / ".ybase" / "REPOS.md").read_text().splitlines() if ln.startswith("- ")]
    assert len(lines) == 2, lines
    alpha_line = next(ln for ln in lines if "**alpha-tool**" in ln)
    beta_line = next(ln for ln in lines if "**beta-site**" in ln)
    assert f"`{root / 'alpha-tool'}` (present)" in alpha_line
    assert f"`{root / 'beta-site'}` (missing; clone: `{w['bare']}`)" in beta_line

    res = yb(clone, env, "repos", "clone", "beta-site")
    assert res.returncode == 0, out(res)
    assert (root / "beta-site" / "README.md").is_file()
    assert git(root / "beta-site", "remote", "get-url", "origin", env=env) == str(w["bare"])
    assert yb(clone, env, "repos", "render").returncode == 0
    text = (clone / ".ybase" / "REPOS.md").read_text()
    assert f"`{root / 'beta-site'}` (present)" in text and "(missing" not in text

    before = git(w["alpha"], "branch", "--show-current", env=env)
    res = yb(clone, env, "wt", "feat/feature-x", "--repo", "alpha-tool")
    assert res.returncode == 0, out(res)
    listing = git(w["alpha"], "worktree", "list", "--porcelain", env=env)
    paths = [ln[len("worktree "):] for ln in listing.splitlines() if ln.startswith("worktree ")]
    linked = [p for p in paths if Path(p).resolve() != w["alpha"].resolve()]
    assert len(linked) == 1 and Path(linked[0]).is_dir(), listing
    assert Path(linked[0]).resolve() == (w["alpha"] / ".worktrees" / "feat-feature-x").resolve()
    assert git(w["alpha"], "status", "--porcelain", env=env) == ""
    assert git(Path(linked[0]), "branch", "--show-current", env=env) == "feat/feature-x"
    assert git(w["alpha"], "branch", "--show-current", env=env) == before == "main"

    for doc in (clone / "CLAUDE.md", clone / ".ybase" / "KB.md", clone / ".ybase" / "MACHINE.md"):
        found = imports_of(doc)
        assert found, f"{doc.name} has no @ lines"
        for imp, target in found:
            assert target.is_file(), f"{doc.name} imports missing file {imp}"
    kb_imports = [Path(t).resolve() for _, t in imports_of(clone / ".ybase" / "KB.md")]
    assert (kb / "rules.md").resolve() in kb_imports
    assert (kb / "memory" / "INDEX.md").resolve() in kb_imports

    assert git(clone, "status", "--porcelain", env=env) == ""
    tracked = git(clone, "ls-files", env=env).splitlines()
    assert not [t for t in tracked if "Home KB" in t or t in ("repos.md", "rules.md", "deny.list")]
    assert "Home KB" not in git(clone, "ls-files", "--others", "--exclude-standard", env=env)

    res = yb(clone, env, "check")
    assert res.returncode == 0, out(res)


def hook(clone, env, command, cwd):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)})
    henv = dict(env, GH_REPO="", GH_HOST="")
    return sh(cwd, sys.executable, clone / ".claude" / "hooks" / "leak_hook.py", env=henv,
              stdin=payload, check=False)


def test_a_private_term_is_refused_everywhere_it_could_be_published(world):
    w = world
    clone, env, kb = w["clone"], w["env"], w["kb"]
    (kb / "deny.list").write_text(f"# private\n{TERM}\n")

    for cwd in (clone, w["alpha"]):
        res = hook(clone, env, f'git commit -m "fix {TERM}"', cwd)
        assert res.returncode == 2, f"cwd={cwd}\n{out(res)}"
        assert "private term" in res.stderr, out(res)
        assert "private term (deny.list)" in res.stderr, res.stderr  # the denial says which list refused it
    res = hook(clone, env, f'LEAK_AUTHORIZED=1 git commit -m "fix {TERM}"', clone)
    assert res.returncode == 0, out(res)
    res = hook(clone, env, 'git commit -m "fix the parser"', clone)
    assert res.returncode == 0, out(res)
    assert hook(clone, env, 'git commit -m "fix the parser"', w["alpha"]).returncode == 0

    (clone / "docs" / "note.md").write_text(f"remember {TERM}\n")
    git(clone, "add", "docs/note.md", env=env)
    res = yb(clone, env, "check", "leaks")
    assert res.returncode != 0, out(res)
    assert "docs/note.md" in out(res), out(res)
    git(clone, "rm", "-q", "-f", "docs/note.md", env=env)
    res = yb(clone, env, "check", "leaks")
    assert res.returncode == 0, out(res)

    (kb / "memory" / "INDEX.md").write_text(f"- a lesson about {TERM}\n")
    res = yb(clone, env, "check", "leaks")
    assert res.returncode == 0, out(res)


def test_a_second_machine_shares_the_kb_but_not_the_paths(tmp_path):
    (tmp_path / "fake-home").mkdir()
    env = _env(tmp_path / "fake-home")
    kb = tmp_path / "shared kb"
    clones, roots = [], []
    for n in ("one", "two"):
        root = tmp_path / f"machine-{n}" / "repos"
        root.mkdir(parents=True)
        clone = clone_root(tmp_path / f"machine-{n}" / "YBase", env)
        res = yb(clone, env, "setup", "--non-interactive", "--kb", kb, "--repos-root", root)
        assert res.returncode == 0, out(res)
        clones.append(clone)
        roots.append(root)
    (kb / "repos.md").write_text(
        "# Repos\n\n" + TABLE_HEAD + "| alpha-tool | a tool | | |\n| beta-site | a site | | |\n")
    texts = []
    for clone, root in zip(clones, roots):
        assert yb(clone, env, "repos", "render").returncode == 0
        text = (clone / ".ybase" / "REPOS.md").read_text()
        texts.append(text)
        assert f"`{root / 'alpha-tool'}`" in text and f"`{root / 'beta-site'}`" in text
    names = [sorted(re.findall(r"\*\*([\w-]+)\*\*", t)) for t in texts]
    assert names[0] == names[1] == ["alpha-tool", "beta-site"]
    assert texts[0] != texts[1]
    assert str(roots[1]) not in texts[0] and str(roots[0]) not in texts[1]

    blob = "\n".join(p.read_text(errors="replace") for p in kb.rglob("*") if p.is_file())
    for clone, root in zip(clones, roots):
        assert str(root) not in blob and str(clone) not in blob
        for line in (clone / ".env").read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                assert line not in blob, line


def test_update_then_migrate_a_kb_layout_change(tmp_path):
    (tmp_path / "fake-home").mkdir()
    env = _env(tmp_path / "fake-home")
    seed = clone_root(tmp_path / "seed", env)
    git(seed, "checkout", "-q", "-B", "main", env=env)
    upstream = tmp_path / "upstream.git"
    sh(tmp_path, "git", "clone", "--quiet", "--bare", seed, upstream, env=env)
    machine, pusher = tmp_path / "machine", tmp_path / "pusher"
    for d in (machine, pusher):
        sh(tmp_path, "git", "clone", "--quiet", upstream, d, env=env)
    res = yb(machine, env, "setup", "--non-interactive")
    assert res.returncode == 0, out(res)
    kb = machine / "kb"
    assert (kb / "VERSION").read_text().strip() == "1"

    (pusher / "templates" / "kb" / "VERSION").write_text("2\n")
    mig = pusher / "tools" / "kb_migrate.py"
    src = mig.read_text()
    old = "Callable[[Path], None]]] = {}"
    new = ('Callable[[Path], None]]] = {\n    1: ("add MIGRATED.md to the KB", '
           'lambda kb: (kb / "MIGRATED.md").write_text("done\\n", encoding="utf-8")),\n}')
    assert old in src
    mig.write_text(src.replace(old, new))
    assert mig.read_text() != src
    git(pusher, "add", "templates/kb/VERSION", "tools/kb_migrate.py", env=env)
    git(pusher, "commit", "-q", "-m", "kb layout 2", env=env)
    git(pusher, "push", "-q", env=env)

    head = git(machine, "rev-parse", "HEAD", env=env)
    res = yb(machine, env, "update")
    assert res.returncode == 0, out(res)
    assert "kb layout 2" in res.stdout, out(res)
    for p in ("templates/kb/VERSION", "tools/kb_migrate.py"):
        assert f"changes what runs on this machine: {p}" in res.stdout, out(res)
    assert git(machine, "rev-parse", "HEAD", env=env) == head

    # Upstream moves again after the user looked. --apply must merge what was shown, no more.
    shown = git(upstream, "rev-parse", "main", env=env)
    (pusher / "LATER.txt").write_text("published after the user looked\n")
    git(pusher, "add", "LATER.txt", env=env)
    git(pusher, "commit", "-q", "-m", "a later commit", env=env)
    git(pusher, "push", "-q", env=env)
    assert git(upstream, "rev-parse", "main", env=env) != shown

    res = yb(machine, env, "update", "--apply")
    assert res.returncode == 0, out(res)
    assert git(machine, "rev-parse", "HEAD", env=env) == shown
    assert not (machine / "LATER.txt").exists()
    assert "== knowledge bases" in res.stdout.splitlines(), out(res)
    assert "would run 1 -> 2: add MIGRATED.md to the KB" in res.stdout, out(res)
    assert (kb / "VERSION").read_text().strip() == "1"
    assert not (kb / "MIGRATED.md").exists()

    res = yb(machine, env, "doctor")
    assert res.returncode == 0, out(res)
    warn = [ln for ln in res.stderr.splitlines() if ln.startswith("WARN") and "layout version" in ln]
    assert len(warn) == 1 and "kb migrate" in warn[0] and "is at layout version 1, current is 2" in warn[0], out(res)

    res = yb(machine, env, "kb", "migrate")
    assert res.returncode == 0, out(res)
    assert (kb / "VERSION").read_text().strip() == "2"
    assert (kb / "MIGRATED.md").is_file()
    res = yb(machine, env, "kb", "migrate")
    assert res.returncode == 0 and "is up to date (layout version 2)" in res.stdout, out(res)
    res = yb(machine, env, "doctor")
    assert res.returncode == 0, out(res)
    assert "layout version" not in out(res) and "kb migrate" not in out(res), out(res)
    assert git(machine, "status", "--porcelain", env=env) == ""


def test_a_kb_that_disappears_is_loud_but_not_fatal(world):
    w = world
    clone, env, kb = w["clone"], w["env"], w["kb"]
    gone = kb.with_name("Home KB.away")
    kb.rename(gone)

    res = yb(clone, env, "kb")
    assert res.returncode == 0, out(res)
    row = next(ln for ln in res.stdout.splitlines() if str(kb) in ln)
    assert row.split("\t")[0] == "primary" and row.split("\t")[-1] == "missing", res.stdout

    res = yb(clone, env, "doctor")
    assert res.returncode == 0, out(res)
    assert any(ln.startswith("WARN") and "is missing" in ln and str(kb) in ln
               for ln in res.stderr.splitlines()), out(res)
    kb_md = clone / ".ybase" / "KB.md"
    for imp, target in imports_of(kb_md):
        assert target.is_file(), f"KB.md imports missing file {imp}"
    res = yb(clone, env, "check", "leaks")
    assert res.returncode != 0, out(res)
    assert "missing" in out(res) and str(kb) in out(res), out(res)

    res = yb(clone, env, "kb", "migrate")
    assert res.returncode == 1, out(res)
    assert "is missing" in res.stderr, out(res)
    assert "kb init" not in out(res), out(res)

    gone.rename(kb)
    res = yb(clone, env, "doctor")
    assert res.returncode == 0, out(res)
    assert "is missing" not in out(res), out(res)
    kb_imports = [Path(t).resolve() for _, t in imports_of(kb_md)]
    assert (kb / "rules.md").resolve() in kb_imports
    res = yb(clone, env, "check")
    assert res.returncode == 0, out(res)


def test_everything_still_works_from_a_path_with_spaces_and_a_linked_worktree(tmp_path):
    (tmp_path / "fake-home").mkdir()
    env = _env(tmp_path / "fake-home")
    clone = clone_root(tmp_path / "my home" / "Y Base", env)
    kb = tmp_path / "some kb"
    res = yb(clone, env, "setup", "--non-interactive", "--kb", kb)
    assert res.returncode == 0, out(res)
    (kb / "deny.list").write_text(f"{TERM}\n")
    linked = tmp_path / "my home" / "linked tree"
    git(clone, "worktree", "add", "-q", "-b", "linked-work", linked, env=env)

    res = yb(linked, env, "check")
    assert res.returncode == 0, out(res)
    res = yb(linked, env, "check", "leaks")
    assert res.returncode == 0, out(res)
    assert re.search(r"deny list: 1 terms? from 1 of \d+ knowledge bases", res.stdout), out(res)

    (linked / "docs" / "note.md").write_text(f"x {TERM}\n")
    git(linked, "add", "docs/note.md", env=env)
    res = yb(linked, env, "check", "leaks")
    assert res.returncode != 0 and "docs/note.md" in out(res), out(res)
