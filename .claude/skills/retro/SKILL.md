---
name: retro
description: Use when running a retrospective over recent Claude Code or Codex sessions on this machine, on demand or on a schedule; distils local transcripts into the ignored .ybase/retro/ directory, derives what the casebook and the knowledge base's lessons already cover, ranks the rest by evidence, reads only the top few, dates each candidate against what has landed since, and writes candidate findings to a private inbox for a human to promote.
---

# retro: find the lessons recent sessions have not yet recorded

A retro turns what went wrong in recent agent sessions into candidate lessons. The counts come from a mechanical distillation; the substance comes from reading a few cited transcript spans; and each candidate is checked against what `docs/casebook/`, the lessons in each knowledge base (KB) and `docs/rules.md` already say, and against what has landed since the evidence, so a run does not rediscover a recorded lesson or a fixed flaw. Transcripts are machine-local and can hold private material (code, credentials pasted by mistake, names, other projects), so **everything this skill writes goes under the gitignored `.ybase/retro/` of the main checkout and nowhere else**. It never edits a lesson, the casebook or `docs/rules.md`: promoting a candidate is a human step.

**Run `tools/retro.py`, do not reimplement it.** Its subcommands are the mechanical half and the only reproducible part of a run: `paths`, `distill`, `turns`, `rank`, `span`, `covered`. `python3 tools/retro.py --help` lists them; the module docstring states the record format. Every stage is shell and stdlib Python, so Claude Code and Codex run it the same way.

## When not to use

- To record a mistake from the session you are in: write that lesson directly, routed as [`docs/kb.md`](../../../docs/kb.md) says ("Record your own mistakes unprompted" in [`docs/rules.md`](../../../docs/rules.md)).
- To review one document or one PR: that is [`proofread`](../proofread/SKILL.md) or [`review-pr`](../review-pr/SKILL.md), not a retro.
- On a machine that does not hold the transcripts. A transcript exists only where its session ran; a run elsewhere has counts at best and evidence at none.

## What feeds it

Two hooks keep the records fresh between runs. Both fire only in Claude Code; Codex has no session or tool hooks, so its sessions are picked up by the window scan in Stage 2 and its records never carry load samples.

- `.claude/hooks/session_end_distil_hook.py` (SessionEnd) runs `distill --only <transcript> --closed` detached when a session ends, and appends the close to `.ybase/retro/closed.jsonl`. A record marked `closed` can be cited as final; a live session's record is a snapshot.
- `.claude/hooks/tool_load_hook.py` (PostToolUse) appends one host-load sample per tool call to `.ybase/retro/load/<session_id>.tsv`. `distill` joins the samples to the tool waits it finds, so a slow call can be told apart from a loaded host. No sample means not measured, never zero load.

Both hooks resolve the main checkout from their own location, never from the session's cwd, so a session in a worktree feeds the same inbox. They are wired in `.claude/settings.json`, so they fire only in a session started inside this checkout or one of its worktrees; a session started elsewhere leaves no record until the next `distill` run.

## Stages

1. **Prove the workspace is ignored, and find it.**

   ```bash
   python3 tools/retro.py paths
   main=$(python3 tools/retro.py paths | sed -n 's/^main: //p'); R="$main/.ybase/retro"
   mkdir -p "$R/distill" "$R/inbox" "$R/done" "$R/work"
   ```

   Stop on `ignored: NO`. The `scope:` lines list the main checkout and its live worktrees; that is what `distill` treats as in scope. Using the main checkout keeps one inbox for every worktree. Guards against: private transcript text reaching a tracked path, and retro state split across worktrees.

2. **Distil.** One record per session in scope, with the transcript line numbers of every signal, so later stages cite lines instead of rereading files:

   ```bash
   python3 tools/retro.py distill --days 14 > "$R/work/distill.txt"; cat "$R/work/distill.txt"
   ```

   Scope is decided by the `cwd` recorded inside each transcript, matched as a directory against the main checkout and its live worktrees, never by the directory name. Add `--prefix DIR` for the directory of a removed worktree, or a parent directory a session was started from, only if it holds no other project's work. The `paths` output says whether each harness's transcript directory is present; an absent one means the harness keeps them elsewhere on this machine, or never ran here; say which before going on. Read the summary lines: a session with zero turns and zero calls, or any `unparsed` lines, did not match the format this reader expects, since formats change between harness versions; count it as unread, never as calm. The correction pattern is a heuristic, so its counts are `[A]` until Stage 5 reads the turns. Guards against: a format change that turns every session into a clean one, and a run that silently read nothing and reports a calm fortnight.

3. **Derive what is already covered.** Nothing here is kept by hand ("One fact, one declaration" in `docs/rules.md`). Lessons already recorded are the numbered rules, the trigger lines of the casebook, and the entries of each KB's `memory/INDEX.md` (`ybase kb` lists the KBs):

   ```bash
   python3 tools/retro.py covered > "$R/covered.txt"
   grep -H '^- `' "$main"/docs/casebook/*.md >> "$R/covered.txt"
   grep -H '^- `' <kb>/memory/INDEX.md >> "$R/covered.txt"     # once per KB
   ```

   Read the count `covered` prints on stderr: if it found no trigger lines, it read none, and the two `grep` lines are what stand between this run and rediscovering every recorded lesson.

   Sessions already examined are the ids in the `## Sessions examined` block of every file in `$R/inbox/` and `$R/done/`; `rank` reads them itself. Move a triaged item to `done/` rather than deleting it, or its sessions are offered again. Guards against: rereading the same sessions every run, and rebuilding a lesson the casebook already holds.

4. **Rank by evidence.**

   ```bash
   python3 tools/retro.py rank --top 3
   ```

   The first line is the scope: how many sessions are unexamined and readable, and how many were skipped as examined, gone (transcript deleted) or unread. Carry those numbers into the output. Each row shows the score with its components; the weights are assumed (`[A]`), so say when one component dominated, and never call volume friction: a long session with many tool calls and no corrections ranks low on purpose. Guards against: ranking by volume and calling it friction.

5. **Read the top few by span, never whole.** Check the size with `ls -lh <path>`; transcripts run to tens of megabytes. Start with the human turns, which carry the timestamp, the correction label and whether the turn followed an interruption:

   ```bash
   python3 tools/retro.py turns "<transcript path>" > "$R/work/<harness>-<id>-turns.txt"
   ```

   Then take the line numbers from the session's record in `$R/distill/` (`corrections`, `interrupts`, `errors`, `waits`), and extract each with a few lines either side:

   ```bash
   python3 tools/retro.py span "<transcript path>" 120 126 410 414 > "$R/work/<harness>-<id>.txt"
   ```

   Redirect to a file; never pipe an extract through `head`, which can end it early with exit status 0 and leave a well-formed partial. `span` prints `no such lines` for a span past the end, so check every requested span appears. Read for what the counts cannot say: nine corrections may be one misunderstanding repeated or nine different ones. Widen by line number around a turn when a span is not enough. Then check each candidate against `$R/covered.txt` and `grep -rn "<words>" "$main/docs/casebook" "$main/docs/rules.md" <kb>/memory`. A covered lesson is "covered by `<casebook group or KB lesson path>#<slug>`", not a finding; a covered lesson the session broke anyway is a finding about the trigger line or a missing check. In Claude Code you may give each top session's reading to its own subagent, with the record and the span files as its brief; Codex reads them in turn. Guards against: a finding nobody can reopen, and a context spent on one file.

6. **Date the evidence before you suggest a change.** A retro reads sessions that are days or weeks old, and the flaw it finds may have been fixed since. Date each finding by the timestamp of the turn or call it cites (`turns` prints `ts`), not by the session: a session can run for days, so a fix can land inside one, and its `ended_at` is only an upper bound. Then look in two places: `grep -rn "<words>" "$main/docs/casebook" <kb>/memory` for a lesson or a dated violation note, and `git -C "$main" log --oneline --since=<evidence date> -- <paths the change would touch>` for a commit. Label each finding with one of three outcomes:

   - **Fixed after the evidence.** Write `**Already fixed:** <commit or lesson slug>` on the finding and suggest nothing. The incident is earlier evidence for that fix, and the promoter folds it into the existing case.
   - **Rule or tool existed before the evidence.** The fix did not land in this session. Suggest a dated violation note on that case, never a second rule or a second tool.
   - **Neither.** Suggest the change as a new candidate.

   Guards against: an old session rediscovering a fixed flaw, and a second rule for a lesson that already has one.

7. **Write the candidates to the inbox.** Take a name no other run holds:

   ```bash
   n=1; d=$(date +%Y-%m-%d)
   while ! ( set -C; : > "$R/inbox/$d-$n.md" ) 2>/dev/null; do n=$((n+1)); done; echo "$R/inbox/$d-$n.md"
   ```

   Per candidate give: what was observed; the evidence as `<harness>:<id>:L<a>-L<b>` spans with the date of the cited turn; one-off or pattern (how many sessions); its evidence label; its Stage 6 outcome; what it is already covered by, if anything; and the suggested destination, routed as [`docs/kb.md`](../../../docs/kb.md) says: a lesson in the primary KB under `memory/<repo>/` plus its `memory/INDEX.md` line when it names anything private; a `docs/casebook/<group>.md` case plus its trigger line when it is generic (see [`docs/casebook/README.md`](../../../docs/casebook/README.md)); a rule in `docs/rules.md` only if it must always apply; or a check. Mark anything the spans did not show as unverified. Close the file with `## Sessions examined` and a fenced block listing every session read, one `<harness>:<id>` per line, including those that produced nothing, and say in prose which produced nothing. Guards against: two runs overwriting each other's file, and an examined session being offered again at the same rank.

8. **Hand promotion to a human, and stop.** This skill ends at the inbox. Promotion follows [`docs/kb.md`](../../../docs/kb.md): a private lesson goes to the primary KB, which is never committed to YBase. A casebook entry is published, so rewrite it in generic words with no transcript quotes, names, paths or ids ([`docs/casebook/publishing.md`](../../../docs/casebook/publishing.md)); add the case and its trigger line in one change; fill the primary KB's `deny.list`; and pass `"$W/bin/ybase" check leaks casebook-router links framework-style` in the worktree `$W` that holds the change (the root `bin/ybase` checks only the main checkout), plus the single-file leak check in [`proofread`](../proofread/SKILL.md) stage 2, run from the YBase root, on each changed file. If no `deny.list` has an uncommented line, the private-term half of `leaks` checks nothing, so promotion is blocked until it is filled. If the user asks the agent to draft a promotion, do it on a branch in a worktree and open the PR as a draft. Then move the inbox file to `$R/done/`. Guards against: private transcript content reaching a published file under a generic heading.

## Output

```
retro: <YYYY-MM-DD> on <hostname>, window <n> days, harnesses <claude n, codex n>
scope: <n> sessions distilled, <n> unread (format mismatch), <n> examined before, <n> unexamined
ranked: top <k> of <n> unexamined; weights assumed; <note if one component dominated>
read: <harness>:<id> (<size>, closed yes/no)          (one line per session read)
candidates: <n> new, <n> already fixed, <n> violations of an existing rule, <n> already covered
  1. <one-line lesson> | <spans> | <evidence date> | one-off|pattern | -> <destination>
covered: <lesson> -> <casebook group or KB lesson>#<slug>   (one line each)
not examined: <n> unexamined sessions; sessions on other machines are not visible here
inbox: <path under .ybase/retro/inbox/>
promotion: human step; deny.list <n terms | empty: blocked>
```

Quote transcript text only into files under `.ybase/retro/`; the reply paraphrases.
