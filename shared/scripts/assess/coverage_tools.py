#!/usr/bin/env python3
"""Coverage, taken from the ecosystem's own tool rather than measured here.

    python3 assess/coverage_tools.py --root . --test-command "pytest -q"

Exit codes:
    0 = a coverage report was produced or found and read
    2 = cannot judge (no tool, no report, no recognisable command)

## Why this is not an instrument

There was one here: six hundred lines of AST instrumentation that computed
statement, branch and MC/DC coverage in a single pass. It worked, and it was
the wrong thing to own. On statement and branch it was strictly worse than
`coverage.py` -- multi-line statements, generators, `async`, `# pragma: no
cover`, exclusion rules, fifteen years of edge cases it had none of -- and
measuring a stranger's repository with an amateur implementation of a solved
problem is not a defensible position for a diagnostic to take.

So: the tools do the measuring. This file knows how to ask them and how to
read what they say back, and that is all it knows.

## Two ways in

**Run the tool**, where the incantation is known and the tool is already
present: `coverage.py` for Python, `go test -cover`, `c8` or `nyc` for Node.
Nothing is installed to make this work -- a repository whose ecosystem has a
coverage tool and does not have it installed is a finding, not a gap in this
file, and installing one would change what the subject repository contains.

**Read a report the repository already produces**, otherwise. lcov, Cobertura,
JaCoCo, coverage.py's own JSON, Go's coverprofile, gcov's JSON. This is the
general path and it is the only one for ecosystems whose build we cannot drive
blind -- C, C++, Rust, Java, anything behind a Makefile we have never seen.
It is also where MC/DC comes from, because the only tools that produce it are
compilers: `clang -fcoverage-mcdc`, `gcc -fcondition-coverage`,
`cargo llvm-cov --mcdc`.

## What is absent is absent, not zero

A criterion the ecosystem's tool does not produce is left out of the result
entirely. Go has no branch coverage -- the language's tooling does not compute
it -- and a Go repository must not read as one whose branches are all
untested. The same for MC/DC, which no mainstream tool outside the compilers
produces at all: for Python, Java, JavaScript and C# the row is simply not
there.

## The inference, and which way it runs

High coverage predicts very little about finding bugs (Zhao, Zhou & Cohen
2026: r <= 0.481 pooled across suites). Read the other way it is not a
correlation but a guarantee: a line no test executes cannot be caught by the
test suite, for any defect, ever. That is the only claim this file's output
supports, and it is why the number belongs above the ladder rather than beside
it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

RUN_TIMEOUT = 900
REPORT_TIMEOUT = 180

# The criteria a result may carry. Order is the order they are printed in, and
# it is the order of increasing strength, so a repository that has only the
# first has the weakest of the four.
CRITERIA = ("statement", "function", "branch", "mcdc")


def sh(args, cwd, timeout):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(args, 127, "", str(exc))


def _pair(total, covered):
    total, covered = int(total), int(covered)
    return {"total": total, "covered": covered,
            "missing": max(0, total - covered)}


# --- readers: a report already on disk --------------------------------------
# Every one of these takes a path and returns the normalised shape, or None if
# the file is not what it claimed to be. None of them raise: a malformed report
# is an abstention, never a crash and never a zero.

def read_coveragepy_json(path):
    """coverage.py's own JSON. Statement and branch; no function, no MC/DC."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    t = data.get("totals") or {}
    if "num_statements" not in t:
        return None
    out = {"statement": _pair(t["num_statements"], t.get("covered_lines", 0))}
    if t.get("num_branches"):
        out["branch"] = _pair(t["num_branches"], t.get("covered_branches", 0))
    files = {f: sorted(v.get("missing_lines") or [])
             for f, v in (data.get("files") or {}).items()}
    return {"tool": "coverage.py", "criteria": out, "files": files}


def read_lcov(path):
    """lcov .info -- c8, nyc, grcov, cargo-llvm-cov, gcov, most of C and Rust.

    The one report format that carries function coverage as a first-class
    counter (FNF/FNH), which is why Node and Rust can answer 2.1's function
    row and Python cannot."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    tally = {"LF": 0, "LH": 0, "BRF": 0, "BRH": 0, "FNF": 0, "FNH": 0}
    files, current, missing = {}, None, []
    for line in text.splitlines():
        if line.startswith("SF:"):
            if current:
                files[current] = sorted(missing)
            current, missing = line[3:].strip(), []
        elif line.startswith("DA:"):
            bits = line[3:].split(",")
            if len(bits) >= 2 and bits[1].strip() in ("0", "-"):
                try:
                    missing.append(int(bits[0]))
                except ValueError:
                    pass
        else:
            for key in tally:
                if line.startswith(key + ":"):
                    try:
                        tally[key] += int(line.split(":", 1)[1].strip())
                    except ValueError:
                        pass
    if current:
        files[current] = sorted(missing)
    out = {}
    if tally["LF"]:
        out["statement"] = _pair(tally["LF"], tally["LH"])
    if tally["FNF"]:
        out["function"] = _pair(tally["FNF"], tally["FNH"])
    if tally["BRF"]:
        out["branch"] = _pair(tally["BRF"], tally["BRH"])
    if not out:
        # The one guard that matters, and the reason it is phrased on `out`
        # rather than on "did any counter line parse": a truncated report
        # yields small numbers, and small numbers here read as `almost
        # nothing is tested` -- the worst reading to produce by accident.
        return None
    return {"tool": "lcov report", "criteria": out, "files": files}


def read_cobertura(path):
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    if root.tag != "coverage" or "lines-valid" not in root.attrib:
        return None
    a = root.attrib
    out = {"statement": _pair(a.get("lines-valid", 0), a.get("lines-covered", 0))}
    if int(a.get("branches-valid", 0) or 0):
        out["branch"] = _pair(a["branches-valid"], a.get("branches-covered", 0))
    return {"tool": "Cobertura report", "criteria": out, "files": {}}


def read_jacoco(path):
    """JaCoCo XML. Line, branch and METHOD -- Java's function coverage."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    if root.tag != "report":
        return None
    want = {"LINE": "statement", "METHOD": "function", "BRANCH": "branch"}
    out = {}
    for counter in root.findall("counter"):
        key = want.get(counter.get("type", ""))
        if not key:
            continue
        missed = int(counter.get("missed", 0))
        covered = int(counter.get("covered", 0))
        out[key] = _pair(missed + covered, covered)
    if not out:
        return None
    return {"tool": "JaCoCo report", "criteria": out, "files": {}}


_GO_BLOCK = re.compile(r"^(.+):\d+\.\d+,\d+\.\d+ (\d+) (\d+)$")


def read_gocover(path):
    """Go's coverprofile. Statements only -- Go's tooling has no branch
    coverage, so the branch row is absent rather than zero."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    if not lines or not lines[0].startswith("mode:"):
        return None
    total = covered = 0
    for line in lines[1:]:
        m = _GO_BLOCK.match(line.strip())
        if not m:
            continue
        n = int(m.group(2))
        total += n
        if int(m.group(3)) > 0:
            covered += n
    if not total:
        return None
    return {"tool": "go test -cover", "files": {},
            "criteria": {"statement": _pair(total, covered)}}


def read_gcov_json(path):
    """gcov's JSON. The one on-disk format that can carry MC/DC.

    GCC 14 added `-fcondition-coverage`, and `gcov --conditions
    --json-format` writes per-line condition counts. It is masking MC/DC,
    the same variant Clang chose independently."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if "files" not in data or "gcc_version" not in data:
        return None
    ls = lc = bs = bc = cs = cc = 0
    for f in data["files"]:
        for line in f.get("lines", []):
            ls += 1
            if line.get("count"):
                lc += 1
            for br in line.get("branches", []):
                bs += 1
                if br.get("count"):
                    bc += 1
            for cond in line.get("conditions", []):
                n = int(cond.get("count", 0))
                cs += n
                cc += n - len(cond.get("not_covered_true", [])) \
                        - len(cond.get("not_covered_false", []))
    out = {}
    if ls:
        out["statement"] = _pair(ls, lc)
    if bs:
        out["branch"] = _pair(bs, bc)
    if cs:
        out["mcdc"] = _pair(cs, max(0, cc))
    if not out:
        return None
    return {"tool": "gcov", "criteria": out, "files": {}}


# Each conventional location paired with the reader that belongs to it.
#
# Paired, rather than trying every reader against every file, because the
# readers are not mutually exclusive on malformed input: a truncated gcov.json
# is not lcov, but lcov's parser has no way to say so except by finding no
# counters, and "found no counters" is one edit away from "found zero
# coverage". Pairing removes the question instead of guarding against it.
REPORTS = (
    ("coverage.json", read_coveragepy_json),
    ("coverage/coverage-final.json", read_coveragepy_json),
    ("lcov.info", read_lcov),
    ("coverage/lcov.info", read_lcov),
    ("target/lcov.info", read_lcov),
    ("coverage.xml", read_cobertura),
    ("cobertura.xml", read_cobertura),
    ("coverage/cobertura-coverage.xml", read_cobertura),
    ("target/site/jacoco/jacoco.xml", read_jacoco),
    ("build/reports/jacoco/test/jacocoTestReport.xml", read_jacoco),
    ("jacoco.xml", read_jacoco),
    ("coverage.out", read_gocover),
    ("cover.out", read_gocover),
    ("coverprofile.out", read_gocover),
    ("coverage.gcov.json", read_gcov_json),
    ("gcov.json", read_gcov_json),
)


def find_report(root):
    """A report the repository already produces, and what read it.

    Deliberately a fixed list of conventional locations rather than a walk: a
    walk finds a coverage report inside a vendored dependency and reports the
    dependency's coverage as the subject's."""
    for rel, reader in REPORTS:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        got = reader(path)
        if got:
            got["report"] = rel
            return got
    return None


# --- runners: drive the ecosystem's tool ourselves ---------------------------
# Only where the incantation is known and the tool is already present. Nothing
# below installs anything: a Python repository without `coverage` installed is
# a repository without a coverage tool, which is a finding about the subject.

class Python:
    name = "python"
    missing = "coverage"
    hint = "pip install coverage"

    def detect(self, root):
        """A packaging marker, or simply Python files.

        The marker alone missed a repository made of scripts -- no
        pyproject.toml, no setup.py, nothing installable, and every file a
        module. That shape is common enough (tooling, plugins, a directory of
        checks) that requiring a packaging file reports those repositories as
        having no ecosystem at all."""
        if any(os.path.exists(os.path.join(root, f)) for f in
               ("pyproject.toml", "setup.py", "setup.cfg",
                "requirements.txt", "tox.ini")):
            return True
        seen = 0
        for base, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs
                       if d not in ("node_modules", "vendor", ".git", "venv",
                                    ".venv", "target", "dist", "build")]
            seen += sum(1 for n in names if n.endswith(".py"))
            if seen >= 3:
                return True
        return False

    def available(self, root):
        return sh([sys.executable, "-c", "import coverage"], root, 60
                  ).returncode == 0

    def wrap(self, command):
        """`coverage run` in front of the suite, whatever shape the suite is.

        Three shapes are recognisable without reading the repository: a bare
        `pytest`, a `-m module` invocation, and a script path. Anything else --
        a shell pipeline, a wrapper script, `make test` -- cannot be wrapped
        blind, and saying so is better than guessing at somebody's build."""
        argv = command if isinstance(command, list) else command.split()
        if not argv:
            return None
        head = os.path.basename(argv[0])
        run = [sys.executable, "-m", "coverage", "run", "--branch", "--source=."]
        if head in ("pytest", "py.test"):
            return run + ["-m", "pytest"] + argv[1:]
        if head.startswith("python") and len(argv) > 1:
            return run + argv[1:]
        if argv[0].endswith(".py"):
            return run + argv
        return None

    def measure(self, root, command, work):
        argv = self.wrap(command)
        if not argv:
            return None, ("the test command cannot be wrapped by `coverage "
                          "run` without reading the repository -- pass one "
                          "shaped like `pytest ...` or `python3 <script>`")
        sh(argv, root, RUN_TIMEOUT)
        out = os.path.join(work, "coverage.json")
        rep = sh([sys.executable, "-m", "coverage", "json", "-o", out],
                 root, REPORT_TIMEOUT)
        if rep.returncode != 0:
            # `No data to report.` arrives on stdout, not stderr, so reading
            # only stderr produced `produced no report: ` with nothing after
            # the colon -- an abstention that does not say what happened.
            said = (rep.stderr or "").strip() or (rep.stdout or "").strip()
            return None, ("coverage.py produced no report: " +
                          (said[:200] or "it said nothing"))
        return read_coveragepy_json(out), ""


class Go:
    name = "go"
    missing = "go"
    hint = "install the Go toolchain"

    def detect(self, root):
        return os.path.exists(os.path.join(root, "go.mod"))

    def available(self, root):
        return shutil.which("go") is not None

    def measure(self, root, command, work):
        out = os.path.join(work, "coverage.out")
        r = sh(["go", "test", "-coverprofile=" + out, "./..."], root, RUN_TIMEOUT)
        if not os.path.exists(out):
            return None, "go test wrote no coverprofile: " + r.stderr[:200]
        return read_gocover(out), ""


class Node:
    name = "node"
    missing = "c8"
    hint = "npm install --save-dev c8"

    def detect(self, root):
        return os.path.exists(os.path.join(root, "package.json"))

    def _bin(self, root):
        for tool in ("c8", "nyc"):
            path = os.path.join(root, "node_modules", ".bin", tool)
            if os.path.exists(path):
                return path
        return None

    def available(self, root):
        return self._bin(root) is not None

    def measure(self, root, command, work):
        argv = command if isinstance(command, list) else command.split()
        if not argv:
            return None, "no test command to instrument"
        r = sh([self._bin(root), "--reporter=lcovonly",
                "--report-dir=" + work] + argv, root, RUN_TIMEOUT)
        out = os.path.join(work, "lcov.info")
        if not os.path.exists(out):
            return None, "c8 wrote no lcov report: " + r.stderr[:200]
        return read_lcov(out), ""


RUNNERS = (Python(), Node(), Go())


def assess(root, command=None, work=None):
    """Coverage for this repository, from its own tooling. Never from ours.

    Order matters. Running the tool is preferred because it measures *this*
    suite now; a report found on disk was produced by somebody at some point
    and may predate the code beside it. But a stale report is still evidence
    and no report is none, so the fallback is worth having -- and for C, C++,
    Rust and Java it is the only path, because their builds cannot be driven
    blind."""
    work = work or os.path.join(root, ".assess-coverage")
    os.makedirs(work, exist_ok=True)
    reasons = []
    for runner in RUNNERS:
        if not runner.detect(root):
            continue
        if not runner.available(root):
            reasons.append("%s: `%s` is not installed here (%s)" %
                           (runner.name, runner.missing, runner.hint))
            continue
        if not command:
            reasons.append("%s: no test command to instrument" % runner.name)
            continue
        got, why = runner.measure(root, command, work)
        if got:
            got["how"] = "ran " + runner.name + "'s own tool"
            return got, ""
        reasons.append("%s: %s" % (runner.name, why))

    found = find_report(root)
    if found:
        found["how"] = "read %s, which this repository already produces" % \
                       found["report"]
        return found, ""

    detail = "; ".join(reasons) if reasons else \
        "no ecosystem here has a coverage tool this knows how to drive"
    return None, ("cannot judge: " + detail + ". No report was found at any "
                  "conventional path either. Nothing is installed to make "
                  "this work -- a repository whose ecosystem has a coverage "
                  "tool and does not have it installed is a finding about the "
                  "repository")


def render(r):
    if not r:
        return "coverage: could not judge\n"
    out = ["coverage -- %s (%s)" % (r.get("tool", "?"), r.get("how", ""))]
    for key in CRITERIA:
        c = r["criteria"].get(key)
        if not c:
            continue
        pct = (100.0 * c["covered"] / c["total"]) if c["total"] else 0.0
        out.append("  %-10s %6d of %-6d untested   (%.0f%% covered)"
                   % (key, c["missing"], c["total"], pct))
    absent = [k for k in CRITERIA if k not in r["criteria"]]
    if absent:
        out.append("  not produced by this tool, so not reported: "
                   + ", ".join(absent))
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--test-command", default="")
    ap.add_argument("--work", default="")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    r, why = assess(root, a.test_command or None, a.work or None)
    if not r:
        print(why, file=sys.stderr)
        return 2
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=1)
    sys.stdout.write(render(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
