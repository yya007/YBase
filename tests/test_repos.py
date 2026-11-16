import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import repos  # noqa: E402

TABLE = (
    "# Repos\n\n| Name | What it is | Remote | Hint |\n|---|---|---|---|\n"
    "| my-repo.js | a tool | git@example.com:me/my-repo.js.git | read its AGENTS.md first |\n"
    "| Notes | a vault | | |\n"
)


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "YBase"
    r.mkdir()
    return r


@pytest.fixture
def kb(tmp_path):
    k = tmp_path / "kb"
    k.mkdir()
    return k


@pytest.fixture
def work(tmp_path):
    root = tmp_path / "my home" / "YBase"
    skip = shutil.ignore_patterns(".git", ".venv", ".ybase", ".env", "tmp", ".worktrees", "__pycache__", ".pytest_cache")

    def ignore(src, names):
        return set(skip(src, names)) | ({"kb"} if Path(src) == REPO else set())

    shutil.copytree(REPO, root, ignore=ignore)
    (root / "kb").mkdir()
    return root


def yb(root, *args, extra=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("YBASE_")}
    env["YB_ROOT"] = str(root)
    env.update(extra or {})
    return subprocess.run([str(root / "bin" / "ybase"), *args], env=env, cwd=root,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True)


def test_parse_reads_rows_and_ignores_other_tables(kb):
    (kb / "repos.md").write_text(TABLE + "\n| A | B |\n|---|---|\n| x | y |\n", encoding="utf-8")
    assert repos.parse_repos(kb) == [
        repos.Repo("my-repo.js", "a tool", "git@example.com:me/my-repo.js.git",
                   "read its AGENTS.md first", ""),
        repos.Repo("Notes", "a vault", "", "", ""),
    ]


def test_missing_repos_md_is_empty(kb):
    assert repos.parse_repos(kb) == []


def test_commented_example_is_ignored(kb):
    (kb / "repos.md").write_text(
        "| Name | What it is | Remote | Hint |\n|---|---|---|---|\n<!--\n| ghost | x | | |\n-->\n",
        encoding="utf-8")
    assert repos.parse_repos(kb) == []


def test_env_key_replaces_invalid_characters():
    assert repos.env_key("my-repo.js") == "YBASE_REPO_PATH_MY_REPO_JS"


def test_path_defaults_to_repos_root_then_override(root):
    r = repos.Repo("my-repo.js", "", "", "", "")
    assert repos.repo_path(r, root, {}) == root.parent / "my-repo.js"
    assert repos.repo_path(r, root, {"YBASE_REPOS_ROOT": "/srv/My Repos"}) == Path("/srv/My Repos/my-repo.js")
    assert repos.repo_path(r, root, {"YBASE_REPO_PATH_MY_REPO_JS": "/x y/z"}) == Path("/x y/z")


def test_pointer_for_missing_repo_names_the_remote(root, kb):
    (kb / "repos.md").write_text(TABLE, encoding="utf-8")
    text = repos.render_pointers(repos.parse_repos(kb), root, {"YBASE_REPOS_ROOT": "/nowhere"})
    assert ("- **my-repo.js**: a tool. Path: `/nowhere/my-repo.js` "
            "(missing; clone: `git@example.com:me/my-repo.js.git`). read its AGENTS.md first") in text
    assert "- **Notes**: a vault. Path: `/nowhere/Notes` (missing; clone: ``)." not in text
    assert "- **Notes**: a vault. Path: `/nowhere/Notes` (missing; no remote recorded)." in text


def test_pointer_for_present_repo_omits_empty_hint(root, tmp_path):
    (tmp_path / "Here").mkdir()
    text = repos.render_pointers([repos.Repo("Here", "x", "", "", "")], root, {"YBASE_REPOS_ROOT": str(tmp_path)})
    assert f"- **Here**: x. Path: `{tmp_path}/Here` (present).\n" in text


def test_area_files_are_read_and_collapsed_past_limit(root, kb):
    (kb / "repos").mkdir()
    rows = "".join(f"| r{i} | w | | |\n" for i in range(21))
    (kb / "repos" / "web.md").write_text("| Name | What it is | Remote | Hint |\n|---|---|---|---|\n" + rows,
                                         encoding="utf-8")
    (kb / "repos.md").write_text(TABLE, encoding="utf-8")
    found = repos.parse_repos(kb)
    assert len(found) == 23 and found[-1].area == "web"
    text = repos.render_pointers(found, root, {"YBASE_KB_PRIMARY": str(kb)})
    assert f"- Area **web**: 21 repos, listed in `{kb}/repos/web.md`" in text
    assert "**r0**" not in text and "**Notes**" in text


def test_find_is_case_insensitive_and_prefers_primary(root, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for k, what in ((a, "from a"), (b, "from b")):
        k.mkdir()
        (k / "repos.md").write_text(
            f"| Name | What it is | Remote | Hint |\n|---|---|---|---|\n| Tool | {what} | | |\n", encoding="utf-8")
    env = {"YBASE_KB_PRIMARY": str(a), "YBASE_KB_PATHS": str(b)}
    assert repos.find("tOOL", root, env).what == "from a"
    assert repos.find("nope", root, env) is None


def test_cli_path_unknown_exits_1(work):
    res = yb(work, "repos", "path", "nope")
    assert res.returncode == 1 and "nope" in res.stderr


def test_cli_render_writes_file_when_root_has_spaces(work):
    (work / "kb" / "repos.md").write_text(TABLE, encoding="utf-8")
    res = yb(work, "repos", "render")
    assert res.returncode == 0, res.stderr
    text = (work / ".ybase" / "REPOS.md").read_text(encoding="utf-8")
    assert "- **my-repo.js**: a tool. Path: `" in text
    listing = yb(work, "repos")
    assert "my-repo.js\t" in listing.stdout and "missing" in listing.stdout


def test_cli_clone_from_local_remote_and_error_paths(work, tmp_path):
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", str(seed)], check=True)
    subprocess.run(["git", "-C", str(seed), "-c", "user.name=t", "-c", "user.email=t@e.x",
                    "commit", "-q", "--allow-empty", "-m", "i"], check=True)
    subprocess.run(["git", "-C", str(seed), "push", "-q", str(remote), "HEAD:refs/heads/main"], check=True)
    (work / "kb" / "repos.md").write_text(
        TABLE.replace("git@example.com:me/my-repo.js.git", str(remote)), encoding="utf-8")
    extra = {"YBASE_REPOS_ROOT": str(tmp_path / "clones")}
    (tmp_path / "clones").mkdir()
    assert yb(work, "repos", "clone", "Notes", extra=extra).returncode == 1  # no remote
    assert yb(work, "repos", "clone", "nope", extra=extra).returncode == 1
    res = yb(work, "repos", "clone", "my-repo.js", extra=extra)
    assert res.returncode == 0, res.stderr
    assert (tmp_path / "clones" / "my-repo.js" / ".git").exists()
    assert yb(work, "repos", "clone", "my-repo.js", extra=extra).returncode == 0  # already present


def test_rows_appended_to_the_shipped_template_are_read(work):
    """`kb init` writes the template, whose example row sits in an HTML comment after the
    separator; rows a user appends after that comment are still part of the table."""
    assert yb(work, "kb", "init").returncode == 0
    path = work / "kb" / "repos.md"
    with path.open("a", encoding="utf-8") as f:
        f.write("| alpha | first tool | git@example.com:me/alpha.git | |\n")
        f.write("| beta | second tool | | read its README |\n")
    assert [r.name for r in repos.parse_repos(work / "kb")] == ["alpha", "beta"]
    listing = yb(work, "repos")
    assert "alpha\t" in listing.stdout and "beta\t" in listing.stdout
    assert yb(work, "repos", "path", "beta").returncode == 0


def test_blank_lines_inside_a_table_do_not_end_it(kb):
    (kb / "repos.md").write_text(
        "| Name | What it is | Remote | Hint |\n|---|---|---|---|\n| a | x | | |\n\n| b | y | | |\n"
        "\nSome prose.\n| c | z | | |\n", encoding="utf-8")
    assert [r.name for r in repos.parse_repos(kb)] == ["a", "b"]


def test_a_following_table_after_a_blank_line_is_not_read_as_rows(kb):
    (kb / "repos.md").write_text(TABLE + "\n| A | B |\n|---|---|\n| x | y |\n", encoding="utf-8")
    assert [r.name for r in repos.parse_repos(kb)] == ["my-repo.js", "Notes"]


def test_header_without_separator_keeps_the_first_row(kb):
    (kb / "repos.md").write_text(
        "| Name | What it is | Remote | Hint |\n| a | x | | |\n| b | y | | |\n", encoding="utf-8")
    assert [r.name for r in repos.parse_repos(kb)] == ["a", "b"]


@pytest.fixture
def clone_env(tmp_path, monkeypatch):
    root = tmp_path / "YBase"
    (root / "kb").mkdir(parents=True)
    for k in list(os.environ):
        if k.startswith("YBASE_"):
            monkeypatch.delenv(k)
    monkeypatch.setenv("YB_ROOT", str(root))
    monkeypatch.setenv("YBASE_REPOS_ROOT", str(tmp_path / "clones"))
    (tmp_path / "clones").mkdir()
    return root


def test_clone_treats_a_remote_starting_with_dash_as_a_remote(clone_env, tmp_path, monkeypatch, capsys):
    remote = tmp_path / "-dash.git"
    seed = tmp_path / "seed"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", str(seed)], check=True)
    subprocess.run(["git", "-C", str(seed), "-c", "user.name=t", "-c", "user.email=t@e.x",
                    "commit", "-q", "--allow-empty", "-m", "i"], check=True)
    subprocess.run(["git", "-C", str(seed), "push", "-q", str(remote), "HEAD:refs/heads/main"], check=True)
    (clone_env / "kb" / "repos.md").write_text(
        "| Name | What it is | Remote | Hint |\n|---|---|---|---|\n| dash | x | -dash.git | |\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert repos.main(["clone", "dash"]) == 0
    assert (tmp_path / "clones" / "dash" / ".git").exists()


def test_clone_without_git_is_a_clean_error(clone_env, tmp_path, monkeypatch, capsys):
    (clone_env / "kb" / "repos.md").write_text(
        "| Name | What it is | Remote | Hint |\n|---|---|---|---|\n| r | x | git@example.com:me/r.git | |\n",
        encoding="utf-8")
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    assert repos.main(["clone", "r"]) == 1
    assert "git" in capsys.readouterr().err
