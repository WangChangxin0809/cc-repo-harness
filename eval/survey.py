#!/usr/bin/env python3
"""Read every corpus repository and tally what is missing, across all of them.

    python3 eval/survey.py [--only <substring>] [--out <path>]

    0 = every repository was surveyed    1 = one could not be read
    2 = cannot judge (no corpus, or it has not been fetched)

Read-only. It writes nothing into the repositories, which is the difference
between this and `run_corpus.py` -- that one scaffolds in place, and left every
tree in the corpus carrying our own `ci.sh` until `fetch.py` learned to notice.

## Why a tally rather than twenty reports

Twenty reports is twenty judgements about somebody else's repository, and every
one of them is arguable. A tally is a different object: *seventeen of twenty
lack X* is a claim about the population this plugin is for, and it is the only
kind of claim that can tell a real gap from a preference. If a gate fires on two
repositories it may be finding something; if it fires on nineteen it is
describing a convention nobody outside this repository shares.

That cuts both ways, which is the point. A moment that is empty in nineteen of
twenty is either the strongest thing this plugin could offer, or evidence that
nobody wants it. The tally cannot tell those apart. What it can do is stop us
arguing about which repository is representative.

## What is counted

Two sources, deliberately not merged. `probe_repo.py` is ours, and it answers
"which of the seven moments is empty" -- the question the plugin is organised
around. The direct inspection below answers "what does an ordinary maintainer
have", and it is written to be boring on purpose: a README, a licence, tests,
CI, a changelog. Where the two disagree, the disagreement is the finding, and
`probe_repo.py` is the more likely of the two to be wrong -- it already reports
`gates / guards 0 / 0` for this repository, whose gates are its whole point.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.join(HERE, ".work")
PROBE = os.path.join(ROOT, "shared", "scripts", "probe_repo.py")

# Ordinary things an ordinary repository has. Nothing here is this plugin's
# invention; a maintainer who never heard of it would recognise every row.
# (label, test) where test takes the repository path.
def _any_file(*names):
    return lambda p: any(os.path.exists(os.path.join(p, n)) for n in names)


def _any_dir(*names):
    return lambda p: any(os.path.isdir(os.path.join(p, n)) for n in names)


def _has_tests(p):
    for root, dirs, files in os.walk(p):
        dirs[:] = [d for d in dirs
                   if d not in (".git", "node_modules", ".venv", "venv",
                                "dist", "build", "vendor", "target")]
        if os.path.basename(root).lower() in ("test", "tests", "__tests__", "spec"):
            return True
        if any(re.search(r"(^test_|_test\.|\.test\.|\.spec\.|_spec\.)", f)
               for f in files):
            return True
    return False


def _ci(p):
    d = os.path.join(p, ".github", "workflows")
    return os.path.isdir(d) and any(f.endswith((".yml", ".yaml"))
                                    for f in os.listdir(d))


ORDINARY = [
    ("README",        _any_file("README.md", "README.rst", "README", "README.txt")),
    ("LICENSE",       _any_file("LICENSE", "LICENSE.md", "LICENCE", "COPYING")),
    ("CLAUDE.md",     _any_file("CLAUDE.md", os.path.join(".claude", "CLAUDE.md"))),
    ("CONTRIBUTING",  _any_file("CONTRIBUTING.md", "CONTRIBUTING")),
    ("tests",         _has_tests),
    ("CI",            _ci),
    ("docs/",         _any_dir("docs", "doc")),
    ("CHANGELOG",     _any_file("CHANGELOG.md", "CHANGELOG", "HISTORY.md")),
    ("SECURITY",      _any_file("SECURITY.md")),
    ("editorconfig",  _any_file(".editorconfig")),
    ("lockfile",      _any_file("package-lock.json", "yarn.lock", "pnpm-lock.yaml",
                                "poetry.lock", "uv.lock", "Cargo.lock", "go.sum",
                                "requirements.txt")),
]

MOMENTS = {
    1: "every turn · CLAUDE.md",
    2: "session start · SessionStart hook",
    3: "each prompt · UserPromptSubmit hook",
    4: "reading a subtree · nested CLAUDE.md",
    5: "before an action · PreToolUse deny",
    6: "after an action · PostToolUse hook",
    7: "on request · skills",
}


def probe(path):
    """probe_repo.py's own reading, or None if it could not produce one."""
    try:
        out = subprocess.run([sys.executable, PROBE, "--root", path, "--json"],
                             capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except ValueError:
        return None


def filled_moments(reading):
    """The moment numbers probe_repo considers filled.

    Its keys are `1_always`, `5_before_action` and so on, and its values are
    whatever suited each moment -- a list of files, a count, or a dict of two
    counts. So "filled" is `any truthy leaf`, and the number is the key's
    prefix. Written tolerantly because this is our own tool and its JSON shape
    is not a contract anybody wrote down; a survey that dies on a key rename is
    a survey nobody runs twice."""
    if not isinstance(reading, dict):
        return set()
    moments = reading.get("moments")
    if not isinstance(moments, dict):
        return set()
    filled = set()
    for key, val in moments.items():
        head = key.split("_", 1)[0]
        if not head.isdigit():
            continue
        if isinstance(val, dict):
            present = any(val.values())
        else:
            present = bool(val)
        if present:
            filled.add(int(head))
    return filled


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default=os.path.join(HERE, "results", "survey.json"))
    a = ap.parse_args()

    manifest = os.path.join(HERE, "corpus.json")
    if not os.path.exists(manifest):
        print("cannot judge: no eval/corpus.json", file=sys.stderr)
        return 2
    with open(manifest, encoding="utf-8") as fh:
        repos = [r["full_name"] for r in json.load(fh)["repos"]]
    if a.only:
        repos = [r for r in repos if a.only in r]
    if not repos or not os.path.isdir(WORK):
        print("cannot judge: nothing to survey; run eval/fetch.py", file=sys.stderr)
        return 2

    rows, unread = [], []
    for name in repos:
        path = os.path.join(WORK, name.replace("/", "__"))
        if not os.path.isdir(path):
            unread.append((name, "not fetched"))
            continue
        has = {label: bool(test(path)) for label, test in ORDINARY}
        reading = probe(path)
        row = {"repo": name, "has": has,
               "tier": (reading or {}).get("tier"),
               "moments": sorted(filled_moments(reading)),
               "probe_read": reading is not None}
        if reading is None:
            unread.append((name, "probe_repo.py produced no reading"))
        rows.append(row)

    width = max(len(r["repo"]) for r in rows)
    labels = [label for label, _ in ORDINARY]

    print("What each repository already has\n")
    header = "  ".join(f"{label[:6]:>6}" for label in labels)
    print(f"{'repo':<{width}}  {header}  tier  moments")
    for r in rows:
        cells = "  ".join(f"{('yes' if r['has'][label] else '-'):>6}"
                          for label in labels)
        print(f"{r['repo']:<{width}}  {cells}  {str(r['tier'] or '-'):>4}  "
              f"{','.join(str(m) for m in r['moments']) or '-'}")

    n = len(rows)
    print(f"\nMissing, across {n} repositories -- most-missing first\n")
    absent = [(label, sum(1 for r in rows if not r["has"][label]))
              for label in labels]
    for label, count in sorted(absent, key=lambda x: -x[1]):
        if count:
            bar = "#" * count
            print(f"  {label:<14} {count:>2}/{n}  {bar}")

    print(f"\nEmpty moments, across {n} repositories\n")
    empties = collections.Counter()
    for r in rows:
        for m in range(1, 8):
            if m not in r["moments"]:
                empties[m] += 1
    for m in range(1, 8):
        count = empties[m]
        print(f"  {m} · {MOMENTS[m]:<38} {count:>2}/{n}  {'#' * count}")

    # The reading that matters most is where the two sources disagree, because
    # one of them is wrong and it is usually ours.
    both = [(r["repo"], r["has"]["CLAUDE.md"], 1 in r["moments"]) for r in rows]
    clash = [(name, f, m) for name, f, m in both if f != m]
    if clash:
        print("\nprobe_repo.py disagrees with the file system:")
        for name, f, m in clash:
            print(f"  {name}: CLAUDE.md on disk={f}, moment 1 filled={m}")

    if unread:
        print(f"\n{len(unread)} could not be read fully:")
        for name, why in unread:
            print(f"  {name}: {why}")

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"repos": n, "rows": rows,
                   "missing": dict(absent),
                   "empty_moments": {str(k): v for k, v in empties.items()}},
                  fh, indent=2)
    print(f"\n-> {os.path.relpath(a.out, os.getcwd())}")
    return 1 if unread else 0


if __name__ == "__main__":
    sys.exit(main())
