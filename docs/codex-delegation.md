# Using codex-delegation

Sends large or perspective-sensitive work to the Codex CLI, keeps the full output in a file,
and brings back only a short digest. Two reasons to use it: **large output stops occupying
your context**, and **a different model reads the repo cold**, which is worth more than a
self-review when you want to be told you are wrong.

Defined by [`.claude/skills/codex-delegation/SKILL.md`](../.claude/skills/codex-delegation/SKILL.md),
which Codex reads through `.agents/skills`; configured by `.agents/codex-delegation.json`.
Design rationale: [`docs/adr/0002-codex-delegation.md`](adr/0002-codex-delegation.md). The
rules for a cross-model hand-off: [`docs/protocols/delegation.md`](protocols/delegation.md).

## Quickstart: three things to try

Ask in plain language; the skill fires on its own above the size thresholds. Or invoke it:

```
/codex-delegation <profile> [<focus text>] [--force] [--local] [--wait]
```

**1. Critique a design you just wrote** (the highest-value case):

```
/codex-delegation critique docs/adr/0002-codex-delegation.md
```

Expect a `VERDICT: sound|revise|reconsider` line, objections ordered by damage, and, by
design, an honest "strongest argument FOR" at the end. If it cannot argue for your design,
treat the critique as contrarian rather than useful.

**2. Review a branch before merging:**

```
/codex-delegation review
```

**3. Get alternatives when you have converged too early:**

```
/codex-delegation brainstorm "how should X work"
```

`brainstorm` never auto-fires. It is cheap to run and easy to over-run, so it waits to be asked.

## What to expect

| Profile | Fires automatically at | Typical wall time |
|---|---|---|
| `review` | 400 changed lines or 8 changed files | **~23 min**, always background |
| `critique` | 600 words of input | 1–4 min |
| `docs` | 800 target words | 1–4 min |
| `plan` | 5 expected tasks | 1–4 min |
| `brainstorm` | never (explicit only) | 1–4 min |

Measured 2026-08-23 against codex-cli 0.149.0. **`review` is in a different class**: it reads
the whole diff before saying anything. A foreground review that times out produces *no file at
all*, so the run is wasted rather than truncated. Let it run in the background.

## Reading the result

Output goes to the profile's scratch directory, never a checkout:
`$YBASE_SCRATCH/codex/<yyyymmdd>-<hhmmss>-<profile>-<slug>.md`, or inside an active run to
`$YBASE_SCRATCH/runs/<run_id>/artifacts/codex/`. `eval "$(ybase env)"` sets
`YBASE_SCRATCH`. Artifacts are evidence, not deliverables. Move a document you intend to
keep into the repo yourself.

You get back the path, a verdict line, and findings by severity. The full text stays on disk:
`grep` it when you want a detail. That is the whole point: asking for the complete artifact in
chat spends exactly what delegating was meant to save.

**Findings are claims, not facts.** The skill presents them and stops; it will not apply a fix
without you saying which ones. That holds even for obvious-looking one-liners, because an
unverified finding applied blind is how a review makes code worse.

## Turning it off

```bash
CODEX_DELEGATION=0     # off for one session
CODEX_DELEGATION=1     # on, overriding the config file
```

Or edit `.agents/codex-delegation.json`: `enabled: false` kills everything;
`profiles.<name>.enabled: false` kills one profile; `profiles.<name>.auto: false` keeps it
available but stops it firing on its own. Thresholds live in the same file.

A machine with no Codex needs no switch: delegation is off wherever the Codex CLI is not
installed. To turn it off on a machine that has Codex, put `YBASE_CODEX_DELEGATION=off` in
that machine's `.env` and run `ybase doctor`. The session override cannot turn such a
machine back on.

This is a workflow switch, not a security boundary. `Bash(codex exec *)` is allowed, so the
config governs this skill's behavior, not access to Codex generally.

## Gotchas worth knowing

- **The thresholds are guesses.** 400 lines, 600 words, 5 tasks: uncalibrated proxies for
  output size. If it delegates work you'd rather have done inline, raise them; that is the
  expected tuning path, not a bug. `docs/evals/codex-delegation.md` case T1 tracks this.
- **Independence is conditional.** If the caller is *itself* Codex, the re-entrancy guard makes
  it answer locally. That is correct, but you get no second perspective. Independence assumes the
  caller is not Codex.
- **Total tokens go up, not down.** A second model reads the repo and writes the full answer.
  What you save is *your* context and its re-payment on later turns. For a long thread that is
  a clear win; for a one-shot task that ends immediately, it usually is not.
- **`--base` and a custom review prompt are mutually exclusive.** Use `critique` when you want
  custom framing.
