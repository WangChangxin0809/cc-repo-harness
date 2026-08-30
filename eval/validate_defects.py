#!/usr/bin/env python3
"""Does reverting the source half of a fix actually make its test fail?

    python3 eval/validate_defects.py --repo philoserf__t5chargen [--limit 8]

`defects.py` counts commits that *look* like defect instances. Counting is not
validating, and the difference is the whole instrument: a commit can carry a
fix and a test that does not cover it, and that instance would silently score
every repository as catching a defect nothing caught.

SWE-bench runs exactly this pass over every candidate instance and keeps only
the ones where the tests fail before the patch and pass after. This is that,
inverted -- we already have the "after", so we remove the source half of the
commit and require the tests to go red.

    validated      green at the fix, red without its source  -> usable
    no-coverage    green at the fix, STILL GREEN without it   -> the test does
                   not exercise the fix. Not a broken instance: a measurement.
                   The repository believes this bug is covered and it is not.
    red-at-fix     the suite does not pass at the fix commit  -> unusable here
    could-not-run  no ecosystem, no toolchain, or an install failed

Exit codes:
    0 = every instance reached a verdict    2 = cannot judge (no repo, no history)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from defects import TEST_PATH, WORK, classify as classify_commits, is_source  # noqa: E402
from green import (  # noqa: E402
    ECOSYSTEMS, INSTALL_TIMEOUT, TEST_TIMEOUT, sh,
)

SCRATCH = os.path.join(HERE, ".defects")


def git(args, cwd, check=True):
    out = subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                         text=True, timeout=300)
    if check and out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])}: {out.stderr.strip()[:200]}")
    return out


def bench(src, name):
    """A scratch clone, so the corpus checkout is never moved off its pin.

    Reused across instances of one repository: an install is paid once, and
    `git clean -qfd` leaves ignored build output alone on purpose."""
    dst = os.path.join(SCRATCH, name)
    if os.path.isdir(os.path.join(dst, ".git")):
        return dst
    os.makedirs(SCRATCH, exist_ok=True)
    shutil.rmtree(dst, ignore_errors=True)
    git(["clone", "-q", "--no-hardlinks", src, dst], SCRATCH)
    return dst


def prepare(repo):
    """Give a Python subject an interpreter of its own, and fill it once.

    `green.classify` re-runs `install()` on every call, so leaving the flag set
    would pay a pip resolve twice per instance. The environment is built here
    and the flag dropped, which is also why this returns the interpreter rather
    than mutating and hoping."""
    if not any(e.name == "python" and e.detect(repo) for e in ECOSYSTEMS):
        return None
    venv = os.path.join(repo, ".venv-defects")
    py = os.path.join(venv, "bin", "python")
    if not os.path.exists(py):
        out = sh([sys.executable, "-m", "venv", venv], repo, INSTALL_TIMEOUT)
        if out.returncode != 0:
            return None
    os.environ["GREEN_PYTHON"] = py
    os.environ["GREEN_INSTALL_DEPS"] = "1"
    for eco in ECOSYSTEMS:
        if eco.name != "python":
            continue
        for step in eco.install(repo):
            out = sh(step, repo, INSTALL_TIMEOUT)
            if out.returncode != 0:
                tail = (out.stderr or out.stdout).strip().splitlines()
                print(f"  (install: {' '.join(step[3:6])} failed: "
                      f"{tail[-1][:90] if tail else out.returncode})")
        break
    os.environ["GREEN_INSTALL_DEPS"] = "0"
    return py


def park(repo, sha):
    # --force, because parking is also how an instance is undone: the tree
    # carries the reverted source at that point and a plain checkout refuses
    # to overwrite it. Without this the second instance in a repository
    # crashes, and the crash looks like a defect in the corpus.
    git(["checkout", "-q", "--force", "--detach", sha], repo)
    git(["clean", "-qfd"], repo)


def revert_source(repo, sha):
    """Put every source file back to its parent state; leave tests at `sha`.

    A file the commit *added* has no parent state, so reverting it means
    removing it -- missing that case leaves the fix in place and the instance
    scores as no-coverage when it is really a bug in this function."""
    changed = git(["diff", "--name-only", f"{sha}^", sha], repo).stdout.split()
    src = [p for p in changed if is_source(p)]
    if not src:
        return None
    at_parent = set(git(["ls-tree", "-r", "--name-only", f"{sha}^"],
                        repo).stdout.split())
    restored, removed = [], []
    for p in src:
        if p in at_parent:
            git(["checkout", f"{sha}^", "--", p], repo)
            restored.append(p)
        else:
            os.remove(os.path.join(repo, p))
            removed.append(p)
    return {"restored": restored, "removed": removed}


# A suite that is red because nothing could be imported is not a red suite.
# The first run of this scored thirteen instances as `red-at-fix` when the only
# fact established was that `pytest_asyncio` was missing from the interpreter --
# the same mistake `nim_smoke.py` paid for, in a new place: a missing dependency
# and a failing test both exit non-zero, and scoring the first as the second
# discards exactly the subjects whose suites are fine.
PYTEST_ERRORS = re.compile(r"\b\d+ errors? in \b")
CANNOT_IMPORT = ("no tests ran", "INTERNALERROR", "ModuleNotFoundError",
                 "ImportError", "ERROR collecting",
                 "cannot find module", "Cannot find module", "MODULE_NOT_FOUND",
                 "no such file or directory", "command not found")


def unusable_environment(detail):
    d = detail or ""
    # `3 errors in 0.29s` with nothing failed is pytest reporting that it could
    # not import the tests. green.py keeps only the last line of output, so the
    # ModuleNotFoundError itself never reaches here -- the summary line is the
    # signal that survives.
    if PYTEST_ERRORS.search(d) and "failed" not in d:
        return True
    return any(m in d for m in CANNOT_IMPORT)


def scoped(eco, cmd, tests):
    """The part of the suite the commit itself touched, or None.

    Whole-suite greenness is the wrong bar and it cost most of the corpus. In
    `resuming`, seventeen tests fail at every commit because a `static/`
    directory is built rather than tracked; the suite is red, the fix is fine,
    and requiring green discards thirteen good instances over one missing
    directory. SWE-bench does not ask whether the suite passes either -- it
    names the specific tests that must flip, and everything else is allowed to
    be as broken as it already was.

    Returns None where narrowing is not reliable (npm test does not take file
    arguments in any portable way), and the caller falls back to the suite."""
    if not tests:
        return None
    if eco == "python":
        return cmd + tests
    if eco == "go":
        dirs = sorted({os.path.dirname(t) or "." for t in tests})
        return ["go", "test"] + [f"./{d}/..." if d != "." else "./..."
                                 for d in dirs]
    return None


def run(repo, cmd):
    """(verdict, one line of detail). green / red / could-not-run."""
    out = sh(cmd, repo, TEST_TIMEOUT)
    tail = (out.stdout or out.stderr).strip().splitlines()
    detail = tail[-1][:140] if tail else f"exit {out.returncode}"
    if out.returncode == 0:
        return "green", detail
    if out.returncode in (5, 124, 127) or unusable_environment(detail):
        return "could-not-run", detail
    return "red", detail


def validate(repo, sha, samples):
    park(repo, sha)
    eco_name, cmd = "-", None
    for eco in ECOSYSTEMS:
        c = eco.detect(repo)
        if c is not None:
            eco_name, cmd = eco.name, c
            break
    if cmd is None:
        return {"verdict": "could-not-run", "ecosystem": "-", "command": "-",
                "detail": "no ecosystem recognised a runnable test command"}

    changed = git(["diff", "--name-only", f"{sha}^", sha], repo).stdout.split()
    tests = [p for p in changed if TEST_PATH.search(p)
             and os.path.exists(os.path.join(repo, p))]
    narrow = scoped(eco_name, cmd, tests)
    cmd = narrow or cmd
    row = {"ecosystem": eco_name, "command": " ".join(cmd),
           "scope": "touched tests" if narrow else "whole suite",
           "tests": tests}

    before, detail = run(repo, cmd)
    if before != "green":
        return {**row, "verdict": "could-not-run" if before == "could-not-run"
                else "red-at-fix", "detail": f"at the fix: {before} — {detail}"}

    touched = revert_source(repo, sha)
    if touched is None:
        return {**row, "verdict": "red-at-fix",
                "detail": "the commit changed no source"}
    after, detail = run(repo, cmd)
    park(repo, sha)

    if after == "red":
        return {**row, "verdict": "validated", "detail": detail, **touched}
    if after == "green":
        return {**row, "verdict": "no-coverage",
                "detail": "these tests still pass without the fix", **touched}
    return {**row, "verdict": "could-not-run",
            "detail": f"after the revert: {detail}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="directory name under eval/.work")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--samples", type=int, default=1)
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    src = os.path.join(WORK, a.repo)
    if not os.path.isdir(os.path.join(src, ".git")):
        print(f"cannot judge: {src} is not a checkout", file=sys.stderr)
        return 2
    found = classify_commits(src)
    if found is None:
        print("cannot judge: no history — run git fetch --unshallow", file=sys.stderr)
        return 2
    rows = [x for x in found["fix_test"] if x["small"]][:a.limit]
    if not rows:
        print(f"cannot judge: {a.repo} offers no small fix+test commit",
              file=sys.stderr)
        return 2

    repo = bench(src, a.repo)
    # `.venv-defects` is untracked, and `git clean -qfd` between instances would
    # delete it. Telling git to ignore it locally costs one line and saves a
    # rebuild per instance.
    with open(os.path.join(repo, ".git", "info", "exclude"), "a") as fh:
        fh.write("\n.venv-defects/\n")
    py = prepare(repo)
    print(f"\n{a.repo}: validating {len(rows)} candidate instance(s)"
          + (f"\n  interpreter: {py}" if py else "") + "\n")
    out, started = [], time.time()
    for row in rows:
        r = validate(repo, row["sha"], a.samples)
        out.append({**row, **r})
        mark = {"validated": "OK ", "no-coverage": "-- ",
                "red-at-fix": "?? ", "could-not-run": "?? "}[r["verdict"]]
        print(f"  {mark}{row['sha']}  {r['verdict']:<14} {row['subject'][:52]}")
        if r["verdict"] != "validated":
            print(f"      {r['detail'][:110]}")

    tally = {}
    for r in out:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    print(f"\n  {'  '.join(f'{k}: {v}' for k, v in sorted(tally.items()))}"
          f"   ({time.time() - started:.0f}s)")
    if a.json:
        with open(a.json, "w") as fh:
            json.dump({"repo": a.repo, "tally": tally, "rows": out}, fh, indent=2)
        print(f"  written to {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
