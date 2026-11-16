---
name: adopt
description: Use on the first run of YBase on a machine that already has repos, or when asked to adopt, onboard or take stock of the existing repos and agent setup; inventories the git repos under the repos root and every skill and agent-facing doc, sorts each into shared, duplicate, repo-specific or installed, and after approval writes repos.md in the primary knowledge base.
---

# adopt: take stock of the repos and agent setup already on this machine

YBase manages repos that already exist, each with its own `AGENTS.md`, `CLAUDE.md`, skills and habits, and the user has skills of their own besides. This skill is the first-run flow: it finds every git repo under the repos root and every skill and agent-facing doc, sorts each item into one of four kinds, and proposes where each should live, together with a draft of the repo list. It changes nothing until the user approves, and then it writes the repo list into the primary knowledge base (KB) and renders the pointers every session loads. It is safe to run again: a second run shows what changed since the first.

## Ground rules

These hold for the whole run. Say them to the user at the start.

1. **Look facts up yourself.** A path, a remote, a visibility or a date is read with a command, never asked. Ask the user only for decisions.
2. **Ask decisions in numbered rounds, each with a recommended answer.** One round per stage that needs one, every question numbered, your recommendation and its reason beside it, so the user can reply "1 yes, 2 b, 3 as recommended".
3. **Stay read-only until approved.** Until the user approves the table in stage 6, the only file you write is the proposal in scratch.
4. **Never read `.env` or secret files**, in YBase or any repo: `.env*`, `*.pem`, `*.key`, credential and token files, and settings files (`.claude/settings.local.json`, user-level settings). List a skill folder's contents; never open a settings file.
5. **A change in a child repo goes on a new local branch** in a worktree (`ybase wt chore/adopt-cleanup --repo NAME`), committed there and left for the user. Read that repo's `AGENTS.md` first; its rules win in it ([`docs/rules.md`](../../../docs/rules.md) rule 20).
6. **Never push**, in any repo, and never open a pull request. Publishing is the user's step.

## When not to use

- To add one repo the user has named: add its row to `repos.md` in the primary KB and run `ybase repos render` ([`docs/kb.md`](../../../docs/kb.md)).
- To lift what the managed repos have in common into YBase: that is [`harvest`](../harvest/SKILL.md), which needs the repo list this skill writes.
- To set up the machine itself (profile, scratch, worktree directory): `bin/ybase setup`.

## Stages

### 1. Find the starting point

```bash
eval "$(ybase env)"; mkdir -p "$TMPDIR/adopt"
ybase kb          # KBs, primary first; each ok, missing or no-skeleton
ybase repos       # repos already listed: name, local path, present or missing
```

The primary KB is the first line of `ybase kb`. If it is `missing` or `no-skeleton`, the fix is `ybase kb init`; that is a decision for round 1, not a step to take now.

The repos root is where managed repos are cloned: the directory that contains YBase, unless `YBASE_REPOS_ROOT` in `.env` says otherwise. You do not read `.env`, so derive it: if `ybase repos` lists a repo, the parent of its path is the root (unless that one repo has its own override). If nothing is listed, take the directory that contains YBase and confirm it in round 1.

### 2. Inventory the git repos

List every clone under the repos root. A `.git` directory marks a clone; a `.git` file marks a linked worktree or a submodule, which belongs to some other clone and is not counted:

```bash
root=<repos root>
find "$root" -maxdepth 3 -name .git -type d -prune 2>/dev/null | sed 's#/\.git$##' | sort > "$TMPDIR/adopt/clones.txt"
```

Then, for each clone, by path from the YBase root (rule 23):

```bash
git -C <path> remote get-url origin              # none: a local-only repo
git -C <path> log -1 --format='%cs %h'           # last commit date and sha
gh repo view <owner>/<repo> --json visibility --jq .visibility   # GitHub remotes only; else "unknown"
```

Record path, remote, visibility and last commit for each. A repo whose visibility cannot be read (no `gh`, not logged in, another host) is `unknown`, never assumed private or public. YBase's own clone is in the list; mark it as the home, not a managed repo.

### 3. Inventory skills and agent-facing docs

For each clone, read only tracked files (`git -C <path> ls-files`):

- `AGENTS.md`, `CLAUDE.md`, and the docs `AGENTS.md` names for agents;
- other agent instructions: `.github/copilot-instructions.md`, `.cursor/rules/`, `.windsurfrules` and the like;
- skills: each `SKILL.md` under `.claude/skills/`, `.agents/skills/` or `.codex/skills/`, with its frontmatter `name` and `description`;
- `.claude/commands/` and `.claude/agents/`.

Then the user-level skill folders, which belong to no repo: `~/.claude/skills/`, `~/.agents/skills/` and `~/.codex/skills/` where they exist. List each entry with `ls -l`, so a symlink shows its target, and read each `SKILL.md` frontmatter. Skills installed by a plugin or a package manager live in that tool's own folder (for Claude Code, under `~/.claude/plugins/`); list their names, nothing more.

For every skill and doc record its location and a content hash (`git hash-object <file>`), so that identical copies are found by hash and near-identical ones by `diff`. Write the inventory to `$TMPDIR/adopt/inventory.md`.

### 4. Sort each item into one kind

| Kind | Means | Usual destination |
|---|---|---|
| `shared` | true of every repo, or a general skill the user wants everywhere | a home-managing piece goes to YBase (through [`harvest`](../harvest/SKILL.md), later); a general-purpose skill goes to the user's own skill library |
| `duplicate` | the same skill or doc, by name or by content, in more than one place | keep one copy, chosen by the user; the others are removed or replaced by a pointer |
| `repo-specific` | true of one repo only | stays where it is (rule 21) |
| `installed` | comes from a plugin, a package manager or a skill source outside these repos | stays; YBase does not manage it |

Two copies with the same name and different content are a `duplicate` whose versions differ: report the dates (`git log -1 --format=%cs -- <file>`, or the file's modification time outside git) and the size of the difference. Choosing between them is the user's call.

### 5. Draft the repo list

Draft `repos.md` in the format of [`templates/kb/repos.md`](../../../templates/kb/repos.md): one table row per repo the user will manage, with its name, one line on what it is, its remote, and a hint for agents.

- **Name** is the folder name under the repos root. A repo cloned elsewhere needs `YBASE_REPO_PATH_<NAME>` in `.env`; note the line for the user to add, since this skill never edits `.env`.
- **What it is** comes from the repo's own `README.md` or `AGENTS.md`, in one line, never invented.
- **Remote** is the `origin` URL, or empty for a local-only repo.
- **Hint** is a fact an agent needs before touching the repo: "read its AGENTS.md first" when it has one; "public; changes go through pull requests" for a public repo; "may be stale, pull first" when the last commit is old and the remote is ahead.

Leave YBase itself out of the list.

### 6. Present, and ask

Write the proposal to `$TMPDIR/adopt/proposal-<YYYY-MM-DD>.md` and show it in chat:

```
adopt: <YYYY-MM-DD>   repos root <path>   primary KB <path> (<state>)

Repos (<n> clones found)
| # | Repo | Path | Remote | Visibility | Last commit | Manage? |

Skills and agent docs (<n> items)
| # | Item | Current location | Kind | Destination | Action |

Draft repos.md
| Name | What it is | Remote | Hint |
```

Then ask, in numbered rounds, each question with your recommendation:

1. The repos root and the primary KB, including `ybase kb init` if the KB has no skeleton.
2. Which repos to manage. Recommend every clone with recent commits; name the ones you would leave out and why.
3. Each `duplicate`: which copy to keep.
4. Each row whose destination is not obvious.
5. The draft `repos.md`, as a whole.

Stop until the user answers. Update the proposal with their answers and show the changed rows again before stage 7.

### 7. Apply what was approved

Only the approved rows, in this order:

1. If approved, `ybase kb init`.
2. Write `repos.md` in the primary KB. If one already exists, show the diff and add rows; never drop a row the user did not approve dropping.
3. `ybase repos render`, which writes `.ybase/REPOS.md`.
4. Offer to add the managed repo names to the primary KB's `deny.list`, so the leak check refuses them in YBase commits ([`docs/kb.md`](../../../docs/kb.md)). Add them only on a yes.
5. Each approved change in a child repo, such as removing a duplicate skill: a worktree on a new local branch (`ybase wt chore/adopt-cleanup --repo NAME`), the change, the repo's own checks, a local commit whose message never mentions YBase, its KB or sibling repos (rule 22). Leave it unpushed and tell the user the branch.
6. A change to a user-level skill folder: give the user the exact commands and let them run them. Moving or deleting there is outside every repo and cannot be undone by git.
7. A `shared` item bound for YBase is not written now: note it for a [`harvest`](../harvest/SKILL.md) run, which has its own approval.

### 8. Verify

Read back from the surfaces a session reads (rule 5):

```bash
ybase repos                     # every approved repo listed, each present
```

Open `.ybase/REPOS.md` and check one line per approved repo. For each child repo branch, `git -C <path> log -1 --format='%h %s' <branch>` and `git -C <path> status --short` in its worktree.

## Output

```
adopt: <YYYY-MM-DD>   repos root <path>   primary KB <path>
found: <n> clones, <k> skills and agent docs (<a> shared, <b> duplicate, <c> repo-specific, <d> installed)
repos.md: <n> rows written to <path>; .ybase/REPOS.md rendered, read back: <n> present, <m> missing
deny.list: <n names added | declined>
child repo branches (local, unpushed): <repo> <branch> <sha> ...
for the user: .env lines to add; user-level commands to run; items noted for harvest; open decisions
```
