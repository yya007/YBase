# git.md: lessons about branches, folders and history

<!-- BEGIN TRIGGERS -->
- `compare-folders-by-tree-sha-and-carry-a-commits-own-delta` - carrying one folder or one commit from a branch onto another base, or checking whether two branches agree on a folder.
- `audit-a-history-rewrite-by-content-against-the-archived-tip` - before and after squashing, rebasing or otherwise rewriting a branch that others have pushed to.
- `a-failed-commit-leaves-its-files-staged` - running several commits in a row, from a script or one after another, and before pushing them.
<!-- END TRIGGERS -->

## compare-folders-by-tree-sha-and-carry-a-commits-own-delta
2026-11-02. When a folder has to move from one branch onto another base, three shortcuts each lose work quietly. Comparing one file says nothing about the folder; `git checkout <sha> -- <path>` copies the folder's whole state and silently reverts anything the base changed there since; and a hosting service's compare endpoint caps the number of files it lists, so it can report no difference inside a folder that differs.
**Why it matters:** each shortcut looks like a clean result, and the loss shows up only when someone misses their change later.
**How to apply:** compare folders by tree sha (`git rev-parse <A>:<path>` against `<B>:<path>`), carry a commit's own delta restricted to the folder (`git diff <sha>^ <sha> -- <path> | git apply --index`), and compare locally rather than through an API.

## audit-a-history-rewrite-by-content-against-the-archived-tip
2026-11-02. A squash or rebase changes history and must change no content, but the usual checks do not prove that. A three-dot diff against the rewritten branch collapses, because the merge-base moved, and attributes the branch's whole old history to whatever it is compared with.
**Why it matters:** after a rewrite, every other branch cut from the old history reads as hundreds of commits behind, and a lost commit hides inside that noise.
**How to apply:** before rewriting, push the tip to an archive ref and read it back. After, `git diff <archive> <new-tip>` must be empty, and every other branch's merge-base is re-derived (`git merge-base --is-ancestor`) rather than read off a diff. The `consolidate-branch` skill carries the full procedure.

## a-failed-commit-leaves-its-files-staged
2026-07-05. A scripted series of seven commits had its first three refused by the pre-commit hook. A refused `git commit` leaves its files staged, so the fourth commit, the first to succeed, swept up everything the three failed ones had staged: four concerns under one wrong message. It was pushed before anyone noticed.
**Why it matters:** the series looks complete at the end, and the damage is visible only in what each commit contains.
**How to apply:** in any run of several commits, check each commit's exit status and `git log -1` before staging the next. Before pushing, compare `git show --stat` of every commit with the grouping you intended.
