#!/usr/bin/env python3
"""SessionStart: print what is only true right now.

Keep the output under ~20 lines. It is paid at every session start, and a brief
long enough to skim is a brief that gets skimmed. Everything here is knowledge
no file can hold -- which is exactly why it otherwise never gets delivered, and
the agent spends its first turns rediscovering it, or does not.
"""

import glob
import os
import re
import subprocess


def sh(*args):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def main():
    lines = []
    branch = sh("git", "rev-parse", "--abbrev-ref", "HEAD")
    dirty = sh("git", "status", "--porcelain")
    n = len(dirty.splitlines()) if dirty else 0
    lines.append(f"branch {branch or '?'} · "
                 f"{'clean' if not n else f'{n} uncommitted file(s)'}")

    behind = sh("git", "rev-list", "--count", "HEAD..@{u}")
    if behind and behind != "0":
        lines.append(f"{behind} commit(s) behind upstream")

    # Concurrent agent sessions writing to this repo. Left undetected this
    # produces edits that appear and vanish between reads, which is a very
    # confusing thing to debug and a very cheap thing to report.
    others = [p for p in sh("pgrep", "-af", "claude").splitlines()
              if "--print" not in p]
    if len(others) > 1:
        lines.append(f"!! {len(others)} agent session(s) appear active in this repo "
                     "— append to shared files rather than rewriting them")

    # The one thing a new session cannot reconstruct by reading: which plan was
    # already underway. Without it the agent either starts something parallel
    # or re-derives the plan from the tree, and both look like progress.
    #
    # Only list rows and table rows are read, never prose. The first version
    # matched `doing` anywhere and reported a plan whose README *explains the
    # convention* -- "nobody reopens a finished step to change `doing` to
    # `done`" -- as the step in progress. A brief that misreads one plan is not
    # a brief anyone reads twice.
    inflight = []
    for plan in sorted(glob.glob("docs/exec-plans/*/README.md")):
        try:
            with open(plan, encoding="utf-8") as fh:
                body = fh.read()
        except OSError:
            continue
        rows = [l.strip() for l in body.splitlines()
                if re.match(r"\s*(?:[-*] \[[ xX]\]|\|)", l)]
        step = next((l for l in rows if re.search(r"\bdoing\b", l, re.I)), "")
        if not step:
            step = next((l for l in rows if l.startswith(("- [ ]", "* [ ]"))), "")
        if step:
            inflight.append((os.path.basename(os.path.dirname(plan)), step))
    for name, step in inflight[:3]:
        lines.append(f"in flight: {name} — {step[:70]}")
    if len(inflight) > 3:
        lines.append(f"...and {len(inflight) - 3} more plan(s) open")

    # TODO: add what else is specific to this repo — which gates are currently
    # red, for instance. Keep the total under ~20 lines.
    print("\n".join(lines))


if __name__ == "__main__":
    main()
