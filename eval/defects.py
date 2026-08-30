#!/usr/bin/env python3
"""How many corpus repositories can supply a defect that somebody else chose.

    python3 eval/defects.py [--only SUBSTR] [--json]

Dimension 2 of the assessment -- *when* is a defect first caught -- needs
defects. If we invent them we will invent the ones our own guards happen to
catch, and the measurement becomes a mirror. The honest source is each
repository's own history: a commit that fixed something is a bug that actually
happened, selected by somebody with no stake in this plugin.

This counts what is available. It plants nothing.

## The four tiers, and why the third one is the interesting one

    fix+test     a fix-shaped commit touching source AND test
                 -> revert the source hunks and the repo's own suite should go
                    red. This is the SWE-bench shape: FAIL_TO_PASS.
    revert       an explicit revert
                 -> the cleanest provenance there is; the repository itself
                    said this was wrong, in its own words.
    any+test     any commit touching source and test
                 -> a larger pool with weaker provenance. A feature commit's
                    new test also fails when its source is reverted, and is
                    less tautological than a fix, but it is not a *bug*.
    fix-no-test  a fix-shaped commit touching source and no test at all
                 -> not a weaker instance. A different measurement: a real bug
                    whose fix nothing verifies. Reverting it creates a defect
                    the repository cannot see, and that is dimension 2's
                    failure mode observed directly rather than simulated.

Exit codes:
    0 = counted    2 = cannot judge (no corpus checked out, or no history)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, ".work")
# One definition of what a defect is, and it lives in the payload. This file is
# the corpus-wide tally on top of it; when the two carried their own copies, a
# fix to the test-path pattern landed in one and not the other within a day.
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "shared", "scripts",
                                "assess"))
from history import (  # noqa: E402
    FIX_SUBJECT, REVERT_SUBJECT, SMALL, SOURCE_EXT, TEST_PATH, is_source,
)






def sh(args, cwd):
    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                             timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None



def commits(repo):
    """Every non-merge commit as (sha, subject, [paths]), newest first."""
    raw = sh(["git", "log", "--no-merges", "--name-only",
              "--format=%x01%H%x00%s"], repo)
    if raw is None:
        return None
    out = []
    for rec in raw.split("\x01")[1:]:
        head, _, rest = rec.partition("\n")
        sha, _, subject = head.partition("\x00")
        paths = [p for p in rest.split("\n") if p.strip()]
        out.append((sha, subject, paths))
    return out


def classify(repo):
    log = commits(repo)
    if log is None:
        return None
    r = {"commits": len(log), "fix_test": [], "revert": [], "any_test": [],
         "fix_no_test": [], "has_any_test_file": False}
    for sha, subject, paths in log:
        src = [p for p in paths if is_source(p)]
        tst = [p for p in paths if TEST_PATH.search(p)]
        if tst:
            r["has_any_test_file"] = True
        if not src:
            continue                      # docs/config only: not a code defect
        small = len(src) <= SMALL
        row = {"sha": sha[:10], "subject": subject[:72],
               "src": len(src), "test": len(tst), "small": small}
        fix = bool(FIX_SUBJECT.search(subject))
        if REVERT_SUBJECT.search(subject):
            r["revert"].append(row)
        if tst:
            r["any_test"].append(row)
            if fix:
                r["fix_test"].append(row)
        elif fix:
            r["fix_no_test"].append(row)
    return r


def small(rows):
    return sum(1 for x in rows if x["small"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if not os.path.isdir(WORK):
        print("cannot judge: eval/.work/ does not exist — run eval/fetch.py",
              file=sys.stderr)
        return 2
    names = sorted(n for n in os.listdir(WORK)
                   if a.only in n and os.path.isdir(os.path.join(WORK, n)))
    if not names:
        print(f"cannot judge: no repository matches {a.only!r}", file=sys.stderr)
        return 2

    report, shallow = {}, []
    for n in names:
        path = os.path.join(WORK, n)
        if os.path.exists(os.path.join(path, ".git", "shallow")):
            shallow.append(n)
        c = classify(path)
        if c is None:
            shallow.append(n)
            continue
        report[n] = c

    if a.json:
        print(json.dumps(report, indent=2))
        return 2 if shallow else 0

    print(f"\n{'repository':<40}{'commits':>8}{'fix+test':>10}{'revert':>8}"
          f"{'any+test':>10}{'fix,no test':>13}")
    print(f"{'':<40}{'':>8}{'(small)':>10}{'(small)':>8}{'(small)':>10}"
          f"{'(small)':>13}")
    print("-" * 89)
    usable = 0
    for n, c in report.items():
        if small(c["fix_test"]) or small(c["revert"]):
            usable += 1
        print(f"{n:<40}{c['commits']:>8}"
              f"{small(c['fix_test']):>6}/{len(c['fix_test']):<3}"
              f"{small(c['revert']):>5}/{len(c['revert']):<2}"
              f"{small(c['any_test']):>7}/{len(c['any_test']):<2}"
              f"{small(c['fix_no_test']):>10}/{len(c['fix_no_test']):<2}")

    tot = {k: sum(small(c[k]) for c in report.values())
           for k in ("fix_test", "revert", "any_test", "fix_no_test")}
    no_tests = [n for n, c in report.items() if not c["has_any_test_file"]]
    print("-" * 89)
    print(f"{'TOTAL (small instances only)':<40}{'':>8}"
          f"{tot['fix_test']:>6}   {tot['revert']:>5}   {tot['any_test']:>7}   "
          f"{tot['fix_no_test']:>10}")
    print(f"\n{usable}/{len(report)} repositories can supply at least one small "
          f"gold instance (fix+test, or a revert).")
    print(f"{len(no_tests)}/{len(report)} carry no test file at all: "
          + (", ".join(no_tests) if no_tests else "-"))
    if shallow:
        print(f"\ncannot judge {len(shallow)}: {', '.join(shallow)}",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
