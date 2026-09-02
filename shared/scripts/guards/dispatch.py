#!/usr/bin/env python3
"""PreToolUse dispatcher: run every guard in this directory against one proposed
tool call.

Wire it once in .claude/settings.json and never touch the wiring again -- adding
a rule is adding one file here.

    {
      "hooks": {
        "PreToolUse": [{
          "matcher": "Bash|Write|Edit|MultiEdit|NotebookEdit",
          "hooks": [{"type": "command",
                     "command": "python3 scripts/guards/dispatch.py"}]
        }]
      }
    }

The matcher names every tool a guard here judges: Bash for the command guards,
Write, Edit, MultiEdit and NotebookEdit for the ones that read what is about
to be written. It is not "*", because an interpreter start on every Read buys
nothing. Add a tool the first time you write a guard that judges it, and
selftest.py checks that you did: a guard wired behind a matcher that never
names its tool is a file that never runs, and because the dispatcher fails
open, nothing at runtime says so. This repository shipped two that way.

Reads the hook payload as JSON on stdin. Exit codes:

    0 = allowed
    2 = blocked; stderr carries the reason, and the model reads it

A guard that crashes or misbehaves does NOT block. That is deliberate: one syntax
error must not become an unbypassable wall across unrelated work, because a
harness that blocks everything gets switched off within the hour and takes the
working guards with it. The cost of failing open is that breakage is silent to
the model -- which is why selftest.py belongs in the fast CI lane.

## What a guard is not

A guard is a *speed bump*, not a boundary. It pattern-matches the text of a
proposed command, so `B=push; git $B origin main | tail` sails through, and it
fails open by construction (above). Both are correct trade-offs for what it is
for -- catching the mistake you were about to make by habit -- and both make it
unfit for anything adversarial.

So when a rule truly cannot tolerate a miss, a guard is the *third* line, not
the first:

    permissions.deny in .claude/settings.json   evaluated by the harness, not
                                                by a regex we maintain
    server-side branch protection, CI required  survives the laptop entirely
    a guard here                                explains why, at the moment,
                                                to whoever was about to do it

The guard's real product is the paragraph on stderr. Prefer a deny rule for
anything a deny rule can express; see no_protected_branch_push.py for the shape
of a rule that genuinely cannot be expressed as one.

Each guard module in this directory exposes:

    def check(tool_name: str, tool_input: dict) -> str | None
        # None to allow; a reason string to block

    CASES: list[tuple[str, dict, bool]]
        # (tool_name, tool_input, should_block) -- read by selftest.py

Nothing here counts how often a guard fires. That was built and removed; see
docs/decisions/0023 for what five agent products do instead, and why a count
kept per-checkout in `.git/` is a weaker signal than it looks.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_guards(directory=HERE):
    """Import every guard module. Returns (guards, broken)."""
    guards, broken = [], []
    for name in sorted(os.listdir(directory)):
        if (not name.endswith(".py")
                or name.startswith("_")
                or name in ("dispatch.py", "selftest.py")):
            continue
        path = os.path.join(directory, name)
        try:
            spec = importlib.util.spec_from_file_location(f"guard_{name[:-3]}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not callable(getattr(mod, "check", None)):
                broken.append((name, "no check() function"))
                continue
            guards.append((name, mod))
        except Exception as exc:  # a broken guard must not break the others
            broken.append((name, f"{type(exc).__name__}: {exc}"))
    return guards, broken


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        # Cannot see the action, so cannot judge it. Allow, and say so.
        print("guards: hook payload did not parse; no guard evaluated",
              file=sys.stderr)
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}

    guards, broken = load_guards()
    reasons = []
    for name, mod in guards:
        try:
            reason = mod.check(tool_name, tool_input)
        except Exception as exc:
            broken.append((name, f"raised {type(exc).__name__}: {exc}"))
            continue
        if reason:
            reasons.append(reason.strip())

    for name, why in broken:
        print(f"guards: {name} is broken and did not run ({why})", file=sys.stderr)

    if reasons:
        print("\n\n".join(reasons), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
