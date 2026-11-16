# Docs: the rules that bind when you write a document

Shown once per session by the moment hook; see [README.md](README.md). Codex reads it before the act.

## Before you write

1. File it by stage and layer ([rule 11](../rules.md#placement)); [`templates/research-topic/PIPELINE.md`](../../templates/research-topic/PIPELINE.md) names the folder. A number the instrument produced is a fact for the experiment record; a number you concluded is inference for `analysis/`; durable truth is `understanding/`. Evidence never recommends.
2. Read [`docs/writing.md`](../writing.md) ([rule 18](../rules.md#working)). When `docs/writing/` holds a register for the path, that register binds too.
3. Keep machine facts and a research topic's knowledge in their own homes ([rules 13 and 14](../rules.md#placement)).
4. Everything committed is published ([rule 19](../rules.md#publishing)): no raw data, no private alias, no path a reader cannot open.

## The shape

- A new file states its end state and carries no history. No "no longer", no "this replaced", no "this PR absorbed"; present-tense rationale stays, and the story goes in the commit message or `## History`.
- A README orients; a catalog lists ([rule 12](../rules.md#placement)). Teach the naming convention or generate the catalog beside it; never grow the README into an index.
- A score names its producer, its population and its metric where it first appears. Unattributed, a number is read as whatever the reader expects.
- Every number carries its label ([rule 2](../rules.md#evidence)). A claim copied from another document is a paraphrase: assumed, not measured, until you open its primary artifact.
- An analysis ships the script that pulled or computed its numbers, never the raw data, and ends with a reproducibility appendix naming the script, the command and the slices cited.
- A `file:line` reference drifts; re-grep for the symbol before you cite it.

## Correcting

- Correct with an erratum, never a silent rewrite ([rule 6](../rules.md#changes)). An erratum on the file you happened to be editing is half a correction: grep the topic for every site that still asserts the claim and give each one its erratum.
- A limitation written into prose is an untested claim. State it only if you observed it; otherwise write the test or drop the sentence.
- Before proposing a mechanism, grep the topic's analyses for the same idea and its withdrawal, and answer the counterexample that withdrew it.
- Where two documents reason in one vocabulary, exactly one defines it and every other links that file ([rule 7](../rules.md#changes)).
