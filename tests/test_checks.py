"""Tests for tools/checks.py. Every check is shown to fire on a planted defect,
not only to pass on a clean tree. Run: python3 -m unittest discover tests"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import checks  # noqa: E402

CASE_MD = """---
name: demo
summary: a demo case
stages: [literature]
notes_dir: literature/papers
catalog: literature/CATALOG.md
note_required_keys: [title, url]
---
# Case: demo
"""
NOTE = "---\ntitle: A paper\nurl: https://arxiv.org/abs/0000.00000\n---\n# A paper\n"
MEM_INDEX = "# router\n## G -> [`g.md`](g.md)\n**Covers:** things\n"
MEM_GROUP = "# g\n<!-- BEGIN TRIGGERS -->\n- `a-lesson` - when\n<!-- END TRIGGERS -->\n\n## a-lesson\nbody\n"


class Repo:
    """A throwaway repository with one valid case, one note and one casebook group."""

    def __init__(self, git: bool = False):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.write("README.md", "# demo\nSee [the case](cases/demo/CASE.md).\n")
        self.write("cases/demo/CASE.md", CASE_MD)
        self.write("cases/demo/literature/papers/a-paper.md", NOTE)
        self.write("cases/demo/literature/CATALOG.md", "| [a-paper](papers/a-paper.md) |\n")
        self.write("docs/casebook/INDEX.md", MEM_INDEX)
        self.write("docs/casebook/g.md", MEM_GROUP)
        if git:
            for cmd in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"],
                        ["add", "-A"], ["commit", "-qm", "init"]):
                subprocess.run(["git", "-C", str(self.root), *cmd], check=True, capture_output=True)

    def write(self, rel: str, text: str):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def run(self, fn):
        return fn(checks.Ctx(self.root))


class CleanTree(unittest.TestCase):
    def test_every_check_passes_on_a_clean_tree_and_scans_something(self):
        r = Repo(git=True)
        for c in checks.CHECKS:
            scanned, bad = r.run(c.fn)
            self.assertEqual(bad, [], c.name)
        self.assertGreater(r.run(checks.check_links)[0], 0)
        self.assertGreater(r.run(checks.check_casebook_router)[0], 0)


class Fires(unittest.TestCase):
    def test_links_broken(self):
        r = Repo()
        r.write("docs/x.md", "[gone](nope.md)\n")
        self.assertTrue(any("nope.md" in b for b in r.run(checks.check_links)[1]))

    def test_links_ignore_code_and_urls(self):
        r = Repo()
        r.write("docs/x.md", "`[a](b.md)`\n[web](https://example.com)\n```\n[c](d.md)\n```\n")
        self.assertEqual(r.run(checks.check_links)[1], [])

    def test_leaks_secret_and_path_and_email(self):
        r = Repo()
        # Built by concatenation so this file does not itself trip the repo's leak scan.
        r.write("x.md", "key AKIA" + "ABCDEFGHIJKLMNOP\npath /ho" + "me/alice/x\nmail bob" + "@corp.io\n"
                "ok you@example.com\n")
        bad = r.run(checks.check_leaks)[1]
        self.assertEqual(len(bad), 3, bad)

    def test_leaks_deny_list(self):
        r = Repo()
        r.write("kb/deny.list", "# c\n(?i)secretco\n")
        r.write("x.md", "made at SecretCo\n")
        self.assertTrue(any("deny.list" in b for b in r.run(checks.check_leaks)[1]))

    def test_leaks_commit_message(self):
        r = Repo(git=True)
        r.write("kb/deny.list", "secretco\n")
        r.write("y.md", "fine\n")
        subprocess.run(["git", "-C", str(r.root), "add", "y.md"], check=True)
        subprocess.run(["git", "-C", str(r.root), "commit", "-qm", "remove secretco mentions"], check=True)
        self.assertTrue(any("message" in b for b in r.run(checks.check_leaks)[1]))

    def test_casebook_unrouted_group_and_orphan_trigger(self):
        r = Repo()
        r.write("docs/casebook/h.md", MEM_GROUP.replace("## a-lesson", "## other"))
        bad = r.run(checks.check_casebook_router)[1]
        self.assertTrue(any("not routed" in b for b in bad))
        self.assertTrue(any("no `## a-lesson`" in b for b in bad))

    def test_tracked_state(self):
        r = Repo(git=True)
        r.write(".ybase/MACHINE.md", "x\n")
        subprocess.run(["git", "-C", str(r.root), "add", "-f", ".ybase/MACHINE.md"], check=True)
        self.assertTrue(r.run(checks.check_no_tracked_state)[1])

    def test_framework_style_em_dash_only_in_framework_prose(self):
        r = Repo()
        r.write("docs/x.md", "one — two\n")
        r.write("cases/demo/literature/papers/c.md", NOTE + "quoted — text\n")
        bad = r.run(checks.check_framework_style)[1]
        self.assertEqual(len(bad), 1, bad)
        self.assertIn("docs/x.md", bad[0])


class Scope(unittest.TestCase):
    def test_excluded_prefix_is_never_scanned(self):
        r = Repo()
        r.write("docs/superpowers/plan.md", "one \u2014 two\n[gone](nope.md)\nmail bob" + "@corp.io\n")
        self.assertNotIn(r.root / "docs/superpowers/plan.md", checks.Ctx(r.root).files())
        for fn in (checks.check_links, checks.check_leaks, checks.check_framework_style):
            self.assertEqual(r.run(fn)[1], [], fn.__name__)

    def test_no_path_is_exempt_once_the_old_content_is_gone(self):
        """The folders and scripts the consolidation removed are scanned like any other path."""
        self.assertFalse(hasattr(checks, "LEGACY_PATHS") or hasattr(checks, "LEGACY_PROSE"))
        r = Repo(git=True)
        r.write(".gitignore", "kb/\n")
        r.write("kb/deny.list", "(?i)zq" + "privterm\n")
        for rel in ("memory/x.md", "scripts/setup.sh", "LICENSE"):
            r.write(rel, "names ZQ" + "privterm\n")
        r.write("memory/y.md", "[gone](nope.md)\n")
        self.assertEqual(len(r.run(checks.check_leaks)[1]), 3)
        self.assertTrue(any("memory/y.md" in b for b in r.run(checks.check_links)[1]))

    def test_legacy_prose_folders_need_the_slash(self):
        self.assertTrue(checks.under("docs/adr/0001.md", ("docs/adr/",)))
        self.assertFalse(checks.under("docs/adrx.md", ("docs/adr/",)))
        self.assertFalse(checks.under("docs/README.md", ("README.md",)))

    def test_legacy_prose_star_covers_a_prefix_only(self):
        self.assertTrue(checks.under("scripts/setup-mine.sh", ("scripts/setup-m*",)))
        self.assertFalse(checks.under("scripts/setup-tools.sh", ("scripts/setup-m*",)))
        self.assertFalse(checks.under("tools/scripts/setup-mine.sh", ("scripts/setup-m*",)))

    def test_rewritten_docs_are_no_longer_legacy(self):
        r = Repo()
        r.write("README.md", "one \u2014 two\n")
        r.write("docs/adr/0001.md", "[gone](nope.md)\n")
        self.assertEqual(len(r.run(checks.check_framework_style)[1]), 1)
        self.assertEqual(len(r.run(checks.check_links)[1]), 1)


class LeaksBaseline(unittest.TestCase):
    def commit(self, r, msg):
        r.write("y.md", msg + "\n")
        subprocess.run(["git", "-C", str(r.root), "add", "y.md"], check=True)
        subprocess.run(["git", "-C", str(r.root), "commit", "-qm", msg], check=True)

    def test_only_messages_after_the_baseline_are_read(self):
        r = Repo(git=True)
        r.write("kb/deny.list", "secretco\n")
        self.commit(r, "old secretco message")
        head = subprocess.run(["git", "-C", str(r.root), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
        r.write(".leaks-baseline", head + "\n")
        self.commit(r, "a clean message")
        self.assertFalse(any("message" in b for b in r.run(checks.check_leaks)[1]))
        self.commit(r, "new secretco message")
        bad = [b for b in r.run(checks.check_leaks)[1] if "message" in b]
        self.assertEqual(len(bad), 1, bad)

    def test_unknown_baseline_is_a_finding_and_reads_everything(self):
        r = Repo(git=True)
        r.write(".leaks-baseline", "0" * 40 + "\n")
        bad = r.run(checks.check_leaks)[1]
        self.assertTrue(any(b.startswith(".leaks-baseline:") for b in bad), bad)


class Skills(unittest.TestCase):
    def repo_with_skill(self, name="demo-skill", fm_name="demo-skill", row=True, link=True):
        r = Repo()
        desc = "Use when the demo needs running end to end."
        r.write(f".claude/skills/{name}/SKILL.md", f"---\nname: {fm_name}\ndescription: {desc}\n---\n# x\n")
        r.write(".claude/skills/README.md", f"| `{name}/` | a | b |\n" if row else "nothing\n")
        if link:
            (r.root / ".agents").mkdir()
            (r.root / ".agents" / "skills").symlink_to("../.claude/skills")
        return r

    def test_clean(self):
        self.assertEqual(self.repo_with_skill().run(checks.check_skills)[1], [])

    def test_name_mismatch(self):
        self.assertTrue(self.repo_with_skill(fm_name="other").run(checks.check_skills)[1])

    def test_missing_contract_row(self):
        self.assertTrue(any("contract row" in b for b in self.repo_with_skill(row=False).run(checks.check_skills)[1]))

    def test_description_yaml_hazards(self):
        for bad_desc in ("Use when fixing findings on #123 quickly", "Use when closing out: reconcile everything"):
            r = self.repo_with_skill()
            r.write(".claude/skills/demo-skill/SKILL.md", f"---\nname: demo-skill\ndescription: {bad_desc}\n---\n")
            self.assertTrue(any("YAML" in b for b in r.run(checks.check_skills)[1]), bad_desc)

    def test_missing_codex_view(self):
        self.assertTrue(any(".agents/skills" in b for b in self.repo_with_skill(link=False).run(checks.check_skills)[1]))


HOOK_SRC = '"""A hook: refuses nothing, passes everything, escape NONE=1."""\nimport sys\nsys.exit(0)\n'


def settings_for(*names):
    return '{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [' + ", ".join(
        '{"type": "command", "command": "h=\\"$CLAUDE_PROJECT_DIR/.claude/hooks/%s\\"; python3 \\"$h\\"; exit 0"}' % n
        for n in names) + "]}]}}\n"


class Hooks(unittest.TestCase):
    def repo(self, names=("a_hook.py",), wired=("a_hook.py",), src=HOOK_SRC):
        r = Repo()
        for n in names:
            r.write(f".claude/hooks/{n}", src)
        r.write(".claude/settings.json", settings_for(*wired))
        return r

    def test_absent_is_a_silent_zero(self):
        self.assertEqual(Repo().run(checks.check_hooks), (0, []))

    def test_clean(self):
        self.assertEqual(self.repo().run(checks.check_hooks), (1, []))

    def test_unwired_hook(self):
        bad = self.repo(names=("a_hook.py", "b_hook.py")).run(checks.check_hooks)[1]
        self.assertTrue(any("b_hook.py: not referenced" in b for b in bad), bad)

    def test_wired_but_missing_hook(self):
        bad = self.repo(wired=("a_hook.py", "ghost_hook.py")).run(checks.check_hooks)[1]
        self.assertTrue(any("ghost_hook.py, which does not exist" in b for b in bad), bad)

    def test_no_docstring_and_no_settings(self):
        bad = self.repo(src="import sys\nsys.exit(0)\n").run(checks.check_hooks)[1]
        self.assertTrue(any("no module docstring" in b for b in bad), bad)
        r = Repo()
        r.write(".claude/hooks/a_hook.py", HOOK_SRC)
        self.assertTrue(any("settings.json: missing" in b for b in r.run(checks.check_hooks)[1]))

    def test_invalid_json(self):
        r = self.repo()
        r.write(".claude/settings.json", "{not json")
        self.assertTrue(any("not valid JSON" in b for b in r.run(checks.check_hooks)[1]))

    def test_real_hooks_each_have_a_docstring(self):
        hooks = Path(__file__).resolve().parent.parent / ".claude" / "hooks"
        for p in sorted(hooks.glob("*.py")):
            self.assertTrue(checks.ast.get_docstring(checks.ast.parse(p.read_text(encoding="utf-8"))), p.name)


class Law(unittest.TestCase):
    REAL_HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "moment_law_hook.py"

    def repo(self, with_hook=True):
        r = Repo()
        if with_hook:
            r.write(".claude/hooks/moment_law_hook.py", self.REAL_HOOK.read_text(encoding="utf-8"))
        return r

    def moments(self):
        return checks.law_moments(checks.Ctx(Path(__file__).resolve().parent.parent))

    def test_absent_is_a_silent_zero(self):
        self.assertEqual(Repo().run(checks.check_law), (0, []))

    def test_clean(self):
        r = self.repo()
        r.write("docs/law/README.md", "# law\n")
        for m in self.moments():
            r.write(f"docs/law/{m}.md", f"# {m}\n")
        scanned, bad = r.run(checks.check_law)
        self.assertEqual(bad, [])
        self.assertEqual(scanned, len(self.moments()))

    def test_missing_law_file(self):
        r = self.repo()
        for m in self.moments():
            if m != "commit":
                r.write(f"docs/law/{m}.md", f"# {m}\n")
        bad = r.run(checks.check_law)[1]
        self.assertEqual(len(bad), 1, bad)
        self.assertIn("docs/law/commit.md: missing", bad[0])

    def test_law_file_without_a_moment(self):
        r = self.repo()
        for m in self.moments():
            r.write(f"docs/law/{m}.md", f"# {m}\n")
        r.write("docs/law/launch.md", "# launch\n")
        bad = r.run(checks.check_law)[1]
        self.assertEqual(len(bad), 1, bad)
        self.assertIn("docs/law/launch.md: no moment", bad[0])

    def test_law_folder_without_the_hook(self):
        r = self.repo(with_hook=False)
        r.write("docs/law/commit.md", "# c\n")
        self.assertTrue(any("commit.md: no moment" in b for b in r.run(checks.check_law)[1]))

    def test_hook_that_does_not_import_is_a_finding(self):
        r = self.repo()
        r.write(".claude/hooks/moment_law_hook.py", "def (\n")
        self.assertTrue(any("cannot be imported" in b for b in r.run(checks.check_law)[1]))


def words(n: int, start: int = 0) -> str:
    return " ".join(f"w{i}" for i in range(start, start + n))


class Budget(unittest.TestCase):
    """AGENTS.md plus docs/rules.md stay within 1,500 words, each numbered rule within 50."""

    def repo(self, agents_words: int, rules: list[int]):
        r = Repo()
        r.write("AGENTS.md", words(agents_words) + "\n")
        body = "".join(f"{i}. {words(n)}\n" for i, n in enumerate(rules, 1))
        r.write("docs/rules.md", "# Rules\n\n" + body)
        return r

    def test_budget_passes_under_limits(self):
        # "# Rules" is 2 words; ten rules of 50 words plus their "n." markers are 510.
        r = self.repo(1500 - 2 - 510, [50] * 10)
        self.assertEqual(r.run(checks.check_always_on_budget)[1], [])

    def test_budget_fails_over_total(self):
        r = self.repo(1501 - 2 - 510, [50] * 10)
        self.assertEqual(r.run(checks.check_always_on_budget)[1],
                         ["AGENTS.md + docs/rules.md: 1501 words, limit 1500"])

    def test_budget_fails_on_long_rule(self):
        r = self.repo(100, [10, 20, 51, 50])
        self.assertEqual(r.run(checks.check_always_on_budget)[1],
                         ["docs/rules.md: rule 3 has 51 words, limit 50"])

    def test_budget_rule_ends_at_blank_line_or_heading(self):
        r = Repo()
        r.write("docs/rules.md", "# R\n\n1. " + words(40) + "\n" + words(40) + "\n\n" + words(40)
                + "\n2. " + words(40) + "\n## Next\n" + words(40) + "\n")
        bad = r.run(checks.check_always_on_budget)[1]
        self.assertEqual(bad, ["docs/rules.md: rule 1 has 80 words, limit 50"])

    def test_real_tree_is_within_budget(self):
        self.assertEqual(checks.check_always_on_budget(checks.Ctx(Path(__file__).resolve().parent.parent))[1], [])


class CheckFile(unittest.TestCase):
    def test_one_file_findings_and_non_markdown(self):
        r = Repo()
        p = r.write("docs/x.md", "a \u2014 b\n[gone](nope.md)\n")
        bad = checks.check_file(p, r.root)
        self.assertEqual(len(bad), 2, bad)
        self.assertTrue(all(b.startswith("docs/x.md") for b in bad))
        self.assertEqual(checks.check_file(r.write("t.py", "x = 1 \u2014 2\n"), r.root), [])
        quoted = r.write("cases/demo/literature/papers/q.md", NOTE + "quoted \u2014 text\n")
        self.assertEqual(checks.check_file(quoted, r.root), [])  # not framework prose

    def test_root_defaults_to_the_enclosing_repository(self):
        r = Repo(git=True)
        p = r.write("docs/y.md", "a \u2014 b\n")
        self.assertEqual(checks.check_file(p), ["docs/y.md:1: em dash; use a comma, colon, semicolon or a new sentence"])


class Frontmatter(unittest.TestCase):
    def test_lists_and_scalars(self):
        fm = checks.frontmatter("---\na: 1\nb: [x, 'y']\nc: \"q\"\n---\nbody")
        self.assertEqual(fm, {"a": "1", "b": ["x", "y"], "c": "q"})

    def test_no_frontmatter(self):
        self.assertEqual(checks.frontmatter("# title\n"), {})


if __name__ == "__main__":
    unittest.main()
