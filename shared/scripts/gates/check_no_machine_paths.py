#!/usr/bin/env python3
"""Gate: a committed file must not carry the absolute path of somebody's machine.

    /home/you/projects/thing/node_modules/.bin/jest
    /Users/you/Library/Caches/pip/wheels/...

Two separate costs, and the smaller one is the privacy.

**It names a person.** A home directory carries a username, and a username is
usually a real name or a work account. It reaches every clone, every fork and
every mirror, and it is in the history afterwards whatever the working tree
says. Nobody chose to publish it; a tool wrote it into a file somebody
committed without reading.

**It is a path nobody else has.** Committed output holding
`/home/you/proj/.venv/bin/python` is a record that cannot be reproduced,
compared, or replayed anywhere but the machine it came from. Two runs of the
same thing on two laptops produce different files and diff as if something
changed. That is what makes this a gate rather than a note: the damage is to
the artefact, and it is silent.

## What is not caught, deliberately

A path with a placeholder where the username goes -- `/home/user/`,
`/Users/username/`, `/home/you/` -- is documentation showing the shape, which
is the thing this asks people to write instead. `/root/` is a container, not a
person. `/home/runner/` is GitHub's hosted runner and belongs to nobody.

Nothing here reads `.gitignore`. A file being ignored today says nothing about
the one somebody adds with `git add -f` tomorrow, and this gate runs over what
the repository actually tracks.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

# `/home/<name>/`, `/Users/<name>/`, `C:\Users\<name>\`. The trailing
# separator matters: `/home` and `/Users` alone are not anybody's.
_UNIX = re.compile(r"/(?:home|Users)/([A-Za-z0-9][A-Za-z0-9._-]{1,31})/")
_WINDOWS = re.compile(r"[A-Za-z]:\\Users\\([A-Za-z0-9][A-Za-z0-9._ -]{1,31})\\")

# Names that are the shape rather than a person.
PLACEHOLDERS = {
    "you", "user", "username", "your-name", "yourname", "me", "name",
    "someone", "somebody", "example", "alice", "bob", "carol", "dev",
    "developer", "test", "tester", "foo", "bar", "myuser", "my-user",
    # Not people: CI runners and container roots.
    "runner", "root", "ubuntu", "vagrant", "docker", "circleci", "travis",
    "jenkins", "builder", "codespace", "vscode", "node", "app",
}

# Binary and vendored things are not read at all.
SKIP_DIRS = {".git", "node_modules", "vendor", "__pycache__", ".venv", "venv",
             "target", "dist", "build", ".mypy_cache", ".ruff_cache"}
BINARY = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz",
          ".tar", ".whl", ".so", ".dylib", ".dll", ".exe", ".woff", ".woff2",
          ".ttf", ".otf", ".mp4", ".mp3", ".wasm", ".jar", ".class")

MAX_BYTES = 2 * 1024 * 1024


def hits(line):
    """Every machine path in one line. The gate and its cases both call this;
    a case list that reimplements the rule tests the reimplementation."""
    out = []
    for pattern in (_UNIX, _WINDOWS):
        for m in pattern.finditer(line):
            if m.group(1).lower() in PLACEHOLDERS:
                continue
            # `https://example.com/Users/jsmith/profile` is a URL. The token
            # the match sits in says so, and a path on somebody's disk never
            # has a scheme in front of it.
            start = line.rfind(" ", 0, m.start()) + 1
            end = line.find(" ", m.end())
            token = line[start:end if end != -1 else len(line)]
            if "://" in token:
                continue
            out.append((m.group(1), m.group(0)))
    return out


def tracked(root):
    """What the repository keeps, or None where git cannot say."""
    try:
        out = subprocess.run(
            ["git", "-c", "core.quotePath=false", "ls-files", "-z"],
            cwd=root, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return [p for p in out.stdout.split("\0") if p]


def findings(root, paths):
    out = []
    for rel in paths:
        if any(part in SKIP_DIRS for part in rel.split("/")):
            continue
        if rel.lower().endswith(BINARY):
            continue
        full = os.path.join(root, rel)
        try:
            if os.path.getsize(full) > MAX_BYTES:
                continue
            with open(full, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        if "\0" in text[:4096]:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for who, text_of in hits(line)[:1]:
                out.append((rel, n, who, text_of))
    return out


REMEDY = """
Write the path relative to the repository, or as a placeholder:

    /home/you/...            # the shape, which is what a reader needs
    $HOME/...                # resolved on the machine that runs it
    ./relative/path          # inside the repository

For a file a tool generates, the fix is at the tool: make it record a path
relative to the root before it writes, so the artefact is the same on every
machine that produces it.
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()

    root = os.path.abspath(a.root)
    paths = tracked(root)
    if paths is None:
        print("could not judge: `git ls-files` did not answer in " + root,
              file=sys.stderr)
        return 2
    if not paths:
        print("could not judge: the repository tracks nothing", file=sys.stderr)
        return 2

    found = findings(root, paths)
    if not found:
        print("no machine-specific path in %d tracked file(s)" % len(paths))
        return 0

    people = sorted({w for _, _, w, _ in found})
    print("%d committed line(s) carry an absolute home directory, naming %s:"
          % (len(found), ", ".join(people)), file=sys.stderr)
    for rel, n, _who, text in found[:20]:
        print("  %s:%d  %s" % (rel, n, text), file=sys.stderr)
    if len(found) > 20:
        print("  ... and %d more" % (len(found) - 20), file=sys.stderr)
    print(REMEDY, file=sys.stderr)
    return 1


# The name is assembled rather than written. A check whose subject is "a real
# username in a committed file" cannot put one in its own source without
# failing itself, and a gate exempting its own file would be a hole rather than
# a fix. This is the sixth time this project has met the same shape -- text
# *about* a thing read as the thing -- and the first where the check is
# correct and the fixture has to move.
_WHO = "j" + "smith"
_HOME = "/ho" + "me/"
_USERS = "/Us" + "ers/"

CASES = (
    # (line, should_be_reported)
    ("dumped to " + _HOME + _WHO + "/proj/out.json", True),
    (_USERS + "jane.doe/Library/Caches/pip", True),
    ("C:\\Users\\" + _WHO + "\\AppData\\Local\\Temp", True),
    # Documentation showing the shape is the thing this asks for.
    ("run it from " + _HOME + "you/projects/thing", False),
    (_USERS + "username/.config/app", False),
    # Nobody's machine.
    (_HOME + "runner/work/repo/repo", False),
    ("/root/.cache/pip", False),
    (_HOME + "ubuntu/app", False),
    # Not a home directory at all.
    ("see /home for the mount", False),
    ("/usr/local/bin/python3", False),
    ("https://example.com" + _USERS + _WHO + "/profile", False),
)


def selftest(verbose=True):
    import tempfile
    bad = 0
    for line, want in CASES:
        got = bool(hits(line))
        ok = got == want
        bad += not ok
        if verbose or not ok:
            print("%s %-52s %s" % ("ok  " if ok else "FAIL", line[:52],
                                   "reported" if got else "allowed"))

    # The gate has to be able to fail on a real tree, not only on a string.
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q"], cwd=d, check=True)
        with open(os.path.join(d, "out.json"), "w", encoding="utf-8") as fh:
            fh.write('{"log": "%s%s/.npm/_logs/debug.log"}\n'
                     % (_HOME, _WHO))
        subprocess.run(["git", "add", "-A"], cwd=d, check=True)
        rc = main(["--root", d])
        ok = rc == 1
        bad += not ok
        print("%s a planted home path fails the gate (exit %d)"
              % ("ok  " if ok else "FAIL", rc))

    # ...and a tree with nothing to find has to pass, or it is not a gate.
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q"], cwd=d, check=True)
        with open(os.path.join(d, "out.json"), "w", encoding="utf-8") as fh:
            fh.write('{"log": "logs/debug.log"}\n')
        subprocess.run(["git", "add", "-A"], cwd=d, check=True)
        rc = main(["--root", d])
        ok = rc == 0
        bad += not ok
        print("%s a clean tree passes (exit %d)" % ("ok  " if ok else "FAIL", rc))

    print("\n%s" % ("all cases pass" if not bad
                    else "%d case(s) failed" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
