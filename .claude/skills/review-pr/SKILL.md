---
name: review-pr
description: Use when asked to review a pull request someone else wrote ("review this PR", "take a look at PR 123", "what do you think of this diff"); drafts the review in chat and posts it only when the user says to.
---

# review-pr: draft a verified review of another author's PR, post it on request

This skill turns a pull request (PR) you did not write into a review the user can approve line by line. Every finding is read out of the file at the PR's head commit, not out of the diff hunk, a bot's summary or your own earlier notes, because each of those hands you findings that dissolve on contact with the file. The review is drafted in chat and nothing reaches GitHub until the user says to post, because a comment on a colleague's PR costs them a read and a reply whether or not it was right, and it cannot be unsent. It works on any GitHub repository through the `gh` CLI.

## When not to use

- The PR is yours: use [`land-pr`](../land-pr/SKILL.md). Most of what a review does is wrong on your own PR.
- You want a pre-commit look at your own uncommitted diff: that is a self-review, with no PR and no posting.
- The thing to review is a design document, not a code change.

## Stages

Set up once. `R` is `<owner>/<repo>`, `N` the PR number. For a managed repo, take `R` from its remote, `git -C "$(ybase repos path NAME)" remote get-url origin`, and read that repo's `AGENTS.md` for its review conventions, which win there ([`docs/rules.md`](../../../docs/rules.md) rule 20). A repo you do not manage needs no local clone: every read below goes through `gh`. All scratch files go under the profile's scratch (rule 16):

```bash
eval "$(ybase env)"; R=<owner>/<repo>; N=<pr>
S="$YBASE_SCRATCH/review-pr-$N"; mkdir -p "$S"
```

1. **Refuse your own PR, and note the state.**
   ```bash
   gh pr view "$N" --repo "$R" --json author,state,isDraft --jq '"\(.author.login) \(.state) draft=\(.isDraft)"'
   gh api user --jq .login
   ```
   If the two logins match, stop and say so. If the PR is closed or merged, ask before going on. This reads authorship from GitHub, not from how the request was worded, which is the whole guard.

2. **Read the head facts from the PR, not from your checkout.**
   ```bash
   gh pr view "$N" --repo "$R" --json headRefOid,baseRefName,title,body,files > "$S/pr.json"
   python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(d['headRefOid'],d['baseRefName']);[print(f['changeType'],f['path'],f['additions'],f['deletions']) for f in d['files']]" "$S/pr.json"
   HEAD=<headRefOid>
   ```
   Hold `HEAD` and each file's `changeType`. A local checkout is whatever branch you last pulled; the PR head is what the author asks you to judge. `MODIFIED` means a layout or default may predate this PR, which kills a whole class of false finding.

3. **Read what other reviewers already said.**
   ```bash
   gh api "repos/$R/pulls/$N/comments?per_page=100" --paginate --jq '.[] | "\(.user.login) \(.path):\(.line // .original_line) \(.body[0:100])"'
   gh pr view "$N" --repo "$R" --json reviews,comments --jq '.reviews[],.comments[] | "\(.author.login) \(.state // "comment") \(.body[0:150])"'
   ```
   An automated reviewer (a bot such as a hosted code-review app) usually covers line-level correctness. Spend your pass where it cannot see. This read expires; stage 6 repeats it.

4. **Sweep eight areas and collect candidates.** None is a finding yet.
   1. *Correctness on the changed lines.* The usual reading, and the area a bot already covers.
   2. *Design shape.* What a caller is forced to know: two booleans that encode three states, a flag that changes what another field means.
   3. *Placement.* Does the new file sit where its neighbours that do the same job sit? Name the precedent if you suggest a move.
   4. *What it can discard in silence.* For every path that drops, truncates, filters or skips: what number would tell an operator it happened? Success and failure that look the same is the defect.
   5. *Blast radius.* Grep the consumers and the tests of every changed symbol, default or field meaning; do not argue about them.
   6. *What the base allows.* A finding must hold against the branch the PR targets, not against some other branch.
   7. *What it newly makes possible.* A change that lifts a constraint leaves values chosen for that constraint, often with a comment still giving the old reason. Grep the touched files for the retired reason.
   8. *Backwards and sideways.* Could the bug this fixes already have happened, and would anyone know? Which sibling configs, scripts or launchers share the changed setting, and do they still agree?

   Areas 7 and 8 are two mechanical calls each:
   ```bash
   gh api -H 'Accept: application/vnd.github.raw' "repos/$R/contents/<file>?ref=$HEAD" | grep -n '<retired-term>'
   gh api "repos/$R/contents/<dir-of-file>?ref=$HEAD" --jq '.[].name'
   ```

5. **Verify every candidate against the head blob.**
   ```bash
   gh api -H 'Accept: application/vnd.github.raw' "repos/$R/contents/<path>?ref=$HEAD" > "$S/head_<name>"
   ```
   Read the whole enclosing function, not the hunk, and ask two questions. Is the behaviour you dislike the function's actual job (a builder that assigns a field is building, not mutating)? Did this PR choose it, or inherit it (`changeType`)? When a finding names something the diff does not contain, such as an image, a config profile or a follow-up PR, list it in the tree first; a scope copied from the author's own comment may not exist. A candidate whose file, symbol or line you have not read at `HEAD` is dropped or read. There is no third option.

6. **Re-read the head, then draft.** Repeat the head call of stage 2 and the comment calls of stage 3. If `headRefOid` moved, redo stage 5 at the new head for every candidate: a comment on a problem the author already fixed shows you read something stale. A span that now carries another reviewer's thread gets a reply in that thread, not a second comment.

   Send the whole review to the user as chat text:
   ```
   body: <one or two sentences: the PR looks good / the comments are inline>

   | ID | Anchor | Side | changeType | Area | Kind | Blocking? | Sev | Conf | At head | Overlap |
   | F1 | path/to/file.py:42 | RIGHT | ADDED | 4 | silent-drop | No | Low | High | Stands | none |

   F1  read: <what you read at HEAD, and what it said>
       comment: <the exact text that will post, two to five lines>
   ```
   `At head` is `Stands` or `RESOLVED by <sha>`. `Overlap` names who already has a thread on that span. `Blocking?`, `Sev` and `Conf` are the user's triage; they never appear in a `comment:` line, where they read as a verdict on someone's work. The `read:` line carries the evidence so the comment does not have to.

   How a comment reads (the voice is [`docs/writing.md`](../../../docs/writing.md)):
   - **One finding per comment**, two to five lines, anchored at the narrowest line it fits. The review body never summarises the findings.
   - **State the observation, then ask a question**: "This returns before the counter moves, so a skipped row is never counted?" reads as a colleague checking and survives being wrong.
   - **Offer an option, do not prescribe a patch**: "we could log the count here", "have we considered X?". The author knows the file better than you.
   - **Every comment ends in a step the author can take.** `nit:` is the only label. Praise is one clause, at most.
   - **A number only when the number is the finding.** Otherwise name the file and symbol so they can look.
   - **A ping about a specific line is answered at that line**, quoting the tagging sentence. A deleted line is commentable at `side: LEFT`.
   - **Nothing from the home repo.** A comment on a managed repo's PR never mentions YBase, its knowledge base or sibling repos (rule 22).
   - **No em dashes.** No hook sees a PR comment, so check the draft yourself: `LC_ALL=C grep -n "$(printf '\342\200\224')" "$S/draft.md"` must print nothing.

7. **Stop. Nothing posts until the user says to.** This holds even when every finding is verified, since the drafting pass is where wrong-but-verified findings die. "They asked for a review" asks for the review, not for posting it. "I will post and delete anything wrong" sends a second notification. "The user is away" blocks nobody: an unposted review costs nothing. A `--method POST` in your next command, posting "the safe ones" first, or choosing `REQUEST_CHANGES` yourself each mean go back to stage 6.

8. **Post one review, once told to.** If more than a few minutes passed, re-run stage 6's head check first. Write `$S/review.json`:
   ```json
   {"commit_id": "<HEAD>", "event": "COMMENT", "body": "<body>",
    "comments": [{"path": "a.py", "line": 42, "side": "RIGHT", "body": "<F1>"},
                 {"path": "b.py", "start_line": 10, "line": 14, "side": "RIGHT", "body": "<F2>"}]}
   ```
   ```bash
   gh api --method POST "repos/$R/pulls/$N/reviews" --input "$S/review.json" --jq .html_url
   ```
   One review, not loose comments. The event is `COMMENT` unless the user chose otherwise. Every anchor must sit inside a diff hunk. A reply to an existing thread goes to `repos/$R/pulls/$N/comments/<id>/replies` instead. If the posted count differs from the approved one, say what merged or split in the same message.

9. **Read the review back off the PR** ([`docs/rules.md`](../../../docs/rules.md) rule 5), not from the POST response:
   ```bash
   gh api "repos/$R/pulls/$N/comments?per_page=100" --paginate --jq ".[] | select(.user.login==\"$(gh api user --jq .login)\") | \"\(.path) \(.start_line // \"-\")->\(.line)\""
   ```
   Check each anchor landed where the draft said, and the count matches.

10. **Loop back.** A finding of yours that turned out wrong, and what would have caught it, becomes a lesson (rule 17), routed as [`docs/kb.md`](../../../docs/kb.md) says: in the primary knowledge base if it names anything private, else proposed for `docs/casebook/`. A real finding the author declines is reported to the user, not re-argued in the thread.

## Output

Before posting (stage 6), the chat message is the draft exactly as shown above: the `body:` line, the table, then one `read:` and `comment:` pair per finding, followed by one line: `Head <sha>, re-read at <time>. Nothing posted; say "post" to send.` Candidates dropped at stage 5 are listed after it, one line each, with the reason.

After posting (stage 9):
```
Posted review <html_url> at head <sha>: <k> comments (<k> approved). <what moved, if anything>
Anchors read back: <k>/<k> as drafted.
```
