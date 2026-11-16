# Profile: docs

Long-form written material. This profile is about cost, not perspective: the reason to delegate is that the output is large, not that a second opinion helps.

## When

- `docs_target_words` threshold tripped
- Guides, READMEs, migration notes, changelogs, runbooks, release notes
- Any document long enough that drafting it inline would crowd the task it belongs to

## Command

```
codex exec -s read-only -o <artifact> "<prompt below>"
```

## Prompt template

```
Write <document type> for <subject>, targeting roughly <N> words.

Ground every claim in this repository. Read the code, config, and existing docs before
writing. Where the repo already documents something, match its terminology and structure
rather than inventing a parallel vocabulary. Existing docs to match in tone: <paths>.

Audience: <who reads this and what they already know>.
Must cover: <required sections>.
Out of scope: <what not to write about>.

Write the document itself as the final message, with no preamble and no meta-commentary about
what you are about to write. Open with a one-line SUMMARY comment stating what the
document covers and its approximate length, then the document body.

Flag anything you could not verify in the repo with an inline TODO rather than writing a
plausible guess. A confident sentence about behavior you did not check is worse than a
gap.
```

## Handling

The leading SUMMARY line exists so the digest is meaningful without reading the document. Review the TODOs before the document is used: unverified claims are the main failure mode of delegated writing. Move the artifact to its real home in the repo once checked; the artifact directory is scratch space, not a publication target.

The repo's house style applies to whatever gets committed: in YBase, [`docs/writing.md`](../../../../docs/writing.md), and the `proofread` skill before it ships; in a managed repo, the style its own `AGENTS.md` names.
