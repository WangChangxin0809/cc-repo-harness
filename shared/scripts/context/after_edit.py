#!/usr/bin/env python3
"""PostToolUse: say what the file just edited is connected to.

Wire on Edit|Write|MultiEdit. Reads the hook payload on stdin, prints at most a
few lines to stdout, always exits 0 -- this is delivery, not judgment, and a
hook that can block an edit that already happened is a hook that only confuses
people.

Moment 6 is the one place a repository can react to what the agent actually did
rather than what it said it would do. Two things are worth saying there, and
both are invisible from inside the edit:

  1. **A document governs this path.** Someone wrote down how this code is
     supposed to work, in a file the agent has no reason to open. `Governs:` in
     the document's first lines is what makes that discoverable, and this is
     where it gets delivered.

  2. **What else is adjacent.** One hop through the repo graph, which costs a
     single pass over the edge list. Not the full ranking -- that runs in
     seconds, and seconds on every edit is a tax nobody accepts for a hint.

If neither applies, print nothing. A hook that speaks after every edit is a hook
whose output stops being read, and then the one time it mattered is missed too.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

GOVERNS = re.compile(r"^Governs:\s*(.+)$", re.M)
MAX_LINES = 6


def repo_root(start="."):
    cur = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def edited_path(payload, root):
    for key in ("file_path", "path", "notebook_path"):
        p = payload.get("tool_input", {}).get(key)
        if p:
            p = os.path.abspath(p)
            return os.path.relpath(p, root) if p.startswith(root) else None
    return None


def governing_docs(root, rel):
    """Documents whose `Governs:` prefix covers this path. Scanning docs/ head
    bytes is cheap enough to do inline; building an index for it would be a
    second source of truth that can go stale."""
    hits = []
    docs = os.path.join(root, "docs")
    for dirpath, dirnames, filenames in os.walk(docs):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    head = "".join(fh.readlines()[:40])
            except OSError:
                continue
            for spec in GOVERNS.findall(head):
                for target in re.split(r"[,\s]+", spec.strip()):
                    if target and rel.startswith(target.rstrip("*")):
                        hits.append(os.path.relpath(path, root))
                        break
    return sorted(set(hits))


def neighbours(root, rel, limit=4):
    query = os.path.join(root, "scripts", "index", "query.py")
    graph = os.path.join(root, ".index", "graph.json")
    if not (os.path.exists(query) and os.path.exists(graph)):
        return []
    try:
        proc = subprocess.run(
            [sys.executable, query, "--root", root, "--seed", rel,
             "--hops", "1", "--paths-only", "--budget", "200"],
            capture_output=True, text=True, timeout=15, cwd=root)
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    return [l for l in proc.stdout.splitlines() if l and l != rel][:limit]


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    root = repo_root()
    if root is None:
        return 0
    rel = edited_path(payload, root)
    if not rel:
        return 0

    lines = []
    for doc in governing_docs(root, rel)[:2]:
        lines.append(f"{doc} governs {rel} — read it before assuming how this "
                     f"is supposed to work")
    near = neighbours(root, rel)
    if near:
        lines.append("adjacent in the repo graph: " + ", ".join(near))

    if lines:
        print("\n".join(lines[:MAX_LINES]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
