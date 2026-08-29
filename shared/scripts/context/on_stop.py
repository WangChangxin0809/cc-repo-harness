#!/usr/bin/env python3
"""Stop hook: do not let a turn end on a red tree without saying so.

Wire it in `.claude/settings.json`:

    {"hooks": {"Stop": [{"matcher": "*", "hooks": [
      {"type": "command", "command": "python3 scripts/context/on_stop.py"}]}]}}

    0 = let the turn end    2 = block, and hand the failures back

The moment an agent stops is the last moment anything can be said to it. Every
other check in this repository fires while work is happening -- a guard before a
tool call, a gate in CI, a context script after an edit. None of them cover the
specific failure of *finishing* with the tree broken, which is the one a person
finds out about later, from CI, after the agent is gone.

**This hook fails open, and that is the opposite of a gate.** A gate returns 2
for "could not judge" and 2 is never a pass, because a check that cannot see its
subject must not bless it. Here the inversion is deliberate: a Stop hook that
errors while blocking would make the session impossible to end. The cost of a
false block is an agent that cannot stop; the cost of a false pass is a red tree
that CI catches minutes later. Those are not comparable, so anything unexpected
here lets the turn end.

Only checks that are fast and about *this repository's state* belong here. The
selftests are not: they take too long to pay on every stop, and they are about
whether the checks work rather than whether the tree is sound.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

# Fast, worktree-scoped, and each one already prints a remedy on failure.
CHECKS = (
    ("docs/index.md routes to every document", "gates/check_docs_index.py"),
    ("documented commands still run", "gates/check_docs_runnable.py"),
    ("templates are filled in", "gates/check_templates_filled.py"),
    ("docs/ top level is the agreed one", "gates/check_docs_layout.py"),
)

BUDGET_SECONDS = 45


def repo_root(start):
    """The worktree root, or None. `git rev-parse` rather than walking up for
    `.git`, because a worktree's `.git` is a file and a submodule's points
    elsewhere."""
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             cwd=start, capture_output=True, text=True,
                             timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    # The runtime sets this when the turn is already a continuation caused by
    # this hook. Without the check, a defect that can never be fixed becomes an
    # unbreakable loop -- the agent is asked to fix it, stops, is blocked again.
    if payload.get("stop_hook_active"):
        return 0

    here = os.path.dirname(os.path.abspath(__file__))
    root = repo_root(here)
    if root is None:
        return 0

    scripts = os.path.dirname(here)
    failures = []
    for label, rel in CHECKS:
        path = os.path.join(scripts, rel)
        if not os.path.exists(path):
            continue
        try:
            out = subprocess.run([sys.executable, path, "--root", root],
                                 capture_output=True, text=True,
                                 timeout=BUDGET_SECONDS)
        except (OSError, subprocess.SubprocessError):
            # Failing open, per the module docstring.
            continue
        # 1 is a judged failure. 2 is "could not judge" and does not block a
        # stop: blocking on it would trap the agent for a reason it cannot see.
        if out.returncode == 1:
            detail = (out.stderr or out.stdout).strip()
            failures.append(f"--- {label} ---\n{detail}")

    if not failures:
        return 0

    print("Stopping with the tree red. Fix these, or say plainly in your reply "
          "that you are leaving them and why:\n\n" + "\n\n".join(failures),
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
