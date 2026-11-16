"""One gate for commits and CI: a single workflow, and no package build."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_one_workflow_runs_registry_tests_and_lint():
    workflows = sorted(p.name for p in (ROOT / ".github" / "workflows").iterdir())
    assert workflows == ["checks.yml"]
    text = (ROOT / ".github" / "workflows" / "checks.yml").read_text()
    for needle in (
        "tools/checks.py",
        "pytest",
        "ruff check",
        "tests/test_profile.sh",
        "ybase doctor --dry-run",
        "ubuntu-latest",
        "macos-latest",
    ):
        assert needle in text, needle


def test_no_package_build():
    lines = (ROOT / "pyproject.toml").read_text().splitlines()
    assert "[build-system]" not in [ln.strip() for ln in lines]
    assert not (ROOT / "src").exists()


def test_workflow_covers_python_floor_and_current():
    text = (ROOT / ".github" / "workflows" / "checks.yml").read_text()
    assert '"3.10"' in text and '"3.13"' in text
