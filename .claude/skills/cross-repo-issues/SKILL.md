---
name: cross-repo-issues
description: Use when asked what is open across the managed repos ("what issues are open", "triage my repos", "anything assigned to me anywhere"), or to file a new issue in whichever managed repo it belongs to; lists open GitHub issues across every managed repo with a GitHub remote, grouped by repo, and files a new issue only after showing the draft and getting the user's say-so.
---

# cross-repo-issues: read issues across the managed repos, file each where it belongs

Each managed repo keeps its own issues (rule 21 in [`docs/rules.md`](../../../docs/rules.md)), so nobody sees them together unless something reads them together. This skill lists the open issues of every managed repo that has a GitHub remote, grouped by repo, through `gh issue list -R`. It also files a new issue in the one repo it belongs to, after the user has read the draft. Listing is read-only. Posting is a published act that notifies people and cannot be unsent, so nothing posts until the user says to.

## When not to use

- To work on an issue: that is ordinary work in the repo, in a worktree from `ybase wt <kind>/<subject> --repo NAME`.
- To review a pull request: [`review-pr`](../review-pr/SKILL.md), or [`land-pr`](../land-pr/SKILL.md) for your own.
- For a repo that is not in the repo list: use `gh issue list -R <owner>/<repo>` directly.
- To close, label, assign, comment on or edit existing issues. Each of those is a published change; do one only when the user names it, and show it first like a new issue.

## Stages

### 1. Find the repos with a GitHub remote

```bash
eval "$(ybase env)"; S="$TMPDIR/cross-repo-issues"; mkdir -p "$S"
ybase repos                                  # name, local path, present or missing
git -C "$(ybase repos path <name>)" remote get-url origin    # each present repo
```

A remote on `github.com` gives `<owner>/<repo>`. A repo with no local clone still has the remote recorded in the Remote column of `repos.md` in the knowledge base (`ybase kb` lists the KBs); read it there. A repo with no remote, or one on another host, is not read: list it under `not read` with the reason, never leave it out silently.

### 2. Check that you can read before you count

```bash
gh auth status
```

A `gh` that is missing or logged out fails as an error, not as an empty list, and the two are easy to confuse. If it is not logged in, stop and say so; logging in is the user's step.

### 3. List the open issues

One call per repo, saved in scratch:

```bash
gh issue list -R <owner>/<repo> --state open --limit 200 \
  --json number,title,labels,assignees,author,updatedAt,url > "$S/<repo>.json"
```

Add `--assignee @me`, `--label <name>` or `--search "<words>"` when the user asked for a slice. Read each result before the next:

- A count equal to `--limit` means the list was cut. Raise the limit and run again, or report the count as a lower bound.
- An error saying issues are disabled, or that the repo cannot be found, is a `not read` line with that message, never zero issues.
- Pull requests are not issues; `gh issue list` leaves them out, and the report says so.

### 4. Report, grouped by repo

Group by repo, newest update first within each. Give each repo's count with the time it was read, labelled `[M]` (rule 2). Where issues in two repos look like the same problem, say so in the report to the user only: an issue in one managed repo never mentions a sibling repo, YBase or its knowledge base (rule 22), so the link lives in this report and nowhere on GitHub.

### 5. File a new issue, only after the user has read it

1. **Pick the repo it belongs to**: the one whose code or docs would change to fix it (rule 21). A problem that spans repos becomes one issue per repo, each complete on its own, none naming the others. When the right repo is unclear, ask, with your recommendation.
2. **Read that repo's rules for issues.** Its `AGENTS.md` and `CONTRIBUTING.md`, and its issue templates (`.github/ISSUE_TEMPLATE/`), read by path in the clone or with `gh api "repos/<owner>/<repo>/contents/.github/ISSUE_TEMPLATE"`. Where they say how an issue is written or labelled, they win (rule 20).
3. **Search for an existing issue first**, open or closed: `gh issue list -R <owner>/<repo> --state all --search "<words>"`. If one covers it, show it to the user instead of drafting a duplicate.
4. **Draft in scratch**: the title in one line, the body in `$S/<repo>-<slug>.md`, following the repo's template. The body states the problem and the evidence a stranger needs: what happened, what was expected, how to reproduce. Plain English ([`docs/writing.md`](../../../docs/writing.md)), and no em dashes: `LC_ALL=C grep -n "$(printf '\342\200\224')" "$S/<repo>-<slug>.md"` must print nothing. Check that it names no private path, sibling repo, YBase or knowledge-base content.
5. **Show the draft and stop.** In chat: the repo, the title, the full body, any labels and assignees. Then one line: `Nothing posted; say "post" to file it in <owner>/<repo>.` A request to file an issue asks for the draft, not for posting it.
6. **Post once told to**, then read it back from GitHub, not from the create output (rule 5):
   ```bash
   gh issue create -R <owner>/<repo> --title "<title>" --body-file "$S/<repo>-<slug>.md"
   gh issue view <number> -R <owner>/<repo> --json number,title,url,state
   ```

## Output

Listing:

```
cross-repo-issues: <YYYY-MM-DD HH:MM UTC>   repos read <n> of <m>
<repo> (<owner>/<repo>): <k> open [M]
  #<number>  <title>  <labels>  <assignees>  updated <date>
  ...
not read: <repo>: <no remote | not on GitHub | issues disabled | error>
possibly related across repos (not linked on GitHub): <repo#n> ~ <repo#m> ...
```

Filing: the draft as in stage 5, then after posting `Filed <url> in <owner>/<repo>, read back: <state>.`
