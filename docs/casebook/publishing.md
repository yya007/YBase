# publishing.md: lessons about making work public

<!-- BEGIN TRIGGERS -->
- `a-scrub-needs-an-independent-second-pass` - before publishing anything derived from a private source.
- `a-generic-sounding-detail-can-still-be-a-fingerprint` - reviewing scrubbed text that no longer says "we" or "our".
- `a-committed-deny-list-leaks-what-it-denies` - deciding where a list of private terms should live.
- `a-commit-message-is-published-too` - writing a commit message in a repository that will be public.
- `rewritten-history-survives-until-pruned` - after amending or rebasing to remove something from history.
<!-- END TRIGGERS -->

## a-scrub-needs-an-independent-second-pass
2026-10. A set of documents was moved out of a private workspace for public release. Several agents scrubbed it file by file against a written brief, and each one's own self-check came back clean. Fresh auditors then diffed every file against its original, with a list of the private facts in hand, and still made dozens of further fixes.
**Why it matters:** the author of a scrub checks for what they already thought to remove. The survivors are exactly the things they did not think of.
**How to apply:** after the scrub, give a different reader the originals, the scrubbed files and a list of private facts to hunt for (kept outside the repo). Ask for a per-file verdict, not one aggregate pass.

## a-generic-sounding-detail-can-still-be-a-fingerprint
2026-10. Most of the misses in the second pass contained no pronoun at all. They were the private configuration restated as a generic example: a set of numbers that matched the private setup, an internal nickname presented as a public convention, and a decision framing carried over from an internal plan.
**Why it matters:** removing "we" and "our" leaves the facts in place. A specific combination of numbers identifies a setup as reliably as its name.
**How to apply:** for every sentence that survived from a passage about the private system, ask whether it is a fact about a public source or private analysis with the pronouns removed. Replace private-matching numbers with the source's own numbers, or with a neutral range.

## a-committed-deny-list-leaks-what-it-denies
2026-10. Designing the `leaks` check raised the question of where its list of private terms should live. A committed list would publish every term it exists to protect.
**Why it matters:** the safest-looking place, in the repository next to the check, is the one place the terms must never be.
**How to apply:** private terms live only in a knowledge base's `deny.list`, which is never part of this repository and is created by `bin/ybase setup`. The committed check carries only generic patterns: keys, tokens, personal paths and emails.

## a-commit-message-is-published-too
2026-10. While removing uncited mentions of an organisation from the files, the commit that did it was titled after that organisation. The file content was clean; the history was not.
**Why it matters:** commit messages, author names and author emails ship with every clone, and nobody re-reads them before pushing.
**How to apply:** the `leaks` check reads every commit message after the `.leaks-baseline` commit, and checks every identity in that range against the `deny.list` files. Describe a scrub commit by what it does ("trim uncited attributions"), never by what it removed.

## rewritten-history-survives-until-pruned
2026-10. After every commit was rewritten to a new author identity, the old commits were still in the object store: reachable from the reflog and from `ORIG_HEAD`, which the rewrite had left behind.
**Why it matters:** anything that copies the `.git` directory, rather than pushing a ref, carries the old commits with it.
**How to apply:** after a rewrite, run `git reflog expire --expire=now --all && git gc --prune=now`, delete a leftover `ORIG_HEAD`, and confirm with `git cat-file --batch-all-objects --batch-check` that only the commits you mean to keep remain.
