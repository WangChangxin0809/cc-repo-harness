#!/usr/bin/env python3
"""Defects this repository already had, taken from its own history.

    python3 assess/history.py [--root .] [--json]

Exit codes:
    0 = counted    2 = cannot judge (not a git repository, or no history)

## Why the repository's history and not a list of ours

The assessment asks *when* a defect is first caught. That needs defects, and
inventing them makes the measurement a mirror: we would invent the ones our own
guards already stop, and every repository would score well on exactly the
things we shipped. A commit that fixed something is a bug that really happened,
chosen by somebody with no stake in this.

## The tiers

    fix+test     a fix-shaped commit touching source AND test. Remove the
                 source half and the repository's own tests should go red.
    revert       an explicit revert -- the cleanest provenance there is: the
                 repository said this was wrong, in its own words.
    fix-no-test  a fix-shaped commit touching source and no test at all. Not a
                 weaker instance, a different measurement: a real bug whose fix
                 nothing verifies.

A shallow clone has no history and therefore no defects. That is a fact about
the clone, so it returns 2 rather than reporting zero.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

SOURCE_EXT = {
    "py", "js", "ts", "tsx", "jsx", "go", "rs", "java", "kt", "rb", "php",
    "c", "h", "cc", "cpp", "hpp", "cs", "swift", "m", "mm", "scala", "ex",
    "exs", "gd", "lua", "sh", "bash", "sql", "vue", "svelte",
}

# Anchored at a path segment or a filename affix. A bare `in` test matches
# `src/contest/` and `latest.json`, and both are real paths.
TEST_PATH = re.compile(
    r"(^|/)(tests?|spec|specs|__tests__|testing|e2e)(/|$)"
    r"|(^|/)conftest\.py$"
    r"|(^|[._-])(test|spec)s?\.[a-z]+$"
    r"|(^|/)test_[^/]+$"
    r"|[._-](test|spec)\.[a-z]+$"
    # `selftest.py` is a real convention -- GCC and CPython both use it, and so
    # does this repository, which reported that it carried no test file at all.
    r"|(^|/)[a-z0-9_]*selftests?\.[a-z]+$",
    re.I,
)

# Conventional commits first, then the words people use when they are not using
# them. `fixup!` is excluded: a rebase instruction is not a claim that anything
# was broken.
FIX_SUBJECT = re.compile(
    r"^\s*(fix|bugfix|hotfix|patch)\s*(\([^)]*\))?\s*!?:"
    r"|\b(bug\s?fix|hotfix|regression|broken|crash(es|ed|ing)?"
    r"|off.by.one|race condition|memory leak|null pointer)\b"
    r"|\bfix(e[sd])?\b(?!up)",
    re.I,
)
REVERT_SUBJECT = re.compile(
    r"^\s*revert\b|\bthis reverts commit\b"
    r"|回滚|回退|还原|撤销|撤回",
    re.I,
)

# Commit subjects are not always in English, and a defect miner that only reads
# English reports a repository with years of history as having nothing to
# replay -- which is indistinguishable, on the page, from a repository that
# genuinely repairs nothing. Measured against a repository whose 53 subjects
# are almost all Chinese: the English matcher found 1 repair, this finds 6.
#
# The one-character form is deliberately narrow. 修改 is "modify" rather than
# "repair", so it is excluded; the rest are unambiguous.
FIX_SUBJECT_CJK = re.compile(r"修(?!改)|订正|解决|改回")

# Above this a revert is a refactor with a bug somewhere inside it, and nothing
# that goes red afterwards can be attributed to one change.
SMALL = 3


# --- which changes owe a test -------------------------------------------
#
# Not every commit that touches source owes one. Renaming a symbol across
# forty files, reformatting, bumping a dependency and moving a directory are
# all changes to source that no new test would make safer, and counting them
# puts a repository's tidiest weeks against it.
#
# What owes a test is a change that adds behaviour or repairs it -- `feat` and
# `fix`, plus `perf`, which is a behaviour claim about speed and is exactly the
# kind that rots silently.
OWES_TEST = ("feat", "fix", "bugfix", "hotfix", "perf")
OWES_NOTHING = ("docs", "chore", "style", "refactor", "test", "tests",
                "build", "ci", "revert", "deps", "release")

_CONVENTIONAL = re.compile(r"^\s*([a-z]+)\s*(?:\([^)]*\))?\s*!?:", re.I)


def owes_a_test(subject):
    """True, False, or None when the subject does not say.

    None is the load-bearing value and the reason this returns three things
    rather than two. A repository that does not type its commit subjects
    cannot be narrowed, and guessing from free-form English would shrink the
    denominator silently -- every repository would score better and none of
    them would have changed. So an untyped subject counts, and the row says
    the denominator was the wide one. Adopting conventional commits sharpens
    your own measurement; not adopting them costs you the benefit of the
    doubt, never a hidden pass."""
    m = _CONVENTIONAL.match(subject or "")
    if not m:
        return None
    kind = m.group(1).lower()
    if kind in OWES_TEST:
        return True
    if kind in OWES_NOTHING:
        return False
    return None


def sh(args, cwd, timeout=120):
    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                             timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def is_source(path):
    return ("." in path
            and path.rsplit(".", 1)[-1].lower() in SOURCE_EXT
            and not TEST_PATH.search(path))


def commits(root):
    """Every non-merge commit as (sha, subject, [paths]), newest first."""
    raw = sh(["git", "-c", "core.quotePath=false", "log", "--no-merges",
              "--name-only", "--format=%x01%H%x00%s"], root)
    if raw is None:
        return None
    out = []
    for rec in raw.split("\x01")[1:]:
        head, _, rest = rec.partition("\n")
        sha, _, subject = head.partition("\x00")
        out.append((sha, subject,
                    [p for p in rest.split("\n") if p.strip()]))
    return out


def mine(root):
    """Defect instances available here, or None if the history cannot be read."""
    log = commits(root)
    if log is None:
        return None
    r = {"commits": len(log), "shallow": os.path.exists(
            os.path.join(root, ".git", "shallow")),
         "fix_test": [], "revert": [], "fix_no_test": [],
         "has_test_files": False}
    for sha, subject, paths in log:
        src = [p for p in paths if is_source(p)]
        tst = [p for p in paths if TEST_PATH.search(p)]
        if tst:
            r["has_test_files"] = True
        if not src:
            continue                    # docs or config only: not a code defect
        row = {"sha": sha, "subject": subject[:100], "source": src,
               "tests": tst, "small": len(src) <= SMALL}
        if REVERT_SUBJECT.search(subject):
            r["revert"].append(row)
        repairs = bool(FIX_SUBJECT.search(subject)
                       or FIX_SUBJECT_CJK.search(subject))
        if tst:
            if repairs:
                r["fix_test"].append(row)
        elif repairs:
            r["fix_no_test"].append(row)
    return r


def candidates(found, limit=0):
    """The instances worth replaying, best provenance first."""
    rows = ([r for r in found["revert"] if r["small"]]
            + [r for r in found["fix_test"] if r["small"]])
    return rows[:limit] if limit else rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    found = mine(a.root)
    if found is None:
        print("cannot judge: not a git repository, or git is unavailable",
              file=sys.stderr)
        return 2
    if found["shallow"]:
        print("cannot judge: this is a shallow clone, so there is no history "
              "to mine — `git fetch --unshallow` first", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(found, indent=2, ensure_ascii=False))
        return 0

    n = len(candidates(found))
    print(f"\n{found['commits']} commits\n")
    print(f"  fix + test      {len(found['fix_test']):>4}  "
          f"({sum(1 for r in found['fix_test'] if r['small'])} small enough to "
          f"replay)")
    print(f"  revert          {len(found['revert']):>4}  "
          f"({sum(1 for r in found['revert'] if r['small'])} small)")
    print(f"  fix, no test    {len(found['fix_no_test']):>4}  "
          f"— real bugs nothing verifies")
    print(f"\n  {n} replayable instance(s).")
    if not found["has_test_files"]:
        print("  This repository carries no test file at all, so no defect "
              "here can be caught by a suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
