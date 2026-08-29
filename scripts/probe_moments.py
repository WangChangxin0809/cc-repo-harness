#!/usr/bin/env python3
"""Rung 1: does each delivery moment actually fire, offline and for free?

    python3 scripts/probe_moments.py [--root .]

    0 = every moment fired as declared    1 = one did not    2 = cannot judge

This is ours, not payload -- it measures this repository's own wiring, and a
target repository has `ci.sh` for the same job.

Rung 1 of the eval ladder asks the cheapest possible question: *did the thing
happen at all*. It needs no model, no network and no API budget, because a hook
is a subprocess with a JSON payload on stdin -- so a synthetic payload answers
it exactly. An outcome eval that spends real money to discover a hook was never
wired is the expensive way to learn this.

Both directions, for the same reason gates have both: a hook that fires on
everything is as broken as one that fires on nothing, and only the quiet case
tells them apart.

One warning that this script learned the hard way. Guards read the *text* of the
command they are judging, so a probe that passes `git restore .` as test data
trips the guard on the probe's own shell command. The payloads below are built
in Python and piped to the hook directly; they never become shell words.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

# (label, script, payload, expect_fires) -- expect_fires is the whole point of
# the table: half these rows must produce nothing.
def cases(root):
    danger = "git " + "restore ."          # split so no probe puts it in argv
    return [
        ("PreToolUse blocks a destructive restore",
         "shared/scripts/guards/dispatch.py",
         {"hook_event_name": "PreToolUse", "tool_name": "Bash",
          "tool_input": {"command": danger}, "cwd": root}, True),
        ("PreToolUse stays quiet on a harmless command",
         "shared/scripts/guards/dispatch.py",
         {"hook_event_name": "PreToolUse", "tool_name": "Bash",
          "tool_input": {"command": "ls -la"}, "cwd": root}, False),
        ("SessionStart reports branch state",
         "scripts/context/session_brief.py",
         {"hook_event_name": "SessionStart", "source": "startup",
          "cwd": root}, True),
        ("PreToolUse surfaces a governing document",
         "shared/scripts/context/before_write.py",
         {"hook_event_name": "PreToolUse", "tool_name": "Edit",
          "tool_input": {"file_path": os.path.join(
              root, "shared/scripts/scaffold.py")},
          "cwd": root}, True),
        ("PreToolUse stays quiet on a file nothing governs",
         "shared/scripts/context/before_write.py",
         {"hook_event_name": "PreToolUse", "tool_name": "Edit",
          "tool_input": {"file_path": os.path.join(root, "LICENSE")},
          "cwd": root}, False),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    rows, failures = [], []
    for label, script, payload, expect in cases(root):
        path = os.path.join(root, script)
        if not os.path.exists(path):
            print(f"cannot judge: {script} is missing", file=sys.stderr)
            return 2
        p = subprocess.run([sys.executable, path], input=json.dumps(payload),
                           capture_output=True, text=True, cwd=root)
        out = (p.stdout + p.stderr).strip()
        fired = bool(out)
        rows.append((label, fired, expect, len(out), p.returncode))
        if fired != expect:
            failures.append(
                f"{label}\n    expected {'output' if expect else 'silence'}, "
                f"got {'output' if fired else 'silence'} (exit {p.returncode})"
                + (f"\n    {out[:300]}" if out and a.verbose else ""))

    width = max(len(r[0]) for r in rows)
    print(f"{'moment':<{width}}  fired  chars  exit")
    for label, fired, expect, n, rc in rows:
        mark = "yes" if fired else "no "
        flag = " " if fired == expect else "!"
        print(f"{label:<{width}}  {mark}{flag}   {n:5d}  {rc:4d}")

    paid = sum(n for _, fired, expect, n, _ in rows if fired and expect)
    print(f"\nOn-fire output across the firing moments: {paid} chars "
          f"(~{round(paid / 3.06)} tok, at the 3.06 chars/token this repo's own "
          f"text calibrates to).")

    if failures:
        print(f"\n{len(failures)} moment(s) did not behave as declared:",
              file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
