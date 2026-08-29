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
import re
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


def case_report_does_not_overstate_the_extractor(t):
    """The report may not name a parser the build did not run.

    This is not hypothetical tidiness. `try_tree_sitter()` used to import
    `tree_sitter_languages`, throw it away, and return "tree-sitter", so on any
    machine with that package installed the negative control opened by
    misdescribing how the graph was produced -- and it is the one file an agent
    reads specifically to calibrate how much an absence is worth.

    Asserting the *value* rather than merely that a key exists is the point: a
    label decoupled from the code that produces it drifts back the first time
    someone adds an extractor and forgets the report.
    """
    g, err = build(make_repo(t, SHARED_NAME))
    if g is None:
        return f"build failed: {err.strip()[:200]}"
    got = g["meta"].get("extractor")
    if got != "regex":
        return (f"extractor reported as {got!r}; symbols are extracted by the "
                f"regexes in LANGS, so the only honest value is 'regex'")
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


def case_benchmark_separates_signal_from_noise(t):
    """The measuring instrument must itself be measured.

    A corpus is planted where the answer is known: four clusters of three files,
    each cluster importing within itself, and every commit touching exactly one
    cluster. A graph that works recalls the other two cluster members; uniform
    sampling cannot. If `random` ever comes out level with the graph here, the
    benchmark is reporting an artefact and every number it produces elsewhere is
    worthless -- which is the failure mode a benchmark has and a test does not."""
    files = {}
    for c in range(4):
        names = [f"pkg{c}/mod{i}.py" for i in range(3)]
        for i, rel in enumerate(names):
            peers = [n for j, n in enumerate(names) if j != i]
            imports = "".join(
                f"from {p[:-3].replace('/', '.')} import f{c}_{k}\n"
                for k, p in enumerate(peers))
            files[rel] = f"{imports}\n\ndef f{c}_{i}():\n    return {c}\n"
    make_repo(t, files)
    sh(["git", "-c", "user.email=s@e.x", "-c", "user.name=s",
        "commit", "-qm", "init"], t)
    # One commit per cluster: the ground truth this benchmark is meant to find.
    for c in range(4):
        for i in range(3):
            rel = f"pkg{c}/mod{i}.py"
            with open(os.path.join(t, rel), "a", encoding="utf-8") as fh:
                fh.write(f"\n# touch {c}\n")
        sh(["git", "add", "-A"], t)
        sh(["git", "-c", "user.email=s@e.x", "-c", "user.name=s",
            "commit", "-qm", f"cluster {c}"], t)

    g, err = build(t)
    if g is None:
        return f"build failed: {err.strip()[:200]}"
    r = sh([sys.executable, os.path.join(HERE, "benchmark.py"),
            "--root", t, "--graph", os.path.join(t, ".index", "graph.json"),
            "--k", "4", "--min-trials", "10",
            # No changelog here, and every file appears in 40% of five commits:
            # the ubiquity heuristic is meaningless on a corpus this small and
            # would exclude the entire repository.
            "--exclude-ubiquitous", "1.0", "--json"], t)
    if r.returncode != 0:
        return f"benchmark exit {r.returncode}: {r.stderr.strip()[:300]}"
    recall = json.loads(r.stdout)["recall"]
    best = max(recall["pagerank"], recall["hops1"])
    if best < 0.9:
        return (f"graph recalled {best:.2f} of a planted cluster it has explicit "
                f"import edges for; the benchmark or the graph is broken")
    if best <= recall["random"]:
        return (f"graph {best:.2f} did not beat random {recall['random']:.2f} "
                f"on a corpus built so that it must")
    return None


def case_governs_window_agrees_with_the_hook(t):
    """Both readers of `Governs:` must scan the same number of lines.

    The defect: `index/build.py` read the first 60 lines and the delivering
    hook read the first 40. A `Governs:` line at line 50 therefore created a
    graph edge and produced no hint -- the convention half-worked, in the
    direction nobody thinks to test, and both halves individually looked
    correct.

    They cannot share a constant: they are installed at different tiers, and a
    tier B repository has the hook with no index/ at all. So the agreement is
    asserted here rather than enforced by an import."""
    hook = os.path.join(HERE, "..", "context", "before_write.py")
    try:
        with open(os.path.join(HERE, "build.py"), encoding="utf-8") as fh:
            build_src = fh.read()
        with open(hook, encoding="utf-8") as fh:
            edit_src = fh.read()
    except OSError as exc:
        return f"cannot read both scanners: {exc}"

    b = re.search(r"lines\[:(\d+)\]", build_src)
    e = re.search(r"GOVERNS_HEAD\s*=\s*(\d+)", edit_src)
    if not b:
        return "build.py no longer slices a fixed head window; update this case"
    if not e:
        return "before_write.py no longer declares GOVERNS_HEAD; update this case"
    if b.group(1) != e.group(1):
        return (f"build.py scans {b.group(1)} lines for Governs:, "
                f"before_write.py scans {e.group(1)} — a Governs: line between "
                f"them makes an edge with no hint, or a hint with no edge")

    # And the agreed window must actually work end to end, not merely match.
    depth = int(b.group(1))
    filler = "\n".join(f"Line {i}." for i in range(depth - 6))
    g, err = build(make_repo(t, {
        "src/billing/pay.py": "def pay():\n    return 1\n",
        "docs/deep.md": f"# Deep\n\n{filler}\n\nGoverns: src/billing/\n",
    }))
    if g is None:
        return f"build failed: {err.strip()[:200]}"
    if not any(a == "doc:docs/deep.md" and kind == "governs"
               for a, _b, kind, _w in g["edges"]):
        return (f"a Governs: line inside the declared {depth}-line window "
                f"produced no edge")
    return None


def case_stale_graph_is_announced_but_still_answers(t):
    """A tree that has moved under the graph is reported, and does not refuse.

    Both halves are the case. The graph had no staleness detection at all and
    nothing rebuilt it, so the delivering hook queried an arbitrarily old graph and
    presented the result with no qualification -- build.py's own docstring
    calls that "confidently wrong answers ... strictly worse than no answers,
    because nobody goes and checks".

    The second half guards the fix from overcorrecting. The hook ran on
    PostToolUse, so the file the agent just edited is *always* among the
    changed ones. A staleness check that exited non-zero would kill the hint
    for the whole session from the first edit onward. Staleness is reported;
    it is never disqualifying on its own."""
    tmp = make_repo(t, {
        "src/pay.py": "def pay():\n    return 1\n",
        "src/bill.py": "from src.pay import pay\n\ndef bill():\n    return pay()\n",
    })
    g, err = build(tmp)
    if g is None:
        return f"build failed: {err}"

    fresh = query(tmp, "--seed", "src/bill.py", "--paths-only")
    if "stale" in fresh.stderr:
        return f"a just-built graph reported itself stale: {fresh.stderr.strip()}"

    with open(os.path.join(tmp, "src", "pay.py"), "w", encoding="utf-8") as fh:
        fh.write("def pay():\n    return 2\n")

    after = query(tmp, "--seed", "src/bill.py", "--paths-only")
    if "stale" not in after.stderr:
        return ("a file changed under the graph and the query said nothing: "
                f"{after.stderr.strip()!r}")
    if after.returncode != 0:
        return (f"staleness made the query exit {after.returncode}; on "
                f"PostToolUse the just-edited file is always stale, so this "
                f"silences every automatic consumer for the rest of the session")
    if not after.stdout.strip():
        return "reported stale and then returned nothing"

    seeded = query(tmp, "--seed", "src/pay.py", "--paths-only")
    if "seed itself moved" not in seeded.stderr:
        return ("seeding on the changed file did not say so — that is the "
                "actionable half, and it is a different quality of wrong from "
                "a stale file out in the neighbourhood")
    return None


def case_generated_report_has_no_clock(t):
    """Regenerating the report must be a no-op when the tree has not changed.

    The report's own header says an empty `git diff` on regeneration is what
    keeps it from being edited by hand. Adding a build timestamp to the graph
    put a clock one careless line away from that file, and a generated document
    that differs on every regeneration trains people to ignore its diff --
    which costs exactly the property the header claims.

    (No gate enforces that header's claim anywhere in this repository. This
    case covers the index's half of it; the claim itself is still broader than
    what is checked.)"""
    tmp = make_repo(t, {"src/pay.py": "def pay():\n    return 1\n",
                        "docs/x.md": "# X\n\nGoverns: src/\n"})

    def regenerate():
        out = sh([sys.executable, os.path.join(HERE, "build.py"), "--root", tmp,
                  "--out", os.path.join(tmp, ".index", "graph.json"),
                  "--report"], tmp)
        if out.returncode != 0:
            return None
        with open(os.path.join(tmp, "docs", "generated", "index-report.md"),
                  encoding="utf-8") as fh:
            return fh.read()

    first = regenerate()
    if first is None:
        return "build --report failed"
    # Move every mtime, which is what the stamp is built from. Content is
    # untouched, so the report must be byte-identical.
    os.utime(os.path.join(tmp, "src", "pay.py"), (1, 1))
    second = regenerate()
    if first != second:
        return ("the generated report changed when only mtimes did — "
                "something time-dependent leaked into it")

    # The comparison above is necessary and not sufficient. `built_at` has
    # one-second resolution, so two regenerations this close carry the *same*
    # clock value and a leaked timestamp would compare equal here -- passing
    # while the property is broken. Check for the values directly as well.
    with open(os.path.join(tmp, ".index", "graph.json"), encoding="utf-8") as fh:
        st = json.load(fh)["meta"]["stamp"]
    for field in ("built_at", "head"):
        value = st.get(field)
        if value and str(value) in second:
            return (f"the generated report contains the graph's {field} — it "
                    f"will differ on regeneration for reasons that are not "
                    f"changes to the tree")
    return None


CASES = [
    ("symbol names are not merged into one hub", case_no_symbol_hub),
    ("a reference resolves to a later-scanned definition", case_forward_reference),
    ("Governs: is directory-aware", case_governs_is_directory_aware),
    ("an unresolvable Governs: target is reported", case_dangling_governs_is_reported),
    ("the report does not overstate the extractor",
     case_report_does_not_overstate_the_extractor),
    ("an unmatched seed cannot judge", case_unmatched_seed_cannot_judge),
    ("a bare symbol name still resolves as a seed", case_seed_by_symbol_name),
    ("the benchmark separates signal from noise",
     case_benchmark_separates_signal_from_noise),
    ("both readers of Governs: scan the same window",
     case_governs_window_agrees_with_the_hook),
    ("a stale graph is announced but still answers",
     case_stale_graph_is_announced_but_still_answers),
    ("the generated report has no clock in it",
     case_generated_report_has_no_clock),
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
