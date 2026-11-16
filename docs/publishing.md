# Publishing: a private clone and its public repository

You can develop YBase in a private repository and publish it to a public one. The private repository is the source of truth. The public one receives snapshots and takes pull requests from other people.

| Direction | Command | What moves |
|---|---|---|
| private to public | `ybase publish` | one snapshot of the committed tree, as a pull request |
| public to private | `ybase absorb` | each public contribution, as a cherry-pick with its author kept |

## Set it up

Add the public repository to the `.env` of the one machine that publishes:

```
YBASE_PUBLIC_REPO=owner/name
```

The value is a GitHub `owner/name`, or any git URL or path. That machine must also have your knowledge base, because the gate reads its `deny.list`. No CI job can publish: the private terms are never in a repository.

## Publish

```
ybase publish --dry-run   # run the gate, push nothing
ybase publish             # run the gate, push sync/<rev>, open a pull request
```

`publish` exports the committed tree at `HEAD` and leaves out every path in `.publishignore`, a file at the root of the private repository that is itself left out. It refuses when tracked files have uncommitted changes, when `HEAD` is not the pushed tip of its upstream, and when the public repository holds a contribution that is not absorbed yet.

The gate runs on the export, inside a clone of the public repository. Nothing is pushed unless every part passes:

1. The check registry, with this machine's deny lists. It reads every file, and every commit message and author already in the public history.
2. The publication checks: the licence file is the expected one; `README.md`, `CONTRIBUTING.md` and `SECURITY.md` exist; no ignored path survived; no symlink leaves the tree; no environment file and no file over 1 MB is present.
3. `gitleaks`, when it is installed. When it is not, the output says the scan was skipped.
4. The export's own test suite, which proves the public tree works without the paths that were left out. `--skip-tests` leaves this out and the pull request says so.

The public history is made of snapshots. Each one is a single commit titled "Sync from upstream" with an `Upstream-Rev:` trailer. No private commit, message or author is pushed.

The first publish to an empty repository pushes the default branch itself, named `master`, because a pull request needs a base. Every later publish is a pull request that a person merges.

Before the first publish, and after any large change, have a second reader go through the export with your list of private facts in hand. A scan finds the terms you thought of; a reader finds the ones you did not ([case](casebook/publishing.md)).

## Absorb a contribution

1. Review and merge the contributor's pull request in the public repository.
2. In a worktree of the private repository, run `ybase absorb`.
3. Run the tests and `ybase check`, then land the branch as you land any other.

`absorb` fetches the public default branch and cherry-picks every commit that is neither a snapshot nor already absorbed. Each pick keeps its author and records the public commit it came from. A commit that does not apply cleanly stops the command with the file named; resolve it, run `git cherry-pick --continue`, then run `absorb` again.

The next `publish` after an absorb changes nothing for those files, because both sides already agree.

## What a contributor cannot change

A path in `.publishignore` does not exist in the public repository, so a public pull request cannot touch it.
