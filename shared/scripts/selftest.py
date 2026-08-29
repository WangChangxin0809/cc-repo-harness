#!/usr/bin/env python3
"""Prove the plugin's own acceptance criterion, the one stated in prose.

    python3 shared/scripts/selftest.py [--verbose] [--case NAME]

    0 = every case held    1 = a case failed    2 = cannot run

The README's claim is literal: install it, run the bootstrap, **uninstall the
plugin**, hand a fresh agent a real task, and the repository must still teach it
the conventions. Every other selftest here runs with the plugin sitting on disk,
so none of them can tell a repository that stands on its own from one quietly
reaching back into the checkout it was scaffolded from. That difference is
invisible to the person who ran the scaffolder and total for the teammate who
clones afterwards.

## Why this is a script and not thirty lines of CI shell

It used to be thirty lines of CI shell. That put the judgement in the one place
this project tells everyone else never to put it: a hook wiring, where it cannot
be run before pushing, cannot be tested, and dies with the CI provider. The rule
is the same rule as `moments.md` states for `.claude/settings.json` -- the
wiring is one line, the judgement lives in `scripts/`.

Which also means it runs on a laptop, which is where an acceptance test that
takes ninety seconds needs to run if anyone is going to run it before pushing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(os.path.dirname(HERE))

BLOCKING = json.dumps(
    {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}})
BENIGN = json.dumps(
    {"tool_name": "Bash",
     "tool_input": {"command": "git push origin feature/x"}})


def sh(args, cwd=None, stdin=None):
    return subprocess.run(args, cwd=cwd, input=stdin, text=True,
                          capture_output=True, timeout=600)


def fresh_repo():
    """A minimal but real git repository. Not empty: a repo with no source at
    all probes as something no user has, and the scaffolder's decisions are
    driven by what it finds."""
    tmp = tempfile.mkdtemp(prefix="harness-acceptance-")
    os.makedirs(os.path.join(tmp, "src"))
    with open(os.path.join(tmp, "src", "a.py"), "w", encoding="utf-8") as fh:
        fh.write("def a():\n    return 1\n")
    sh(["git", "init", "-q", "."], cwd=tmp)
    sh(["git", "add", "-A"], cwd=tmp)
    sh(["git", "-c", "user.email=selftest@example.com", "-c",
        "user.name=selftest", "commit", "-qm", "init"], cwd=tmp)
    return tmp


def fill_placeholders(root):
    """Do what an author does in an afternoon, in one pass.

    Crude on purpose. The case is not "did the prose come out well", which no
    script can judge; it is "does the red list terminate" -- a scaffold whose
    gates stay red after every placeholder is gone is a scaffold that can never
    be finished, and that is detectable.
    """
    for dirpath, _dirs, names in os.walk(root):
        if ".git" in dirpath.split(os.sep):
            continue
        for name in names:
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(re.sub(r"<[^<>\n]{2,}>", "written by a human", body))
    with open(os.path.join(root, "LICENSE"), "w", encoding="utf-8") as fh:
        fh.write("MIT\n")


def scaffold(root, tier, from_dir=PLUGIN, dry=False):
    return sh([sys.executable,
               os.path.join(from_dir, "shared", "scripts", "scaffold.py"),
               "--root", root, "--tier", tier] + (["--dry-run"] if dry else []))


def ci(root, lane="--fast"):
    return sh(["./ci.sh", lane], cwd=root)


# ---------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------

def case_scaffold_reaches_green(tier):
    """A fresh scaffold is red for the placeholders, and only for those.

    Both halves are load-bearing. Red-on-fresh is what makes the red list a
    to-do list rather than an insult; green-once-filled is the claim that the
    list terminates. A release shipped in which it did not, and every gate here
    passed on the scaffolder's own output.
    """
    def run():
        repo = fresh_repo()
        try:
            out = scaffold(repo, tier)
            if out.returncode != 0:
                return f"scaffold --tier {tier} exited {out.returncode}: " \
                       f"{out.stderr.strip()[:300]}"

            first = ci(repo)
            if first.returncode == 0:
                return "a fresh scaffold was green; the placeholders in it " \
                       "should have made it red"
            body = first.stdout + first.stderr
            if "unfilled placeholder" not in body:
                return ("red, but not for the placeholders it is supposed to "
                        f"name: {body.strip()[:300]}")

            fill_placeholders(repo)
            second = ci(repo)
            if second.returncode != 0:
                return (f"still not green with every placeholder filled "
                        f"(exit {second.returncode}): "
                        f"{(second.stdout + second.stderr).strip()[:400]}")
            return None
        finally:
            shutil.rmtree(repo, ignore_errors=True)
    return run


def case_tier_a_ships_working_guards():
    """Tier A has no ci.sh, so the case above cannot see it at all.

    It is also the tier most repositories will actually install, being the
    floor. Judge what it does ship: guards that pass their own selftest and a
    settings.json that wires them.
    """
    repo = fresh_repo()
    try:
        out = scaffold(repo, "A")
        if out.returncode != 0:
            return f"scaffold --tier A exited {out.returncode}"

        selftest = sh([sys.executable, "scripts/guards/selftest.py"], cwd=repo)
        if selftest.returncode != 0:
            return (f"the guards it shipped do not pass their own selftest "
                    f"(exit {selftest.returncode}): "
                    f"{(selftest.stdout + selftest.stderr).strip()[:300]}")

        settings = os.path.join(repo, ".claude", "settings.json")
        if not os.path.exists(settings):
            return "no .claude/settings.json, so nothing runs the guards"
        with open(settings, encoding="utf-8") as fh:
            wiring = fh.read()
        if "scripts/guards/dispatch.py" not in wiring:
            return ("settings.json does not wire scripts/guards/dispatch.py, "
                    "so the guards are files that never run")
        return None
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def case_dry_run_describes_the_run_that_happens():
    """`--dry-run` must name exactly the files the real run creates.

    It did not. The preview printed `NEW scripts/context/after_edit.py`
    unconditionally while the writer gated that copy on tier B, so a tier A
    `--dry-run` promised a file the actual run never wrote. Found by scaffolding
    this repository onto itself -- nothing here scaffolds a *tier A* repo and
    then looks at what landed, so both halves were individually plausible.

    A preview exists to be approved before the thing happens. One that
    describes a different run is worse than none, because none is not trusted.
    """
    for tier in ("A", "B"):
        repo = fresh_repo()
        try:
            preview = scaffold(repo, tier, dry=True)
            if preview.returncode != 0:
                return f"--dry-run --tier {tier} exited {preview.returncode}"
            # `  COPY           scripts/guards/  (6 files)` -- the path is the
            # second field, not the last one.
            promised = {
                line.split()[1].rstrip("/")
                for line in preview.stdout.splitlines()
                if line.strip().startswith(("NEW", "COPY", "DIR"))
            }
            if scaffold(repo, tier).returncode != 0:
                return f"scaffold --tier {tier} failed after its own dry run"

            for rel in sorted(promised):
                if not os.path.exists(os.path.join(repo, rel)):
                    return (f"tier {tier}: --dry-run promised {rel}, and the "
                            f"real run did not create it")
        finally:
            shutil.rmtree(repo, ignore_errors=True)
    return None


def case_personal_permission_grants_cannot_be_committed():
    """A scaffolded repository must never be able to commit settings.local.json.

    Claude Code writes that file by itself the moment someone grants a
    permission, and it holds grants rather than preferences. Committed, it does
    not merely leak one person's setup -- it *applies* to everyone who clones,
    so one approval silently becomes the whole team's.

    This was found by opening our own `.claude/`. It looked safe, and it was:
    the file was ignored by the developer's *global* gitignore, on one machine.
    The repository itself had no such line and neither did anything we
    scaffolded. That is the worst shape a defect can have -- invisible exactly
    to whoever would notice it, and present for everybody else.

    `core.excludesFile=/dev/null` is what makes this test mean anything; without
    it, the machine running the suite would pass on its own configuration."""
    for existing in (None, "node_modules/\n*.log\n"):
        repo = fresh_repo()
        try:
            sh(["git", "config", "core.excludesFile", os.devnull], repo)
            if existing is not None:
                with open(os.path.join(repo, ".gitignore"), "w",
                          encoding="utf-8") as fh:
                    fh.write(existing)
            if scaffold(repo, "B").returncode != 0:
                return "scaffold --tier B failed"

            local = os.path.join(repo, ".claude", "settings.local.json")
            os.makedirs(os.path.dirname(local), exist_ok=True)
            with open(local, "w", encoding="utf-8") as fh:
                fh.write('{"permissions": {"allow": ["Bash(curl evil.sh)"]}}\n')

            sh(["git", "add", "-A"], repo)
            staged = sh(["git", "diff", "--cached", "--name-only"], repo).stdout
            if "settings.local.json" in staged:
                return ("settings.local.json is staged for commit — one "
                        "person's permission grants would apply to everyone")

            # And the pre-existing content must survive: appending is the only
            # safe thing to do to a file a stranger's repository already owns.
            if existing:
                with open(os.path.join(repo, ".gitignore"), encoding="utf-8") as fh:
                    body = fh.read()
                for line in existing.strip().splitlines():
                    if line not in body:
                        return f".gitignore lost a pre-existing line: {line}"
        finally:
            shutil.rmtree(repo, ignore_errors=True)
    return None


def case_survives_the_plugin_being_deleted():
    """The acceptance criterion, mechanised.

    Scaffold from a *copy* of the plugin, delete the copy, and only then judge.
    Deleting it is what makes this different from every other case: a path baked
    into settings.json or into a copied script keeps working while the original
    checkout is still there, and breaks for the teammate who never had it.
    """
    staging = tempfile.mkdtemp(prefix="harness-plugin-copy-")
    copy = os.path.join(staging, "plugin")
    repo = fresh_repo()
    try:
        shutil.copytree(PLUGIN, copy,
                        ignore=shutil.ignore_patterns(".git", "__pycache__"))
        out = scaffold(repo, "C", from_dir=copy)
        if out.returncode != 0:
            return f"scaffold from the copy exited {out.returncode}"
        fill_placeholders(repo)

        # Nothing scaffolded may name the place it came from.
        for dirpath, dirs, names in os.walk(repo):
            dirs[:] = [d for d in dirs if d != ".git"]
            for name in names:
                path = os.path.join(dirpath, name)
                try:
                    with open(path, encoding="utf-8") as fh:
                        if copy in fh.read():
                            rel = os.path.relpath(path, repo)
                            return (f"{rel} refers back to the plugin checkout "
                                    f"it was scaffolded from")
                except (OSError, UnicodeDecodeError):
                    continue

        shutil.rmtree(copy, ignore_errors=True)

        result = ci(repo)
        if result.returncode != 0:
            return (f"./ci.sh --fast exits {result.returncode} once the plugin "
                    f"is gone: {(result.stdout + result.stderr).strip()[:400]}")

        # ci.sh proves the guards' selftest passes. It does not prove the
        # dispatcher answers a real payload, which is the thing that has to work
        # before every command anyone types.
        blocked = sh([sys.executable, "scripts/guards/dispatch.py"],
                     cwd=repo, stdin=BLOCKING)
        if blocked.returncode != 2:
            return (f"a push to a protected branch was not blocked "
                    f"(exit {blocked.returncode})")
        if not blocked.stderr.strip():
            return "blocked, but with no reason on stderr for the model to read"
        allowed = sh([sys.executable, "scripts/guards/dispatch.py"],
                     cwd=repo, stdin=BENIGN)
        if allowed.returncode != 0:
            return (f"a push to a feature branch was blocked "
                    f"(exit {allowed.returncode}); a guard that blocks "
                    f"everything gets switched off within a day")

        index = sh([sys.executable, "scripts/index/build.py", "--root", "."],
                   cwd=repo)
        if index.returncode != 0:
            return f"scripts/index/build.py exits {index.returncode}"
        return None
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(repo, ignore_errors=True)


CASES = [
    ("tier B scaffold reaches green from a clean worktree",
     case_scaffold_reaches_green("B")),
    ("tier C scaffold reaches green from a clean worktree",
     case_scaffold_reaches_green("C")),
    ("tier A ships guards that are wired and pass their own selftest",
     case_tier_a_ships_working_guards),
    ("--dry-run describes the run that actually happens",
     case_dry_run_describes_the_run_that_happens),
    ("personal permission grants cannot be committed",
     case_personal_permission_grants_cannot_be_committed),
    ("the repository survives the plugin being deleted",
     case_survives_the_plugin_being_deleted),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--case", help="substring of one case label, to run alone")
    a = ap.parse_args()

    if shutil.which("git") is None:
        print("cannot run: git not on PATH", file=sys.stderr)
        return 2
    if not os.path.exists(os.path.join(HERE, "scaffold.py")):
        print(f"cannot run: no scaffold.py beside {HERE}", file=sys.stderr)
        return 2

    selected = [(label, fn) for label, fn in CASES
                if not a.case or a.case in label]
    if not selected:
        print(f"cannot run: no case matching {a.case!r}", file=sys.stderr)
        return 2

    failures = []
    for label, fn in selected:
        try:
            problem = fn()
        except Exception as exc:
            problem = f"raised {type(exc).__name__}: {exc}"
        if problem:
            failures.append(f"{label}\n    {problem}")
        elif a.verbose:
            print(f"  ok  {label}")

    if failures:
        print(f"\n{len(failures)} of {len(selected)} acceptance case(s) "
              f"failed:\n", file=sys.stderr)
        for f in failures:
            print(f"  {f}\n", file=sys.stderr)
        return 1
    if a.verbose:
        print(f"{len(selected)} acceptance cases: the scaffold reaches green, "
              f"and the repository outlives the plugin")
    return 0


if __name__ == "__main__":
    sys.exit(main())
