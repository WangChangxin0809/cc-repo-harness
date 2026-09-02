#!/usr/bin/env python3
"""Decide whether the version at HEAD needs a tag, and refuse the wrong one.

    python3 .github/scripts/release_tag.py            # prints key=value lines
    python3 .github/scripts/release_tag.py --self-test [--verbose]

    0 = decided (see `action=`)    1 = the version already has a tag elsewhere
    2 = cannot judge (not a git repository, unreadable plugin.json)

Output, one per line, in the shape `$GITHUB_OUTPUT` takes:

    version=1.1.0
    action=create | exists

## Why a script and not six lines of shell in the workflow

The same reason every step in ci.yml is one line: judgement written into a
workflow cannot be run before pushing and cannot be tested. This one has three
answers and the third is the one that matters -- a tag that already exists at
a *different* commit means a version was reused, and the only safe thing is to
stop and say so. `gh release create` would either fail obscurely or, worse,
attach release notes to the old commit.

## Idempotent on purpose

The workflow runs on every push to main that touches plugin.json. A merge that
touches the file without changing the version, or a rerun, finds the tag at
HEAD's version already in place and does nothing. That is `exists`, and it is
a pass.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

MANIFEST = ".claude-plugin/plugin.json"


def sh(args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          timeout=60)


def decide(root):
    """Returns (exit_code, version, action, message)."""
    if sh(["git", "rev-parse", "--git-dir"], cwd=root).returncode != 0:
        return 2, "", "", "cannot judge: not a git repository"
    try:
        with open(os.path.join(root, MANIFEST), encoding="utf-8") as fh:
            version = str(json.load(fh).get("version") or "").strip()
    except (OSError, ValueError) as exc:
        return 2, "", "", f"cannot judge: {MANIFEST} unreadable ({exc})"
    if not version:
        return 2, "", "", f"cannot judge: {MANIFEST} has no version"
    tag = f"v{version}"
    head = sh(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
    at = sh(["git", "rev-parse", "-q", "--verify", tag + "^{commit}"],
            cwd=root)
    if at.returncode != 0:
        return 0, version, "create", f"{tag} does not exist; create it at HEAD"
    if at.stdout.strip() == head:
        return 0, version, "exists", f"{tag} already points at HEAD"
    return 1, version, "", (f"{tag} already exists at {at.stdout.strip()[:10]}"
                            f", not at HEAD {head[:10]}: the version in "
                            f"{MANIFEST} was reused. Raise it.")


# --------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------

def _repo(version):
    tmp = tempfile.mkdtemp(prefix="release-tag-")
    sh(["git", "init", "-q", "-b", "main"], cwd=tmp)
    sh(["git", "config", "user.email", "t@example.invalid"], cwd=tmp)
    sh(["git", "config", "user.name", "t"], cwd=tmp)
    os.makedirs(os.path.join(tmp, ".claude-plugin"))
    with open(os.path.join(tmp, MANIFEST), "w", encoding="utf-8") as fh:
        json.dump({"name": "demo", "version": version}, fh)
    sh(["git", "add", "-A"], cwd=tmp)
    sh(["git", "commit", "-q", "-m", "one"], cwd=tmp)
    return tmp


def self_test(verbose):
    cases = []

    def case(why, build, want_code, want_action):
        tmp = build()
        try:
            code, _v, action, msg = decide(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        ok = code == want_code and action == want_action
        cases.append((ok, why, f"got {code}/{action or '-'}: {msg}"))

    case("no tag yet is `create`", lambda: _repo("1.0.0"), 0, "create")

    def tagged_here():
        t = _repo("1.0.0")
        sh(["git", "tag", "v1.0.0"], cwd=t)
        return t
    case("a tag already at HEAD is `exists`", tagged_here, 0, "exists")

    def tagged_elsewhere():
        t = _repo("1.0.0")
        sh(["git", "tag", "v1.0.0"], cwd=t)
        with open(os.path.join(t, "x"), "w") as fh:
            fh.write("x")
        sh(["git", "add", "-A"], cwd=t)
        sh(["git", "commit", "-q", "-m", "two"], cwd=t)
        return t
    case("a reused version is refused", tagged_elsewhere, 1, "")

    def not_a_repo():
        t = tempfile.mkdtemp(prefix="release-tag-")
        os.makedirs(os.path.join(t, ".claude-plugin"))
        with open(os.path.join(t, MANIFEST), "w") as fh:
            json.dump({"version": "1.0.0"}, fh)
        return t
    case("outside git it cannot judge", not_a_repo, 2, "")

    failed = [c for c in cases if not c[0]]
    for ok, why, detail in cases:
        if verbose or not ok:
            print(f"  {'ok ' if ok else 'BAD'}  {why}" +
                  ("" if ok else f"\n        {detail}"))
    print(f"{len(cases)} cases: a reused version is refused, and a tag "
          f"already in place is not")
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test(a.verbose)
    code, version, action, msg = decide(os.path.abspath(a.root))
    if code == 0:
        print(f"version={version}")
        print(f"action={action}")
        print(msg, file=sys.stderr)
    else:
        print(f"::error::{msg}" if code == 1 else msg, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
