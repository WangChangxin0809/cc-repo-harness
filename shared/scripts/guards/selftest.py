#!/usr/bin/env python3
"""Prove every guard fires on what it should and stays out of the way otherwise.

    python3 scripts/guards/selftest.py [-v]

    0 = every declared case behaved as declared
    1 = a guard misbehaved, or is not adequately tested
    2 = cannot judge (no guards found, a guard failed to import)

Put this in the fast CI lane. A guard is a file that claims to block something;
until it has been observed blocking -- and observed *not* blocking a near miss --
that claim is untested. The dispatcher deliberately fails open, so a guard that
quietly stopped working is invisible at runtime. This is what makes it visible.

Three structural requirements, checked alongside the cases themselves:

* At least one case per guard must expect a block, and at least one must not.
  A guard with only positive cases passes every test while blocking everything,
  and you find out when it has cost someone a day.
* A blocking guard must return a non-empty reason. Exit code 2 is reached by
  several different paths, including a guard crashing on unexpected input, so a
  test that only checks the code passes while the guard is broken.
* Every tool a guard can refuse must be one its wiring shows it. A guard that
  judges a Write behind `matcher: "Bash"` in .claude/settings.json is a file
  that never runs, and because the dispatcher fails open, an unasked guard
  and a quiet one look identical at runtime. This repository shipped two
  guards that way.
"""

from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dispatch import load_guards  # noqa: E402


def _settings_above(start):
    """The nearest .claude/settings*.json above the guards directory."""
    cur = os.path.abspath(start)
    for _ in range(8):
        found = [os.path.join(cur, ".claude", name)
                 for name in ("settings.json", "settings.local.json")
                 if os.path.exists(os.path.join(cur, ".claude", name))]
        if found:
            return found
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return []


def _matches(matcher, tool):
    """Would Claude Code run a hook with this matcher for this tool?"""
    if not matcher or matcher in ("*", ".*"):
        return True
    try:
        return re.fullmatch(matcher, tool) is not None
    except re.error:
        return tool in [p.strip() for p in matcher.split("|")]


def wiring_gaps(guards, here=HERE):
    """Tools a guard can refuse that its wiring never shows it.

    Silent when nothing above this directory wires dispatch.py: then the
    wiring is somebody else's, or absent, and neither is this check's
    subject."""
    matchers = []
    for path in _settings_above(here):
        try:
            with open(path, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except (OSError, ValueError):
            continue
        for group in (cfg.get("hooks") or {}).get("PreToolUse") or []:
            commands = [h.get("command") or "" for h in group.get("hooks") or []]
            if any("dispatch.py" in c for c in commands):
                matchers.append((group.get("matcher") or "",
                                 os.path.join(".claude", os.path.basename(path))))
    if not matchers:
        return []
    refuses = {}
    for name, mod in guards:
        for tool, _input, should in getattr(mod, "CASES", None) or []:
            if should:
                refuses.setdefault(tool, set()).add(name)
    gaps = []
    for tool in sorted(refuses):
        if any(_matches(m, tool) for m, _where in matchers):
            continue
        wired = ", ".join(f'matcher "{m}" in {where}' for m, where in matchers)
        gaps.append(f"{', '.join(sorted(refuses[tool]))}: refuses a {tool}, but "
                    f"dispatch.py is wired at {wired}, so it is never asked "
                    f"-- a file that never runs. Name {tool} in the matcher.")
    return gaps


def main():
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    guards, broken = load_guards()

    for name, why in broken:
        print(f"CANNOT JUDGE  {name}: {why}")
    if broken:
        return 2
    if not guards:
        print("CANNOT JUDGE  no guard modules found")
        return 2

    failures = []
    for name, mod in guards:
        cases = getattr(mod, "CASES", None)
        if not cases:
            failures.append(f"{name}: declares no CASES, so nothing proves it works")
            continue

        expected_block = sum(1 for *_, should in cases if should)
        if expected_block == 0:
            failures.append(f"{name}: no case expects a block -- untested")
        if expected_block == len(cases):
            failures.append(
                f"{name}: every case expects a block, so no negative control. "
                "A guard that blocks everything would pass this suite.")

        for tool_name, tool_input, should_block in cases:
            try:
                reason = mod.check(tool_name, tool_input)
            except Exception as exc:
                failures.append(
                    f"{name}: raised {type(exc).__name__} on {tool_input!r}")
                continue

            blocked = bool(reason)
            shown = str(tool_input)[:70]
            if blocked != should_block:
                verb = "did not block" if should_block else "blocked"
                failures.append(f"{name}: {verb} {shown}")
            elif blocked and not str(reason).strip():
                failures.append(f"{name}: blocked {shown} with an empty reason")
            elif verbose:
                print(f"  ok  {name:<34} {'block ' if blocked else 'allow '} {shown}")

    failures += wiring_gaps(guards)

    total = sum(len(getattr(m, 'CASES', [])) for _, m in guards)
    if failures:
        print(f"\nFAIL  {len(failures)} problem(s) across {len(guards)} guard(s):")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(f"PASS  {len(guards)} guard(s), {total} case(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
