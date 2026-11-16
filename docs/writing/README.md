# docs/writing/: the writing registers

[`../writing.md`](../writing.md) is the one-page guide every writer in this repo reads. This folder refines it by **register**: the rules a document follows because of who reads it and what they will do with it. A folder's `README.md` says what belongs in the folder; the register says how a file there is written.

## TL;DR

- Read [`general.md`](general.md), then the one register your path or surface maps to below, then write.
- **Every register inherits `general.md`.** A register adds rules, narrows them, or, where its `## What it inverts` section says so, inverts one.
- A rule is **`[mechanical]`** when a program can check it and **`[judgment]`** when a reader has to confirm it. Both bind; only the first has a check.
- Anything read outside the repo also takes [`external.md`](external.md), because that reader cannot open a path.
- Two files here are methodology notes, not registers: [`outlining.md`](outlining.md) and [`performance-reporting.md`](performance-reporting.md).

## What a register is

A register is the answer to "who reads this, and what changes because of that". An analysis is read by a colleague who can open the repo, so a bracketed `[M]` label is faster than a sentence. A readout is read by a lead who cannot, so the same label is banned there and the provenance goes in prose. Neither is the right style everywhere; each is right for its reader. Every register file has the same sections: who is reading, the rules with their tags, what the register inverts relative to `general` or a sibling, and a short bad and good example.

## Path to register

The path decides. Paths under `research/<topic>/`, `memory/` and `worklog/` sit in a knowledge base (KB); the rest sit in this repo. Where a surface has no path (a message, a PR comment, a readout handed to someone), the kind of document decides.

| Path or surface | Register | In one line |
|---|---|---|
| `research/<topic>/literature/**`, `research/<topic>/understanding/**`, any `CATALOG.md` | [`reference`](reference.md) | Present-tense current truth, anchored to `file:line` or a URL, corrected with an `ERRATUM` block. |
| `research/<topic>/analysis/**` | [`analysis`](analysis.md) | Measured result first, every number labelled, negative results stated as plainly as positive ones. |
| `research/<topic>/opportunities/**`, `research/<topic>/projects/**/PLAN*` | [`plan`](plan.md) | Imperative and decision-bearing: motivation, hypothesis, verification, impact, tier, four legs. |
| `research/<topic>/projects/**/design/**` | [`design`](design.md) | The shape of one proposed system for a senior lead: alternatives scored on axes, risks with de-risk plans, worked examples in an appendix. |
| `memory/**`, `worklog/**` | [`record`](record.md) | Past tense, absolute dates, what happened and why; the wrong turn is the content. |
| `docs/**`, `.claude/skills/**`, `profiles/**`, `README.md`, `AGENTS.md`, any folder `README.md` | [`general`](general.md) only | The rules every writing task follows. |
| code comments, docstrings, commit messages | [`code`](code.md) | Self-contained for a reader with no workspace access; the invariant sits at the fix site. |
| PR bodies, PR review comments and replies, review documents | [`review`](review.md) | To an author about one artifact, verdict first, every finding anchored. |
| a message to a person | [`message`](message.md) | Peer-to-peer and tight: cut hedges and sign-offs, keep every identifier, say what you want. |
| a readout of results | [`readout`](readout.md) | A living view over a batch of changes and their measured impact, numbered, normalized, decomposed. |
| an investigation or debugging write-up | [`investigation`](investigation.md) | One question answered with evidence, dated and immutable, alternatives named with what ruled each out. |
| a one-page record of a project's key decisions | [`tech_summary`](tech_summary.md) | Each option adopted, promoted, dropped, deferred or reversed, with the fact that settled it. |

The most specific match wins where globs overlap: a `PLAN.md` under a project's `design/` folder is a plan. A file that matches nothing takes `general`.

## How registers stack

`general` is the base of everything. `external` sits under every surface whose reader cannot open the repo: `readout`, `investigation`, `design`, `tech_summary`, `message`, and the PR surfaces of `review`. A readout is therefore graded `general` for language, `external` for what an outside reader can follow, and `readout` for the shape and arithmetic of that document type. The type register adds only what that type needs; it never restates `external`.

A register of its own is the exception, and it has to clear a bar: either its documents invert a rule the register above them states (a readout is edited in place, an investigation is immutable, and `external` cannot hold both), or a reader of the parent register alone would be wrong rather than underserved. A folder that merely has its own subject matter does not clear it; it gets a row in the table above pointing at an existing register.

## Mechanical and judgment

A `[mechanical]` rule is one a program can decide from the text: a banned pattern, a missing section, a count. `tools/checks.py` enforces the mechanical rules that reach framework prose today (`framework-style` for em dashes, `leaks` for personal paths and private terms, `links` for broken relative links), and `ybase check` runs them before a commit. In Claude Code a hook may also advise on the mechanical rules after each write; hooks fire only in Claude Code, so Codex and other agents run `python3 tools/checks.py framework-style leaks links` by hand. Not every rule tagged `[mechanical]` has a check yet: the tag says a check is possible, and a rule without one is still a rule.

A `[judgment]` rule is one only a reader can confirm: whether the first sentence is the conclusion, whether a number names its basis. The `proofread` skill dispatches fresh reviewers who read `docs/writing.md` and `docs/rules.md` as their instructions, and through the first the register for the path; it is the judgment half, and it catches the confident sentence about a config nobody opened.

## Adding a rule or a register

A rule goes in the register whose reader it protects, with its tag, and in `general.md` only if every register needs it. A mechanical rule also gets its check in `tools/checks.py`, with a test holding a planted violation and a near-miss. A new register needs a row above, the standard sections, and the bar in § How registers stack.
