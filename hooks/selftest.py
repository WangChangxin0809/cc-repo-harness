#!/usr/bin/env python3
"""Prove the two plugin hooks do nothing to a repository they were not asked to.

Both fail in the same direction. The trust gate lets nothing run until it has
been trusted, and stops running it the moment the code changes; the first-look
notice reads a repository and must never execute any part of it.

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
check. The first-look cases are built the same way: the one that matters is
that a repository carrying a hook and a guard which write files ends the run
with neither file written.

## Isolation

Every case runs with `CLAUDE_CONFIG_DIR` pointed at a throwaway directory. That
is not tidiness: the trust store is the file that records "the human read this
code". A selftest that wrote to the real one would be granting trust on the
developer's behalf, which is the exact thing the gate exists to prevent -- and
it would do it while printing PASS. The same isolation covers the first-look
marker, whose real store would otherwise be told this developer had already
seen the notice in a directory that no longer exists.
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
LOOK = os.path.join(HERE, "first_look.py")
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


# --------------------------------------------------------------------------
# the first-look notice
# --------------------------------------------------------------------------

STARTUP = json.dumps({"hook_event_name": "SessionStart", "source": "startup"})
COMPACT = json.dumps({"hook_event_name": "SessionStart", "source": "compact"})

# A repository that writes a file the moment anything executes any part of it.
# `probe_repo.py` reads; `blast.py` fires hooks and `catch.py` runs the suite,
# and neither may be reached from a SessionStart notice nobody asked for.
LOUD_GUARD = ('import os\n'
              'open(os.path.join(os.path.dirname(__file__), "..", "..",\n'
              '                  "GUARD_RAN"), "w").close()\n')
LOUD_HOOK = json.dumps({"hooks": {"PreToolUse": [
    {"matcher": "Bash", "hooks": [
        {"type": "command", "command": "touch HOOK_RAN"}]}]}})


def make_loud_repo():
    """A repo whose guard writes on import and whose hook writes when fired."""
    tmp = make_repo(with_guards=False)
    os.makedirs(os.path.join(tmp, "scripts", "guards"))
    for name in ("dispatch.py", "loud.py"):
        with open(os.path.join(tmp, "scripts", "guards", name), "w",
                  encoding="utf-8") as fh:
            fh.write(LOUD_GUARD)
    os.makedirs(os.path.join(tmp, ".claude"), exist_ok=True)
    with open(os.path.join(tmp, ".claude", "settings.json"), "w",
              encoding="utf-8") as fh:
        fh.write(LOUD_HOOK + "\n")
    sh(["git", "add", "-A"], cwd=tmp)
    return tmp


class Look:
    """One throwaway repo, one throwaway marker store."""

    def __init__(self, repo, config):
        self.repo, self.config = repo, config
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=config)
        self.failures = []

    def start(self, payload=STARTUP, cwd=None):
        p = sh([sys.executable, LOOK], cwd=cwd or self.repo, env=self.env,
               stdin=payload)
        return p.returncode, p.stdout + p.stderr

    def manage(self, *flags):
        return sh([sys.executable, LOOK, *flags], cwd=self.repo, env=self.env)

    def want_notice(self, what):
        rc, out = self.start()
        if rc != 0:
            self.failures.append(f"{what}\n    a SessionStart hook must exit 0, "
                                 f"got {rc}\n    {out.strip()[:300]}")
        elif "tokens/turn" not in out or "delivery moments" not in out:
            # "it printed something" is reached by an error banner too. The
            # notice exists to carry numbers; assert the numbers.
            self.failures.append(
                f"{what}\n    no measured notice was printed\n"
                f"    {out.strip()[:300]!r}")

    def want_silence(self, what):
        rc, out = self.start()
        if rc != 0 or out.strip():
            self.failures.append(f"{what}\n    exit {rc}, output "
                                 f"{out.strip()[:200]!r}")


def case_speaks_once(look):
    look.want_notice("the first session in a repository gets the notice")
    look.want_silence("the second session must get nothing")


def case_executes_nothing(look):
    """The one that matters. Everything else here is about noise."""
    look.start()
    for sentinel, what in (("GUARD_RAN", "imported the repository's guards"),
                           ("HOOK_RAN", "fired the repository's hooks")):
        if os.path.exists(os.path.join(look.repo, sentinel)):
            look.failures.append(
                f"the notice {what}\n    a read-only first look must execute "
                f"no part of a repository nobody has read")


def case_forget_speaks_again(look):
    look.want_notice("first session")
    look.want_silence("second session")
    look.manage("--forget")
    look.want_notice("after --forget the notice must come back")


def case_marker_covers_subdirectories(look):
    """Deliberately the subdirectory first.

    Root-then-subdirectory cannot tell the two failures apart: a hook that
    walked up correctly is silent the second time because the repository was
    marked, and a hook that never walks up is silent because it thinks a
    subdirectory is not a repository at all. Starting in the subdirectory
    separates them -- it must speak there, and the root must then be quiet.
    """
    sub = os.path.join(look.repo, "src")
    rc, out = look.start(cwd=sub)
    if rc != 0 or "tokens/turn" not in out:
        look.failures.append(
            "a session started in a subdirectory must find the repository "
            f"above it\n    exit {rc}, output {out.strip()[:200]!r}")
    look.want_silence("and the root is then the same repository, already seen")


def case_compaction_is_silent(look):
    rc, out = look.start(payload=COMPACT)
    if rc != 0 or out.strip():
        look.failures.append(
            "a compaction is mid-session; the notice must not appear in it\n"
            f"    exit {rc}, output {out.strip()[:200]!r}")
    look.want_notice("and the next real start still gets it")


def case_outside_a_repo_is_silent(look):
    plain = tempfile.mkdtemp(prefix="not-a-repo-")
    try:
        rc, out = look.start(cwd=plain)
        if rc != 0 or out.strip():
            look.failures.append(
                "outside a git repository there is nothing to say\n"
                f"    exit {rc}, output {out.strip()[:200]!r}")
        # Silence alone does not prove it declined: a hook that tried to probe
        # a directory with no git in it is also silent, and has meanwhile
        # written a marker for somebody's home directory.
        store = os.path.join(look.config, "cc-repo-harness", "first-look.json")
        if os.path.exists(store):
            with open(store, encoding="utf-8") as fh:
                if plain in fh.read():
                    look.failures.append(f"a marker was recorded for {plain}, "
                                         f"which is not a repository")
    finally:
        shutil.rmtree(plain, ignore_errors=True)


def case_malformed_payload_is_not_an_error(look):
    p = sh([sys.executable, LOOK], cwd=look.repo, env=look.env,
           stdin="not json{{")
    if p.returncode != 0:
        look.failures.append(
            f"an unfamiliar payload must not become an error at the top of "
            f"every session; exit {p.returncode}\n"
            f"    {(p.stdout + p.stderr).strip()[:300]}")


def case_unmeasurable_repo_is_marked_anyway(look):
    """A repository the probe cannot read must not be retried forever.

    A worktree whose main repository was deleted still has a `.git`, so this
    hook still fires in it and the probe still fails. Nagging every session
    about it is the exact noise the once-only rule exists to prevent, and it
    would fall on the person with the least to gain from the notice.
    """
    shutil.rmtree(os.path.join(look.repo, ".git"))
    with open(os.path.join(look.repo, ".git"), "w", encoding="utf-8") as fh:
        fh.write("gitdir: /nonexistent/wherever-it-used-to-be\n")

    rc, out = look.start()
    if rc != 0:
        look.failures.append(f"a probe failure must not become an error at the "
                             f"top of a session; exit {rc}\n    {out[:300]}")
    # Not "the second run is silent" -- an unmeasurable repository is silent
    # either way, so that assertion holds just as well when nothing was
    # recorded. The marker is the only thing that separates them.
    st = look.manage("--status")
    if "not seen yet" in st.stdout:
        look.failures.append(
            "a repository that could not be measured was not marked, so this "
            "runs the probe again at the top of every session forever")


# (label, case, how to build the repository it runs against)
LOOK_CASES = [
    ("the notice executes nothing from the repository",
     case_executes_nothing, make_loud_repo),
    ("it speaks once and then stops", case_speaks_once, make_repo),
    ("--forget makes it speak again", case_forget_speaks_again, make_repo),
    ("a subdirectory is the same repository",
     case_marker_covers_subdirectories, make_repo),
    ("a compaction gets silence", case_compaction_is_silent, make_repo),
    ("outside a repository, silence", case_outside_a_repo_is_silent, make_repo),
    ("a malformed payload is not an error",
     case_malformed_payload_is_not_an_error, make_repo),
    ("a repo it cannot measure is still marked",
     case_unmeasurable_repo_is_marked_anyway, make_repo),
]


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

    for label, fn, factory in LOOK_CASES:
        repo = factory()
        config = tempfile.mkdtemp(prefix="look-store-")
        look = Look(repo, config)
        try:
            fn(look)
        except Exception as exc:  # a raising case is a failing case
            look.failures.append(f"{label}\n    raised {exc!r}")
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(config, ignore_errors=True)
        if look.failures:
            failures.extend(f"{label}: {f}" for f in look.failures)
        elif a.verbose:
            print(f"  ok  {label}")

    if failures:
        print(f"{len(failures)} plugin-hook assertion(s) failed:\n",
              file=sys.stderr)
        for f in failures:
            print(f"  {f}\n", file=sys.stderr)
        return 1
    if a.verbose:
        print(f"{len(CASES) + len(LOOK_CASES)} cases: nothing runs until it is "
              f"trusted, editing it stops it running, and the first look reads "
              f"without executing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
