# record: what happened

**Surfaces:** `worklog/**`, `memory/**`.

## TL;DR

- Past tense, absolute dates, what happened and why, which commits.
- A worklog is append-only: a superseded entry earns a later entry, never an edit.
- A memory entry is a lesson: what happened, why it matters, how to apply it. It links a rule and never restates one.
- Your own wrong turn gets the same prominence as anyone else's; it is the value of the document.
- A factual correction to a circulated record is a dated `ERRATUM` block in place.

## Who is reading, and what that changes

Someone reconstructing what was done, or looking for the lesson before repeating a mistake. They need dates they can order and commits they can open. The formats are fixed by [`../casebook/README.md`](../casebook/README.md) and [`../../templates/kb/worklog/README.md`](../../templates/kb/worklog/README.md); this register says how the prose inside them reads.

## Rules

| Rule | Tag |
|---|---|
| Past tense. Absolute dates (`2026-03-14`), never relative (`last week`). | `[judgment]` |
| What happened, why, what changed, and the commit range. | `[judgment]` |
| Dated by the session that wrote the entry, not by the date of the thing described. | `[judgment]` |
| No prescriptions in a worklog: a rule belongs in [`../rules.md`](../rules.md), its case in `memory/`. A memory entry's prescription lives in its `How to apply` field and nowhere else. | `[judgment]` |
| A worklog entry is never edited once pushed; a correction is a later entry or a dated `ERRATUM` block. A memory entry is refined in place or deleted when wrong, per its README. | `[judgment]` |
| The wrong turn is stated, with what it cost and what would have caught it sooner. | `[judgment]` |
| Every identifier in full: commit hashes, run ids, file paths (`full-identifiers`). | `[mechanical]` |
| The three plain-English rules (`long-sentence`, `clause-stack`, `no-formal-word`) describe how to write an entry but are not enforced on a landed one, because the fix would be an edit the contract forbids. | `[mechanical]` (scope note) |

## What it inverts

The wrong path, cut in `external` and `message`, is the content here. Nothing in `general` is inverted.

## Example

Bad: "Fixed the flaky test. We should always run the suite twice from now on."

Good: "2026-03-14. The suite passed locally and failed in CI on `abc1234` because the test read a file the sandbox does not mount. Added the mount to the fixture in `def5678`. Lesson filed as `memory/testing.md#test-reads-unmounted-path`."
