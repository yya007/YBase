# Profile: critique

Adversarial critique of a design, spec, ADR, or proposed approach. The output you want here is disagreement.

## When

- `critique_input_words` threshold tripped on the document under review
- Before committing to an architecture or an ADR
- Whenever the main thread authored the design: self-critique from the same model is structurally weak

## Command

```
codex exec -s read-only -o <artifact> "<prompt below>"
```

## Prompt template

```
Read <path-to-design> and the parts of this repository it touches.

Your job is to find what is wrong with this design, not to summarize or improve it.
Assume the author is competent and has already considered the obvious objections.
Look for what they are invested in not seeing.

Specifically hunt for:
- Assumptions stated as facts, and what breaks if each is false
- Failure modes under partial failure, concurrency, or scale
- Places the design conflicts with how this repository actually works today
- Complexity that buys nothing (name what to delete)
- Missing acceptance criteria: what would prove this design wrong?

Lead with a single VERDICT line: "sound", "revise", or "reconsider", plus a one-sentence
reason. Then list objections ordered by how much damage they do if ignored. For each:
the objection, the evidence in the repo, and what would have to be true for it not to
matter. Separate what you verified in the code from what you are inferring. End with the
strongest argument FOR the design, stated honestly. If you cannot make one, say so.
```

## Handling

The closing "strongest argument for" section is a calibration check: a critique that cannot state the design's best case is probably contrarian rather than useful. Weigh objections accordingly, and keep Codex's verified/inferred split intact when reporting.
