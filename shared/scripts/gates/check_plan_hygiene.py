#!/usr/bin/env python3
"""Gate: a finished exec-plan is not still shipping its CLAUDE.md.

    python3 scripts/gates/check_plan_hygiene.py [--root .]

    0 = no finished plan is still delivering one    1 = one is    2 = cannot judge

An active plan folder carries a `CLAUDE.md`, and the runtime delivers it
whenever anything in that folder is read. That is the point of it: while the
plan is in flight, the invariant not to break and the command that proves a step
landed are worth paying for on every touch.

The moment the plan finishes, every line in that file stops being true and none
of it stops being delivered. `docs/index.md` says to delete it, and that
sentence has no enforcement behind it, which is the shape of a rule that gets
followed until the first busy afternoon.

**Why this one runs at Stop as well as in CI.** Every other exec-plan rule is
charged per pull request: a reviewer sees it, or CI does, and the cost of being
late is one review cycle. This one is charged *per turn* -- a stale plan
CLAUDE.md is injected into every session that touches the folder, for as long as
it exists. A cost measured in turns has to be objected to at a turn boundary, so
`scripts/context/on_stop.py` runs it too.

## What counts as finished

Only checkbox rows and table rows are read, never prose, and fenced blocks are
stripped first. `session_brief.py` learned this the expensive way: its first
version matched `doing` anywhere and reported a README that merely *explains*
the convention -- "nobody reopens a finished step to change `doing` to `done`"
-- as the step in progress. A README that documents the markers would be read as
using them.

A plan whose README has no state rows at all is not judged. That is a folder
somebody has started rather than a plan that has ended, and a gate that fires
on it would fire in the one window where the author is still typing.

Only the `CLAUDE.md` is judged, not the folder. `kinds.md` says to delete the
whole folder on completion and promote anything decided into a decision record,
but writing that record takes an afternoon, and the folder sitting there
meanwhile is a legitimate state. The `CLAUDE.md` has no such window: from the
moment the last step closes there is no turn on which its presence is correct.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys

# Fenced blocks are removed before any row matching. A README showing the
# marker table inside ```markdown is documenting the convention, not using it.
FENCE = re.compile(r"^\s*(?:```|~~~)")

# A state row is a checkbox item or a table row. Anything else is prose, and
# prose about a plan is not the plan's state.
BOX = re.compile(r"^\s*[-*]\s+\[(.)\]")
TABLE = re.compile(r"^\s*\|")

# The markers `kinds.md` defines, plus the spellings a plan drifts into.
OPEN_WORDS = re.compile(r"\b(doing|todo|to-do|blocked|wip|in progress)\b", re.I)
CLOSED_WORDS = re.compile(r"\b(done|dropped|skipped|abandoned)\b", re.I)

# `[ ]` and `[>]` are open; `[x]`, `[X]` and `[~]` are closed. Anything else in
# the box is not a marker this convention defines, so the row falls through to
# its words rather than being guessed at.
OPEN_BOXES = " >"
CLOSED_BOXES = "xX~"


def strip_fences(body):
    out, inside = [], False
    for line in body.splitlines():
        if FENCE.match(line):
            inside = not inside
            continue
        if not inside:
            out.append(line)
    return out


def plan_state(body):
    """(open_rows, closed_rows) counted from one plan README."""
    opened = closed = 0
    for line in strip_fences(body):
        box = BOX.match(line)
        if box:
            char = box.group(1)
            if char in OPEN_BOXES:
                opened += 1
                continue
            if char in CLOSED_BOXES:
                closed += 1
                continue
        elif not TABLE.match(line):
            continue
        # A table row, or a checkbox whose marker is not one this convention
        # defines. Judge it by its words or not at all.
        if OPEN_WORDS.search(line):
            opened += 1
        elif CLOSED_WORDS.search(line):
            closed += 1
    return opened, closed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    plans = os.path.join(root, "docs", "exec-plans")

    # No plans is a judged pass, not a cannot-judge. Whether this directory has
    # to exist at all is `check_docs_layout.py`'s subject; this gate owns only
    # what is inside it, and zero plans means zero of them offend.
    if not os.path.isdir(plans):
        return 0

    stale = []
    for readme in sorted(glob.glob(os.path.join(plans, "*", "README.md"))):
        folder = os.path.dirname(readme)
        # Presence on disk, not in the index: the loader delivers the file it
        # finds, so an untracked one costs exactly as much as a committed one.
        nested = os.path.join(folder, "CLAUDE.md")
        if not os.path.exists(nested):
            continue
        try:
            with open(readme, encoding="utf-8") as fh:
                body = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            print(f"cannot judge: {os.path.relpath(readme, root)}: {exc}",
                  file=sys.stderr)
            return 2
        opened, closed = plan_state(body)
        if closed and not opened:
            stale.append((os.path.relpath(nested, root), closed))

    if not stale:
        return 0

    print(f"{len(stale)} finished plan(s) still delivering a CLAUDE.md:",
          file=sys.stderr)
    for rel, closed in stale:
        print(f"  {rel}\n"
              f"      every step in the README beside it is closed ({closed} of "
              f"{closed}), so nothing in this file is still true — and it is "
              f"still injected into every session that reads the folder",
              file=sys.stderr)
    print("\n  Delete it. If the plan is not actually finished, the README is\n"
          "  the thing that is wrong: reopen the step that is still running.\n"
          "  If it is finished, `docs/exec-plans/` wants the whole folder gone\n"
          "  and anything decided promoted into docs/decisions/.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
