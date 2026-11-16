---
name: session-check
description: Use when you need to know where a session stands, mid-session, before handing off, or before session-closeout; reconciles what this session owns against what the repo records and reports landed, in flight, stranded, owed and next, writing nothing.
---

# session-check: reconcile what the session did against what the repo records

The thread of a session lives in the repo, not in the conversation, and it is lost when the two disagree. This skill compares them and names every gap. Side A, what this session owns and what each row is doing, comes from [`session-scope`](../session-scope/SKILL.md), unchanged. Side B is the record: the `projects/` boards of the knowledge base (KB) research topic the session works on, when the topic has that stage; the current week's `worklog/` file in the primary KB; the lessons in the KB's `memory/` and in `docs/casebook/`; and the remote of each repo the session changed (pushed branches and pull requests). The report sorts the work into landed, in flight and stranded, lists the records the rules already require, and derives the next step from the record rather than from memory. It writes nothing, so it is safe to run any time you have lost the thread. A clean report is a valid outcome, and it still names what it could not check.

## When not to use

- To find out what the session owns: that is `session-scope`, which this skill runs first.
- To land, write a record, stop a task or reap a worktree: that is [`session-closeout`](../session-closeout/SKILL.md). Every write belongs there.
- To audit a whole repository, other sessions' branches, or a research topic's backlog. This report covers this session's rows only.

## Stages

### 1. Take side A from session-scope

Run [`session-scope`](../session-scope/SKILL.md) and carry its report through unchanged: identity, every owned row with its ownership tier and write class, the harness rows, the untracked side, the footprint and the gaps. Do not re-derive any of it, and do not restate what a tier or a write class means; link that file. Two definitions drift the moment either one changes.

Read its `GAPS` before you continue. A gap there is side A admitting what it could not settle. A reconciliation that treats an admitted gap as a clean read produces a confident wrong answer where `unknown` was the true one.

### 2. Find side B: which records apply to this session

```bash
ybase kb                                  # the KBs, primary first
python3 -c 'import datetime; y, w, _ = datetime.date.today().isocalendar(); print("%d-W%02d" % (y, w))'
git -C <repo> fetch origin                       # each repo the session changed; moves remote-tracking refs only
```

- **What the session works on.** Name it: YBase itself, a managed repo from `ybase repos`, or a KB research topic under `<kb>/research/<topic>/`. There is no machine-wide pointer to it; the session's own request and its owned rows from side A say which.
- **Topic boards.** For a research topic, open its `CASE.md` and read the `stages:` list. If it includes `projects`, the boards and experiment records under `<kb>/research/<topic>/projects/` are side B for that work, per [`templates/research-topic/PIPELINE.md`](../../../templates/research-topic/PIPELINE.md#projects). If it does not, there is no board: say so in `BOARD` rather than inventing one.
- **Repo work has no board.** A session that changed YBase or a managed repo's code or docs will find every topic board silent. That silence is an artifact of which file was opened, not a finding. Its record is the worklog, and the repo's own records where its `AGENTS.md` names them.
- **The worklog.** `<primary KB>/worklog/<ISO week>.md`, the week the command above prints. Its format is in [`templates/kb/worklog/README.md`](../../../templates/kb/worklog/README.md).
- **The lessons.** Each KB's `memory/INDEX.md` routes to one folder per repo; [`docs/casebook/INDEX.md`](../../../docs/casebook/INDEX.md) routes to the generic groups. Search both for the topic of anything that went wrong this session: `grep -rn "<words>" <kb>/memory/ docs/casebook/`.
- **The remote.** For each owned branch: `git -C <repo> rev-parse origin/<branch>` and, if the forge has a CLI, its pull request state, for example `gh pr list -R <owner>/<repo> --head <branch> --state all --json number,state,isDraft,headRefOid,url`. Without a forge CLI, the PR state is a gap, not an assumption.

### 3. Read the board before you resolve anything

For every task this session touched, open its row on the board and read it whole. A row can already carry a prediction, a falsifier or a decision someone wrote while they held the evidence; landing first and reading later turns that into a follow-up commit. Never infer a board's contents from the conversation.

Report which boards you read. "No row exists" and "I opened the wrong board" produce the same empty result and mean opposite things.

### 4. Sort the work into landed, in flight and stranded

Each claim is read from the surface its consumer reads ([`docs/rules.md`](../../../docs/rules.md) rule 5), never from your own memory of doing it.

| Claim | Read it from | Not from |
|---|---|---|
| this landed | `git show <landing>:<path>` after a fetch, or `git cherry <landing> <branch>` showing only `-` lines (`<landing>` is the ref the inventory prints, such as `origin/master`) | the push output, or your own commit |
| this branch is pushed | `git rev-parse origin/<branch>` equals the local tip | "Everything up-to-date", which also prints when you pushed the wrong ref |
| this PR is open, draft, at my tip | the forge's PR view: state, draft flag, head commit | memory of opening it |
| this run or job is alive | the artifact it exists to produce, or its scheduler's own state | a pid, or a "Running" line in its launch output |
| this task finished | its output, or the harness listing | that you stopped hearing from it |
| this worktree is safe to remove | its verdict and reason in `ybase worktrees` | a branch name or a commit subject |

**A pushed branch is not a landed change, and a draft PR is in flight.** Under the framework's default landing convention ([`docs/law/push.md`](../../../docs/law/push.md); a repo's own `AGENTS.md` may set another) a change lands when its pull request merges into the landing ref; until then the default branch serves the old text.

**Stranded means the only copy is on this machine**: commits on no remote ref, untracked or uncommitted files in an owned worktree, an owned branch with no worktree and no upstream. When session-scope flagged the row `EPHEMERAL`, stranded work dies when the instance stops; put those rows first.

### 5. Derive the next step from the record

Take the next step from the board row and the plan it belongs to, never from the conversation, which is the thing about to be lost. Where the board is silent, say so: that silence is a missing row and a finding, not permission to invent a next step. For framework work, the next step comes from the worklog's latest entry for that area, or from the user.

### 6. List what is owed

`OWED` is derived, never invented: each line is a write some existing rule or contract already requires, and it names that rule. Look for each of these, and say that you did:

- a mistake of this session's own that cost real time or produced a wrong claim and is not yet a lesson in the primary KB or a proposed casebook entry (rule 17; [`docs/kb.md`](../../../docs/kb.md), "Where new content goes");
- a corrected claim whose other sites still assert the old one (rule 6);
- an experiment record with no numbers under its results, or an opportunity whose status was not updated after a run tested it ([`docs/flows.md`](../../../docs/flows.md), "Analyze a run");
- a literature note with no catalog row ([`docs/flows.md`](../../../docs/flows.md), "Add a source note");
- a change with no entry in this week's worklog in the primary KB;
- a YBase commit made without its worktree's own `bin/ybase check` passing (rule 19; the root `bin/ybase` checks only the main checkout), or a managed repo's commit made without the checks its `AGENTS.md` names;
- stranded work on non-durable storage that has not been pushed ([`docs/flows.md`](../../../docs/flows.md), "Start a unit of work", step 3).

An empty `OWED` is a fine outcome, and it is a claim that you looked for each item above.

## Output

```
SCOPE      session-scope's report, carried through unchanged as side A
LANDED     what reached the landing ref, each with the ref and command it was read from
IN FLIGHT  pushed branches and open or draft PRs, each with its state and head commit;
           live tasks and jobs, with where their progress is written
STRANDED   commits, files, branches and worktrees whose only copy is here; EPHEMERAL first
BOARD      the topic and boards read (or "no projects stage" / "repo work: no board"),
           each touched row with its state and any prediction it already carries
OWED       each record a rule already requires, with the rule or flow that requires it
NEXT       the next step and the row or entry it comes from, or "board is silent"
GAPS       session-scope's gaps, carried, plus side B's: boards not read, PR state not
           reachable, rows established on one side only
```

`GAPS` is never empty. Nothing here reports the namespace: how many branches and worktrees the repository carries is a fact about the repo, and session-scope says why it stays out of an owned-rows report.
