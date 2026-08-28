#!/usr/bin/env python3
"""Dream: consolidate accumulated agent notes into a reviewable candidate.

    python3 dream.py prepare --notes <dir> [--sessions <dir>] [--out <dir>]
    python3 dream.py diff    [--out <dir>]

    0 = done            1 = differences need review (diff only)
    2 = cannot judge (no notes found, snapshot missing)

`prepare` copies the notes into a read-only snapshot and writes a synthesis
brief. Run the synthesis with a subagent whose write access is limited to the
candidate directory, then `diff` and decide.

The input is never modified, and that is the whole safety model. Consolidation
is lossy in a direction that reads as improvement: the output is shorter, better
organised, internally consistent, and quietly missing things. Diffing against an
untouched original is the only way to see what left.

Layout under --out (default `.dream/`):

    .dream/snapshot/    read-only copy of the inputs
    .dream/candidate/   the subagent writes here
    .dream/BRIEF.md     synthesis instructions
"""

from __future__ import annotations

import argparse
import difflib
import os
import shutil
import stat
import sys

BRIEF = """\
# Synthesis brief

Read every file in `snapshot/`. Write a reorganised store into `candidate/`.
Do not modify `snapshot/` — it is the control this pass is judged against.

## Merge

Merge entries whose CONCLUSION is the same. Do NOT merge entries whose
MEASUREMENTS differ: two readings of the same thing are data, not duplication.

## Preserve verbatim

In every entry that has them, carry through unchanged:

* measured numbers with their units  (`87 ms`, `11.6 / 26.1 / 30.2 ms`, `76.9%`)
* commit hashes, file paths, error strings, tool and version numbers
* dates on which something was measured

These read as incidental detail and are the first thing a summariser smooths
away. What is left — "performance measurements can be misleading" — is true,
useless, and impossible to act on. The reading is the entry's whole value.

## Keep the trail

When two entries contradict, keep the current conclusion AND the reason the
superseded one was believed. Mark which is current. Never delete the trail: an
entry recording a belief that was later overturned is worth more than the
correction alone, because the reason it was plausible is what recurs — and it
was paid for with a real failure.

## Promote

Promote a NEW entry only for a pattern appearing in three or more sessions.
State what was observed, not advice.

## Leave alone

Entries about the user's own preferences, machine, or habits are not knowledge
about the repository. Copy them through untouched.

## Route (this harness is repo-first)

For each surviving entry, put a `ROUTE:` line at its end:

    ROUTE: docs/<path>       # a rule of this repo
    ROUTE: guard             # can be blocked before it happens
    ROUTE: subtree-claude-md  # only true inside one directory
    ROUTE: memory            # genuinely about the user, not the repo

Only `memory` stays in the note store. Everything else should end this pass as a
repository change — reviewable in a diff, visible to teammates, checkable by a
gate. A rule living only in one person's memory does not exist for anyone else.
"""


def _harden(path):
    """Make the snapshot read-only, so 'never modify the input' is enforced by
    the filesystem and not by remembering."""
    for root, _, files in os.walk(path):
        for f in files:
            p = os.path.join(root, f)
            os.chmod(p, os.stat(p).st_mode & ~stat.S_IWUSR & ~stat.S_IWGRP
                     & ~stat.S_IWOTH)


def prepare(notes, sessions, out):
    if not os.path.isdir(notes):
        print(f"cannot judge: notes directory not found: {notes}", file=sys.stderr)
        return 2
    entries = [f for f in sorted(os.listdir(notes)) if f.endswith(".md")]
    if not entries:
        print(f"cannot judge: no .md notes in {notes}", file=sys.stderr)
        return 2

    snap = os.path.join(out, "snapshot")
    if os.path.exists(snap):
        shutil.rmtree(snap, onerror=lambda f, p, e: (os.chmod(p, 0o700), f(p)))
    shutil.copytree(notes, snap)
    if sessions and os.path.isdir(sessions):
        shutil.copytree(sessions, os.path.join(out, "sessions"),
                        dirs_exist_ok=True)
    _harden(snap)
    os.makedirs(os.path.join(out, "candidate"), exist_ok=True)
    with open(os.path.join(out, "BRIEF.md"), "w", encoding="utf-8") as fh:
        fh.write(BRIEF)

    print(f"snapshot   {snap}  ({len(entries)} entries, read-only)")
    if sessions and os.path.isdir(sessions):
        print(f"sessions   {os.path.join(out, 'sessions')}")
    print(f"brief      {os.path.join(out, 'BRIEF.md')}")
    print(f"candidate  {os.path.join(out, 'candidate')}  (empty — synthesis writes here)")
    print("\nNext: run the synthesis in a subagent that reads the brief and the\n"
          "snapshot, and may write ONLY to candidate/. Then: dream.py diff")
    return 0


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def diff(out):
    snap, cand = os.path.join(out, "snapshot"), os.path.join(out, "candidate")
    if not os.path.isdir(snap):
        print("cannot judge: no snapshot — run `dream.py prepare` first",
              file=sys.stderr)
        return 2
    before = {f for f in os.listdir(snap) if f.endswith(".md")}
    after = ({f for f in os.listdir(cand) if f.endswith(".md")}
             if os.path.isdir(cand) else set())
    if not after:
        print("cannot judge: candidate/ is empty — the synthesis has not run",
              file=sys.stderr)
        return 2

    dropped, added = sorted(before - after), sorted(after - before)
    changed, identical = [], []
    for name in sorted(before & after):
        a, b = _read(os.path.join(snap, name)), _read(os.path.join(cand, name))
        (identical if a == b else changed).append(name)

    print(f"unchanged {len(identical)}   rewritten {len(changed)}   "
          f"dropped {len(dropped)}   new {len(added)}\n")
    for name in dropped:
        print(f"  DROPPED  {name}")
    for name in added:
        print(f"  NEW      {name}")
    for name in changed:
        print(f"  REWRITTEN {name}")
        a = (_read(os.path.join(snap, name)) or "").splitlines()
        b = (_read(os.path.join(cand, name)) or "").splitlines()
        for line in list(difflib.unified_diff(a, b, lineterm="", n=1))[2:]:
            if line.startswith(("+", "-")):
                print(f"      {line}")

    print("\nReview before adopting. Check specifically:")
    print("  * every measured number and commit hash still present, verbatim")
    print("  * superseded beliefs still carry the reason they were believed")
    print("  * DROPPED entries were duplicates, not the only record of something")
    return 1 if (dropped or added or changed) else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["prepare", "diff"])
    ap.add_argument("--notes", default="")
    ap.add_argument("--sessions", default="")
    ap.add_argument("--out", default=".dream")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.command == "prepare":
        if not a.notes:
            print("cannot judge: --notes is required for prepare", file=sys.stderr)
            return 2
        return prepare(a.notes, a.sessions, a.out)
    return diff(a.out)


if __name__ == "__main__":
    sys.exit(main())
