#!/usr/bin/env python3
"""Gate: the always-on context budget.

    python3 scripts/gates/check_context_budget.py [--root .] [--cap 100]

    0 = within budget    1 = over    2 = cannot judge

`CLAUDE.md` and every installed skill's `description` are paid on every turn of
every session, forever. Nothing about that cost is visible while writing them --
each addition is one plausible line -- so it only ever grows. This gate is the
feedback the writing does not otherwise have.

It judges three things:

  1. CLAUDE.md line count against the cap.
  2. Skill descriptions, summed. Every description in `.claude/skills/*/SKILL.md`
     is loaded whether the skill triggers or not; twenty skills at eighty tokens
     each is 1,600 tokens gone before anyone types.
  3. Nested CLAUDE.md files are *not* counted -- they are the escape hatch this
     gate exists to push work toward, and charging for them would push it back.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys

TOKENS_PER_WORD = 1.35   # measured against tokenized English prose; identifiers
                         # and punctuation push it higher, so this under-reports


def frontmatter_description(path):
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return ""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return ""
    d = re.search(r"^description:\s*(.+?)(?=\n\w+:|\Z)", m.group(1), re.S | re.M)
    return " ".join(d.group(1).split()) if d else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--cap", type=int, default=100,
                    help="max lines in the root CLAUDE.md")
    ap.add_argument("--skill-cap", type=int, default=2000,
                    help="max total tokens of always-on skill descriptions")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    failures = []

    claude = os.path.join(root, "CLAUDE.md")
    if not os.path.exists(claude):
        print("cannot judge: no CLAUDE.md at the repository root",
              file=sys.stderr)
        return 2
    with open(claude, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    body = [l for l in lines if l.strip() and not l.strip().startswith("<!--")]
    if len(lines) > a.cap:
        failures.append(
            f"CLAUDE.md is {len(lines)} lines, cap is {a.cap}.\n"
            f"  Move rules out, do not compress them:\n"
            f"    - an action a script can block   -> scripts/guards/\n"
            f"    - a state a script can detect    -> scripts/gates/\n"
            f"    - true only inside one directory -> that directory's CLAUDE.md\n"
            f"    - a procedure with a trigger     -> a skill\n"
            f"  See docs/decisions/0001-agent-harness.md")

    # An empty or placeholder CLAUDE.md passes every length check ever written.
    # One positive assertion is what catches it.
    if len(body) < 5:
        failures.append("CLAUDE.md has almost no content — a template left "
                        "unfilled is worse than no file, because it reads as "
                        "though the conventions were written down.")

    total = 0
    per_skill = []
    for path in sorted(glob.glob(os.path.join(root, ".claude", "skills",
                                              "*", "SKILL.md"))):
        desc = frontmatter_description(path)
        cost = int(len(desc.split()) * TOKENS_PER_WORD)
        total += cost
        per_skill.append((os.path.basename(os.path.dirname(path)), cost))
    if total > a.skill_cap:
        listing = "\n".join(f"    {n:<32} ~{c} tok"
                            for n, c in sorted(per_skill, key=lambda t: -t[1]))
        failures.append(
            f"Skill descriptions cost ~{total} tokens on every turn, cap is "
            f"{a.skill_cap}.\n{listing}\n"
            f"  Merge skills that compete for the same trigger; split only what\n"
            f"  is re-entered independently. See the writing-docs skill.")

    if not failures:
        return 0
    for f in failures:
        print(f, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
