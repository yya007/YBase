# ADR 0007: Publish by snapshot, under a noncommercial licence

- Status: Accepted
- Date: 2026-11-15

## Context

YBase is developed in a private repository and is to have a public one. Three things had to be decided: how content leaves, how contributions come back, and what the licence allows.

The private history cannot be pushed as it is. The leak check reads commit messages only after a baseline commit, so older messages and author identities were never scanned. The private terms live only in a knowledge base on the owner's machine, so no hosted CI job can run the full scan.

## Decision

1. **Snapshots, not history.** `ybase publish` exports the committed tree, less the paths in `.publishignore`, and commits it to the public repository as one commit. Private commits, messages and authors stay private.
2. **The gate runs on the publishing machine.** It needs the deny lists, so publishing is a local command and never a CI job. It refuses when the leak scan has no deny-list terms.
3. **A pull request is the review point.** `publish` pushes a `sync/` branch and opens a pull request; a person merges it. Only the first publish to an empty repository pushes the default branch.
4. **The private repository stays the source of truth.** A public contribution is merged in public, then `ybase absorb` cherry-picks it into the private repository with its author kept.
5. **The licence is the PolyForm Noncommercial License 1.0.0.** It allows personal, research, educational and nonprofit use and forbids commercial use. Contributors license their changes to the project owner on terms that let the owner relicense ([`CONTRIBUTING.md`](../../CONTRIBUTING.md)).

## Considered and not chosen

- **Mirroring the history**, filtered: any miss is permanent, and a rewrite of public history breaks every clone.
- **Renaming or rewriting content during export**: a public patch would no longer apply to the private tree unchanged.
- **Publishing on a schedule**: nothing would look at a snapshot before it left.
- **MIT with the Commons Clause, the Business Source License, CC BY-NC-SA**: the first still allows internal business use, the second becomes open after a fixed time, and the third is not written for software.

## Consequences

- YBase is source-available, not open source as the Open Source Initiative defines it. The docs must not call it open source.
- The public history shows snapshots and contributors' commits. It does not show how a change was developed.
- A contribution reaches the private repository only when someone runs `absorb`. Until then the two sides differ, so `publish` refuses while any public commit is not absorbed.
- The export must pass its own tests without the ignored paths, which keeps `.publishignore` honest.
