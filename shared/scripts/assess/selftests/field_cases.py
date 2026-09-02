#!/usr/bin/env python3
"""Assessment selftest cases: the field: what 1.0.0 got wrong on repositories nobody here wrote.

Split out of ``assess/selftest.py`` to keep every file under this
repository's line-count ceiling; see that file for the CLI, exit codes, and
why this selftest exists. Every case here is unchanged from the original --
same name, body, docstring, comments -- and this module's own ``CASES`` list
keeps them in the same order relative to each other that the original single
list held. ``selftest.py`` concatenates every case module's list, so all 192
cases still run, each exactly once.
"""

from __future__ import annotations

import json
import shutil

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _support import (
    catch_mod,
    commit,
    dim_mod,
    dims_of,
    eco_mod,
    put,
    repo,
    review_mod,
)



# --------------------------------------------------------------------------
# the field: what 1.0.0 got wrong on repositories nobody here wrote
# --------------------------------------------------------------------------

def case_an_unscored_axis_is_not_drawn_at_zero(t):
    """A dimension nobody scored used to get a vertex at the centre and a
    solid dot -- the exact picture a zero draws. 0041 forbids that in words;
    the shape leaked it."""
    svg = review_mod.radar({"1": 5, "3": 5, "4": 5, "5": 5}, size=400)
    cx, cy = 200.0, 400 * 0.46
    if "%.1f,%.1f" % (cx, cy) in svg:
        return "an unscored axis was drawn at the centre, like a zero"
    if "not scored" not in svg:
        return "an unscored axis is not labelled as unscored"
    if "stroke-dasharray" not in svg:
        return "an incomplete polygon is drawn like a complete one"
    full = review_mod.radar({"1": 5, "2": 5, "3": 5, "4": 5, "5": 5}, size=400)
    if 'stroke-dasharray="5 4"' in full:
        return "a fully scored polygon was drawn dashed"
    return None


def case_a_suite_below_the_root_is_found(t):
    """A Go module under cli/, a Makefile under svc/: the root has no
    marker for a language the table supports, and 1.0.0 reported no
    ecosystem at all."""
    repo(t)
    put(t, "README.md", "# mono\n")
    put(t, "svc/Makefile", "test:\n\t@true\n")
    commit(t, "feat: a service under svc/")
    eco, cmd = eco_mod.find(t)
    if eco is None or "svc/" not in eco.name:
        return f"a suite under svc/ was routed to {eco and eco.name!r}"
    if shutil.which("make") and cmd != ["bash", "-c", "cd svc && make test"]:
        return f"the command does not run from svc/: {cmd}"
    put(t, "web/node_modules/pkg/package.json",
        json.dumps({"scripts": {"test": "jest"}}))
    put(t, "web/README.md", "x")
    eco2, _c = eco_mod.find(t)
    if eco2 is not None and "node" in eco2.name:
        return "a package.json under node_modules was read as the repository's"
    return None


def case_a_typed_command_goes_through_a_shell(t):
    """`cd app && flutter test` was split on whitespace and exec'd, so `cd`
    was looked up on PATH. The help text promised a shell it did not have."""
    if shutil.which("make") is None:
        return ""
    repo(t)
    check = ("test:\n"
             "\t@python3 -c \"import sys; sys.path.insert(0,'.'); "
             "from src.a import f; sys.exit(0 if f() == {want} else 1)\"\n")
    put(t, "src/__init__.py", "")
    put(t, "src/a.py", "def f():\n    return 2\n")
    put(t, "tests/.keep", "")
    put(t, "Makefile", check.format(want=2))
    commit(t, "feat: a")
    put(t, "src/a.py", "def f():\n    return 3\n")
    put(t, "Makefile", check.format(want=3))
    put(t, "tests/case_f.py", "# moved with the fix\n")
    commit(t, "fix: f returned the wrong number")
    r, why = catch_mod.assess(t, 1, os.path.join(t, ".work"),
                              "true && make test")
    if r is None:
        return f"a shell command could not run: {why}"
    if [row["rung"] for row in r["rows"]] != ["local-suite"]:
        return f"a shell command did not reach the suite: {r['rows']}"
    if r["command"] != "true && make test":
        return f"the command is displayed as {r['command']!r}"
    return None


def case_an_untracked_entry_point_is_named(t):
    """The replay runs in a clean clone, so a helper script that was never
    committed is not there. `No such file` says nothing about why."""
    repo(t)
    put(t, "src/a.py", "x = 1\n")
    put(t, "tests/.keep", "")
    commit(t, "feat: a")
    put(t, "src/a.py", "x = 2\n")
    put(t, "tests/case.py", "# with the fix\n")
    commit(t, "fix: a")
    put(t, "run-tests.sh", "#!/bin/sh\nexit 0\n")       # never committed
    r, why = catch_mod.assess(t, 1, os.path.join(t, ".work"),
                              "bash run-tests.sh")
    if r is not None or "not tracked" not in why:
        return f"an untracked entry point was not named: {r} {why}"
    return None


def case_nothing_wired_is_scored_as_nothing_refused(t):
    """No .claude/ is not `not asked`. The answer is known -- nothing is
    refused -- and it has to reach the brief under 1.1, or the worst
    possible reading leaves the page while the fact sheet says BAD."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    commit(t, "feat")
    d1 = dims_of(t, with_blast=False)[1]
    row = next((r for r in d1["rows"]
                if "refused before they happen" in r["label"]), None)
    if not row or not row["value"].startswith("0/") or row["flag"] != "bad":
        return f"no .claude/ read as {row and row['value']!r}"
    items, _un = review_mod.collect({"dimensions": [d1]})
    if not any(it["id"] == "1.1" for it in items):
        return "the nothing-wired row did not reach sub-item 1.1"
    return None


def case_a_test_that_already_existed_is_told_from_the_fix_s_own(t):
    """The ladder keeps the fix's own regression test, so local-suite is
    near-certain by construction. The control puts tests back too: a suite
    that saw the defect before its regression test existed is the exception
    worth reporting, and the ordinary case is `missed`."""
    if shutil.which("make") is None:
        return ""
    check = ("test:\n"
             "\t@python3 -c \"import sys; sys.path.insert(0,'.'); "
             "from src.a import f; sys.exit(0 if f() == {want} else 1)\"\n")
    # (a) the Makefile already asserted 3 before the fix: an existing test
    # sees the defect.
    repo(t)
    put(t, "src/__init__.py", "")
    put(t, "src/a.py", "def f():\n    return 2\n")
    put(t, "tests/.keep", "")
    put(t, "Makefile", check.format(want=3))
    commit(t, "feat: a, with a test it fails")
    put(t, "src/a.py", "def f():\n    return 3\n")
    put(t, "tests/case_f.py", "# with the fix\n")
    commit(t, "fix: f returned the wrong number")
    r, why = catch_mod.assess(t, 1, os.path.join(t, ".work"))
    if r is None:
        return f"could not run the ladder: {why}"
    if [row.get("prior_suite") for row in r["rows"]] != ["caught"]:
        return (f"a pre-existing test that sees the defect read as "
                f"{[row.get('prior_suite') for row in r['rows']]}")
    d2 = dim_mod.change_validation(
        {"replayable": 1, "shallow": False}, r, "", catch_mod.LADDER)
    row = next((x for x in d2["rows"] if "already existed" in x["label"]), None)
    if not row or not row["value"].startswith("1 of 1"):
        return f"the control row reads {row and row['value']!r}"
    return None


def case_a_defect_the_suite_never_reaches_is_not_a_survivor(t):
    """A command that covers part of the repository was recorded as the
    repository failing to catch a defect in the other part. `1 defect
    survives past the end of a session` is a sentence about the repository;
    the true sentence is about the command."""
    catch = {"command": "cd svc && make test", "rows": [
        {"sha": "aaaaaaaaaa", "subject": "fix: cli", "rung": "never",
         "detail": "nothing went red", "seconds": None,
         "source": ["cli/main.go"], "tests": ["cli/main_test.go"]},
        {"sha": "bbbbbbbbbb", "subject": "fix: svc", "rung": "local-suite",
         "detail": "red", "seconds": 1.0,
         "source": ["svc/a.py"], "tests": ["svc/test_a.py"]}]}
    d2 = dim_mod.change_validation(
        {"replayable": 2, "shallow": False}, catch, "", catch_mod.LADDER)
    if "0 of 1 defects survive" not in d2["headline"]:
        return f"an unreached defect counted as surviving: {d2['headline']}"
    row = next((x for x in d2["rows"] if "suite's reach" in x["label"]), None)
    if not row or row["value"] != "1" or "cli/main.go" not in row["note"]:
        return f"the unreached row reads {row}"
    # And by coverage, with no cd: the suite ran but never entered the file.
    catch["command"] = "make test"
    cover = {"tool": "coverage.py", "criteria": {}, "files": {},
             "reached": {"cli/main.go": False, "svc/a.py": True}}
    d2 = dim_mod.change_validation(
        {"replayable": 2, "shallow": False}, catch, "", catch_mod.LADDER,
        cover=cover)
    if "0 of 1 defects survive" not in d2["headline"]:
        return f"a file coverage never entered counted as a miss: {d2['headline']}"
    # A file the suite did reach and still missed is a real survivor.
    cover["reached"]["cli/main.go"] = True
    d2 = dim_mod.change_validation(
        {"replayable": 2, "shallow": False}, catch, "", catch_mod.LADDER,
        cover=cover)
    if "1 of 2 defects survive" not in d2["headline"]:
        return f"a reached-and-missed defect was excused: {d2['headline']}"
    return None


def case_both_denominators_travel_with_the_row(t):
    """Typed commits narrow the denominator; untyped ones do not. The same
    repository on two branches gave two percentages that could not be
    compared, so the row now carries the all-source number too."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    commit(t, "a change without a type")
    put(t, "app.py", "x = 2\n")
    commit(t, "another")
    d3 = dims_of(t, with_blast=False)[3]
    row = next((r for r in d3["rows"] if "verified nothing" in r["label"]), None)
    if not row or "all_source" not in row or "denominator" not in row:
        return f"the row carries no second denominator: {row}"
    if "every change to source" not in row["note"]:
        return "the note does not say what the second number is"
    return None


CASES = [
    ('an unscored axis is not drawn at zero',
     case_an_unscored_axis_is_not_drawn_at_zero),
    ('a suite below the root is found',
     case_a_suite_below_the_root_is_found),
    ('a typed command goes through a shell',
     case_a_typed_command_goes_through_a_shell),
    ('an untracked entry point is named',
     case_an_untracked_entry_point_is_named),
    ('nothing wired is scored as nothing refused',
     case_nothing_wired_is_scored_as_nothing_refused),
    ("a test that already existed is told from the fix's own",
     case_a_test_that_already_existed_is_told_from_the_fix_s_own),
    ('a defect the suite never reaches is not a survivor',
     case_a_defect_the_suite_never_reaches_is_not_a_survivor),
    ('both denominators travel with the row',
     case_both_denominators_travel_with_the_row),
]
