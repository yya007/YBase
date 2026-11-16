# Importing skills: adopting a skill from outside

Open this when you bring a skill in from somewhere else, such as a public repository. Check first that no installed skill already does the job ([`docs/rules.md`](../rules.md)).

## Where it goes

- A general-purpose skill goes in the skill library you install skills from: a skills repo or plugin you maintain. Follow that library's own `AGENTS.md`.
- A skill that manages the home (repos, worktrees, sessions, the knowledge base) goes in `.claude/skills/<name>/` in YBase, with a row in [`.claude/skills/README.md`](../../.claude/skills/README.md). Codex sees the same folder through `.agents/skills`.

Start a new skill from [`templates/skill-template.md`](../../templates/skill-template.md) and review it against [`templates/skill-review-checklist.md`](../../templates/skill-review-checklist.md).

## The specification

Every skill conforms to the [Agent Skills specification](https://agentskills.io/specification):

- a folder holding a `SKILL.md`;
- YAML frontmatter with `name` and `description`, both required;
- `name` in lowercase kebab case, equal to the folder name, with no leading, trailing or doubled hyphen;
- Markdown instructions after the frontmatter;
- optional `scripts/`, `references/` and `assets/` folders, so detail loads only when needed.

Bring an import into conformance as part of the import, not in a later pass.

## Keep its provenance

- Add a `## Source` section near the top of the imported `SKILL.md` that links to the original, pinned to a commit or a release when one exists, so the import can be reproduced.
- Copy the upstream licence into the frontmatter's `license` field and keep any bundled `LICENSE` file. Never drop attribution or licence terms.
- Under `## Source`, list what you changed from upstream: renames, edits, removed steps. A later sync then knows what not to overwrite.

## Names

Keep the upstream name. If it collides with another skill in the library or in an environment that installs it, rename it to `<skill>-<repo>`, with the source repo's name as the suffix so same-named skills sort together. Change the frontmatter `name`, the folder and every cross-reference inside the suite, and record the rename under `## Source`.
