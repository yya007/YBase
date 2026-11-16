#!/usr/bin/env python3
"""PostToolUse hook: advise on writing after a Write or Edit to a markdown file.

Runs the `framework-style` and `links` logic from tools/checks.py on the one
file that was just written (`checks.check_file`), and appends the five
judgment checks from docs/writing.md that no linter can run. The findings
return to the agent as `hookSpecificOutput.additionalContext`, which Claude
Code places next to the tool result.

REFUSES nothing. ALWAYS exits 0: a finding must never look like a failure,
and a non-zero exit would put only the first stderr line in the transcript,
where the agent does not reliably read it. The wrapper in .claude/settings.json
ends in `exit 0` for the same reason; keep it.

ADVISES after Write or Edit on a `.md` file inside this repository when the
mechanical pass finds something; a clean file earns silence, and the judgment
half then belongs to the proofread skill. Mechanical findings are capped so one
long file cannot flood the context.

PASSES silently: any other file type; a path outside this repository; a
payload the hook cannot read; any internal error (said on stderr, so a
disabled hook does not read like a clean one).

ESCAPE: `WRITING_STYLE_SKIP=1` in the session's environment silences the
advice; there is no command line to prefix for an editing tool.

Claude Code only. Codex runs only the allow gate as a hook (.codex/hooks.json);
`ybase check links framework-style`
gives the mechanical half, and docs/writing.md the rest. Runnable by hand:
`python3 .claude/hooks/writing_style_hook.py < payload.json`.
"""
import json
import os
import pathlib
import sys
import traceback

REPO = pathlib.Path(__file__).resolve().parents[2]
ESCAPE = "WRITING_STYLE_SKIP"
MAX_FINDINGS = 20

# The judgment checks, in the order docs/writing.md states them. Change them there first.
CHECKLIST = (
    "Lead with the answer: does the document open with its conclusion, not its history?",
    "One fact per sentence, under about 60 words, in the everyday word.",
    "Every number carries its label ([M], [D] or [A]) and its source.",
    "Written for the outside reader: no private alias, internal id or personal path.",
    "States the end state, not the story of how it got there; history goes in ## History or the worklog.",
)


def advice(path, findings):
    rel = path
    try:
        rel = str(pathlib.Path(path).resolve().relative_to(REPO))
    except ValueError:
        pass
    lines = [f"Writing check for {rel} (advisory, nothing was blocked)."]
    if findings:
        lines.append("Mechanical findings (links, framework-style):")
        lines += [f"  {f}" for f in findings[:MAX_FINDINGS]]
        if len(findings) > MAX_FINDINGS:
            lines.append(f"  ... and {len(findings) - MAX_FINDINGS} more; run: ybase check links framework-style")
    else:
        lines.append("No mechanical finding (links, framework-style).")
    lines.append("Judgment checks from docs/writing.md, for you to read the file against:")
    lines += [f"  {i}. {c}" for i, c in enumerate(CHECKLIST, 1)]
    return "\n".join(lines)


def _run():
    if os.environ.get(ESCAPE) == "1":
        return 0
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    raw = tool_input.get("file_path")
    if not isinstance(raw, str) or not raw.endswith(".md"):
        return 0
    path = pathlib.Path(raw).expanduser()
    if not path.is_absolute():
        path = pathlib.Path(payload.get("cwd") or ".") / path
    path = path.resolve()
    try:
        path.relative_to(REPO)
    except ValueError:
        return 0  # outside the repository this hook was loaded from
    if not path.is_file():
        return 0
    tools = REPO / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import checks  # noqa: E402
    findings = checks.check_file(path, REPO)
    if not findings:
        return 0  # a clean file earns silence; the judgment half belongs to the proofread skill
    json.dump({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": advice(str(path), findings),
    }}, sys.stdout)
    return 0


def main():
    try:
        _run()
    except Exception:
        sys.stderr.write("writing_style_hook: no advice for this call, it raised:\n" + traceback.format_exc())
    return 0


if __name__ == "__main__":
    sys.exit(main())
