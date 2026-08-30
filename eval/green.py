#!/usr/bin/env python3
"""Run each corpus repository's own test suite, untouched, and count the green.

    python3 eval/green.py [--only <substring>] [--samples 2] [--out <path>]

    0 = every repository reached a verdict    1 = this script broke on one
    2 = cannot judge (no corpus, or it has not been fetched)

That count -- not twenty -- is the corpus size for any before/after measurement,
because a repository whose tests already fail cannot report an "after" state.
Red stays red and the number means nothing.

## The distinction this script exists to make

A missing toolchain and a failing test both exit non-zero. Scoring the first as
the second discards exactly the repositories whose suites are fine, and it does
it silently, in the direction that makes the corpus look worse than it is. So
installing and testing are separate phases with separate verdicts:

    green            the suite ran and passed, every sample
    red              the suite ran and failed
    flaky            it ran and disagreed with itself between samples
    could-not-run    the toolchain is absent, the install failed, or it timed out
    contaminated     the tree is not the pinned commit, so "untouched" is a lie

Only the first is usable as an instrument. Only the second is a fact about the
repository. `could-not-run` is a fact about this machine, and it is the one that
must never be quietly folded into the others.

The last one was not anticipated; it was found. `run_corpus.py` scaffolds these
trees in place -- seventeen files written, two tracked files edited, no commit --
and the first version of this script read our own `ci.sh` and `docs/` back and
reported that five repositories had no recognisable test command. They have
tests. We were reading our own scaffold. A script that claims to measure an
untouched repository has to check that the repository is untouched, and this one
refuses rather than guessing.

## What "green" was decided to mean

The declared test command exits 0, twice. Not "has tests", not "has good tests":
a repository with three assertion-free tests passes here and is a poor
instrument, and this script does not pretend to know the difference. What it
buys is the property that matters for a paired comparison -- that the suite
gives the same answer twice when nothing changed -- because a suite that
disagrees with itself cannot report a difference smaller than its own noise.
One sample is not a measurement; that lesson was paid for in `nim_smoke.py`.

## What it does not decide

Whether a non-green repository leaves the corpus. It does not: the "do no harm"
step needs a repository, not a green one, and a manifest edited from a run is a
manifest that quietly forgets why. This writes a verdict and stops.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, ".work")

# Generous, and different by phase on purpose: an install pulling a Node tree
# over a slow link is not a hung test suite, and a shared timeout would report
# them the same way.
INSTALL_TIMEOUT = 900
TEST_TIMEOUT = 600


class Ecosystem:
    """A way to recognise a repository, set it up, and run its tests.

    `detect` returns the test command when this ecosystem applies, else None --
    so recognising the repository and knowing what to run are one decision. A
    repository with a package.json and no `scripts.test` is not a Node subject
    with a missing command; it is not a Node subject."""

    name = "?"
    tool = None  # the binary that must exist, or the ecosystem cannot run

    def detect(self, path):
        raise NotImplementedError

    def install(self, path):
        """Commands to run before testing. Failure here is could-not-run."""
        return []


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
        # npm's own placeholder. It exits 1 and means "nobody wrote a test
        # command", which is could-not-run rather than red -- and treating it as
        # red would be this script inventing a failure.
        if not test or "no test specified" in test:
            return None
        return ["npm", "test", "--silent"]

    def install(self, path):
        # `npm ci` needs a lockfile and is exact; `npm install` resolves and is
        # what a repository without one actually supports.
        lock = any(os.path.exists(os.path.join(path, f))
                   for f in ("package-lock.json", "npm-shrinkwrap.json"))
        cmd = ["npm", "ci"] if lock else ["npm", "install"]
        return [cmd + ["--no-audit", "--no-fund"]]


def interpreter():
    """The interpreter a Python subject's tests run under.

    `GREEN_PYTHON` exists for `eval/validate_defects.py`, which builds one venv
    per repository. The survey keeps the ambient interpreter, for the reason
    documented in `Python.install`."""
    return os.environ.get("GREEN_PYTHON") or sys.executable


class Python(Ecosystem):
    name = "python"
    tool = "python3"

    def detect(self, path):
        markers = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
        has_marker = any(os.path.exists(os.path.join(path, m)) for m in markers)
        if not any(os.path.isdir(os.path.join(path, d)) for d in ("tests", "test")):
            # pytest can still find scattered test_*.py, but a repository with
            # no test directory and no declared runner is a guess, not a subject.
            return None
        if not has_marker:
            # A test directory and sixty-six tracked `.py` files is not a guess.
            # `dingtalk-opencode-tag` is exactly that shape and carried the
            # second-largest supply of validated defect instances in the corpus,
            # all of them invisible while a packaging marker was required.
            out = sh(["git", "ls-files", "*.py"], path, 60)
            if out.returncode != 0 or len(out.stdout.split()) < 10:
                return None
        return [interpreter(), "-m", "pytest", "-q"]

    def install(self, path):
        # The survey installs nothing on purpose: `pip install -e .` mutates the
        # machine's environment for every later repository, and one repository's
        # pin becomes another's failure. pytest from the ambient environment, or
        # could-not-run.
        #
        # `GREEN_INSTALL_DEPS=1` lifts that only where the caller has given this
        # repository an interpreter of its own, so nothing installed here can
        # reach the next subject. Without it, every Python subject in the corpus
        # is could-not-run on its own declared dependencies -- which is a fact
        # about this script, not about the repository.
        if os.environ.get("GREEN_INSTALL_DEPS") != "1":
            return []
        py = interpreter()
        base = [py, "-m", "pip", "install", "--quiet",
                "--disable-pip-version-check"]
        steps = [base + ["pytest", "pytest-asyncio"]]
        reqs = [f for f in ("requirements.txt", "requirements-dev.txt",
                            "dev-requirements.txt", "test-requirements.txt")
                if os.path.exists(os.path.join(path, f))]
        for f in reqs:
            steps.append(base + ["-r", f])
        if not reqs and any(os.path.exists(os.path.join(path, m))
                            for m in ("pyproject.toml", "setup.py", "setup.cfg")):
            steps.append(base + ["-e", "."])
        return steps


class Rust(Ecosystem):
    name = "rust"
    tool = "cargo"

    def detect(self, path):
        if not os.path.exists(os.path.join(path, "Cargo.toml")):
            return None
        return ["cargo", "test", "--quiet"]


class Go(Ecosystem):
    name = "go"
    tool = "go"

    def detect(self, path):
        if not os.path.exists(os.path.join(path, "go.mod")):
            return None
        return ["go", "test", "./..."]

    def install(self, path):
        return [["go", "mod", "download"]]


class Make(Ecosystem):
    """Last, because a Makefile `test:` target usually drives one of the above.

    Reaching this means the ecosystems that know how to install dependencies
    did not recognise the repository, so the target is being run against
    whatever happens to be installed."""

    name = "make"
    tool = "make"

    def detect(self, path):
        mf = os.path.join(path, "Makefile")
        if not os.path.exists(mf):
            return None
        try:
            with open(mf, encoding="utf-8", errors="replace") as fh:
                body = fh.read()
        except OSError:
            return None
        if not any(line.startswith(("test:", "test :")) for line in body.splitlines()):
            return None
        return ["make", "test"]


ECOSYSTEMS = (Node(), Python(), Rust(), Go(), Make())


def sh(args, cwd, timeout):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "",
                                           f"timed out after {timeout}s")
    except OSError as exc:
        return subprocess.CompletedProcess(args, 127, "", str(exc))


def dirt(path):
    """A one-line description of how the tree differs from its commit, or ""."""
    out = sh(["git", "status", "--porcelain"], path, 120)
    if out.returncode != 0:
        return "not a git repository"
    lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    if not lines:
        return ""
    modified = sum(1 for ln in lines if not ln.startswith("??"))
    untracked = len(lines) - modified
    return (f"{modified} tracked file(s) modified, {untracked} untracked "
            f"-- run eval/fetch.py to restore")


def classify(path, samples, require_clean=True):
    """(verdict, detail, seconds, ecosystem, command) for one repository.

    `require_clean` is the corpus survey's question, not everybody's. Here an
    unexpected diff means we are about to measure our own scaffold and call it
    the repository. In `improve.py` the tree is *supposed* to be dirty -- it has
    just been scaffolded and edited by an agent -- and refusing there reported
    `contaminated` for every subject, which read as harm and was a refusal to
    look."""
    soiled = dirt(path) if require_clean else ""
    if soiled:
        return ("contaminated", soiled, None, "-", "-")

    for eco in ECOSYSTEMS:
        cmd = eco.detect(path)
        if cmd is None:
            continue
        if eco.tool and shutil.which(eco.tool) is None:
            return ("could-not-run", f"{eco.tool} is not on PATH", None,
                    eco.name, " ".join(cmd))

        for step in eco.install(path):
            out = sh(step, path, INSTALL_TIMEOUT)
            if out.returncode != 0:
                tail = (out.stderr or out.stdout).strip().splitlines()
                return ("could-not-run",
                        f"{' '.join(step[:2])} failed: "
                        + (tail[-1][:160] if tail else f"exit {out.returncode}"),
                        None, eco.name, " ".join(cmd))

        codes, secs = [], []
        for _ in range(samples):
            started = time.time()
            out = sh(cmd, path, TEST_TIMEOUT)
            secs.append(time.time() - started)
            if out.returncode == 127:
                return ("could-not-run", (out.stderr or "").strip()[:160],
                        None, eco.name, " ".join(cmd))
            if out.returncode == 124:
                return ("could-not-run", f"tests timed out after {TEST_TIMEOUT}s",
                        None, eco.name, " ".join(cmd))
            codes.append(out.returncode)
            last = out

        median = sorted(secs)[len(secs) // 2]
        if len(set(codes)) > 1:
            return ("flaky", f"exit codes {codes} across {samples} runs",
                    median, eco.name, " ".join(cmd))
        if codes[0] == 0:
            return ("green", "", median, eco.name, " ".join(cmd))
        tail = (last.stdout or last.stderr).strip().splitlines()
        return ("red", (tail[-1][:160] if tail else f"exit {codes[0]}"),
                median, eco.name, " ".join(cmd))

    return ("could-not-run", "no ecosystem recognised a runnable test command",
            None, "-", "-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--samples", type=int, default=2,
                    help="runs per suite; a suite that disagrees with itself "
                         "cannot report a difference smaller than its own noise")
    ap.add_argument("--out", default=os.path.join(HERE, "results", "green.json"))
    a = ap.parse_args()

    manifest = os.path.join(HERE, "corpus.json")
    if not os.path.exists(manifest):
        print("cannot judge: no eval/corpus.json", file=sys.stderr)
        return 2
    with open(manifest, encoding="utf-8") as fh:
        repos = [r["full_name"] for r in json.load(fh)["repos"]]
    if a.only:
        repos = [r for r in repos if a.only in r]
    if not repos:
        print("cannot judge: --only matched no repository", file=sys.stderr)
        return 2
    if not os.path.isdir(WORK):
        print("cannot judge: nothing fetched; run eval/fetch.py", file=sys.stderr)
        return 2

    started = time.time()
    rows, broke = [], []
    width = max(len(r) for r in repos)
    print(f"{'repo':<{width}}  {'verdict':<13} {'eco':<7} {'median':>7}  detail")
    for name in repos:
        path = os.path.join(WORK, name.replace("/", "__"))
        if not os.path.isdir(path):
            verdict, detail, secs, eco, cmd = (
                "could-not-run", "not fetched", None, "-", "-")
        else:
            try:
                verdict, detail, secs, eco, cmd = classify(path, a.samples)
            except Exception as exc:  # noqa: BLE001 -- one repo must not end the run
                verdict, detail, secs, eco, cmd = ("could-not-run", "", None, "-", "-")
                broke.append((name, f"{type(exc).__name__}: {exc}"))
        rows.append({"repo": name, "verdict": verdict, "detail": detail,
                     "seconds": None if secs is None else round(secs, 1),
                     "ecosystem": eco, "command": cmd})
        shown = "   --  " if secs is None else f"{secs:6.1f}s"
        print(f"{name:<{width}}  {verdict:<13} {eco:<7} {shown}  {detail[:70]}")

    import collections
    tally = collections.Counter(r["verdict"] for r in rows)
    green = [r for r in rows if r["verdict"] == "green"]
    print("\n" + "  ".join(f"{v}: {n}" for v, n in tally.most_common()))

    soiled = [r for r in rows if r["verdict"] == "contaminated"]
    if soiled:
        print(f"\n{len(soiled)}/{len(rows)} trees are not at their pinned "
              f"commit. Nothing below is a measurement of an untouched "
              f"repository until `python3 eval/fetch.py` has restored them.")

    if green:
        total = sum(r["seconds"] or 0 for r in green)
        print(f"\n{len(green)} usable as a before/after instrument. Their suites "
              f"cost {total:.0f}s per pass, so one paired run over all of them "
              f"is about {2 * total:.0f}s of test time alone.")
    else:
        print("\nNo repository is green. There is no instrument, and phase C "
              "cannot be built on this corpus as it stands.")

    for label, reason in (("contaminated", "not the pinned commit; measuring "
                                            "these would measure our own scaffold"),
                          ("could-not-run", "this machine, not the repository"),
                          ("red", "the repository, not this machine")):
        named = [r for r in rows if r["verdict"] == label]
        if named:
            print(f"\n{label} ({reason}):")
            for r in named:
                print(f"  {r['repo']:<{width}}  {r['detail'][:90]}")

    if broke:
        print(f"\n{len(broke)} repositor(ies) broke this script:")
        for name, detail in broke:
            print(f"  {name}: {detail}")

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"samples": a.samples, "seconds": round(time.time() - started),
                   "tally": dict(tally), "rows": rows}, fh, indent=2)
    print(f"\n-> {os.path.relpath(a.out, os.getcwd())}")
    return 1 if broke else 0


if __name__ == "__main__":
    sys.exit(main())
