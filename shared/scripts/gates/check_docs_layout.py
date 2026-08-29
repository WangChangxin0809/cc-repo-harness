#!/usr/bin/env python3
"""Gate: docs/ has the agreed top level, and nothing pretending to be it.

    python3 scripts/gates/check_docs_layout.py [--root .]

    0 = the top level is sound    1 = drift    2 = cannot judge

**Only the top level is fixed. Inside each directory, organise however suits
the material.** That split is not a compromise, it is the finding: OpenStack
mandates a shallow top level for every project repository and explicitly leaves
the interior free, and it held for about a decade across hundreds of
repositories -- six of seven sampled conform, each with project-specific
additions alongside. Meanwhile the two controlled studies of documentation
*shape* -- one on people, one on agent sessions -- both found no effect. So the
constraint goes where the evidence is and stays off where it is not.

The failure this catches is the one that actually happened to the seventh
repository: a required bucket quietly renamed, `configuration/` becoming
`config/`. Nothing breaks that day. The taxonomy forks, both spellings
accumulate documents, and by the time anyone notices, merging them is a
migration. A near-miss is therefore always an error, even when the directory is
routed from the index -- being routed makes a fork legible, not harmless.

An unrecognised directory that is *not* a near-miss is a different matter. A
repository may legitimately need `docs/images/`, and OpenStack's conformers all
carried additions. So an addition is allowed once the index routes it, which
makes adding one a deliberate, reviewable act rather than an accident.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

LINK = re.compile(r"\]\(([^)#]+?)(?:#[^)]*)?\)|`(docs/[\w./-]+)`")

# Fixed, and small on purpose. Each earned its place from what survived in
# repositories much older than any we will scaffold; `docs/index.md` carries
# the reasoning, and docs/decisions/ carries the evidence.
REQUIRED = ("decisions", "exec-plans", "how-to", "reference")

# The spellings a taxonomy forks into. Left is the drift, right is ours.
# Deliberately a table and not an edit distance: `adr` is nowhere near
# `decisions` by any string metric, and it is the single most likely fork of
# it -- roughly twice as common on GitHub as `decisions` is.
ALIASES = {
    "adr": "decisions", "adrs": "decisions", "decision": "decisions",
    "architecture-decisions": "decisions", "arch": "decisions",
    "design": "decisions", "rfc": "decisions", "rfcs": "decisions",
    "howto": "how-to", "how-tos": "how-to", "howtos": "how-to",
    "how_to": "how-to", "guides": "how-to", "guide": "how-to",
    "tutorial": "how-to", "tutorials": "how-to", "recipes": "how-to",
    "ref": "reference", "refs": "reference", "references": "reference",
    "exec-plan": "exec-plans", "execplans": "exec-plans", "plans": "exec-plans",
    "plan": "exec-plans", "tasks": "exec-plans", "roadmap": "exec-plans",
}


def routed_dirs(docs, index_text):
    """Top-level docs/ directories the index deliberately points into."""
    reached = set()
    for m in LINK.finditer(index_text):
        target = (m.group(1) or m.group(2) or "").strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        rel = target[len("docs/"):] if target.startswith("docs/") else target
        head = os.path.normpath(rel).split(os.sep)[0]
        if head and head not in (".", ".."):
            reached.add(head)
    return reached


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    docs = os.path.join(root, "docs")
    index = os.path.join(docs, "index.md")

    if not os.path.isdir(docs):
        print("cannot judge: no docs/ directory", file=sys.stderr)
        return 2
    if not os.path.exists(index):
        print("cannot judge: no docs/index.md", file=sys.stderr)
        return 2

    with open(index, encoding="utf-8") as fh:
        index_text = fh.read()
    routed = routed_dirs(docs, index_text)

    forks, strays, loose = [], [], []
    for name in sorted(os.listdir(docs)):
        path = os.path.join(docs, name)
        if name.startswith("."):
            continue
        if os.path.isfile(path):
            if name != "index.md":
                loose.append(name)
            continue
        if name in REQUIRED:
            continue
        if name.lower() in ALIASES:
            forks.append((name, ALIASES[name.lower()]))
        elif name not in routed:
            strays.append(name)

    if not forks and not strays and not loose:
        return 0

    if forks:
        print(f"{len(forks)} director(ies) fork a required name:", file=sys.stderr)
        for name, canonical in forks:
            print(f"  docs/{name}/  ->  docs/{canonical}/", file=sys.stderr)
        print("  Two spellings of one bucket both accumulate documents, and\n"
              "  merging them later is a migration. Rename now, while it is\n"
              "  a `git mv`.", file=sys.stderr)
    if strays:
        print(f"\n{len(strays)} top-level director(ies) the index does not route:",
              file=sys.stderr)
        for name in strays:
            print(f"  docs/{name}/", file=sys.stderr)
        print(f"  The fixed top level is: {', '.join(REQUIRED)}.\n"
              "  Additions are allowed -- add a row to docs/index.md pointing\n"
              "  into it, so that adding one is a deliberate act.", file=sys.stderr)
    if loose:
        print(f"\n{len(loose)} file(s) loose at the top of docs/:", file=sys.stderr)
        for name in loose:
            print(f"  docs/{name}", file=sys.stderr)
        print("  Only docs/index.md belongs there. A document with no bucket\n"
              "  is a document whose reading trigger was never decided.",
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
