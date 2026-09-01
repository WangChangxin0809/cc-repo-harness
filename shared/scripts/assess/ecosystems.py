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
            out = sh(["git", "-c", "core.quotePath=false", "ls-files",
                      "*.py"], path, 60)
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


class Declared(Ecosystem):
    """The command the repository documents for itself, when nothing else fits.

    Every detector above recognises a *convention* -- `pytest`, `npm test`,
    `cargo test`. A repository whose suite is five bespoke scripts matches
    none of them, and the assessment then reports "no runnable test command",
    which is a fact about the detectors rather than about the repository.
    This project's own tree was that repository: it has 142 assessment cases,
    18 CI steps and a documented entry point, and dimension 2 abstained on it
    for months.

    ## Why reading a command out of a document is dangerous, and the rule

    A `README` is prose, and prose about commands contains commands --
    including the ones it is warning you against. Running the first fenced
    line in a document would eventually run `rm -rf /` out of a section
    explaining why not to. That is the failure this project has shipped five
    times in other checks: text *about* a thing read as the thing.

    So a candidate has to survive all of:

    * it sits in a fenced block **introduced by a line about running checks**
      -- a heading or sentence naming tests, checks, the suite, or pushing;
    * it is one line, with no `;`, `&&`, `|`, redirect, backtick or `$(`, so
      it cannot fan out into something the text never showed;
    * it **names a path that exists in the tree**. This is the load-bearing
      one. `python3 scripts/check.py` names a file; `rm -rf /` and
      `curl ... | sh` name nothing, and neither does an illustrative command
      from a document about some other repository.

    A command that fails any of these is not narrowed down to something safer
    -- it is dropped, and the ecosystem goes on abstaining. An abstention is a
    correct answer here and a guessed command is not.
    """

    name = "declared"
    tool = None
    # Which document the command came from, set by `detect`. The assessment
    # runs this against a repository nobody here has read; printing the
    # command without saying where it was found would present somebody's
    # documentation as this tool's own choice.
    source = None

    # Where a repository states its own entry point, most authoritative first.
    DOCS = ("CLAUDE.md", "AGENTS.md", "CONTRIBUTING.md", "README.md",
            "docs/CONTRIBUTING.md", ".github/CONTRIBUTING.md")

    # The line that introduces the block. `test` alone is too weak -- every
    # README says the word -- so it has to be doing the introducing.
    INTRO = re.compile(
        r"(?:^|\n)[^\n]{0,120}?\b(?:before (?:you )?(?:push|commit)|"
        r"run (?:the )?(?:tests?|checks?|suite)|the (?:whole )?suite|"
        r"running the tests?|to test|local (?:test|check)|"
        r"tests?\s*$|checks?\s*$)[^\n]{0,80}$", re.I | re.M)

    FENCE = re.compile(r"```(?:bash|sh|shell|console)?\n(.*?)```", re.S)

    # Anything that lets one line become several.
    FANOUT = re.compile(r"[;&|><`]|\$\(")

    def _candidates(self, path):
        for rel in self.DOCS:
            full = os.path.join(path, rel)
            if not os.path.exists(full):
                continue
            try:
                with open(full, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            for m in self.FENCE.finditer(text):
                intro = text[:m.start()]
                if not self.INTRO.search(intro[-260:]):
                    continue
                for line in m.group(1).splitlines():
                    line = line.split("#")[0].strip()
                    if line.startswith("$ "):
                        line = line[2:].strip()
                    if line:
                        yield rel, line
                        break

    def detect(self, path):
        for rel, line in self._candidates(path):
            if self.FANOUT.search(line):
                continue
            parts = line.split()
            # The load-bearing rule: some argument has to be a file that is
            # really there. Without it this would run text.
            # Relative only. `os.path.join(root, "/")` is `/`, which exists
            # on every machine -- so without this line `rm -rf /` satisfies
            # the rule that a command must name something real. The
            # repository's own selftest caught that on its first run.
            named = [p.strip("\"'") for p in parts[1:]
                     if "/" in p or p.endswith((".py", ".sh", ".js", ".ts"))]
            named = [p for p in named
                     if p and not os.path.isabs(p) and ".." not in p.split("/")]
            if not named:
                continue
            if not any(os.path.exists(os.path.join(path, p)) for p in named):
                continue
            if shutil.which(parts[0]) is None:
                continue
            self.source = rel
            return parts
        return None


# Last, deliberately. Where a convention applies it is the better answer --
# `pytest` knows how to name a single test and a documented shell line does
# not. This is the fallback for the repositories the conventions cannot see.
ECOSYSTEMS = (Node(), Python(), Rust(), Go(), Make(), Declared())

# A suite that is red because nothing could be imported is not a red suite. A
# missing dependency and a failing test both exit non-zero, and scoring the
# first as the second discards exactly the subjects whose suites are fine.
CANNOT_RUN = (
    "no tests ran", "INTERNALERROR", "ModuleNotFoundError", "ImportError",
    "ERROR collecting", "cannot find module", "Cannot find module",
    "MODULE_NOT_FOUND", "command not found", "is not on PATH",
    # The entry point is not there at this commit. A repository's test command
    # is discovered at HEAD and the replay checks out its history, so a suite
    # that was introduced last week does not exist at the commit being
    # replayed -- and an interpreter that cannot open its own script exits
    # non-zero exactly like a failing test. Reading that as red would report
    # every commit older than the suite as broken.
    # Only the interpreter's own wording. A bare "No such file or directory"
    # was here for one revision and taken out again: a test that fails on a
    # missing fixture prints exactly that, and calling it could-not-run would
    # hide a real defect. A shell script that is not there exits 127, which is
    # already handled above.
    "can't open file", "cannot open file",
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
