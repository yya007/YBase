---
name: review-skill
description: Use when the user says "review my skills", "audit the skills" or "are the skills still good", asks about skill drift or staleness, wants a health check on .claude/skills in YBase or a managed repo, or has finished a round of skill edits; audits one or all skills against a quality rubric (completeness, structure, output contracts, internal consistency) into a markdown report, and with --fix applies a narrow set of safe patches.
---

# review-skill

Audit skills against a quality rubric. Produces a structured markdown report; with `--fix`, applies a narrow set of safe automated patches. Defaults to report-only.

## Why this exists

Skills are prompts stored as files. They rot quietly: paths get renamed, sibling skills get deleted, templates drift out of sync with their sources, conditional language ("if time allows") leaks in during edits. Tests and CI do not catch the rot: the skill just silently gives worse instructions. This skill is the periodic health check.

## Usage

```
/review-skill [<skill_name>] [--fix] [--dry-run] [--skills-dir <path>]
```

- No positional argument: review **every** skill discovered in the skills directory.
- `<skill_name>`: review only that one skill (directory name under the skills root).
- `--fix`: after reporting, apply the safe automated patches listed in Step 5. Writes files.
- `--dry-run`: run every analysis step including Rubric E currency checks; print what `--fix` *would* do, but write nothing. Mutually exclusive with `--fix`.
- `--skills-dir <path>`: override the skills directory. Default is `.claude/skills/` at the YBase root (`.agents/skills` is a symlink to it, the view Codex reads). To review a managed repo's skills, pass its directory, for example `"$(ybase repos path NAME)"/.claude/skills`; read it by path and never `cd` there ([`docs/rules.md`](../../../docs/rules.md) rule 23).

If the skills directory is empty or contains no `SKILL.md` files, report "No skills found to review" and stop.

## Algorithm

Every step is mandatory unless explicitly marked optional. Do not skip steps to save time: the rubric is the whole point.

### Step 1: Discover

1. Resolve the skills directory (explicit flag wins, else the default above).
2. List immediate subdirectories; each that contains `SKILL.md` is a skill to evaluate.
3. If `<skill_name>` was passed, narrow the list to just that one. If it doesn't exist, report `Skill not found: <skill_name>` and stop.

### Step 2: Load shared context once

Read these files once before per-skill evaluation so currency checks have a reference:

- The root `AGENTS.md` of the repo that owns the skills directory, and the rules file it names (in YBase, `docs/rules.md`).
- That repo's root `CLAUDE.md`, if present.
- The skill directory's own `README.md`, if present. In YBase it holds the contract table that the `skills` check enforces (`ybase check skills` for the main checkout; `"$W/bin/ybase" check skills` for a worktree `$W`).

Missing any of these is not a failure: skip the dependent currency checks and note the missing source in the report.

### Step 3: Per-skill rubric

For each skill, read the full `SKILL.md` (and any files in `references/`, `scripts/`, etc. that the body names). Score each check as **Pass / Warn / Fail**. Parallelize per-skill evaluation: skills are independent during this step. In Claude Code, one read-only subagent per skill; in Codex, evaluate them one after another.

#### Rubric A: Completeness

| Check | Pass | Warn | Fail |
|---|---|---|---|
| No deferring language | No "skip if", "optionally", "if time allows", "if possible" in mandatory steps | - | Any mandatory step is conditionally deferred |
| Every branch explicit | Each decision point has an action for each outcome | Partial | Implicit fallthrough |
| Dry-run-followable | Another agent could execute every step with only the skill body + referenced files | Minor gap | Requires unstated context |
| Referenced paths resolve | Every file/dir path named in the body exists, or is clearly described as an output | Relative path ambiguous | Path refers to renamed/deleted target |

#### Rubric B: Structure

| Check | Pass | Warn | Fail |
|---|---|---|---|
| Frontmatter valid | `name`, `description` present; `description` states both what and when | `description` lacks "when" triggers | Missing frontmatter or `name` |
| Usage section | Invocation example with flags explained | Present but example-free | Missing |
| Algorithm/Steps section | Numbered or clearly-ordered, each step actionable | Prose only | Single undivided block |
| Output contract | Explicit output format (markdown skeleton, JSON schema, etc.) with example | Implied by description | None |
| Edge cases | ≥2 explicit edge cases handled | 1 case | None |
| Reads / Writes declarations | Skill states which paths it reads and which it writes, especially if it mutates state | `Reads` but no `Writes` (and it writes) | Neither, and it mutates files |

#### Rubric C: Quality

| Check | Pass | Warn | Fail |
|---|---|---|---|
| Self-validation | Final step verifies own output before declaring done | Partial check | No verification |
| Idempotency | States what happens on re-run (no surprise duplication, no state drift) | Implied | Unsafe to re-run |
| No implicit knowledge | All context read explicitly inside the algorithm | One assumption | Relies on unstated external state |
| Composable output | Output format is machine-readable or clearly structured for downstream use | Possible but unstated | Free-form prose only |

#### Rubric D: Project fit

| Check | Pass | Warn | Fail |
|---|---|---|---|
| Description "pushes" triggering | Description uses concrete trigger phrases ("use when the user says X", "also use proactively when Y") | Mentions trigger implicitly | No "when to use" guidance |
| Invariants stated | Skill names what it will never do (e.g. "does not modify paths under Y", "does not commit without approval") | - | No boundaries stated; risk of scope creep |
| Dry-run / fix-mode coherence | If the skill mutates state, it defines `--dry-run` (or equivalent) and a default-off side-effect mode | - | Undocumented side effects |
| Naming | Skill directory name is lowercase-hyphenated, stable, and matches `name` in frontmatter | Case mismatch | Directory renamed without updating frontmatter |

#### Rubric E: Currency

Skills embed static content: path lists, sibling-skill names, inline templates, lifted paragraphs from other docs. When the source drifts, the skill gives stale instructions silently. For each skill:

| Check | Pass | Warn | Fail |
|---|---|---|---|
| Referenced sibling skills exist | Every `.../skills/<other>` path, every `/<slash-command>` invocation, resolves to a real skill | - | Sibling is missing |
| Template blocks match sources | If the skill embeds a template that lives elsewhere (for example `templates/run/handoff-template.md`), the embedded copy matches the current source | Minor field drift | Template is structurally different from source |
| Contract alignment | Skill's rules don't contradict the currently-loaded `AGENTS.md` / `CLAUDE.md` | Minor drift | Skill instructs something explicitly forbidden by contracts |
| Referenced files exist | Every concrete file path named in the body (beyond well-known ones like `.git/`) resolves | Relative path ambiguous | Path no longer exists |

Flag findings as:

- `STALE_CONTENT: <skill> embeds <what> from <source>; source now says <different>`
- `MISSING_SIBLING: <skill> references <other> but not found under skills root`
- `CONTRACT_CONFLICT: <skill> Step N says X, but <contract-file> requires Y`

### Step 4: Cross-skill checks (only when reviewing all skills)

- **OVERLAP**: Compare the one-line purpose from each skill's description. Flag any pair whose purpose overlaps ≥70%. These are candidates for merge or explicit narrowing.
- **MISSING_REFERENCE**: If a skill's description or steps mention "see also X" or "delegates to X", confirm X exists. Flag if not.
- **NAMING_COLLISION**: Two skills with very similar names (Levenshtein ≤2, or one is a plural/tense of another).

### Step 5: Produce report

Print the full report. Do not summarize; list every finding. Use this exact structure so downstream tooling can parse it:

```
## Skill Review Report, <YYYY-MM-DD>
[DRY RUN: no files will be written]      <- include only if --dry-run

### Summary
- N skills reviewed
- N_pass fully-green, N_warn ≥1 warning, N_fail ≥1 failure
- N_currency stale-content findings
- Top issues: <top 3 actionable>

### Per-Skill Results

#### <skill-name>  [PASS | WARN | FAIL]
Completeness: <✅/⚠️/❌ per check>
Structure:    <✅/⚠️/❌ per check>
Quality:      <✅/⚠️/❌ per check>
Project fit:  <✅/⚠️/❌ per check>
Currency:     <✅/⚠️/❌ per check>

Issues:
- ❌ [Category] <specific finding with step/section reference>
- ⚠️ [Category] <specific finding>
…

(repeat for each skill)

### Cross-skill issues
- OVERLAP: <a> <-> <b>: both do <X>
- MISSING_REFERENCE: <a> delegates to <b>: not found
- NAMING_COLLISION: <a> <-> <b>

### Recommended actions

HIGH (blocks correctness or causes confusion):
- <skill>: <specific fix, with location>

MEDIUM (degrades reliability or discoverability):
- <skill>: <specific fix>

LOW (optional polish):
- <skill>: <specific fix>

### Skills with no issues
<list>

[If --dry-run:]
### Fixes that would be applied under --fix
- <skill>: <what would be added/changed>
```

### Step 6: Apply fixes (only if `--fix`)

Without `--fix` and without `--dry-run`: print the report and ask the user whether to apply fixes. Stop until they respond.

Under `--dry-run`: list what would be fixed in the "Fixes that would be applied" section of the report. Do not write.

Under `--fix`: apply only the following safe patches. Read each file before editing. After applying, list every file changed and what was added.

- **Missing `Usage` section**: Append after the frontmatter + title, before the first `##` body section:
  ```markdown
  ## Usage

  ```
  /<skill-name> [args]
  ```

  [describe what args do]
  ```
- **Missing `Output` or `Output format` section**: Append before the last step in the algorithm.
- **Missing `Edge cases`** section: Append after `Usage`.
- **Case-mismatched or drifted frontmatter `name`** vs. directory name: rewrite frontmatter `name` to match the directory name (lowercase-hyphenated form).

Never auto-fix any of:
- Algorithm restructuring or step reordering.
- Removing deferring language (needs human judgment about whether the deferral was intentional).
- Merging overlapping skills.
- Template content (copy the current source-of-truth content manually; mechanical sync risks overwriting intentional deviation).
- Priority or scope changes.

### Step 7: Self-validation

Before returning:

- Every skill in scope was evaluated (zero "not yet read" notes).
- Every rubric (A–E) was applied to every skill.
- Shared context (Step 2) was loaded and currency checks that depend on it ran.
- Cross-skill checks ran when in all-skills mode.
- Under `--fix`, every applied fix is listed in the output.
- Under `--dry-run`, zero files were written.

If any item is unsatisfied, complete it before printing the report.

## Output format

Markdown report per Step 5 structure. Final line:

```
Review complete: N skills, N_pass pass, N_warn warn, N_fail fail. [M fixes applied.]
```

## Invariants

- **Default is report-only.** Any state mutation requires `--fix` (and is not available under `--dry-run`).
- **Read before write.** Every file the skill modifies under `--fix` is read first.
- **Never introduce project-specific rules into the rubric.** If a project has extra conventions, those live in that project's own `AGENTS.md` / `CLAUDE.md`; this skill enforces the generic rubric and flags contract conflicts (Rubric E).
- **Do not auto-commit.** The skill writes files under `--fix`; the human stages and commits.

## References

- [`AGENTS.md`](../../../AGENTS.md) and [`docs/rules.md`](../../../docs/rules.md): the contract this skill checks YBase's skills against; a managed repo's skills answer to that repo's own `AGENTS.md`.
- [`README.md`](../README.md): YBase's skill contract table and the cross-agent contract.
- [`templates/skill-template.md`](../../../templates/skill-template.md): canonical skill structure, the shape reference for Rubric B.
- [`templates/skill-review-checklist.md`](../../../templates/skill-review-checklist.md): the human-facing version of this rubric, for manual reviews.
