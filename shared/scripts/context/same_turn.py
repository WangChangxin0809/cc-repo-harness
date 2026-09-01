#!/usr/bin/env python3
"""PostToolUse hook: run the check that sits beside the file just edited.

Wire it in `.claude/settings.json`:

    {"hooks": {"PostToolUse": [{"matcher": "Write|Edit|MultiEdit", "hooks": [
      {"type": "command", "command": "python3 scripts/context/same_turn.py"}]}]}}

    0 = nothing to say, or something to say that does not block
    2 = the check went red, and its output goes back to the agent

## The rung this fills

The catch ladder this project measures repositories against runs
`before-write / same-turn / local-suite / [the cliff] / ci / never`, and the
distance between two rungs is what a defect costs. `before-write` is a guard
refusing a tool call. `local-suite` is the agent choosing to run the tests,
which is a rung that depends on the agent remembering. Between them sits the
one nothing here occupied: the check runs **because an edit happened**, in the
same turn, with the reasoning that produced the edit still in front of the
model.

The gap matters most for the files a repository cannot afford to get wrong.
Editing a guard and finding out at CI that it now refuses everything is four
minutes and a context switch; finding out in the same turn is a sentence.

## One rule, and no configuration

**The check for a file is the `selftest.py` sitting in its own directory.**

That is the whole rule. Editing `scripts/guards/no_force_push.py` runs
`scripts/guards/selftest.py`; editing `scripts/gates/check_layering.py` runs
`scripts/gates/selftest.py`. A directory with no selftest has nothing to run
and this stays silent.

A table mapping paths to commands was the obvious alternative and it is worse
twice over: it is a second place to update when a directory is added -- so it
goes stale in the passing direction, running nothing and saying nothing -- and
it would have to ship pre-filled with this repository's own layout, which is
the one thing nothing under `shared/` may assume.

## Failures block; abstentions do not

A check that returns 1 has judged, and its output goes back on stderr with
exit 2, which is the channel that reaches the model. Measured, not assumed:
this file's predecessor printed to stdout and delivered nothing to anyone for
its whole life -> before_write.py

A check that returns 2, times out, or cannot be started has **not** judged, and
blocking on it would trap the agent in a loop it cannot see the cause of. Those
arrive as `additionalContext` with exit 0: the model is told the check did not
run, and is not stopped by it. An abstention that looks like a pass is what
this whole project is written against; an abstention that looks like a failure
is a hook people switch off.

## What this costs, said plainly

The selftest beside a file is not free -- in this repository they run from
about a tenth of a second to eleven seconds -- and this pays it on every edit
to a directory that has one. That is the trade the rung is: seconds now
against a red CI run later. `SAME_TURN_BUDGET` caps it, and a check over the
cap is reported as not run rather than silently skipped.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

BUDGET_SECONDS = int(os.environ.get("SAME_TURN_BUDGET", "60"))

# Written to, not read from, by an edit: there is nothing to verify about a
# document, and the gates already judge them.
SKIP_SUFFIX = (".md", ".txt", ".rst", ".json", ".lock", ".yml", ".yaml",
               ".toml", ".cfg", ".ini")


def payload():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        return {}


def edited(data):
    """The path this tool call wrote, or None."""
    ti = data.get("tool_input") or {}
    if isinstance(ti, str):
        try:
            ti = json.loads(ti)
        except ValueError:
            return None
    if not isinstance(ti, dict):
        return None
    return ti.get("file_path") or ti.get("notebook_path")


def check_for(path):
    """The selftest beside `path`, or None. Never `path` itself -- running a
    selftest because somebody edited that selftest is right, and it is the
    same file, so the caller does not need to care."""
    if not path or path.endswith(SKIP_SUFFIX):
        return None
    directory = os.path.dirname(os.path.abspath(path))
    candidate = os.path.join(directory, "selftest.py")
    return candidate if os.path.exists(candidate) else None


def say(text):
    """Non-blocking. `additionalContext` is the channel that arrives; stdout
    is the debug log everywhere except three hook events, and this is not one
    of them -> before_write.py"""
    json.dump({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": text}}, sys.stdout)
    return 0


def main():
    data = payload()
    path = edited(data)
    check = check_for(path)
    if not check:
        return 0

    rel = os.path.relpath(check, os.getcwd())
    try:
        out = subprocess.run([sys.executable, check], capture_output=True,
                             text=True, timeout=BUDGET_SECONDS,
                             cwd=os.path.dirname(check))
    except subprocess.TimeoutExpired:
        return say("`%s` did not finish inside %ds, so nothing here has "
                   "checked the edit you just made. Run it yourself, or raise "
                   "SAME_TURN_BUDGET." % (rel, BUDGET_SECONDS))
    except (OSError, subprocess.SubprocessError) as exc:
        return say("`%s` could not be started (%s), so the edit you just made "
                   "is unchecked." % (rel, exc))

    if out.returncode == 0:
        return 0
    detail = ((out.stdout or "") + "\n" + (out.stderr or "")).strip()
    if out.returncode != 1:
        # COULD NOT JUDGE. Told, not blocked on: a hook that blocks on a check
        # which cannot see its subject leaves no way forward.
        return say("`%s` exited %d — it could not judge the edit you just "
                   "made:\n\n%s" % (rel, out.returncode, detail[-1500:]))

    sys.stderr.write(
        "The check beside the file you just edited went red.\n\n"
        "    %s\n\n%s\n\nFix it now, while the reason for the edit is still "
        "here, or say plainly that you are leaving it and why.\n"
        % (rel, detail[-3000:]))
    return 2


if __name__ == "__main__":
    sys.exit(main())
