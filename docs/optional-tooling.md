# Optional Agent Tooling

User-level CLIs that extend what agents working in YBase can do: internet
research channels, code knowledge graphs, browser-session access.
They are **optional**: nothing in YBase or a managed repo requires them,
and a machine without them loses capabilities, not correctness.

Canonical automation: `ybase tools install` (runs `tools/setup-tools.sh`)
and `ybase tools update` (runs `tools/update-tools.sh`). This document is the reference for what
the tools are, how the scripts behave, and the guidelines for extending or
operating them.

## Quick start

```bash
ybase tools install      # install whatever is missing
ybase tools update       # refresh whatever is installed
DRY_RUN=1 ybase tools install   # preview without changing anything (same for update)
```

Both are idempotent and safe to re-run; a failing tool warns and the script
continues, exiting non-zero at the end so CI/callers notice.

## The tools

| Tool | Installed via | Purpose |
|---|---|---|
| [agent-reach](https://github.com/Panniantong/agent-reach) | `uv tool` (from `main.zip`) | Router/installer for internet-access channels (web, search, YouTube, GitHub, RSS, V2EX, Bilibili, and optional cookie-gated platforms). Installs an `agent-reach` skill into `~/.agents/skills/` and `~/.claude/skills/`. |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | `uv tool` | Video/audio extraction; backs agent-reach's YouTube channel. |
| [gitnexus](https://github.com/abhigyanpatwari/GitNexus) | `npm -g` | MCP-native code knowledge-graph engine (`gitnexus analyze` in a repo, `gitnexus setup` to wire editors/agents). |
| [OpenCLI](https://www.npmjs.com/package/@jackwener/opencli) | `npm -g` | Browser-session backend (小红书/Reddit/Facebook/Instagram/B站字幕) reusing Chrome login state. Needs a one-click Chrome extension install; see caveats. |
| [mcporter](https://www.npmjs.com/package/mcporter) | `npm -g` | MCP server runner/configurator; backs agent-reach's Exa search channel. |
| ffmpeg | `brew` | Audio transcoding; backs agent-reach's podcast-transcription channel. |
| twitter-cli, bilibili-cli | *(update-only)* | Installed by agent-reach itself when their channels are enabled. The manifest refreshes them but never installs them. |

## Manifest contract

The single source of truth is the manifest inside `tools/setup-tools.sh`,
one line per tool:

```
name|check_cmd|install_cmd|update_cmd
```

- `check_cmd`: binary probed with `command -v`; presence decides skip/install/update.
- `install_cmd`: runs via `bash -c`. The literal `-` marks an **update-only**
  tool: another installer owns it (e.g. agent-reach installs `twitter-cli`),
  so we refresh it when present but never pull it onto machines that didn't
  opt in.
- `update_cmd`: runs via `bash -c`; empty means "no update procedure" (skipped
  in update mode). Only this last field may contain `|`, since it absorbs the
  remainder of the line.
- `#` comments and blank lines are ignored. Tests override the whole manifest
  via `TOOLS_MANIFEST=<file>`.

Mode semantics:

- **install** (default): missing → install; present → skip. Never updates.
- **update** (`UPDATE=1`, or the `update-tools.sh` wrapper): present → update;
  missing → skip. **Never installs**: per the upstream update guides, an
  update pass must not grow the tool set.

## Adding a tool

1. Append a manifest line in `tools/setup-tools.sh`. Requirements:
   - **User-scoped, no sudo.** Acceptable installers: `uv tool install`,
     `npm install -g` (linuxbrew prefix is user-writable), `brew install`,
     or a `~/`-scoped fetch. If a tool needs root, it doesn't belong here;
     document it as a manual prerequisite instead.
   - A real `update_cmd`. If the package installs from a moving URL (like
     agent-reach's `main.zip`), force a re-download: `uv tool upgrade
     --reinstall <name>` (`--reinstall` implies `--refresh`, defeating the URL
     cache). Plain version-pinned packages use the installer's native upgrade.
2. Update the tool table above, and the one-line list in `README.md` if it names
   the tools.
3. Extend `tests/test_setup_tools.py` only if the new line exercises new
   *mechanics* (the manifest behaviors themselves are already covered).
4. Verify: `uv run --extra dev pytest`, then `DRY_RUN=1` both modes, then a live run.

## Operating guidelines

- **Workspace boundary.** These tools live in `~` (uv tool venvs, npm -g
  prefix, `~/.agent-reach/`, `~/.mcporter/`, `~/.agents/skills/`); they must
  never write into YBase or a managed repo. Watch for cwd-relative configs:
  `mcporter config add` defaults to **project scope** and drops
  `config/mcporter.json` into the current directory. Always pass
  `--scope home` (flags after positionals), and `git status` after any
  tool-driven setup to confirm the repo stayed clean.
- **Credentials are need-to-know.** Several agent-reach channels want cookies
  (Twitter/X, 雪球, 小红书) or API keys (Groq for podcast transcription).
  Configure them only via `agent-reach configure …` into `~/.agent-reach/`;
  never commit them, echo them into logs/PRs, or store them in repo files.
  Prefer secondary accounts for cookie-auth platforms: cookie auth carries
  account-ban and credential-exposure risk.
- **Never uninstall on update.** Retired or superseded backends stay installed
  (coexistence, per the agent-reach update guide); removal is a human decision.
- **Health checks.** `agent-reach doctor` reports per-channel status and the
  exact fix command for anything broken; `opencli doctor` verifies the browser
  extension pairing; `gitnexus --version` / `mcporter config list` sanity-check
  the rest.

## Known quirks

- **`brew install`/`upgrade` can bump `python@3.14`** as a side effect and
  silently invalidate the project `.venv` (symptom: the test run fails
  at once because `pytest` itself is missing from the environment).
  Fix: `uv sync --extra dev`. Details in
  [`profiles/macos/NOTES.md`](../profiles/macos/NOTES.md).
- **OpenCLI on WSL2**: the daemon runs in WSL while Chrome (and its extension)
  run on Windows. Pairing across that boundary is unverified; expect
  `opencli doctor` troubleshooting before the browser-session channels work.
- **Jina Reader (agent-reach's web channel) blocks anonymous calls from
  low-reputation networks** (seen on a residential connection: HTTP 401
  `bad network reputation`). Fall back to the agent's built-in web fetch, or
  authenticate Jina if the channel matters.
- **`brew upgrade <formula>`** exits 0 with a warning when already up to date, so
  no special-casing needed in update commands (an earlier `|| true` here
  masked real failures and was removed by review).
