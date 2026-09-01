#!/usr/bin/env python3
"""The one command to run before pushing. It reads CI rather than restating it.

## Why this is not a `ci.sh`

`.github/workflows/ci.yml` opens by saying that judgement written into a CI
wiring cannot be run before pushing. The obvious remedy is a shell script that
runs the same things, and it is the wrong one: two files listing the same
sixteen commands drift on the first change, and they drift *silently in the
passing direction* -- the local script keeps exiting 0 while CI has grown a
step it never heard of. That is the cliff this repository's own dimension 2.4
is about, installed by the fix for it.

So there is one list, and it is the workflow. This script parses it and runs
what a laptop can run. A step added to CI is a step this runs the same day,
because there was never a second copy to update.

## What "what a laptop can run" means

Every step in the workflow gets exactly one verdict, and there is no fourth:

* **run** -- a single-line `run:` with nothing in it that only the runner has.
* **skip** -- an action rather than a command, a step conditional on the CI
  event, or a command referencing `${{ }}` or a value from the step's `env:`.
  The reason is printed; a skipped step is a thing you did not check, and
  hiding that would make this exactly the false green it exists to avoid.
* **cannot classify** -- a multi-line `run:` block that needs no CI values.
  That is judgement living in the YAML, which the workflow's own header
  forbids, so this exits 2 rather than guessing at it. Exit 2 is COULD NOT
  JUDGE here as everywhere else in this repository, and it is never a pass.

A tool the workflow installs but this machine does not have is the same
answer: exit 2, with the install line. A local run that quietly omits `ruff`
because `ruff` is missing is a green square for a suite that did not run.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORKFLOW = os.path.join(".github", "workflows", "ci.yml")

RUN, SKIP, UNKNOWN = "run", "skip", "unknown"

# Values only the runner has. `${{ }}` is GitHub's; the rest are what a step's
# own `env:` block introduces, which this does not evaluate.
_CI_VALUE = re.compile(r"\$\{\{|\$\{?[A-Z][A-Z0-9_]*\}?")

# A step that changes the machine it runs on. On a runner that machine is
# thrown away afterwards; here it is the reader's. Skipped with the line
# printed, so somebody who is missing a linter can see what to run.
_INSTALLS = re.compile(
    r"\b(?:pip[0-9.]*\s+install|pip\s+install|-m\s+pip\s+install"
    r"|npm\s+(?:ci|install)|apt-get|brew\s+install|cargo\s+install)\b")


class Step:
    def __init__(self, job, name):
        self.job = job
        self.name = name or "(unnamed)"
        self.uses = None
        self.run = None          # list of lines, already dedented
        self.has_if = False
        self.has_env = False

    @property
    def verdict(self):
        if self.uses:
            return SKIP, "an action, which only exists on the runner"
        if self.run is None:
            return SKIP, "no command"
        if self.has_if:
            return SKIP, "conditional on the CI event"
        body = "\n".join(self.run).strip()
        if self.has_env or _CI_VALUE.search(body):
            return SKIP, "needs a value only CI has"
        if _INSTALLS.search(body):
            return SKIP, "would install into this machine's environment"
        if len(self.run) == 1:
            return RUN, self.run[0]
        return UNKNOWN, "a multi-line command with no CI values in it"


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def parse(text):
    """Every step in the workflow, in order. Deliberately small: this reads one
    file with a shape the repository controls, and a YAML library would be a
    dependency the payload rule forbids anywhere near here."""
    steps = []
    job = "?"
    cur = None
    block = None          # (indent_of_run_key, [lines]) while inside `run: |`
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            if block:
                block[1].append("")
            continue
        ind = _indent(line)
        body = line.strip()

        if block is not None:
            if ind > block[0]:
                block[1].append(line[block[0] + 2:])
                continue
            cur.run = [x for x in block[1] if x.strip()]
            block = None

        # `  jobs:` children sit at indent 2 and end with a colon.
        if ind == 2 and body.endswith(":") and not body.startswith("- "):
            job = body[:-1]
            cur = None
            continue
        if body.startswith("- "):
            inner = body[2:]
            if inner.startswith(("name:", "uses:", "run:")):
                cur = Step(job, None)
                steps.append(cur)
                body = inner
            elif cur is not None and ind <= 6:
                cur = None
        if cur is None:
            continue

        if body.startswith("name:"):
            cur.name = body[5:].strip()
        elif body.startswith("uses:"):
            cur.uses = body[5:].strip()
        elif body.startswith("if:"):
            cur.has_if = True
        elif body.startswith("env:"):
            cur.has_env = True
        elif body.startswith("run:"):
            rest = body[4:].strip()
            if rest in ("|", "|-", ">", ">-"):
                block = (ind, [])
            else:
                cur.run = [rest]
    if block is not None and cur is not None:
        cur.run = [x for x in block[1] if x.strip()]
    return steps


def _tool(command):
    """The executable a command starts with, or None where there is none to
    look for (a shell builtin, an assignment)."""
    first = command.split()[0] if command.split() else ""
    return first if first and "=" not in first and "/" not in first else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--list", action="store_true",
                    help="print the verdicts and run nothing")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()

    path = os.path.join(args.root, WORKFLOW)
    if not os.path.exists(path):
        print("could not judge: no " + WORKFLOW, file=sys.stderr)
        return 2
    with open(path, encoding="utf-8") as fh:
        steps = parse(fh.read())

    unknown = [s for s in steps if s.verdict[0] == UNKNOWN]
    if unknown:
        print("could not judge: " + WORKFLOW + " has a step this cannot read.\n",
              file=sys.stderr)
        for s in unknown:
            print("  {0} / {1}\n    {2}".format(s.job, s.name, s.verdict[1]),
                  file=sys.stderr)
        print("\nA multi-line `run:` is judgement in the workflow, which its own\n"
              "header forbids. Move it into a script and call the script.",
              file=sys.stderr)
        return 2

    todo = [s for s in steps if s.verdict[0] == RUN]
    missing = sorted({t for t in (_tool(s.verdict[1]) for s in todo)
                      if t and not shutil.which(t)})

    if args.list:
        for s in steps:
            kind, why = s.verdict
            print("{0:5} {1:18} {2}".format(kind, s.job, s.name))
            print("      {0}".format(why))
        return 0

    if missing:
        print("could not judge: this machine has no " + ", ".join(missing),
              file=sys.stderr)
        print("\n    python3 -m pip install -r .github/requirements-dev.txt\n",
              file=sys.stderr)
        print("Running the rest and calling it green would be a pass for a\n"
              "suite that did not run.", file=sys.stderr)
        return 2

    print("{0} step(s) from {1}\n".format(len(todo), WORKFLOW))
    failed = []
    began = time.time()
    for s in todo:
        cmd = s.verdict[1]
        t0 = time.time()
        r = subprocess.run(cmd, shell=True, cwd=args.root)
        took = time.time() - t0
        mark = "ok  " if r.returncode == 0 else "FAIL"
        print("{0} {1:5.1f}s  {2}".format(mark, took, s.name))
        if r.returncode != 0:
            failed.append((s, r.returncode))
            print("       {0}\n       exit {1}".format(cmd, r.returncode))

    skipped = [s for s in steps if s.verdict[0] == SKIP and s.run]
    print("\n{0} ran, {1} failed, {2:.0f}s".format(
        len(todo), len(failed), time.time() - began))
    if skipped:
        print("\nnot run here, and CI still will:")
        for s in skipped:
            print("  {0}  ({1})".format(s.name, s.verdict[1]))
    return 1 if failed else 0


# --- the parser's own cases -------------------------------------------------
#
# A runner that misreads the workflow fails in the passing direction: it drops
# a step, prints a green line, and the first anyone hears is CI. So the cases
# below are mostly about what must NOT come back as `run`.

_FIXTURE = """\
name: ci
jobs:
  checks:
    steps:
      - uses: actions/checkout@abc  # v1
        with:
          persist-credentials: false
      - name: a plain one
        run: python3 shared/scripts/gates/selftest.py --verbose
      # a comment between steps
      - name: conditional
        if: github.event_name == 'pull_request'
        run: python3 something.py
      - name: needs an env value
        env:
          BASE: ${{ github.sha }}
        run: |
          set -euo pipefail
          python3 x.py --base "$BASE"
      - name: an expression inline
        run: echo ${{ github.ref }}
      - name: install the linters
        run: python3 -m pip install -r .github/requirements-dev.txt
  other:
    steps:
      - name: judgement in the yaml
        run: |
          set -e
          python3 a.py
          python3 b.py
"""


def selftest(verbose=True):
    steps = parse(_FIXTURE)
    got = [(s.job, s.name, s.verdict[0]) for s in steps]
    want = [
        ("checks", "(unnamed)", SKIP),          # uses:, and `with:` is not a step
        ("checks", "a plain one", RUN),
        ("checks", "conditional", SKIP),
        ("checks", "needs an env value", SKIP),
        ("checks", "an expression inline", SKIP),
        ("checks", "install the linters", SKIP),
        ("other", "judgement in the yaml", UNKNOWN),
    ]
    bad = 0
    for i, expect in enumerate(want):
        actual = got[i] if i < len(got) else None
        ok = actual == expect
        bad += not ok
        if verbose or not ok:
            print("{0} {1}".format("ok  " if ok else "FAIL", expect))
            if not ok:
                print("     got {0}".format(actual))
    if len(got) != len(want):
        print("FAIL parsed {0} steps, wanted {1}".format(len(got), len(want)))
        for g in got:
            print("     {0}".format(g))
        bad += 1

    # The real workflow, which must be fully classified. This is the drift
    # catcher: a step nobody here can read turns this red the day it lands.
    path = os.path.join(ROOT, WORKFLOW)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            real = parse(fh.read())
        stuck = [s.name for s in real if s.verdict[0] == UNKNOWN]
        runs = [s for s in real if s.verdict[0] == RUN]
        ok = not stuck and len(runs) >= 10
        bad += not ok
        print("{0} the real workflow: {1} runnable, {2} unreadable".format(
            "ok  " if ok else "FAIL", len(runs), len(stuck)))
        for name in stuck:
            print("     {0}".format(name))
    print("\n{0}".format("all cases pass" if not bad
                         else "{0} case(s) failed".format(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
