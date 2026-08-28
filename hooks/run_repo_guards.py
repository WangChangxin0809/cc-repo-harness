#!/usr/bin/env python3
"""Run the *repository's own* guards, if it has any and has not wired them itself.

This is the one thing a plugin can do that a skill cannot, and it is worth being
precise about what it is for. Guards live in the target repository under
`scripts/guards/` so that they keep working after this plugin is uninstalled —
that is the whole acceptance criterion of the harness. But a repository that has
guards and has not yet wired `.claude/settings.json` gets no protection at all,
which is the exact window in which someone is most likely to lose work.

So: if the repo has guards, and its own settings do not already invoke them,
invoke them here. If its settings *do*, exit silently and let the repo's wiring
own it — running the same dispatcher twice doubles latency on every Bash call
and prints the block reason twice.

Contract, per PreToolUse:

    stdin  = JSON  {"tool_name": ..., "tool_input": {...}}
    exit 0 = allow (stdout is not shown to the model)
    exit 2 = block; stderr is fed back to the model as the reason
    other  = non-blocking error

Failures here are deliberately non-blocking. This runs before every Bash command
in every repository the plugin is enabled for; a bug in it must not become a
wall that nobody can get past. The repository's own `selftest.py` is what proves
the guards themselves work.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

DISPATCH = os.path.join("scripts", "guards", "dispatch.py")
SETTINGS = os.path.join(".claude", "settings.json")


def repo_root(start):
    """Nearest ancestor containing .git. Returns None outside a repository."""
    cur = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def repo_wires_it_already(root):
    path = os.path.join(root, SETTINGS)
    try:
        with open(path, encoding="utf-8") as fh:
            return "guards/dispatch.py" in fh.read()
    except OSError:
        return False


def main():
    raw = sys.stdin.read()
    root = repo_root(os.getcwd())
    if root is None:
        return 0

    dispatch = os.path.join(root, DISPATCH)
    if not os.path.exists(dispatch) or repo_wires_it_already(root):
        return 0

    try:
        json.loads(raw or "{}")
    except ValueError:
        return 0

    try:
        proc = subprocess.run([sys.executable, dispatch], input=raw, text=True,
                              capture_output=True, cwd=root, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"agent-harness: could not run repo guards: {exc}", file=sys.stderr)
        return 0

    if proc.returncode == 2:
        sys.stderr.write(proc.stderr)
        return 2
    if proc.returncode not in (0, 2):
        # The dispatcher itself is broken. Say so once, on stderr, and allow --
        # see the module docstring on why this fails open.
        sys.stderr.write(proc.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
