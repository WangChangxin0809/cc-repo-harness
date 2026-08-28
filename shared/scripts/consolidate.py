#!/usr/bin/env python3
"""Consolidate accumulated agent notes into a candidate you can review.

    python3 consolidate.py prepare --notes <dir> [--sessions <dir>] [--out <dir>]
    python3 consolidate.py diff    [--out <dir>]

    0 = done            1 = differences need review (diff only)
    2 = cannot judge (no notes found, snapshot missing)

This was called `dream.py`. It borrowed the name from Claude's Dreams API and
delivered something much smaller: Dreams is an asynchronous managed job that
runs a model over a memory store and up to 100 session transcripts and returns a
new store. This is two commands that freeze the input, hand a brief to whatever
you point at it, and then tell you what the output lost. Both halves are useful
and they are not the same thing, so this one is named after what it does. The
Dreams API itself is covered in the consolidating-notes skill's references.

`prepare` copies the notes into a read-only snapshot and writes a synthesis
brief. Run the synthesis with a subagent whose write access is limited to the
candidate directory, then `diff` and decide.

The input is never modified, and that is the whole safety model. Consolidation
is lossy in a direction that reads as improvement: the output is shorter, better
organised, internally consistent, and quietly missing things. Diffing against an
untouched original is the only way to see what left.

But a per-file diff cannot see it. Consolidation *merges* -- two entries become
one, under a third name -- and a name-keyed comparison reports that as
`DROPPED, DROPPED, NEW` whether the content survived or evaporated. So `diff`
leads with a comparison that ignores filenames entirely: every measurement,
commit hash, and path in the snapshot is looked for anywhere in the candidate.
That is the one check the brief asks for, and asking a human to do it by eye
across a merged corpus is asking for it not to happen.

Layout under --out (default `.consolidation/`):

    .consolidation/snapshot/    read-only copy of the inputs
    .consolidation/sessions/    transcripts, if given: the source of new observations
    .consolidation/candidate/   the subagent writes here
    .consolidation/BRIEF.md     synthesis instructions
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import shutil
import stat
import sys

# What must survive a merge character for character. Each of these is worthless
# once paraphrased -- "noticeably slower" cannot be compared against a later
# reading, and a rounded commit hash cannot be checked out -- and each reads as
# incidental detail to a summariser, which is why they are the first to go.
LOAD_BEARING = (
    ("measurement", re.compile(
        r"\b\d+(?:\.\d+)?\s?(?:ms|s|m|h|kb|mb|gb|k|%|x|ns|us|µs|"
        r"tokens?|files?|lines?|commits?)\b", re.I)),
    ("commit", re.compile(r"\b[0-9a-f]{7,40}\b")),
    ("path", re.compile(r"\b[\w.-]+/[\w./-]+\.\w{1,5}\b")),
    ("version", re.compile(r"\bv?\d+\.\d+(?:\.\d+)?\b")),
)
ROUTE = re.compile(r"^\s*ROUTE:\s*(\S+)", re.M)
ROUTE_KINDS = ("guard", "gate", "memory", "subtree-claude-md")

BRIEF = """\
# Synthesis brief

Read every file in `snapshot/`. Write a reorganised store into `candidate/`.
Do not modify `snapshot/` — it is the control this pass is judged against.

If `sessions/` exists, read it too. The notes are what somebody chose to write
down; the transcripts are where the things nobody thought to write down are
still visible. A pattern that shows up in three transcripts and in zero notes is
the most valuable thing this pass can produce, and it is the only thing here
that cannot be recovered by re-reading the notes later.

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

Every surviving entry gets a `ROUTE:` line at its end. An entry without one is
reported as unrouted, because an entry with no destination has not been
consolidated — it has been retyped.

    ROUTE: docs/<path>        # a rule of this repo
    ROUTE: guard              # can be blocked before it happens
    ROUTE: gate               # can be caught in CI
    ROUTE: subtree-claude-md  # only true inside one directory
    ROUTE: memory             # genuinely about the user, not the repo

Only `memory` stays in the note store, and it should be the shortest list. A
rule living only in one person's memory does not exist for anyone else.
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
          "snapshot, and may write ONLY to candidate/. Then: consolidate.py diff")
    return 0


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _corpus(directory):
    """Every .md file's text, joined. Filenames are deliberately discarded."""
    parts = []
    for name in sorted(os.listdir(directory)):
        if name.endswith(".md"):
            parts.append(_read(os.path.join(directory, name)) or "")
    return "\n".join(parts)


def lost_verbatim(snap_text, cand_text):
    """[(kind, token)] present in the snapshot and absent from the candidate.

    Whole-corpus, not per file: an entry moved from `cache.md` into `perf.md`
    has lost nothing, and a check keyed on filenames would call that a loss
    while missing a number silently dropped during the same move."""
    lost = []
    for kind, pattern in LOAD_BEARING:
        for tok in dict.fromkeys(pattern.findall(snap_text)):
            if tok in cand_text:
                continue
            # The patterns overlap on purpose -- `11.6 ms` is a measurement and
            # `11.6` is a version -- so report the longest form and drop the
            # fragments of it. Two lines for one loss trains people to skim.
            if any(tok in seen for _k, seen in lost):
                continue
            lost = [(k, s) for k, s in lost if s not in tok]
            lost.append((kind, tok))
    return lost


def routes(directory):
    """{entry: [route targets]} for every candidate entry."""
    out = {}
    for name in sorted(os.listdir(directory)):
        if name.endswith(".md"):
            out[name] = ROUTE.findall(_read(os.path.join(directory, name)) or "")
    return out


def diff(out):
    snap, cand = os.path.join(out, "snapshot"), os.path.join(out, "candidate")
    if not os.path.isdir(snap):
        print("cannot judge: no snapshot — run `consolidate.py prepare` first",
              file=sys.stderr)
        return 2
    before = {f for f in os.listdir(snap) if f.endswith(".md")}
    after = ({f for f in os.listdir(cand) if f.endswith(".md")}
             if os.path.isdir(cand) else set())
    if not after:
        print("cannot judge: candidate/ is empty — the synthesis has not run",
              file=sys.stderr)
        return 2

    # 1. What is gone. First, because it is the only irreversible thing here.
    lost = lost_verbatim(_corpus(snap), _corpus(cand))
    if lost:
        print(f"GONE — {len(lost)} load-bearing token(s) in the input do not "
              f"appear anywhere in the output:\n")
        for kind, tok in lost:
            print(f"  {kind:<12} {tok}")
        print("\n  Each of these is unrecoverable by reading the candidate. A\n"
              "  measurement without its number, or a belief without the commit\n"
              "  that overturned it, has not been summarised — it has expired.\n")
    else:
        print("GONE — nothing: every measurement, commit, path and version in "
              "the input\n       survives somewhere in the output.\n")

    # 2. What has no destination. A tidier pile of notes has moved nothing.
    routed = routes(cand)
    unrouted = sorted(n for n, r in routed.items() if not r)
    kinds = {}
    for targets in routed.values():
        for t in targets:
            kinds[t if t in ROUTE_KINDS else "docs/…"] = \
                kinds.get(t if t in ROUTE_KINDS else "docs/…", 0) + 1
    if unrouted:
        print(f"NO DESTINATION — {len(unrouted)} of {len(routed)} entries "
              f"carry no ROUTE: line:\n")
        for n in unrouted:
            print(f"  {n}")
        print()
    if kinds:
        print("  routed: " + "  ".join(f"{k}×{v}" for k, v in sorted(kinds.items())))
        mem = kinds.get("memory", 0)
        total = sum(kinds.values())
        if mem * 2 > total:
            print(f"  {mem} of {total} routes are `memory`. Repo-scoped "
                  f"knowledge left in a private\n  note pile is invisible to "
                  f"review and dies with the machine.")
        print()

    # 3. The per-file breakdown, last: it is the easiest part to skim and the
    #    least able to tell a good merge from a lossy one.
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

    print("\nWhat is left for a human: whether a superseded belief still carries\n"
          "the reason it was believed, and whether a DROPPED entry was a\n"
          "duplicate or the only record of something.")
    return 1 if (lost or unrouted or dropped or added or changed) else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["prepare", "diff"])
    ap.add_argument("--notes", default="")
    ap.add_argument("--sessions", default="")
    ap.add_argument("--out", default=".consolidation")
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
