#!/usr/bin/env python3
"""PreToolUse dispatcher: run every guard in this directory against one proposed
tool call.

Wire it once in .claude/settings.json and never touch the wiring again -- adding
a rule is adding one file here.

    {
      "hooks": {
        "PreToolUse": [{
          "matcher": "Bash",
          "hooks": [{"type": "command",
                     "command": "python3 scripts/guards/dispatch.py"}]
        }]
      }
    }

The matcher is "Bash" because every guard that ships here returns early on any
other tool; paying an interpreter start on Read and Edit buys nothing. Widen it
to "*" the first time you write a guard that judges a non-Bash call, and not
before.

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

    def fingerprint(tool_input: dict) -> str        # optional
        # collapse the spellings of one mistake into one identity, so that
        # _recurrence.py counts the habit rather than the wording

## Counting

Every refusal is counted by shape in `.git/agent-harness/`, and when the same
shape is refused three times inside a fortnight one paragraph is appended to
the reason. A guard that keeps refusing the same thing is not a guard working;
it is a habit meeting a speed bump, and habits are cheaper to move than to keep
stopping. See `_recurrence.py`, which is underscored so this file does not try
to load it as a guard, and which fails open like everything else here.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _recurrence():
    """Optional. A repository that deleted the counter keeps its guards."""
    path = os.path.join(HERE, "_recurrence.py")
    if not os.path.exists(path):
        return None
    try:
        spec = importlib.util.spec_from_file_location("guard_recurrence", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:                                    # noqa: BLE001
        return None


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
    counter = _recurrence()
    reasons, notes = [], []
    for name, mod in guards:
        try:
            reason = mod.check(tool_name, tool_input)
        except Exception as exc:
            broken.append((name, f"raised {type(exc).__name__}: {exc}"))
            continue
        if reason:
            reasons.append(reason.strip())
            if counter is not None:
                # Ask the counter where the repository is rather than assuming
                # scripts/guards/ is two levels below it. In this plugin's own
                # tree the guards live at shared/scripts/guards/, and a fixed
                # depth would count into a directory with no .git in it --
                # silently, which is the worst way for a counter to be wrong.
                note = counter.observe(counter.repo_root(HERE), name,
                                       tool_input, mod)
                if note:
                    notes.append(note)

    for name, why in broken:
        print(f"guards: {name} is broken and did not run ({why})", file=sys.stderr)

    if reasons:
        print("\n\n".join(reasons + notes), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
