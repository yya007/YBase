import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import kb_migrate  # noqa: E402

sys.path.insert(0, str(REPO / "tests"))
from test_kb import work, yb  # noqa: E402,F401


def make_kb(tmp_path, version):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "memory").mkdir()
    (kb / "memory" / "INDEX.md").write_text("# index\n", encoding="utf-8")
    if version is not None:
        (kb / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    return kb


def version_of(kb):
    return (kb / "VERSION").read_text(encoding="utf-8").strip()


def inject(monkeypatch, current, steps):
    monkeypatch.setattr(kb_migrate, "CURRENT", current)
    monkeypatch.setattr(kb_migrate, "MIGRATIONS", steps)


def test_up_to_date_kb_is_left_alone(tmp_path, capsys):
    kb = make_kb(tmp_path, kb_migrate.CURRENT)
    assert kb_migrate.migrate(kb, dry_run=False) == 0
    assert "up to date" in capsys.readouterr().out
    assert version_of(kb) == str(kb_migrate.CURRENT)


def test_steps_run_in_order_and_version_advances_after_each(tmp_path, monkeypatch):
    kb = make_kb(tmp_path, 1)
    seen = []

    def step(n):
        def run(path):
            seen.append((n, version_of(path)))
        return run

    inject(monkeypatch, 3, {1: ("one to two", step(1)), 2: ("two to three", step(2))})
    assert kb_migrate.migrate(kb, dry_run=False) == 0
    assert seen == [(1, "1"), (2, "2")]
    assert version_of(kb) == "3"


def test_dry_run_changes_nothing(tmp_path, monkeypatch, capsys):
    kb = make_kb(tmp_path, 1)
    called = []
    inject(monkeypatch, 3, {1: ("first change", lambda p: called.append(1)),
                            2: ("second change", lambda p: called.append(2))})
    assert kb_migrate.migrate(kb, dry_run=True) == 0
    out = capsys.readouterr().out
    assert "first change" in out and "second change" in out
    assert called == []
    assert version_of(kb) == "1"


def test_a_failing_step_stops_and_keeps_the_last_finished_version(tmp_path, monkeypatch, capsys):
    kb = make_kb(tmp_path, 1)

    def boom(path):
        raise RuntimeError("disk on fire")

    inject(monkeypatch, 3, {1: ("ok", lambda p: None), 2: ("bad", boom)})
    assert kb_migrate.migrate(kb, dry_run=False) == 1
    assert version_of(kb) == "2"
    assert "disk on fire" in capsys.readouterr().err


def test_a_newer_kb_is_refused(tmp_path, capsys):
    kb = make_kb(tmp_path, 9)
    assert kb_migrate.migrate(kb, dry_run=False) == 1
    assert "update YBase" in capsys.readouterr().err
    assert version_of(kb) == "9"


@pytest.mark.parametrize("content", [None, "abc"])
def test_missing_or_garbled_version_is_refused(tmp_path, capsys, content):
    kb = make_kb(tmp_path, content)
    assert kb_migrate.migrate(kb, dry_run=False) == 1
    assert 'ybase kb init "' in capsys.readouterr().err
    if content is None:
        assert not (kb / "VERSION").exists()
    else:
        assert version_of(kb) == "abc"


def test_a_gap_in_the_steps_is_refused_before_anything_runs(tmp_path, monkeypatch):
    kb = make_kb(tmp_path, 1)
    called = []
    inject(monkeypatch, 3, {2: ("two to three", lambda p: called.append(2))})
    assert kb_migrate.migrate(kb, dry_run=False) == 1
    assert called == []
    assert version_of(kb) == "1"


def test_cli_defaults_to_the_primary_kb(work, tmp_path):  # noqa: F811
    kb = make_kb(tmp_path, 1)
    res = yb(work, "kb", "migrate", "--dry-run", extra={"YBASE_KB_PRIMARY": str(kb)})
    assert "up to date" in res.stdout
    assert version_of(kb) == "1"


def test_doctor_warns_about_a_kb_layout_version(work, tmp_path):  # noqa: F811
    old = make_kb(tmp_path, 0)
    res = yb(work, "doctor", extra={"YBASE_KB_PRIMARY": str(old)})
    assert f'ybase kb migrate "{old}"' in res.stdout + res.stderr
    (old / "VERSION").write_text("9\n", encoding="utf-8")
    res = yb(work, "doctor", extra={"YBASE_KB_PRIMARY": str(old)})
    assert "update YBase" in res.stdout + res.stderr


def test_a_directory_that_is_not_a_kb_is_refused(tmp_path, capsys):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "VERSION").write_text("1\n", encoding="utf-8")  # a VERSION file alone is not a KB
    assert kb_migrate.migrate(folder, dry_run=False) == 1
    assert "does not look like a knowledge base" in capsys.readouterr().err
    assert version_of(folder) == "1"


def test_a_missing_folder_is_not_told_to_init(tmp_path, capsys):
    gone = tmp_path / "unmounted disk" / "kb"
    assert kb_migrate.migrate(gone, dry_run=False) == 1
    err = capsys.readouterr().err
    assert "missing" in err
    assert "kb init" not in err
    assert not gone.exists()


def test_a_mistyped_flag_is_refused_and_nothing_runs(work, tmp_path):  # noqa: F811
    kb = make_kb(tmp_path, 0)
    res = yb(work, "kb", "migrate", "--dryrun", str(kb), check=False)
    assert res.returncode == 2, res.stdout + res.stderr
    assert "usage: ybase kb migrate" in res.stderr
    assert version_of(kb) == "0"


def test_two_paths_are_refused(work, tmp_path):  # noqa: F811
    kb = make_kb(tmp_path, 0)
    res = yb(work, "kb", "migrate", str(kb), str(tmp_path), check=False)
    assert res.returncode == 2, res.stdout + res.stderr
    assert "usage: ybase kb migrate" in res.stderr
    assert version_of(kb) == "0"
    assert kb_migrate.main(["--dryrun", str(kb)]) == 2
    assert kb_migrate.main([str(kb), str(kb)]) == 2
    assert version_of(kb) == "0"
