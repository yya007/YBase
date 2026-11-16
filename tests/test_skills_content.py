from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent / ".claude" / "skills"
EXPECTED = {
    "adopt", "cleanup-worktrees", "codex-delegation", "consolidate-branch", "cross-repo-issues",
    "git-forward", "gpu-census", "harvest", "land-pr", "proofread", "retro", "review-pr",
    "review-skill", "session-check", "session-closeout", "session-scope",
}


def test_skill_set_is_exact():
    assert {p.name for p in SKILLS.iterdir() if p.is_dir()} == EXPECTED
