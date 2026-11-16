# Knowledge bases

YBase is a public framework, so it holds nothing private. What is private to you lives in a knowledge base (KB): your repo list, saved lessons, worklog, research notes, your own rules and your list of private terms. A KB is a plain folder of Markdown.

## Where KBs live

Every install has a local KB at `kb/`. Its contents are gitignored, so nothing in it enters YBase's history. You may add other KB folders, for example a folder inside a notes vault or a private repo, and name one of them primary.

| Command | Effect |
|---|---|
| `ybase kb` | list KBs, primary first, each `ok`, `missing` (no such folder) or `no-skeleton` (no `VERSION` file) |
| `ybase kb init [PATH]` | copy the skeleton into PATH (default: the primary), never overwriting a file |
| `ybase kb primary PATH` | init PATH, then make it the KB that receives new content |
| `ybase kb add PATH` / `kb remove PATH` | add or drop an additional KB |
| `ybase kb migrate [PATH] [--dry-run]` | bring a KB's layout up to the current version ([below](#layout-versions)) |

The choice is stored in `.env` as `YBASE_KB_PRIMARY` and `YBASE_KB_PATHS` (additional roots, separated by `:`). `ybase doctor` writes `.ybase/KB.md`, which lists the KBs and imports the primary KB's `rules.md` and every KB's `memory/INDEX.md` into a Claude Code session. Other agents open the files it names.

## Layout

```
<kb>/
  VERSION            skeleton version
  repos.md           the repos you manage
  rules.md           your own standing rules
  deny.list          private terms the leak check refuses
  memory/
    INDEX.md         the router: one group per repo, a Covers: line each
    <repo>/<topic>.md
  worklog/           what changed, when
  research/          notes and findings
```

`deny.list` holds one Python regular expression per line; `#` starts a comment. Do not list a name or handle that your own commits carry as author: the `leaks` check scans commit identities, so every commit of yours would be refused. The `leaks` check and the commit-time leak hook read the `deny.list` of every KB, so a term kept in one KB is refused in all of YBase. The hook applies the list to every commit, tag and PR command, whichever repo it targets. The list names your managed repos, so a managed repo's commit that names itself needs the `LEAK_AUTHORIZED=1` prefix ([ADR 0005](adr/0005-leak-hook-strict-everywhere.md)). Both find the KBs from a linked worktree through its main checkout's `.env`. A line that is not a valid regular expression is skipped; the `leaks` check names its file and line so you can fix it. The `leaks` check's result line says how many terms it loaded and from how many of the KBs, and it fails when a KB named in `.env` or the environment is missing, when `.env` cannot be read, or when a `deny.list` exists but cannot be read, since each of those would quietly drop terms. The default `kb/` with nothing in it, and a KB with no `deny.list`, are fine. The commit-time hook still allows a command when it cannot load the list.

## Layout versions

`VERSION` in a KB holds an integer: the layout version of the skeleton. `templates/kb/VERSION` is the version this YBase knows. When a KB is behind, `ybase doctor` warns (it does not fail) and names the fix:

```
ybase kb migrate [PATH] [--dry-run]
```

`PATH` defaults to the primary KB. `--dry-run` lists the steps and changes nothing. Each step moves a KB up one version, and `VERSION` is rewritten after each finished step, so a failed step leaves it at the last one that completed. The command refuses a KB whose `VERSION` is newer than YBase knows (update YBase instead) or missing (run `kb init`). It also refuses a missing folder (naming it as missing, with no `kb init` advice) and a folder that lacks `VERSION` or `memory/INDEX.md` (not a KB), an unknown `-` option, and more than one path, with exit 2 for the last two. It never touches git: commit the result yourself.

To change the layout, a contributor bumps `templates/kb/VERSION`, adds the step to `MIGRATIONS` in `tools/kb_migrate.py` (keyed by the version it starts from), and adds a test in `tests/test_kb_migrate.py`.

## Where new content goes

New content goes to the primary KB unless a request names another.

Before you save a lesson, ask whether it names anything private: a managed repo, an employer, a path, a person. If it does, it goes to the primary KB. If it is generic and would help any user, propose it for [`casebook/`](casebook/README.md) in the framework instead, rewritten in generic words.

## What to store

Signal, not noise.

- Root causes of non-trivial bugs and the fix that worked, not just the symptom.
- Recurring failure modes and the recovery procedure that un-stuck them.
- Tool and environment quirks, with the invocation that actually works.
- Hard-won decisions and constraints that the code does not show.
- What was tried, what worked, what failed, and why.
- Not transient state, not secrets, and nothing derivable from code, git or the project's own contract docs.

## When to write

Extract a lesson right after:

- fixing a non-trivial bug, or resolving a blocker or a recovery;
- working out how a tool or environment really behaves;
- any correction from the user.

Ground each lesson in the instance that produced it: the failure, the command, the file. A reflection that cites its evidence stays auditable and does not turn into a baseless generalization.

## Structure

- One lesson per file under `memory/<repo>/`, named in kebab-case. A short body: what was tried, why it matters, the fix, the meta-lesson. Link related entries.
- Index each group in `memory/INDEX.md` with a `Covers:` line, so a session loads the index first and opens only the lessons relevant to its task.

## Hygiene

- Update the existing file rather than appending a duplicate; delete entries proven wrong.
- Keep roughly 30 active lessons per repo; merge or prune stale ones.
- Treat every entry as point-in-time: before acting on a file, flag or function it names, check it against the current code.
