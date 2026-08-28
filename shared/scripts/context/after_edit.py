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
# Must equal index/build.py's window. It did not: this scanned 40 lines and the
# graph builder scanned 60, so a `Governs:` on line 50 created an edge in the
# graph and produced no hint here -- the convention half-worked, in a direction
# nobody would think to test. These two files cannot share a constant (they are
# installed at different tiers and one is often absent), so the index selftest
# asserts they agree instead.
GOVERNS_HEAD = 60
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


MAX_DOCS_SCANNED = 500


def covers(target, rel):
    """Whether a `Governs:` target covers this path.

    Must agree with `governed_by` in scripts/index/build.py exactly. Two
    implementations of one convention is already one too many; two that
    *disagree* means a document governs a file in the graph and not in the
    hook, which is indistinguishable from the convention not working."""
    t = target.rstrip("*")
    if t.endswith("/"):
        return rel.startswith(t)
    return rel == t or rel.startswith(t + "/")


def markdown_files(root):
    """Every tracked markdown file, not just docs/.

    This used to walk `docs/` only, while build.py indexed every tracked
    markdown. A `Governs:` line in ARCHITECTURE.md or a skill therefore created
    a real edge in the graph and was invisible here -- the delivery moment the
    convention exists for. Same set on both sides or the convention is a
    coin flip."""
    out = subprocess.run(["git", "ls-files", "-z", "*.md"], cwd=root,
                         capture_output=True, text=True)
    if out.returncode == 0:
        return [p for p in out.stdout.split("\0") if p][:MAX_DOCS_SCANNED]
    docs = os.path.join(root, "docs")          # not a git repo: best effort
    return [os.path.relpath(os.path.join(d, n), root)
            for d, _, names in os.walk(docs) for n in names
            if n.endswith(".md")][:MAX_DOCS_SCANNED]


def governing_docs(root, rel):
    """Documents whose `Governs:` target covers this path. Reading head bytes
    inline is cheap enough; building an index for it would be a second source
    of truth that can go stale."""
    hits = []
    for doc in markdown_files(root):
        try:
            with open(os.path.join(root, doc), encoding="utf-8",
                      errors="replace") as fh:
                head = "".join(fh.readlines()[:GOVERNS_HEAD])
        except OSError:
            continue
        for spec in GOVERNS.findall(head):
            if any(covers(t, rel) for t in re.split(r"[,\s]+", spec.strip()) if t):
                hits.append(doc)
                break
    return sorted(set(hits))


def neighbours(root, rel, limit=4):
    """(paths, stale) — adjacent files, and whether the graph is out of date.

    `stale` is not decoration. Nothing in this repository rebuilds the graph,
    so by the time an agent is editing, the neighbour list can describe a tree
    that no longer exists. query.py reports that on stderr; this used to
    capture stderr and discard it, which meant the detection existed and the
    only consumer of the answer never saw it. A stale hint presented as a
    current one is the failure build.py's own docstring warns about, delivered
    through the one moment that fires automatically."""
    query = os.path.join(root, "scripts", "index", "query.py")
    graph = os.path.join(root, ".index", "graph.json")
    if not (os.path.exists(query) and os.path.exists(graph)):
        return [], False
    try:
        proc = subprocess.run(
            [sys.executable, query, "--root", root, "--seed", rel,
             "--hops", "1", "--paths-only", "--budget", "200"],
            capture_output=True, text=True, timeout=15, cwd=root)
    except (OSError, subprocess.SubprocessError):
        return [], False
    if proc.returncode != 0:
        return [], False
    stale = "graph is stale" in proc.stderr
    return ([l for l in proc.stdout.splitlines() if l and l != rel][:limit],
            stale)


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
    near, stale = neighbours(root, rel)
    if near:
        lines.append("adjacent in the repo graph: " + ", ".join(near)
                     + (" (graph is out of date — rebuild with "
                        "scripts/index/build.py before trusting this)"
                        if stale else ""))

    if lines:
        print("\n".join(lines[:MAX_LINES]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
