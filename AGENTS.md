# AGENTS.md: entry point for AI agents working in YBase

YBase is a home repo: start agent sessions here, and it points at every other repo you manage. It holds shared rules, hooks, machine setup and skills; whatever is private to you lives in a knowledge base (KB) outside the tracked tree.

| Context | Files |
|---|---|
| How to work | [`docs/rules.md`](docs/rules.md), [`docs/casebook/INDEX.md`](docs/casebook/INDEX.md), [`docs/law/`](docs/law/README.md) |
| This machine | `.ybase/MACHINE.md`, then the `profiles/<profile>/NOTES.md` it names |
| Your repos and knowledge | `.ybase/REPOS.md`, `.ybase/KB.md` |

The `.ybase/` files are generated; if one is missing, run `bin/ybase setup`. Setup also puts the `ybase` command on your PATH; where it is not there, `.ybase/MACHINE.md` says so, and `bin/ybase` from this folder does the same. Sessions start in YBase; reach a managed repo through its path in `.ybase/REPOS.md`.

Claude Code imports all of this through `CLAUDE.md`. **Any other agent reads these now, in order:**

1. `docs/rules.md`, the ground rules.
2. `docs/casebook/INDEX.md`. Open a group only when its `Covers:` line matches your task.
3. `.ybase/MACHINE.md`, then the profile notes it names.
4. `.ybase/REPOS.md`: one line per managed repo, with its path here.
5. `.ybase/KB.md`, then the files it names: your `rules.md` and each KB's `memory/INDEX.md`.
6. [`docs/codex.md`](docs/codex.md): what Claude Code's hooks would enforce, and the law file to read before each kind of command.

| I want to... | Go to |
|---|---|
| change a managed repo | its own `AGENTS.md`, then `ybase wt <kind>/<subject> --repo NAME` |
| add a repo or a KB, or save a lesson | [`docs/kb.md`](docs/kb.md), `ybase repos`, `ybase kb` |
| understand how YBase is built | [`docs/architecture.md`](docs/architecture.md), [`docs/flows.md`](docs/flows.md) |
| set up or debug a machine | [`docs/machines.md`](docs/machines.md), `ybase doctor` |
| know the rules for one moment | [`docs/law/`](docs/law/README.md) |
| run a named procedure | [`.claude/skills/`](.claude/skills/README.md): `/name` in Claude Code, `$name` in Codex |
| track a multi-step or multi-agent task | [`runs.md`](docs/protocols/runs.md), [`multi-agent.md`](docs/protocols/multi-agent.md) |
| hand work to Codex | [`docs/protocols/delegation.md`](docs/protocols/delegation.md) |
| publish to the public repository, or take a contribution back | [`docs/publishing.md`](docs/publishing.md) |
| record a design decision | [`docs/protocols/decisions.md`](docs/protocols/decisions.md) |
| import a skill | [`docs/protocols/importing-skills.md`](docs/protocols/importing-skills.md) |
| write anything a person reads | [`docs/writing.md`](docs/writing.md) |
| start a research topic | [`templates/research-topic/`](templates/research-topic/README.md) |

Before you commit, run `ybase check`.
