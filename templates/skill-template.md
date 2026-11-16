---
name: <skill-name>            # lowercase-kebab, must match the directory name
license: PolyForm-Noncommercial-1.0.0   # repo default; mirror the upstream license for imports
description: <what it does + trigger-rich "Use when the user ..." clause so model invocation fires reliably>
---

# <Skill Title>

<!-- For skills imported from outside the workspace, add a provenance section
     here (required by docs/protocols/importing-skills.md):

## Source

Imported from [<owner>/<repo> → <path>](<url pinned to commit/tag>), <license>
© <author>. Pinned to upstream commit `<sha>`.

**Local divergence:** <what was changed from upstream, or "imported verbatim">.
-->

## Why this exists

<The friction or failure mode this skill removes, in one short paragraph.>

## Usage

```
/<skill-name> [<args>] [--flags]
```

## Workflow

1. <Step 1>
2. <Step 2>
3. <Step 3>

## Invariants

- <Boundary that must hold, e.g. "propose-only by default">
- <Boundary 2>

## Output Checklist

- <Required output 1>
- <Required output 2>

## References

- `references/<reference-file>.md`

<!-- Placement: a general-purpose skill goes in the skill library you install
     from (a skills repo or plugin). A skill that manages the home goes in
     .claude/skills/<name>/ with a row in .claude/skills/README.md. -->
