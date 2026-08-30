#!/usr/bin/env python3
"""How to run a repository's own tests, without being told.

Recognising the repository and knowing what to run are one decision, so
`detect` returns the command or None: a `package.json` with no `scripts.test`
is not a Node subject with a missing command, it is not a Node subject.

Nothing here assumes a layout. The assessment's whole claim is that it judges
by behaviour rather than by resemblance, and a test runner that only recognises
repositories shaped like ours would break that claim in the first file.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

INSTALL_TIMEOUT = 900
TEST_TIMEOUT = 600


def sh(args, cwd, timeout, env=None):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "",
                                           f"timed out after {timeout}s")
    except OSError as exc:
        return subprocess.CompletedProcess(args, 127, "", str(exc))


def interpreter():
    """The interpreter a Python subject's tests run under.

    `ASSESS_PYTHON` lets a caller give one repository an environment of its own,
    so a repository's pins never reach the next one."""
    return os.environ.get("ASSESS_PYTHON") or sys.executable


class Ecosystem:
    name = "?"
    tool = None

    def detect(self, path):
        raise NotImplementedError

    def install(self, path):
        return []

    def scope(self, cmd, tests):
        """The command narrowed to `tests`, or None where narrowing is not
        reliable.

        Whole-suite greenness is the wrong bar for a defect replay. A suite can
        be red for a reason older than the defect -- a built directory that is
        not tracked, a service that is not running -- and requiring green there
        discards good instances over facts about the machine. SWE-bench names
        the specific tests that must flip and lets the rest stay as broken as
        it already was."""
        return None


class Node(Ecosystem):
    name = "node"
    tool = "npm"

    def detect(self, path):
        pj = os.path.join(path, "package.json")
        if not os.path.exists(pj):
            return None
        try:
            with open(pj, encoding="utf-8") as fh:
                scripts = (json.load(fh) or {}).get("scripts") or {}
        except (ValueError, OSError):
            return None
        test = scripts.get("test")
        # npm's own placeholder exits 1 and means "nobody wrote a test
        # command". Treating that as red would be this script inventing a
        # failure the repository never had.
        if not test or "no test specified" in test:
            return None
        return ["npm", "test", "--silent"]

    def install(self, path):
        lock = any(os.path.exists(os.path.join(path, f))
                   for f in ("package-lock.json", "npm-shrinkwrap.json"))
        cmd = ["npm", "ci"] if lock else ["npm", "install"]
        return [cmd + ["--no-audit", "--no-fund"]]


class Python(Ecosystem):
    name = "python"
    tool = "python3"
    MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")

    def detect(self, path):
        if not any(os.path.isdir(os.path.join(path, d))
                   for d in ("tests", "test")):
            # pytest can still find scattered test_*.py, but a repository with
            # no test directory and no declared runner is a guess.
            return None
        if not any(os.path.exists(os.path.join(path, m)) for m in self.MARKERS):
            # A test directory plus sixty-odd tracked `.py` files is not a
            # guess. Requiring a packaging marker made the corpus repository
            # with the second-largest supply of defect instances invisible.
            out = sh(["git", "ls-files", "*.py"], path, 60)
            if out.returncode != 0 or len(out.stdout.split()) < 10:
                return None
        return [interpreter(), "-m", "pytest", "-q"]

    def install(self, path):
        # Nothing, unless the caller has given this repository an interpreter of
        # its own -- `pip install` into a shared environment makes one
        # repository's pin the next one's failure.
        if not os.environ.get("ASSESS_PYTHON"):
            return []
        base = [interpreter(), "-m", "pip", "install", "--quiet",
                "--disable-pip-version-check"]
        steps = [base + ["pytest", "pytest-asyncio"]]
        reqs = [f for f in ("requirements.txt", "requirements-dev.txt",
                            "dev-requirements.txt", "test-requirements.txt")
                if os.path.exists(os.path.join(path, f))]
        for f in reqs:
            steps.append(base + ["-r", f])
        if not reqs and any(os.path.exists(os.path.join(path, m))
                            for m in self.MARKERS[:3]):
            steps.append(base + ["-e", "."])
        return steps

    def scope(self, cmd, tests):
        return cmd + tests if tests else None


class Rust(Ecosystem):
    name = "rust"
    tool = "cargo"

    def detect(self, path):
        return (["cargo", "test", "--quiet"]
                if os.path.exists(os.path.join(path, "Cargo.toml")) else None)


class Go(Ecosystem):
    name = "go"
    tool = "go"

    def detect(self, path):
        return (["go", "test", "./..."]
                if os.path.exists(os.path.join(path, "go.mod")) else None)

    def scope(self, cmd, tests):
        if not tests:
            return None
        dirs = sorted({os.path.dirname(t) or "." for t in tests})
        return ["go", "test"] + [f"./{d}/..." if d != "." else "./..."
                                 for d in dirs]


class Make(Ecosystem):
    name = "make"
    tool = "make"

    def detect(self, path):
        # Last, because a `test:` target usually drives one of the others, and
        # the ecosystem it drives gives better failures than `make` does.
        mk = os.path.join(path, "Makefile")
        if not os.path.exists(mk):
            return None
        try:
            with open(mk, encoding="utf-8", errors="replace") as fh:
                body = fh.read()
        except OSError:
            return None
        return ["make", "test"] if "\ntest:" in "\n" + body else None


ECOSYSTEMS = (Node(), Python(), Rust(), Go(), Make())

# A suite that is red because nothing could be imported is not a red suite. A
# missing dependency and a failing test both exit non-zero, and scoring the
# first as the second discards exactly the subjects whose suites are fine.
CANNOT_RUN = (
    "no tests ran", "INTERNALERROR", "ModuleNotFoundError", "ImportError",
    "ERROR collecting", "cannot find module", "Cannot find module",
    "MODULE_NOT_FOUND", "command not found", "is not on PATH",
)


def unusable(detail):
    d = detail or ""
    # `3 errors in 0.29s` with nothing failed is pytest saying it could not
    # import the tests. Only the summary line survives to here.
    if re.search(r"\b\d+ errors? in \b", d) and "failed" not in d:
        return True
    return any(m in d for m in CANNOT_RUN)


def find(path):
    """(ecosystem, command) for a repository, or (None, None)."""
    for eco in ECOSYSTEMS:
        cmd = eco.detect(path)
        if cmd is None:
            continue
        if eco.tool and shutil.which(eco.tool) is None:
            return eco, None
        return eco, cmd
    return None, None


def run(path, cmd):
    """(verdict, one line). green / red / could-not-run -- never a bare bool."""
    out = sh(cmd, path, TEST_TIMEOUT)
    tail = (out.stdout or out.stderr).strip().splitlines()
    detail = tail[-1][:160] if tail else f"exit {out.returncode}"
    if out.returncode == 0:
        return "green", detail
    if out.returncode in (5, 124, 127) or unusable(detail):
        return "could-not-run", detail
    return "red", detail
