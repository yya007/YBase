import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import checks  # noqa: E402
import envfile  # noqa: E402


@pytest.fixture
def work(tmp_path):
    root = tmp_path / "YBase"
    skip = shutil.ignore_patterns(".git", ".venv", ".ybase", ".env", "tmp", ".worktrees", "__pycache__", ".pytest_cache")

    def ignore(src, names):  # never copy the real working tree's kb/
        return set(skip(src, names)) | ({"kb"} if Path(src) == REPO else set())

    shutil.copytree(REPO, root, ignore=ignore)
    (root / "kb").mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def yb(root, *args, extra=None, check=True):
    env = {k: v for k, v in os.environ.items() if not k.startswith("YBASE_")}
    env["YB_ROOT"] = str(root)
    env["YBASE_PROFILE"] = "linux"
    env["YBASE_SCRATCH"] = str(root.parent / "scratch")
    env.update(extra or {})
    res = subprocess.run([str(root / "bin" / "ybase"), *args], env=env, cwd=root,
                         stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if check:
        assert res.returncode == 0, res.stdout + res.stderr
    return res


def test_kb_roots_default_is_local_kb(tmp_path):
    assert envfile.kb_roots(tmp_path, {}) == [tmp_path / "kb"]


def test_kb_roots_primary_then_extras_deduplicated(tmp_path):
    env = {"YBASE_KB_PRIMARY": "/a", "YBASE_KB_PATHS": "/b:/a:/c"}
    assert envfile.kb_roots(tmp_path, env) == [Path("/a"), Path("/b"), Path("/c")]


def test_init_copies_skeleton_without_overwriting(work, tmp_path):
    target = tmp_path / "newkb"
    target.mkdir()
    (target / "rules.md").write_text("mine\n", encoding="utf-8")
    yb(work, "kb", "init", str(target))
    for rel in ("repos.md", "rules.md", "memory/INDEX.md", "worklog/README.md",
                "research/README.md", "deny.list", "VERSION"):
        assert (target / rel).is_file(), rel
    assert "mine" in (target / "rules.md").read_text(encoding="utf-8")
    assert (target / "VERSION").read_text(encoding="utf-8").strip() == "1"


def test_primary_into_path_with_spaces(work, tmp_path):
    target = tmp_path / "My Vault" / "YBase"
    yb(work, "kb", "primary", str(target))
    out = subprocess.run(
        ["/bin/bash", "-c", f". {REPO}/tools/lib.sh; yb_env_get YBASE_KB_PRIMARY"],
        env={**os.environ, "YB_ROOT": str(work)}, capture_output=True, text=True, check=True)
    assert out.stdout == f"{target}\n"
    assert (target / "VERSION").is_file()


def test_add_and_remove_extra(work, tmp_path):
    a, b = tmp_path / "a b", tmp_path / "c"
    yb(work, "kb", "add", str(a))
    yb(work, "kb", "add", str(b))
    yb(work, "kb", "add", str(a))
    assert envfile.read_env(work)["YBASE_KB_PATHS"] == f"{a}:{b}"
    yb(work, "kb", "remove", str(a))
    assert envfile.read_env(work)["YBASE_KB_PATHS"] == str(b)


def test_list_reports_missing_root_and_exits_zero(work):
    res = yb(work, "kb", extra={"YBASE_KB_PATHS": "/nonexistent/kb"})
    assert "extra\t/nonexistent/kb\tmissing" in res.stdout.splitlines()
    assert f"primary\t{work}/kb\tno-skeleton" in res.stdout.splitlines()


def test_doctor_writes_kb_md_with_imports_only_for_existing_files(work, tmp_path):
    primary = tmp_path / "pkb"
    yb(work, "kb", "init", str(primary))
    yb(work, "doctor", extra={"YBASE_KB_PRIMARY": str(primary),
                              "YBASE_KB_PATHS": "/nonexistent/kb"})
    text = (work / ".ybase" / "KB.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert f"@{primary}/rules.md" in lines
    assert f"@{primary}/memory/INDEX.md" in lines
    assert f"- primary: `{primary}` (ok)" in lines
    assert "- extra: `/nonexistent/kb` (missing)" in lines
    assert not [ln for ln in lines if "/nonexistent/kb/memory/INDEX.md" in ln]


# Claude Code's import pattern: a path ends at the first unescaped whitespace.
IMPORT = re.compile(r"(?:^|\s)@((?:[^\s\\]|\\ )+)")


def test_doctor_escapes_spaces_in_kb_imports(work, tmp_path):
    primary = tmp_path / "my kb"
    yb(work, "kb", "init", str(primary))
    yb(work, "doctor", extra={"YBASE_KB_PRIMARY": str(primary)})
    text = (work / ".ybase" / "KB.md").read_text(encoding="utf-8")
    targets = [m.replace("\\ ", " ") for m in IMPORT.findall(text)]
    assert targets == [f"{primary}/rules.md", f"{primary}/memory/INDEX.md"]
    assert all(Path(t).is_file() for t in targets)


def _ctx_with_kbs(work, tmp_path, monkeypatch, extra_exists=True):
    primary, extra = tmp_path / "p", tmp_path / "x"
    primary.mkdir()
    (primary / "deny.list").write_text("# c\nsecretword\n", encoding="utf-8")
    monkeypatch.setenv("YBASE_KB_PRIMARY", str(primary))
    monkeypatch.setenv("YBASE_KB_PATHS", str(extra))
    if extra_exists:
        extra.mkdir()
        (extra / "deny.list").write_text("otherword\n", encoding="utf-8")
    return checks.Ctx(work)


def test_deny_list_from_every_kb(work, tmp_path, monkeypatch):
    ctx = _ctx_with_kbs(work, tmp_path, monkeypatch)
    hits = checks.leak_hits("x secretword otherword", checks.deny_patterns(ctx))
    assert len(hits) == 2
    assert all(h.startswith("private term (deny.list)") for h in hits)


def test_missing_kb_does_not_break_deny_patterns(work, tmp_path, monkeypatch):
    ctx = _ctx_with_kbs(work, tmp_path, monkeypatch, extra_exists=False)
    assert len(checks.deny_patterns(ctx)) == 1


def test_kb_content_is_never_tracked(work):
    (work / "kb" / "README.md").write_text("# kb\n", encoding="utf-8")
    (work / "kb" / "notes.md").write_text("private\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(work), "add", "-f", "kb/README.md", "kb/notes.md"], check=True)
    _, bad = checks.check_no_tracked_state(checks.Ctx(work))
    assert any(b.startswith("kb/notes.md") for b in bad)
    assert not any(b.startswith("kb/README.md") for b in bad)


def _no_ybase_env(monkeypatch):
    for key in [k for k in os.environ if k.startswith("YBASE_")]:
        monkeypatch.delenv(key)


def test_deny_list_reached_through_the_main_checkout_from_a_worktree(tmp_path, monkeypatch):
    _no_ybase_env(monkeypatch)
    kb = tmp_path / "private-kb"
    kb.mkdir()
    (kb / "deny.list").write_text("(?i)secretco\n", encoding="utf-8")
    main = tmp_path / "main"
    main.mkdir()
    git = ["git", "-C", str(main), "-c", "user.email=t@example.com", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], check=True)
    (main / ".gitignore").write_text(".env\n", encoding="utf-8")
    (main / ".env").write_text(f"YBASE_KB_PRIMARY={kb}\n", encoding="utf-8")
    subprocess.run([*git, "add", ".gitignore"], check=True)
    subprocess.run([*git, "commit", "-qm", "init"], check=True)
    wt = tmp_path / "wt"
    subprocess.run([*git, "worktree", "add", "-q", str(wt)], check=True, capture_output=True)
    (wt / "notes.md").write_text("made at SecretCo\n", encoding="utf-8")
    assert not (wt / ".env").exists()
    _, bad = checks.check_leaks(checks.Ctx(wt))
    assert any(b.startswith("notes.md:1: private term (deny.list)") for b in bad), bad


def test_deny_list_still_reads_a_worktree_of_its_own_env(tmp_path, monkeypatch):
    _no_ybase_env(monkeypatch)
    own, main_kb = tmp_path / "own-kb", tmp_path / "main-kb"
    for kb, term in ((own, "ownword"), (main_kb, "mainword")):
        kb.mkdir()
        (kb / "deny.list").write_text(term + "\n", encoding="utf-8")
    main = tmp_path / "main"
    (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
    (main / ".env").write_text(f"YBASE_KB_PRIMARY={main_kb}\n", encoding="utf-8")
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'wt'}\n", encoding="utf-8")
    (wt / ".env").write_text(f"YBASE_KB_PRIMARY={own}\n", encoding="utf-8")
    hits = checks.leak_hits("ownword mainword", checks.deny_patterns(checks.Ctx(wt)))
    assert len(hits) == 2, hits


def test_a_malformed_deny_line_is_a_finding_and_the_rest_still_apply(work, tmp_path, monkeypatch):
    _no_ybase_env(monkeypatch)
    kb = tmp_path / "pkb"
    kb.mkdir()
    (kb / "deny.list").write_text("# c\n(unclosed\nsecretword\n", encoding="utf-8")
    monkeypatch.setenv("YBASE_KB_PRIMARY", str(kb))
    (work / "notes.md").write_text("x secretword\n", encoding="utf-8")
    _, bad = checks.check_leaks(checks.Ctx(work))
    assert any(b.startswith(f"{kb / 'deny.list'}:2: not a valid regular expression") for b in bad), bad
    assert not any("(unclosed" in b for b in bad), bad  # the finding never repeats the private line
    assert any(b.startswith("notes.md:1: private term (deny.list)") for b in bad), bad
    assert len(checks.deny_patterns(checks.Ctx(work))) == 1


@pytest.mark.parametrize("bad", ["a{99999999999999999999}", "(" * 2000 + ")" * 2000],
                         ids=["overflow", "recursion"])
def test_a_deny_line_that_overflows_or_recurses_is_a_finding(work, tmp_path, monkeypatch, bad):
    # re.compile raises OverflowError or RecursionError here, not re.error.
    _no_ybase_env(monkeypatch)
    kb = tmp_path / "pkb"
    kb.mkdir()
    (kb / "deny.list").write_text(f"{bad}\nsecretword\n", encoding="utf-8")
    monkeypatch.setenv("YBASE_KB_PRIMARY", str(kb))
    (work / "notes.md").write_text("x secretword\n", encoding="utf-8")
    _, bad_found = checks.check_leaks(checks.Ctx(work))
    assert any(b.startswith(f"{kb / 'deny.list'}:1: not a valid regular expression") for b in bad_found), bad_found
    assert not any(bad[:20] in b for b in bad_found), bad_found
    assert any(b.startswith("notes.md:1: private term (deny.list)") for b in bad_found), bad_found


def test_parent_importer_escapes_a_space_in_the_clone_name(work, tmp_path):
    parent = tmp_path / "parent"
    parent.mkdir()
    clone = parent / "Y Base"
    work.rename(clone)
    yb(clone, "setup", "--parent-importer", extra={"HOME": str(tmp_path)})
    text = (parent / "CLAUDE.md").read_text(encoding="utf-8")
    targets = [m.replace("\\ ", " ") for m in IMPORT.findall(text)]
    assert targets == ["Y Base/CLAUDE.md"]
    assert (parent / targets[0]).is_file()


def test_env_header_examples_parse_as_written_when_uncommented(work, tmp_path):
    yb(work, "setup")
    header = (work / ".env").read_text(encoding="utf-8")
    examples = [ln[2:] for ln in header.splitlines() if re.match(r"# [A-Z][A-Z0-9_<>]*=", ln)]
    keys = {ln.split("=", 1)[0] for ln in examples}
    assert {"YBASE_PROFILE", "YBASE_SCRATCH", "YBASE_KB_PRIMARY", "YBASE_ALLOW_GATE",
            "YBASE_GUARD_READONLY_CHECKOUT", "YBASE_GUARD_PR_DRAFT"} <= keys
    values = {}
    for i, line in enumerate(examples):
        d = tmp_path / f"env{i}"
        d.mkdir()
        (d / ".env").write_text(line + "\n", encoding="utf-8")
        parsed = envfile.read_env(d)
        assert list(parsed) == [line.split("=", 1)[0]], line  # the key is valid as written
        value = next(iter(parsed.values()))
        assert value and "#" not in value and value == value.strip(), line
        values.update(parsed)
    for key in ("YBASE_ALLOW_GATE", "YBASE_GUARD_READONLY_CHECKOUT", "YBASE_GUARD_PR_DRAFT"):
        assert values[key] == "1", key


def _leaks_line(root, capsys):
    rc = checks.run(["leaks"], root)
    return rc, capsys.readouterr().out


@pytest.fixture
def clone(tmp_path):
    """A fresh clone of the committed tree: no `.env`, an empty `kb/`."""
    c = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(REPO), str(c)], check=True)
    return c


# Built by concatenation so no file in the tree holds the terms themselves.
TERM_A, TERM_B = "zq" + "termalpha", "zq" + "termbeta"


def test_leaks_reports_its_deny_list_sources(clone, tmp_path, monkeypatch, capsys):
    _no_ybase_env(monkeypatch)
    primary, extra = tmp_path / "p", tmp_path / "x"
    primary.mkdir()
    extra.mkdir()  # a KB with no deny.list is not a finding
    (primary / "deny.list").write_text(f"# c\n{TERM_A}\n{TERM_B}\n", encoding="utf-8")
    monkeypatch.setenv("YBASE_KB_PRIMARY", str(primary))
    monkeypatch.setenv("YBASE_KB_PATHS", str(extra))
    rc, out = _leaks_line(clone, capsys)
    assert rc == 0, out
    assert "pass leaks: scanned " in out and "deny list: 2 terms from 1 of 2 knowledge bases" in out, out
    (clone / "notes.md").write_text(f"x {TERM_A}\n", encoding="utf-8")
    rc, out = _leaks_line(clone, capsys)
    assert rc == 1 and "FAIL leaks:" in out and "deny list: 2 terms from 1 of 2 knowledge bases" in out, out


def test_a_fresh_clone_with_no_env_and_no_kb_content_passes(clone, monkeypatch, capsys):
    _no_ybase_env(monkeypatch)
    assert not (clone / ".env").exists()
    rc, out = _leaks_line(clone, capsys)
    assert rc == 0, out
    assert "deny list: 0 terms from 0 of 1 knowledge bases" in out, out
    shutil.rmtree(clone / "kb")  # the default kb/ missing, nothing configured: still not a finding
    rc, out = _leaks_line(clone, capsys)
    assert rc == 0, out


@pytest.mark.parametrize("where", ["environment", "env file"])
def test_a_configured_kb_that_is_missing_is_a_leaks_finding(work, tmp_path, monkeypatch, where):
    _no_ybase_env(monkeypatch)
    gone = tmp_path / "unplugged" / "kb"
    if where == "environment":
        monkeypatch.setenv("YBASE_KB_PRIMARY", str(gone))
    else:
        (work / ".env").write_text(f"YBASE_KB_PATHS={gone}\n", encoding="utf-8")
    _, bad = checks.check_leaks(checks.Ctx(work))
    assert any(b.startswith(f"{gone}: ") and "missing" in b for b in bad), bad


def test_an_unreadable_env_file_is_a_leaks_finding(work, monkeypatch):
    _no_ybase_env(monkeypatch)
    (work / ".env").write_bytes(b"YBASE_KB_PRIMARY=/x\n\xff\xfe\n")
    _, bad = checks.check_leaks(checks.Ctx(work))
    assert any(b.startswith(f"{work / '.env'}: cannot be read") for b in bad), bad


@pytest.mark.parametrize("kind", ["undecodable", "unreadable"])
def test_a_deny_list_that_cannot_be_read_is_a_leaks_finding(work, tmp_path, monkeypatch, kind):
    _no_ybase_env(monkeypatch)
    kb = tmp_path / "pkb"
    kb.mkdir()
    if kind == "undecodable":
        (kb / "deny.list").write_bytes(b"secret\xff\n")
    else:
        (kb / "deny.list").mkdir()  # reading it raises an OSError, whoever runs the test
    monkeypatch.setenv("YBASE_KB_PRIMARY", str(kb))
    _, bad = checks.check_leaks(checks.Ctx(work))
    assert any(b.startswith(f"{kb / 'deny.list'}: cannot be read") for b in bad), bad
