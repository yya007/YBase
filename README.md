# YBase

YBase is a home repo for AI coding agents. You start every agent session in it, and it points at all your other repos. Claude Code and Codex both read it.

It gives every session the same ground rules, the facts about the machine it runs on, the list of repos you manage, and the lessons you saved last time. It also holds the guards and checks that stop common agent mistakes, such as a leaked path in a commit message or a search that walks a whole shared disk.

YBase holds no private data. Your repo list, your lessons and your private terms live in a knowledge base (KB): a plain folder of Markdown that git never tracks here. So you can share YBase, and take it to a work machine, without taking your data with it.

## How a session works

1. You start an agent in the YBase folder.
2. The agent loads the short rule chain: [`AGENTS.md`](AGENTS.md), [`docs/rules.md`](docs/rules.md), and three generated files that describe this machine, your repos and your KBs.
3. To change a managed repo, the agent reads that repo's own `AGENTS.md`, then makes a worktree for the change with `ybase wt <kind>/<subject> --repo NAME`.
4. Before a commit, a push or a pull request, the agent sees the rules for that moment in [`docs/law/`](docs/law/README.md). Guards and the check registry refuse the mistakes they know.
5. What the session learns goes to your KB if it names anything private, or to the shared [casebook](docs/casebook/README.md) if it would help anyone.

## Quickstart

You need git, bash and Python 3.10 or later.

```bash
git clone <repo-url> YBase && cd YBase
bin/ybase setup      # detect the machine type, write .env, create your KB, put `ybase` on your PATH
claude                  # or codex: start the agent here
```

Setup writes a small `ybase` command into `~/.local/bin`, so after it you type `ybase doctor`, not `bin/ybase doctor`. If that folder is not on your PATH, setup prints the line to add, and `bin/ybase` keeps working.

Then list the repos you manage in your KB's `repos.md` and run `ybase repos render`. Or ask the agent to run the `adopt` skill, which finds your repos and proposes the list for you. [`docs/flows.md`](docs/flows.md) walks through each step.

**Updating.** `ybase update` fetches your upstream (which updates remote-tracking refs and nothing else) and lists the incoming commits, files and the upstream tip's short SHA; it merges nothing. `ybase update --apply` fetches nothing: it fast-forwards to exactly the tip the last `update` showed, without running incoming git hooks, then runs the updated doctor and lists any pending knowledge base layout steps (run them with `ybase kb migrate`). It refuses, and leaves everything as it was, when you have uncommitted tracked changes, local commits the upstream lacks, a detached HEAD, or no upstream.

## Three scopes

Every file belongs to exactly one scope.

| Scope | Holds | Where | Tracked in YBase? |
|---|---|---|---|
| Framework | rules, moment rules, hooks, checks, machine profiles, skills, templates, generic lessons, tests | this repo | yes |
| Knowledge base | your repo list, saved lessons, worklog, research notes, your own rules, your private terms | `kb/` here, or any folder you name | never |
| Machine | settings and generated facts for this one machine | `.env` and `.ybase/` | never |

The test for framework content: would it be true and harmless for a stranger who installs YBase? If not, it belongs in a KB or in machine settings.

## Layout

| Path | What it is |
|---|---|
| `AGENTS.md` | the entry point every agent reads first |
| `CLAUDE.md` | imports the rule chain for Claude Code |
| `bin/ybase` | the command line, typed as `ybase` once setup has put it on your PATH: `setup`, `doctor`, `update`, `env`, `wt`, `repos`, `kb`, `check` and more (`ybase help`) |
| `tools/` | the scripts behind the command line, standard-library Python and bash 3.2 |
| `profiles/<type>/` | one folder per machine type (`macos`, `linux`, `aws`, `ci`): defaults, setup probes and notes |
| `docs/rules.md` | the always-on ground rules |
| `docs/law/` | rules shown at one moment: commit, push, worktree, PR, review and others |
| `docs/protocols/` | longer procedures, opened when needed |
| `docs/casebook/` | generic lessons, routed by an index |
| `docs/writing/` | how to write each kind of document |
| `.claude/hooks/` | guards Claude Code runs around its tool calls |
| `.claude/skills/` | named procedures; Codex sees the same files through `.agents/skills` |
| `.codex/` | the hook Codex runs |
| `templates/` | the KB skeleton, a research topic, run and task templates |
| `kb/` | the local KB; its contents are gitignored |
| `.env`, `.ybase/` | this machine's settings and generated files; gitignored |

## Read next

- [`docs/architecture.md`](docs/architecture.md): how the pieces fit, and what each guard and check refuses.
- [`docs/flows.md`](docs/flows.md): step-by-step procedures, from setting up a machine to adding a lesson.
- [`docs/kb.md`](docs/kb.md) and [`docs/machines.md`](docs/machines.md): knowledge bases and machine profiles.
- [`docs/codex.md`](docs/codex.md): what changes when the agent is Codex.
- [`docs/contributing.md`](docs/contributing.md): development commands, conventions, and how to add a profile, a hook or a check. Start from [`CONTRIBUTING.md`](CONTRIBUTING.md); report a leak or a guard bypass through [`SECURITY.md`](SECURITY.md).
- [`docs/roadmap.md`](docs/roadmap.md): open product questions.
- Optional extras: [agent tooling](docs/optional-tooling.md) and [resuming sessions after a usage limit](docs/claude-autoresume.md).

## License

[PolyForm Noncommercial License 1.0.0](LICENSE). You may use, change and share YBase for any noncommercial purpose: personal use, research, education, and use by a charity or a public body. Commercial use is not allowed. YBase is source-available, not open source as the Open Source Initiative defines it.
