# agents.md: lessons about agent harnesses, skills and the shell

<!-- BEGIN TRIGGERS -->
- `codex-may-not-follow-a-symlinked-skills-directory` - changing how skills are linked into `.agents/skills`, or when Codex lists no skills.
- `reach-a-sibling-repo-with-git-c-not-cd` - running a command against a managed repo from a session started in YBase.
- `absolute-path-imports-from-generated-kb-file-are-followed` - deciding whether generated context files must be inlined into `CLAUDE.md`.
<!-- END TRIGGERS -->

## codex-may-not-follow-a-symlinked-skills-directory
2026-06-25. Two spellings of one skills directory were deduplicated by making the path Codex reads a symlink to the other spelling. Codex then found no skills at all: it did not traverse the symlinked directory.
**Why it matters:** both paths resolve in a shell, so every manual check passes while the one consumer that matters sees nothing.
**How to apply:** after any change to how skills are linked, start Codex in the repo and confirm it lists a skill before relying on the layout. If it lists none, make the path Codex reads the real directory and point the other path at it.
2026-11-13. In this repo, codex-cli 0.165.0 does list the skills through the `.agents/skills` symlink to `.claude/skills`. The check above still applies after any change to the link, since the behaviour may differ by version or by how the link is made.

## reach-a-sibling-repo-with-git-c-not-cd
2026-06-19. A session started in the home repo ran `cd <sibling repo> && ...` to work on a managed repo. The agent shell keeps its working directory across tool calls. A hook resolved its own script from the working directory's git root, found nothing in the sibling repo, failed, and blocked every later shell command, including the `cd` back. Only a new session recovered.
**Why it matters:** a hook that cannot start blocks the whole session, and subagents share the same shell.
**How to apply:** stay in YBase and name the repo instead: `git -C <path> ...`, with the path from `ybase repos path NAME`, or a worktree from `ybase wt <name> --repo NAME`. A hook resolves its own location from `$CLAUDE_PROJECT_DIR` or its file path, never from the working directory. Never disable a hook to get unstuck.

## absolute-path-imports-from-generated-kb-file-are-followed
2026-11-14. In a scratch clone after one setup, a marker sentence was put in the primary KB's `rules.md` and another in its `memory/INDEX.md`, and `doctor` was re-run so the generated `.ybase/KB.md` held absolute-path `@` lines for both. One `claude -p` call from the clone root, told to use no tools and to quote any marker strings it was given, quoted both (for example "KB-RULES-MARKER-7391: always greet with the word persimmon") and obeyed the rule. So the chain `CLAUDE.md`, `.ybase/KB.md`, then the KB files was followed, absolute paths included, and inlining was not needed. Not covered: interactive sessions, a KB outside the project that needs an approval, and a populated repo list. The clone was untrusted for that call, which only ignored the project's allow list.
2026-11-14. Claude Code ends an `@` import path at the first unescaped space, so a path with a space must be written with a backslash before each space; the generated files now do that. The probe was repeated from a scratch clone whose parent directory and clone directory both held a space, after one setup with stdin closed and a marker sentence added to the clone's `kb/rules.md`. The generated `KB.md` held the escaped absolute paths, and one `claude -p` call from the clone root, told to use no tools, quoted the marker verbatim. So escaped paths with spaces are followed.
**Why it matters:** inlining would have made the generated files larger and always-on for no gain.
**How to apply:** keep the imports. After changing how context is generated, repeat the marker check and inline only if the markers are not quoted.
