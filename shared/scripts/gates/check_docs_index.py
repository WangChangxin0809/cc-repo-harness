#!/usr/bin/env python3
"""Gate: docs/index.md routes to every document, and every path it names exists.

    python3 scripts/gates/check_docs_index.py [--root .]

    0 = consistent    1 = drift    2 = cannot judge

Two failures, opposite directions, both silent:

  * A document nothing routes to. It was written, and then it was never read --
    which looks exactly like a document that is simply not needed, so nobody
    notices for a year.
  * A route to a path that no longer exists. The reader follows it, finds
    nothing, and concludes the documentation is unreliable in general.

Ten lines of checking catches both in the week they happen instead of the
quarter. Files whose first 40 lines contain `<!-- unrouted: reason -->` are
exempt; the reason is required, because an exemption without one becomes a
blanket exemption.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

LINK = re.compile(r"\]\(([^)#]+?)(?:#[^)]*)?\)|`(docs/[\w./-]+)`")
EXEMPT = re.compile(r"<!--\s*unrouted:\s*\S+")
SKIP_DIRS = {"generated"}


PLANS = os.path.join("docs", "exec-plans")


def plan_steps(root, routed):
    """Files an already-routed exec-plan README links inside its own folder.

    Multi-session work outgrows one file: the plan's state has to be readable at
    a glance while a single step may carry pages of decisions. So a plan is a
    folder -- `README.md` plus `steps/` -- and one row in the routing table has
    to cover all of it. Ten steps meaning ten rows would bury the table's actual
    job, which is answering "I am about to do X, what do I read".

    Deliberately one hop, and deliberately confined to the plan's own folder. A
    general transitive closure would make routing accidental: any document
    mentioned in passing by any routed document would count as reached, and the
    gate's whole subject is documents that nothing deliberately points at. Here
    the README is the deliberate pointer, and it is itself routed from the index
    or none of this applies.

    A step file the README does not link stays unrouted and is reported -- the
    same defect one level down, and the one this shape makes easy to create."""
    reached = set()
    for rel in routed:
        parts = rel.split(os.sep)
        if not (rel.startswith(PLANS + os.sep) and len(parts) == 4
                and parts[3] == "README.md"):
            continue
        folder = os.path.dirname(rel)
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                body = fh.read()
        except OSError:
            continue
        for m in LINK.finditer(body):
            target = (m.group(1) or m.group(2) or "").strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            norm = os.path.normpath(
                target if target.startswith("docs/")
                else os.path.join(folder, target))
            # Confined to the plan's own folder: a README may not route a
            # document that belongs to somebody else's part of docs/.
            if norm.startswith(folder + os.sep):
                reached.add(norm)
    return reached


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    docs = os.path.join(root, "docs")
    index = os.path.join(docs, "index.md")

    if not os.path.exists(index):
        print("cannot judge: no docs/index.md", file=sys.stderr)
        return 2

    with open(index, encoding="utf-8") as fh:
        index_text = fh.read()

    routed = set()
    for m in LINK.finditer(index_text):
        target = (m.group(1) or m.group(2) or "").strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        norm = os.path.normpath(os.path.join("docs", target)
                                if not target.startswith("docs/") else target)
        routed.add(norm)

    routed |= plan_steps(root, routed)

    present = set()
    for dirpath, dirnames, filenames in os.walk(docs):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS
                       and not d.startswith(".")]
        for name in filenames:
            if not name.endswith(".md"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            if rel == "docs/index.md":
                continue
            with open(os.path.join(dirpath, name), encoding="utf-8") as fh:
                head = "".join(fh.readlines()[:40])
            if EXEMPT.search(head):
                continue
            present.add(rel)

    unrouted = sorted(present - routed)
    # Directories are legitimate route targets; only judge file routes.
    broken = sorted(p for p in routed - present
                    if not os.path.exists(os.path.join(root, p)))

    if not unrouted and not broken:
        return 0

    if unrouted:
        print(f"{len(unrouted)} document(s) that docs/index.md does not route to:",
              file=sys.stderr)
        for p in unrouted:
            print(f"  {p}", file=sys.stderr)
        print("  Add a row to the routing table, or mark the file\n"
              "  <!-- unrouted: <reason> --> if it is deliberately unreachable.",
              file=sys.stderr)
    if broken:
        print(f"\n{len(broken)} route(s) in docs/index.md point at nothing:",
              file=sys.stderr)
        for p in broken:
            print(f"  {p}", file=sys.stderr)
        print("  A dead link has two causes that look identical. Run\n"
              "    git cat-file -e HEAD:<path>\n"
              "  exit 0 means the file was deleted from the worktree — restore it.\n"
              "  Non-zero means it never existed here — fix the link.",
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
