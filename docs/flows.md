# Flows: repeatable procedures

Pick the flow that matches what you are doing. A flow that changes YBase ends with `ybase check`.

Procedures an agent runs start to finish are skills, not flows, and live in [`.claude/skills/`](../.claude/skills/README.md). For example: `adopt` for a first run, `session-scope`, `session-check` and `session-closeout` for a session's lifecycle, `git-forward` and `cleanup-worktrees` for unlanded work and stale worktrees, `review-pr` and `land-pr` for pull requests, and `retro` over recent sessions.

## Set up a machine

1. Clone YBase and run `bin/ybase setup`. It detects the machine type, writes `.env`, asks where your primary KB lives (default `kb/` in the clone), creates the KB skeleton, and runs the doctor.
2. Read `.ybase/MACHINE.md` and the profile notes it names. Fix every `FAIL` line, then run `ybase doctor` again.
3. Put your private terms in the primary KB's `deny.list`, one regular expression per line. The leak check and the leak hook refuse them.
4. Optional: run `ybase hooks install-user` so five of the blocking guards, the leak guard among them, also apply in sessions started outside YBase ([which five](machines.md#hooks)).

Setup is safe to re-run. Profiles, `.env` keys and how to pin a profile: [`machines.md`](machines.md).

## Update YBase

1. Run `ybase update`. It fetches (updating remote-tracking refs and nothing else) and lists the incoming commits, the changed files and the upstream tip's short SHA. A change under `.githooks/`, `bin/`, `tools/`, `profiles/`, `.claude/hooks/` or `.codex/`, or to `.claude/settings.json` or `templates/kb/VERSION`, gets its own line, because those change what runs on your machine. Nothing is merged.
2. Read the list, then run `ybase update --apply`. It fetches nothing: it fast-forwards to exactly the tip you were shown, without running any incoming git hook, then runs the updated `ybase doctor` and shows pending knowledge base layout steps without running them. If more was published since, run `update` again to see it.
3. Run `ybase kb migrate` to apply those steps to your primary KB.

Update refuses, changing nothing, when tracked files have uncommitted changes, the branch has commits its upstream lacks, HEAD is detached, or there is no upstream. When the upstream also has commits you lack, it reports that its history was rewritten or diverged and leaves it to you. Commit, stash or merge by hand, then run it again.

## Add a repo

1. Add a row to `repos.md` in your primary KB: name, what it is, its git remote, and an optional hint such as "read its AGENTS.md first".
2. If the repo is not at `<repos root>/<name>` on this machine, set `YBASE_REPO_PATH_<NAME>` in `.env`. The key is the name in capitals, with every other character turned into `_`.
3. Run `ybase repos` to see each repo's path and whether it is present. `ybase repos clone NAME` clones a missing one.
4. Run `ybase repos render` so the next session's `.ybase/REPOS.md` lists it.

On a machine that already has many repos, the `adopt` skill finds them and proposes the rows for you.

## Add or switch a KB

1. `ybase kb` lists your KBs, primary first, with their state.
2. To add a KB folder, for example one inside a notes vault or a private repo: `ybase kb add PATH`. It is read from then on; new content still goes to the primary.
3. To make a folder the primary: `ybase kb primary PATH`. It copies in the skeleton without overwriting anything, then stores the choice in `.env`.
4. `ybase kb remove PATH` takes an additional KB out again. Its files stay where they are.
5. Run `ybase doctor` so `.ybase/KB.md` names the new set.

YBase never commits inside a KB. If the KB folder is in a repo, commit there under that repo's own rules. More: [`kb.md`](kb.md).

## Start a unit of work in a managed repo

1. Read the repo's own `AGENTS.md` and the docs it names. Its rules win in that repo.
2. `ybase wt <kind>/<subject> --repo NAME` creates that branch from the repo's default branch, in the repo's own `.worktrees/` folder. The name says what the work is, for example `fix/leak-scan-symlinks` ([law](law/worktree.md)). Leave out `--repo` to work on YBase itself.
3. If the profile says scratch is not durable, push the branch before the machine stops.
4. `eval "$(ybase env)"` points `TMPDIR` at the profile's scratch folder. Run it from YBase, at the start of each command that needs scratch: an agent's shell state does not last from one command to the next.
5. Work by path from YBase: `git -C <worktree> ...`. Do not `cd` into the repo. Run the repo's tools the same way, for example `uv run --directory <worktree> pytest`, `npm --prefix <worktree> test` or `make -C <worktree> test`.
6. Before a commit, run the repo's own tests and checks. `ybase check` covers YBase's tree only; it says nothing about a managed repo. The leak guard does read a managed repo's commit message and staged lines, but only in a Claude Code session started in the YBase folder, or on a machine where `ybase hooks install-user` has been run. In any other session, read [`law/commit.md`](law/commit.md) and hold yourself to it.
7. Land the work as the repo's own rules say. Where it says nothing, [`law/push.md`](law/push.md) and [`law/pr.md`](law/pr.md) apply: a draft PR, merged only by the user.

## Add a lesson

1. Decide where it goes. If it names anything private (a managed repo, an employer, a path, a person), it goes to the primary KB. If it would help any user, it goes to the casebook.
2. Search first: `grep -rn "<words>" <primary KB>/memory/ docs/casebook/`. If a lesson already covers it, add a dated note to that one.
3. **Private:** write `<primary KB>/memory/<repo>/<topic>.md` and add its group to `memory/INDEX.md` with a `Covers:` line ([`kb.md`](kb.md)).
4. **Generic:** add an entry to the matching `docs/casebook/<group>.md`, with its trigger line in the same file, in generic words ([`casebook/README.md`](casebook/README.md)). Then run `ybase check`.
5. Only if it must always apply, add a short rule that links the lesson: to the KB's `rules.md` for your own repos, or to `docs/rules.md` for everyone.

## Start a research topic

1. Copy [`templates/research-topic/`](../templates/research-topic/README.md) to `<primary KB>/research/<topic>/`.
2. Delete `test_checks.py` from the copy. It tests the template's own checks and belongs to YBase.
3. Edit `CASE.md`: summary, the stages the topic uses, and what a newcomer gets wrong. Delete the stage folders it will not use.
4. Run `python3 checks.py .` inside the topic to check its manifest, source notes and catalog.

The stage contracts are in the topic's `PIPELINE.md`. The three flows below apply inside a topic.

### Add a source note

1. Pick a slug: lowercase kebab-case of a distinctive short name.
2. Sweep the source's whole artifact set: preprint, report, project page, code, weights, data, demo. Record the absent ones and how you checked.
3. Write `literature/papers/<slug>.md` with the frontmatter the topic requires and the shape in [`PIPELINE.md`](../templates/research-topic/PIPELINE.md#literature).
4. Add its row to the topic's `CATALOG.md`.
5. Update every deep dive on the note's subject, or state that none applies. A contradiction becomes a dated `ERRATUM` in the deep dive.

### Analyze a run

1. The run's facts (config in, numbers out) go in its experiment record under `projects/`.
2. If the numbers need explaining beyond that one run, write `analysis/<date>_<slug>.md` with its header, citing the record.
3. If the picture across runs moved, update the `understanding/` document and its `## History`.
4. Update the opportunity's status if the run tested one.

### Propose an opportunity

1. Write one file per idea in `opportunities/`, with the four legs: `[lit]`, `[code]`, `[run]`, `[status]`.
2. State the impact estimate with its label (`[M]`, `[D]` or `[A]`) and the cheapest test that could prove it wrong.

## Add a machine type

See [`machines.md`](machines.md#adding-a-machine-type), and [`contributing.md`](contributing.md) for the tests that come with it.

## Publish

1. Put every private term you know in the primary KB's `deny.list`.
2. `ybase check` must pass, including `leaks`, which also reads the message and the identities of every commit after the one named in `.leaks-baseline` (every commit, when that file is absent).
3. Have a second reader, who was not the author, compare the content with its private origin. They look for facts that survived with the names removed. See [`casebook/publishing.md`](casebook/publishing.md).
4. Confirm every commit's author and committer identity is the one you mean to publish.
