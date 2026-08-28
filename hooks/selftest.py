#!/usr/bin/env python3
"""Prove the trust gate lets nothing run until it has been trusted, and stops
running it the moment the code changes.

    python3 hooks/selftest.py [--verbose]

    0 = every case held    1 = a case failed    2 = cannot run (git missing)

This is the one file in the repository that decides whether an unread
repository's code executes on your machine, and it shipped with no test at all.
Every other component here fails loudly: a gate turns red, a guard fails open
and its selftest catches it. This one fails *silently and in the safe-looking
direction* -- a trust check that accidentally returns "trusted" produces no
error, no output, and no symptom until the repository it waved through was
hostile.

So the cases below assert the negative space, not the happy path. That an
untrusted repo's guards do NOT run matters more than that a trusted repo's do,
and it is the assertion that would survive somebody "simplifying" the digest
check.

## Isolation

Every case runs with `CLAUDE_CONFIG_DIR` pointed at a throwaway directory. That
is not tidiness: the trust store is the file that records "the human read this
code". A selftest that wrote to the real one would be granting trust on the
developer's behalf, which is the exact thing the gate exists to prevent -- and
it would do it while printing PASS.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HOOK = os.path.join(HERE, "run_repo_guards.py")
GUARD_SRC = os.path.join(ROOT, "shared", "scripts", "guards")

BLOCKING = json.dumps(
    {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}})
BENIGN = json.dumps(
    {"tool_name": "Bash",
     "tool_input": {"command": "git push origin feature/x"}})

WIRED = json.dumps({"hooks": {"PreToolUse": [
    {"matcher": "Bash", "hooks": [
        {"type": "command", "command": "python3 scripts/guards/dispatch.py"}]}]}})


def sh(args, cwd=None, env=None, stdin=None):
    return subprocess.run(args, cwd=cwd, env=env, input=stdin, text=True,
                          capture_output=True, timeout=60)


def make_repo(with_guards=True):
    """A git repository carrying the shipped guards, and nothing else.

    Deliberately not built by calling scaffold.py. A test of the trust gate
    that breaks when the scaffolder's file list changes is a test of the
    scaffolder, and the failure would be read as a trust-gate regression.
    """
    tmp = tempfile.mkdtemp(prefix="trust-selftest-")
    os.makedirs(os.path.join(tmp, "src"))
    with open(os.path.join(tmp, "src", "a.py"), "w", encoding="utf-8") as fh:
        fh.write("def a():\n    return 1\n")
    if with_guards:
        shutil.copytree(GUARD_SRC, os.path.join(tmp, "scripts", "guards"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        os.makedirs(os.path.join(tmp, ".claude"), exist_ok=True)
        with open(os.path.join(tmp, ".claude", "guards.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"protected_branches": ["main"]}, fh)
    sh(["git", "init", "-q", "."], cwd=tmp)
    sh(["git", "add", "-A"], cwd=tmp)
    return tmp


class Case:
    """One throwaway repo, one throwaway trust store, a sequence of assertions."""

    def __init__(self, repo, config):
        self.repo, self.config = repo, config
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=config)
        self.failures = []

    def call(self, payload=BLOCKING):
        p = sh([sys.executable, HOOK], cwd=self.repo, env=self.env,
               stdin=payload)
        return p.returncode, p.stdout + p.stderr

    def manage(self, *flags):
        return sh([sys.executable, HOOK, *flags], cwd=self.repo, env=self.env)

    def expect(self, what, code, payload=BLOCKING, says=None):
        rc, out = self.call(payload)
        if rc != code:
            self.failures.append(
                f"{what}\n    expected exit {code}, got {rc}\n"
                f"    {out.strip()[:400]}")
        elif says is not None and says not in out:
            # Exit codes are shared observables: 1 is reached by a crash as
            # well as by the warning, and 0 by "allowed" as well as by "gave
            # up early". A code-only assertion passes while the gate is broken.
            self.failures.append(
                f"{what}\n    exit {code} as expected, but {says!r} is absent "
                f"— reached by the wrong path\n    {out.strip()[:400]}")

    def edit_guard(self):
        path = os.path.join(self.repo, "scripts", "guards",
                            "no_protected_branch_push.py")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n# one line, added after the human read it\n")

    def wire(self):
        with open(os.path.join(self.repo, ".claude", "settings.json"), "w",
                  encoding="utf-8") as fh:
            fh.write(WIRED + "\n")


def case_untrusted_does_not_run(c):
    # One call, both assertions. The warning is said once per guard set on
    # purpose, so asserting it twice would test the throttle, not the gate.
    rc, out = c.call()
    if rc != 1:
        c.failures.append(
            f"an untrusted repo's guards must not run\n"
            f"    expected exit 1 (warn and allow), got {rc}\n"
            f"    {out.strip()[:400]}")
    elif "NOT running" not in out or "no_protected_branch_push.py" not in out:
        c.failures.append(
            "the warning must name the files that are not running\n"
            f"    {out.strip()[:400]}")


def case_warning_is_said_once(c):
    c.call()
    c.expect("the same warning must not repeat on every Bash call", 0)


def case_trust_makes_them_run(c):
    c.manage("--trust")
    c.expect("a trusted guard must block what it claims to block", 2,
             says="protected")


def case_trust_is_not_a_blanket(c):
    c.manage("--trust")
    c.expect("a trusted guard must stay out of the way otherwise", 0,
             payload=BENIGN)


def case_editing_revokes(c):
    c.manage("--trust")
    c.expect("baseline: trusted and blocking", 2)
    c.edit_guard()
    c.expect("editing a guard must revoke trust", 1,
             says="Changed since you trusted them")


def case_forget_revokes(c):
    c.manage("--trust")
    c.expect("baseline: trusted and blocking", 2)
    c.manage("--forget")
    c.expect("--forget must revoke trust", 1, says="NOT running")


def case_trust_does_not_travel(c):
    """Trusting one checkout must not trust another that happens to look alike.

    Same guard files, byte for byte, different path. If trust were keyed on the
    digest alone, cloning a hostile repo whose guards match a trusted one would
    inherit the approval.
    """
    c.manage("--trust")
    other = make_repo()
    try:
        p = sh([sys.executable, HOOK], cwd=other, env=c.env, stdin=BLOCKING)
        if p.returncode == 2:
            c.failures.append(
                "trusting one repository must not trust an identical other\n"
                "    a second checkout ran its guards with no approval")
    finally:
        shutil.rmtree(other, ignore_errors=True)


def case_wired_repo_is_silent(c):
    """Once the repo owns its guards, this hook must do nothing at all.

    Not "nothing harmful" -- nothing. The repository's own settings.json runs
    the dispatcher, so anything this hook adds is a second execution of the
    same guards on every Bash call, and the user is paying for it twice.
    """
    c.wire()
    rc, out = c.call()
    if rc != 0 or out.strip():
        c.failures.append(
            "a repo that wires the dispatcher itself must get silence\n"
            f"    exit {rc}, output {out.strip()[:200]!r}")


def case_no_guards_is_silent(c):
    rc, out = c.call()
    if rc != 0 or out.strip():
        c.failures.append(
            "a repo with no guards must get silence\n"
            f"    exit {rc}, output {out.strip()[:200]!r}")


def case_malformed_payload_allows(c):
    """A hook that raises on an unfamiliar payload blocks every Bash call.

    The payload shape is not this repository's to control -- a new tool, a new
    field, and a strict parser becomes an outage that looks like Claude Code
    breaking.
    """
    c.manage("--trust")
    p = sh([sys.executable, HOOK], cwd=c.repo, env=c.env, stdin="not json{{")
    if p.returncode not in (0, 1):
        c.failures.append(
            f"a malformed payload must not block; exit {p.returncode}\n"
            f"    {(p.stdout + p.stderr).strip()[:300]}")


CASES = [
    ("untrusted guards do not run", case_untrusted_does_not_run, True),
    ("the warning is said once", case_warning_is_said_once, True),
    ("trust makes them run", case_trust_makes_them_run, True),
    ("trust is not a blanket block", case_trust_is_not_a_blanket, True),
    ("editing a guard revokes trust", case_editing_revokes, True),
    ("--forget revokes trust", case_forget_revokes, True),
    ("trust does not travel between checkouts", case_trust_does_not_travel, True),
    ("a wired repo gets silence", case_wired_repo_is_silent, True),
    ("a repo with no guards gets silence", case_no_guards_is_silent, False),
    ("a malformed payload does not block", case_malformed_payload_allows, True),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    if shutil.which("git") is None:
        print("cannot run: git not on PATH", file=sys.stderr)
        return 2
    if not os.path.isdir(GUARD_SRC):
        print(f"cannot run: no guards at {GUARD_SRC}", file=sys.stderr)
        return 2

    failures = []
    for label, fn, with_guards in CASES:
        repo = make_repo(with_guards=with_guards)
        config = tempfile.mkdtemp(prefix="trust-store-")
        case = Case(repo, config)
        try:
            fn(case)
        except Exception as exc:  # a raising case is a failing case
            case.failures.append(f"{label}\n    raised {exc!r}")
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(config, ignore_errors=True)
        if case.failures:
            failures.extend(f"{label}: {f}" for f in case.failures)
        elif a.verbose:
            print(f"  ok  {label}")

    if failures:
        print(f"{len(failures)} trust-gate assertion(s) failed:\n",
              file=sys.stderr)
        for f in failures:
            print(f"  {f}\n", file=sys.stderr)
        return 1
    if a.verbose:
        print(f"{len(CASES)} cases: nothing runs until it is trusted, and "
              f"editing it stops it running")
    return 0


if __name__ == "__main__":
    sys.exit(main())
