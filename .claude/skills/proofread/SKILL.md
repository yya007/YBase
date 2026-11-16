---
name: proofread
description: Use when a document someone will read or act on is about to ship (a note, an analysis, a plan, a PR body, a message to another person) or when the user asks to proofread or review a draft; runs the mechanical checks, then independent judgment lenses that read docs/writing.md and docs/rules.md, and triages what they return.
---

# proofread: review a draft against the documents that govern it

This skill routes; the governing documents decide. The mechanical half is `ybase check`. The judgment half is [`docs/writing.md`](../../../docs/writing.md), [`docs/rules.md`](../../../docs/rules.md) and, for a research note in a knowledge-base (KB) topic, that topic's `PIPELINE.md` (the template is [`templates/research-topic/PIPELINE.md`](../../../templates/research-topic/PIPELINE.md)). A draft in a managed repo also answers to that repo's own `AGENTS.md` and the docs it names. Each lens below reads those files as its instructions. None of them gets a checklist copied out of them, because a copied checklist keeps grading rules the documents no longer carry. The lenses run as separate fresh reviewers because a writer cannot see their own assumptions, and a second pass in the same context inherits them. One reviewer holding everything also skims unevenly, and nothing in a single report shows where; split lenses make a skipped lens visible as a silent one.

## When not to use

- A worklog line, a scratch note, or a routine table row nobody will act on.
- A code change: that is a code review, not a proofread.
- A scrub of private material before publishing. That needs a second reader holding the originals and a list of private facts, per [`docs/casebook/publishing.md`](../../../docs/casebook/publishing.md); the `outsider` lens here does not see the originals.
- A draft that is still moving. Proofread the version you intend to ship; findings against text that is about to change have to be gathered again.

## Stages

1. **Pin the draft and name what governs it.** Set `draft=<path>`. An in-repo draft is its own path. A draft that lives elsewhere (a PR body, a message) goes to a file in scratch first, and `draft` names that file:

   ```bash
   eval "$(ybase env)"; mkdir -p "$TMPDIR/proofread"
   ```

   Then list, as paths and not as summaries: always `docs/writing.md` and `docs/rules.md`; for a note under `<kb>/research/<topic>/`, the section of that topic's `PIPELINE.md` for its stage and the topic's `CASE.md`; for a draft in a managed repo, that repo's `AGENTS.md` and the docs it names; any `docs/casebook/<group>.md` whose `Covers:` line in `docs/casebook/INDEX.md` matches, and any KB lesson group whose `Covers:` line in that KB's `memory/INDEX.md` matches (for anything going public, `docs/casebook/publishing.md`). Collect the sources the draft cites mechanically, not from memory:

   ```bash
   grep -noE '\]\([^)]+\)|`[^`]+\.(md|py|sh|json|yaml|csv)(:[0-9]+)?`' "$draft"
   ```

   Name the **sources root**, the checkout those paths resolve against. A reviewer told to open a file and given nowhere to open it from returns `unverifiable` for everything. Name the **reader**: who receives this and what they will do with it. Guards against: a reviewer checking against rules nobody named, or against a summary of them that the writer's blind spot shaped.

2. **Gate on the mechanical half.**

   ```bash
   "$W/bin/ybase" check framework-style links leaks     # W: the YBase worktree that holds the draft
   ```

   Run the entry point of the tree that holds the draft: the root `bin/ybase` checks only the main checkout ([`README.md`](../README.md#cross-agent-contract)). Read what each check scanned. No check reads a file outside that tree: a KB note, a file in a managed repo, or anything under ignored scratch. For those, run the same patterns on the one file:

   ```bash
   python3 - "$draft" <<'PY'
   import sys; sys.path.insert(0, "tools"); import checks
   deny = checks.deny_patterns(checks.Ctx(checks.ROOT))
   for i, line in enumerate(open(sys.argv[1], encoding="utf-8"), 1):
       for hit in checks.leak_hits(line, deny) + (["em dash"] if chr(0x2014) in line else []):
           print(f"{i}: {hit}")
   PY
   ```

   Run it from the YBase root or a worktree of it; either reads the `deny.list` of every KB. If no knowledge base's `deny.list` has an uncommented line, say so in the report: the private-term half of `leaks` checked nothing. Fix every finding in the draft before Stage 3. Guards against: spending six reviews on text the mechanical fixes are about to move.

3. **Dispatch the lenses.** Each lens gets the draft path, its row below, the governing paths from Stage 1, the sources root, the reader, and the finding fields. Each reads its instruction files in full before it judges the draft; `outsider` is the one exception, below.

   | Lens | Reads as its instructions | Question it answers | Verdicts |
   |---|---|---|---|
   | `outsider` | the draft alone first; then the outside-reader point in `docs/writing.md` and `docs/casebook/publishing.md` | What would the named reader, with none of the author's context, misread, push back on, or learn that they should not? | `lands`, `misleads`, `gap`, `leak` |
   | `plain` | `docs/writing.md` | Does each sentence read the way that file requires, and does the prose get in the reader's way anywhere? | `violates`, `unverifiable` |
   | `lead` | `docs/writing.md` on the lead and the end state; for a research note, the topic `PIPELINE.md` section for the draft's stage and the topic's `CASE.md` | Does the opening state the conclusion, and does each section deliver what its heading promises, in the shape its stage requires? | `proves`, `partial`, `absent` |
   | `claims` | the Evidence section of `docs/rules.md`; the number rule in `docs/writing.md` | Is every claim backed the way the rules require: a label and a source on every number, unverified premises marked, absence claims searched? | `supported`, `unsupported`, `unverifiable` |
   | `accuracy` | the sources the draft cites, opened from the sources root | Does each claim survive re-reading its source, and each number re-deriving? | `confirmed`, `contradicted`, `unverifiable` |
   | `placement` | the Changes and Placement sections of `docs/rules.md`; the topic `PIPELINE.md` for a research note; `docs/kb.md` and `docs/casebook/README.md` for a lesson; the diff against the landing ref | Is it filed in the right stage and layer, and does it change committed claims the way the rules require: an erratum and not a silent rewrite, every other site swept, one declaration per fact? | `violates`, `unverifiable` |

   For `placement`, the diff is `git diff "$(git merge-base HEAD <landing-ref>)" -- <draft>`, where the landing ref is usually `origin/HEAD`, or the whole file when it is new. `outsider` reads the draft before anything else, because context it has read cannot be unread.

   Every finding carries: `lens`, `line`, `span` (quoted from the draft), `verdict`, `severity` (`blocking`, `warning` or `nit`), and `evidence` (what was opened and what it showed). Evidence is required for `contradicted`, `misleads`, `leak` and anything `blocking`. A `misleads` names the wrong takeaway in the reader's words. Every lens also returns `opened:`, the files it read, even when it found nothing. Four rules bind every lens: quote the span; cite what you opened, and if you could not open it the verdict is `unverifiable`; call something absent only after running the search that settles it; and re-derive a figure before calling it wrong, because a reason to expect a number to have moved is a prediction, not a finding.

   **Claude Code:** one fresh subagent per lens, all six in one message so they run in parallel. Pass paths, not file contents.
   **Codex:** there are no subagents. Run the lenses one at a time in this context, in table order (`outsider` first), finishing each lens's findings before opening the next lens's files. Record `lenses: sequential, one context` in the report: the independence the parallel form buys was not obtained, so a clean result is weaker evidence.
   Guards against: one reviewer serving the interesting parts, and a lens grading against a stale copy of a rule.

4. **Merge and triage.** Reject a finding with no span, or with a verdict its lens cannot return. Downgrade to `unverifiable` any `contradicted` or `misleads` with no evidence. A lens with no findings and an empty `opened:` list is **silent**: it either found nothing or never ran, and those look the same, so re-run it. An `outsider` report of nothing but `lands` with no objection actually tried is also silent. Merge findings on the same span and keep the strongest. Check each finding you disagree with against the same source it cites; where the reviewer was wrong, say why in your own words rather than editing to satisfy it. Then act:

   - `contradicted`, `leak`, or anything `blocking` stops the draft. Fix it, re-run Stage 2, then re-run the lens that raised it.
   - `unsupported` or `unverifiable`: cite something checkable, or mark the sentence as unverified in the text ("Verify before you assert" in `docs/rules.md`).
   - `misleads`: change the draft until the stated wrong takeaway is no longer available.
   - A fix to a claim already committed is an erratum, and every other site asserting it gets one too ("Correct with an erratum" and "Sweep the class" in `docs/rules.md`). Find them with `grep -rn`.
   - A defect in a source the draft cites goes to that source, with its own erratum. Fixing only the draft leaves the wrong claim live for the next writer.
   - A finding that contradicts something code decides is settled in the code, not in a note that quotes it.
   - Moving, merging or renumbering sections invalidates the whole review: run Stages 2 to 4 again.

   Write the merged report to `$TMPDIR/proofread/<slug>-<YYYY-MM-DD>.md`; it is a review artifact, not a document, and is never committed. Guards against: a merged list that hides a lens that did no work, and a fix that lands in one place while the claim stays wrong in three others.

## Output

Reply with this, and nothing that summarizes it into a single grade:

```
proofread: <draft path>   <YYYY-MM-DD>
reader: <who, and what they will do with it>
governing: <every path from Stage 1>
mechanical: <checks run, scanned counts, findings fixed>; deny.list: <n terms | empty>
lenses: parallel subagents | sequential, one context
  <lens>  opened <n>  findings <n>  [silent]        (one line per lens)
stops: <finding numbers that stop the draft, or none>

| # | lens | line | span | verdict | severity | evidence |
|---|------|------|------|---------|----------|----------|

routed to sources: <path: what is wrong there, erratum needed> | none
dismissed: <#: why the finding was wrong, checked against what> | none
not reached by any lens: whether this reader is authorized to see each fact;
  link targets beyond what the links check resolves
report: <path of the report in scratch>
```

`stops` is derived from the table, never asserted: it lists every `contradicted`, `leak` and `blocking` finding still open. The draft ships only when `stops` reads `none` and no lens is silent.
