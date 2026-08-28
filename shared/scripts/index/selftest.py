#!/usr/bin/env python3
"""Prove the graph says what it claims about a repository it did not choose.

    python3 scripts/index/selftest.py [--verbose]

    0 = every case held    1 = a case failed    2 = cannot run

The index had no selftest for its first release, and it is the one component
here where a defect is *invisible*: a gate that breaks turns red, a guard that
breaks fails open and gets caught by its selftest, but a graph that ranks the
wrong file returns a confident, plausible, wrong answer that nobody checks.
The defects below were all real, and none of them would have produced an error.

Each case builds a throwaway repository with a planted structure, builds the
graph, and asserts a property of the result -- not that it did not crash.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))


def sh(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def make_repo(tmp, files):
    for rel, body in files.items():
        path = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(path) or tmp, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
    sh(["git", "init", "-q"], tmp)
    sh(["git", "add", "-A"], tmp)
    return tmp


def build(tmp):
    out = sh([sys.executable, os.path.join(HERE, "build.py"),
              "--root", tmp, "--out", os.path.join(tmp, ".index", "graph.json")],
             tmp)
    if out.returncode != 0:
        return None, out.stderr
    with open(os.path.join(tmp, ".index", "graph.json"), encoding="utf-8") as fh:
        return json.load(fh), ""


def query(tmp, *args):
    return sh([sys.executable, os.path.join(HERE, "query.py"), "--root", tmp,
               "--graph", os.path.join(tmp, ".index", "graph.json"), *args], tmp)


def definers(g):
    out = defaultdict(list)
    for a, b, kind, _w in g["edges"]:
        if kind == "defines":
            out[g["nodes"][b]["name"]].append(a)
    return out


# --- cases -----------------------------------------------------------------
# Each returns None when it holds, or a string describing what was wrong.

SHARED_NAME = {
    "a/one.py": "def main():\n    return 1\n",
    "b/two.py": "def main():\n    return 2\n",
    "c/three.py": "def main():\n    return 3\n",
}


def case_no_symbol_hub(t):
    """A name defined in three files must be three nodes, not one hub.

    The defect: `sym:main` was a single node with a higher degree than any real
    file, and PageRank flowed through it. Nothing about that is observable from
    the outside -- the ranking is merely wrong."""
    g, err = build(make_repo(t, SHARED_NAME))
    if g is None:
        return f"build failed: {err.strip()[:200]}"
    d = definers(g)
    if len(d.get("main", [])) != 3:
        return f"expected 3 definitions of main, graph has {len(d.get('main', []))}"
    syms = [n for n, v in g["nodes"].items() if v["kind"] == "symbol"]
    if len(syms) != 3:
        return f"expected 3 symbol nodes, got {len(syms)}: {syms}"
    return None


# The caller sorts BEFORE the definer, deliberately. `git ls-files` is ordered,
# so a fixture where the definer comes first passes under the single-pass bug
# too and proves nothing. This is the direction that was broken.
FORWARD_REF = {
    "a_caller.py": "from z_defs import helper\n\ndef go():\n    return helper()\n",
    "z_defs.py": "def helper():\n    return 1\n",
}


def case_forward_reference(t):
    """A reference must resolve to a definition in a file scanned later.

    The defect: references were resolved in the same pass that collected
    definitions, so an edge existed only if the definer happened to sort first.
    `a_caller.py` referencing `z_defs.helper` produced no edge at all, and
    which edges existed depended on filenames."""
    g, err = build(make_repo(t, FORWARD_REF))
    if g is None:
        return f"build failed: {err.strip()[:200]}"
    want = ("file:a_caller.py", "sym:z_defs.py:helper")
    if not any((a, b) == want and kind in ("references", "calls")
               for a, b, kind, _w in g["edges"]):
        return "no edge from a_caller.py to helper defined in z_defs.py"
    return None


# `Governs: src/billing` carries NO trailing slash, deliberately. With one, the
# broken prefix implementation and the correct one agree, and the case is
# vacuous -- it was, until an injection showed it staying green.
GOVERNS = {
    "src/billing/pay.py": "def pay():\n    return 1\n",
    "src/billing_old/pay.py": "def pay_old():\n    return 1\n",
    "docs/billing.md": "# Billing\n\nGoverns: src/billing\n\nHow billing works.\n",
    "docs/gone.md": "# Gone\n\nGoverns: src/removed/\n\nNothing here.\n",
}


def case_governs_is_directory_aware(t):
    """`Governs: src/billing` must not also claim `src/billing_old/`.

    The defect: plain prefix matching. An over-broad claim is worse than a
    missing one -- it reads as though somebody documented that code."""
    g, err = build(make_repo(t, GOVERNS))
    if g is None:
        return f"build failed: {err.strip()[:200]}"
    governed = {b for a, b, kind, _w in g["edges"]
                if kind == "governs" and a == "doc:docs/billing.md"}
    if "file:src/billing/pay.py" not in governed:
        return "docs/billing.md does not govern the file it names"
    if "file:src/billing_old/pay.py" in governed:
        return "docs/billing.md over-matched into src/billing_old/"
    return None


def case_dangling_governs_is_reported(t):
    """A target that resolves to nothing is a finding, not a silent drop."""
    g, err = build(make_repo(t, GOVERNS))
    if g is None:
        return f"build failed: {err.strip()[:200]}"
    dangling = g["meta"]["blind"]["dangling_governs"]
    if not any("docs/gone.md" in x for x in dangling):
        return f"docs/gone.md -> src/removed/ not reported; got {dangling}"
    return None


def case_unmatched_seed_cannot_judge(t):
    """A seed matching nothing must exit 2, never degrade to a global ranking.

    A silent degrade returns the graph's global top-N, which is a real-looking
    answer to a question that was never asked."""
    build(make_repo(t, SHARED_NAME))
    r = query(t, "--seed", "nothing_by_this_name")
    if r.returncode != 2:
        return f"expected exit 2, got {r.returncode}: {r.stdout.strip()[:200]}"
    return None


def case_seed_by_symbol_name(t):
    """A bare symbol name must still resolve now that nodes are path-keyed."""
    build(make_repo(t, FORWARD_REF))
    r = query(t, "--seed", "helper", "--paths-only")
    if r.returncode != 0:
        return f"exit {r.returncode}: {r.stderr.strip()[:200]}"
    if "z_defs.py" not in r.stdout:
        return f"seeding on 'helper' did not surface its definer: {r.stdout!r}"
    return None


CASES = [
    ("symbol names are not merged into one hub", case_no_symbol_hub),
    ("a reference resolves to a later-scanned definition", case_forward_reference),
    ("Governs: is directory-aware", case_governs_is_directory_aware),
    ("an unresolvable Governs: target is reported", case_dangling_governs_is_reported),
    ("an unmatched seed cannot judge", case_unmatched_seed_cannot_judge),
    ("a bare symbol name still resolves as a seed", case_seed_by_symbol_name),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    if shutil.which("git") is None:
        print("cannot run: git not on PATH", file=sys.stderr)
        return 2

    failures = []
    for label, fn in CASES:
        tmp = tempfile.mkdtemp(prefix="index-selftest-")
        try:
            problem = fn(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if problem:
            failures.append(f"{label}\n    {problem}")
        elif a.verbose:
            print(f"  ok  {label}")

    if failures:
        print(f"{len(failures)} of {len(CASES)} index case(s) failed:\n",
              file=sys.stderr)
        for f in failures:
            print(f"  {f}\n", file=sys.stderr)
        return 1
    if a.verbose:
        print(f"{len(CASES)} index cases held")
    return 0


if __name__ == "__main__":
    sys.exit(main())
