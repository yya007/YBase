# message: to a person, now

**Surfaces:** chat messages, cross-team notes, anything a person reads in a thread rather than in a document.

## TL;DR

- Peer-to-peer and tight: one clean story beats an exhaustive taxonomy.
- Cut hedges, scope caveats, meta-status and sign-offs. Identifiers survive every cut.
- Lead with the current state or the correct setup; skip the wrong path once the right one stands alone.
- Recommendations go in a separate trailing section, framed as options.
- Describe behaviour, not blame. Slightly casual beats over-polished.

## Who is reading, and what that changes

A colleague reading on a phone between other things. They need to know in the first line what happened and what you want. They cannot open this repo, so [`external.md`](external.md) applies too: no workspace paths, no codenames.

## Rules

| Rule | Tag |
|---|---|
| Short headline; no infrastructure jargon in parentheses. | `[judgment]` |
| Cut hedges, scope caveats, meta-status ("I looked into this") and politeness sign-offs. | `[judgment]` |
| Every identifier stays, in full: job ids, request ids, cluster and namespace names, commit hashes (`full-identifiers`). | `[mechanical]` |
| Replace an inference with the concrete observation plus the workaround. | `[judgment]` |
| State plainly what you want from the reader. | `[judgment]` |
| Recommendations sit in a trailing section as options, never mixed into the account. | `[judgment]` |
| Prose connectors (`in short`, `which confirms`), never arrows. | `[judgment]` |
| Attach raw logs as a file; never paste a wall of text. | `[judgment]` |
| `no-em-dash` and `one-para-per-line` are graded here, because the reader is outside the repo. | `[mechanical]` |

## What it inverts

Nothing in `general`; this register narrows. Against `analysis` and `record` it drops the wrong path, which there is the finding.

## Example

Bad: "Hi team, I may have possibly found something: it seems like the scheduler might be assigning two jobs to one node in some cases (see my earlier message). Let me know if you want me to dig deeper. Thanks!"

Good: "Two jobs landed on one node. Job `<job-a>` and job `<job-b>` both show `<node>` in their placement at 09:40 UTC; the node has 4 GPUs and each job asked for 4. Workaround: pinning `<job-b>` to a second node ran it clean. Options, if useful: a placement assert in the launcher, or a per-node admission cap of one job."
