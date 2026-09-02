#!/usr/bin/env python3
"""Prove the assessment can still tell a good repository from a bad one.

    python3 assess/selftest.py [--verbose]

    0 = every case held    1 = a case failed    2 = cannot run

## Why an assessment needs this more than a gate does

A gate that stops working is loud: the thing it guarded breaks. An assessment
that stops working is silent and worse than silent, because it keeps printing
numbers. A probe that has quietly gone blind reports a repository as safe, and
the report is indistinguishable from the report on a repository that is safe.

So every case here builds a repository with a known answer and insists the
probe finds it. Half of them build a repository that must score *badly*: a
measurement that cannot go down has not measured anything, and two of the
defects below were live in this tree when these cases were written --
`probe_repo.py` reported this repository's own gates as absent, and reported an
always-on skill cost of zero while an installed plugin was spending about eight
hundred tokens a turn. Both are cases here now.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
SELFTESTS = os.path.join(HERE, "selftests")
sys.path.insert(0, SELFTESTS)

import probe_defects_cases as _m01   # noqa: E402
import history_cases as _m02   # noqa: E402
import catch_cases as _m03   # noqa: E402
import blast_cases as _m04   # noqa: E402
import dimensions_cases as _m05   # noqa: E402
import truth_cases as _m06   # noqa: E402
import mutation_cases as _m07   # noqa: E402
import coverage_cases as _m08   # noqa: E402
import value_cases_1 as _m09   # noqa: E402
import value_cases_2 as _m10   # noqa: E402
import value_cases_3 as _m11   # noqa: E402
import pipeline_cases as _m12   # noqa: E402
import field_cases as _m13   # noqa: E402
import ecosystems_cases as _m14   # noqa: E402

CASES = (
    _m01.CASES
    + _m02.CASES
    + _m03.CASES
    + _m04.CASES
    + _m05.CASES
    + _m06.CASES
    + _m07.CASES
    + _m08.CASES
    + _m09.CASES
    + _m10.CASES
    + _m11.CASES
    + _m12.CASES
    + _m13.CASES
    + _m14.CASES
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    if shutil.which("git") is None:
        print("cannot run: git not on PATH", file=sys.stderr)
        return 2
    for name in ("probe_repo.py",):
        if not os.path.exists(os.path.join(PARENT, name)):
            print(f"cannot run: {name} is missing", file=sys.stderr)
            return 2

    failures = []
    for label, fn in CASES:
        tmp = tempfile.mkdtemp(prefix="assess-selftest-")
        try:
            problem = fn(tmp)
        except Exception as exc:                          # noqa: BLE001
            problem = f"{type(exc).__name__}: {exc}"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if problem:
            failures.append(f"{label}\n    {problem}")
        elif a.verbose:
            print(f"  ok  {label}")

    if failures:
        print(f"{len(failures)} of {len(CASES)} assessment case(s) failed:\n",
              file=sys.stderr)
        for f in failures:
            print(f"  {f}\n", file=sys.stderr)
        return 1
    print(f"PASS  {len(CASES)} assessment case(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
