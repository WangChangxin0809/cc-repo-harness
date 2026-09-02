#!/usr/bin/env python3
"""Assessment selftest cases: several ecosystems in one tree.

Split out of ``assess/selftest.py`` to keep every file under this
repository's line-count ceiling; see that file for the CLI, exit codes, and
why this selftest exists. Every case here is unchanged from the original --
same name, body, docstring, comments -- and this module's own ``CASES`` list
keeps them in the same order relative to each other that the original single
list held. ``selftest.py`` concatenates every case module's list, so all 192
cases still run, each exactly once.
"""

from __future__ import annotations

import shutil

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _support import (
    _pooled_python_history,
    _pytest_here,
    _two_suite_root,
    catch_mod,
    commit,
    cover_mod,
    dim_mod,
    eco_mod,
    put,
    repo,
    review_mod,
)



# --------------------------------------------------------------------------
# several ecosystems in one tree: every one is measured, the verdict pooled
# --------------------------------------------------------------------------


def case_every_ecosystem_is_found_and_an_aggregate_claims_the_tree(t):
    """`find` returned the first ecosystem and stopped. A tree with Python at
    the root and a suite under svc/ was measured as if it had one suite, and
    nothing on the page said a second existed.

    A root Makefile or a root documented command is the recipe that drives
    everything, so it claims the tree; without one, every suite is returned,
    root first, and `find` stays the first of them."""
    _two_suite_root(t)
    got = eco_mod.find_all(t)
    names = [e.name for e, _c in got]
    if names != ["python", "make in svc/"]:
        return f"two suites, no aggregate: find_all gave {names}"
    first, _c = eco_mod.find(t)
    if first is None or first.name != names[0]:
        return f"find is no longer the first of find_all: {first and first.name}"
    if shutil.which("make") and got[1][1] != ["bash", "-c",
                                              "cd svc && make test"]:
        return f"the second suite does not run from svc/: {got[1][1]}"
    # A Makefile at the root drives both; only it is returned.
    put(t, "Makefile", "test:\n\t@true\n")
    names = [e.name for e, _c in eco_mod.find_all(t)]
    if names != ["make"]:
        return f"a root Makefile did not claim the tree: {names}"
    os.remove(os.path.join(t, "Makefile"))
    # A documented command at the root is the operator's aggregate.
    put(t, "check.py", "import sys\nsys.exit(0)\n")
    put(t, "README.md", "# x\n\nRun the tests:\n\n```bash\n"
                        "python3 check.py\n```\n")
    names = [e.name for e, _c in eco_mod.find_all(t)]
    if names != ["declared"]:
        return f"a root documented command did not claim the tree: {names}"
    return None


def case_a_defect_whose_test_lives_in_the_second_suite_is_caught(t):
    """The replay ran one suite. A defect whose regression test sits in the
    other one read as `never`, which is a sentence about the instrument
    printed as a sentence about the repository."""
    if not _pytest_here():
        return None
    _pooled_python_history(t)
    names = [e.name for e, _c in eco_mod.find_all(t)] \
        if hasattr(eco_mod, "find_all") else []
    r, why = catch_mod.assess(t, 1, os.path.join(t, ".work"))
    if r is None:
        return f"could not run the ladder at all: {why}"
    rungs = [row["rung"] for row in r["rows"]]
    if rungs != ["local-suite"]:
        return (f"a defect tested under b/ was put on {rungs}, not "
                f"['local-suite'] — suites seen: {names}; detail: "
                f"{[str(row['detail'])[:70] for row in r['rows']]}")
    if "python in a/" not in r["ecosystem"] or "python in b/" not in r["ecosystem"]:
        return f"the result does not name both suites: {r['ecosystem']!r}"
    suites = r.get("suites") or []
    if len(suites) != 2 or not all(s.get("ran") for s in suites):
        return f"the result does not say both suites ran: {suites}"
    d2 = dim_mod.change_validation(
        {"replayable": 1, "shallow": False, "has_test_files": True},
        r, "", catch_mod.LADDER)
    row = next((x for x in d2["rows"] if x["label"] == "suites measured"), None)
    if not row or not row["value"].startswith("2"):
        return f"the page does not count the suites: {row and row['value']!r}"
    return None


def case_coverage_pooled_across_suites_is_the_sum_of_each(t):
    """One tool's figure was reported as the repository's. With two suites
    the figure is each runner against its own suite, summed per criterion,
    and the page says which tools it pools."""
    if not cover_mod.Python().available(t):
        print("  note: coverage is not installed; the pooled-coverage case "
              "was not run", file=sys.stderr)
        return None
    _pooled_python_history(t)
    alone = []
    for sub in ("a", "b"):
        got, why = cover_mod.Python().measure(
            os.path.join(t, sub), [sys.executable, "-m", "pytest", "-q"],
            os.path.join(t, ".w-" + sub))
        if not got:
            return f"the fixture is wrong: {sub}/ alone gave no report: {why}"
        alone.append(got["criteria"]["statement"])
    pooled, why = cover_mod.assess(t, None, os.path.join(t, ".w"))
    if not pooled:
        return f"nothing was measured with no command given: {why}"
    st = pooled["criteria"].get("statement") or {}
    want = sum(a["total"] for a in alone), sum(a["covered"] for a in alone)
    if (st.get("total"), st.get("covered")) != want:
        return (f"pooled statement coverage is {st}, and the two suites "
                f"alone sum to total={want[0]} covered={want[1]}")
    if not any(f.startswith("b/") for f in pooled.get("files") or {}):
        return ("the files are not merged under their suite: "
                f"{sorted(pooled.get('files') or {})[:4]}")
    rows = dim_mod.coverage_rows(pooled)
    row = next((x for x in rows if "statements" in x["label"]), None)
    if not row or "python in a/" not in row["note"] \
            or "python in b/" not in row["note"]:
        return ("the coverage row does not say which suites it pools: "
                f"{row and row['note']!r}")
    return None


def case_a_suite_whose_tool_is_missing_is_found_but_not_run(t):
    """A second suite whose toolchain this machine lacks is an absence on
    the machine, not in the repository -> 0047. It is listed as found and
    not run, the Python suite beside it is still measured, and the pooled
    verdict is not red because of it."""
    if not _pytest_here():
        return None
    repo(t)
    put(t, "pyproject.toml", "[project]\nname = 'x'\n")
    put(t, "a.py", "def f():\n    return 2\n")
    put(t, "tests/test_a.py", "from a import f\n\ndef test_f():\n"
                              "    assert f() == 2\n")
    put(t, "cli/go.mod", "module example.com/cli\n\ngo 1.22\n")
    commit(t, "feat: a, and a cli in go")
    put(t, "a.py", "def f():\n    return 3\n")
    put(t, "tests/test_a.py", "from a import f\n\ndef test_f():\n"
                              "    assert f() == 3\n")
    commit(t, "fix: f returned the wrong number")
    real = shutil.which

    def without_go(name, *args, **kw):
        return None if name == "go" else real(name, *args, **kw)

    shutil.which = without_go
    try:
        r, why = catch_mod.assess(t, 1, os.path.join(t, ".work"))
    finally:
        shutil.which = real
    if r is None:
        return f"a missing toolchain for one suite abstained on both: {why}"
    rungs = [row["rung"] for row in r["rows"]]
    if rungs != ["local-suite"]:
        return (f"the Python suite was not measured beside the missing one: "
                f"{rungs}; {[str(row['detail'])[:70] for row in r['rows']]}")
    suites = r.get("suites") or []
    missing = [s for s in suites if not s.get("ran")]
    if len(suites) != 2 or len(missing) != 1 \
            or "go" not in missing[0]["ecosystem"]:
        return ("the result does not list the Go suite as found and not "
                f"run: {suites}")
    d2 = dim_mod.change_validation(
        {"replayable": 1, "shallow": False, "has_test_files": True},
        r, "", catch_mod.LADDER)
    row = next((x for x in d2["rows"]
                if x["label"] == "suites found but not run"), None)
    if not row or "go in cli/" not in row["value"] \
            or "not installed" not in row["value"]:
        return f"the page has no found-but-not-run row: {row and row['value']!r}"
    if row["flag"] != "info" or review_mod.measured(row):
        return f"found-but-not-run is scored rather than abstained: {row}"
    ladder = next(x for x in d2["rows"]
                  if x["label"] == "where each was first caught")
    if ladder["flag"] == "bad":
        return f"the missing toolchain made the ladder red: {ladder['value']}"
    return None


CASES = [
    ('every ecosystem is found, and an aggregate at the root claims the tree',
     case_every_ecosystem_is_found_and_an_aggregate_claims_the_tree),
    ('a defect whose test lives in the second suite is caught',
     case_a_defect_whose_test_lives_in_the_second_suite_is_caught),
    ('coverage pooled across suites is the sum of each',
     case_coverage_pooled_across_suites_is_the_sum_of_each),
    ('a suite whose tool is missing is found but not run',
     case_a_suite_whose_tool_is_missing_is_found_but_not_run),
]
