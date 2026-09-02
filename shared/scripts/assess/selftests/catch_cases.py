#!/usr/bin/env python3
"""Assessment selftest cases: catch: the ladder, and the rung that must not fire.

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
    BLOCKER,
    QUIET,
    catch_mod,
    commit,
    dim_mod,
    history_mod,
    hook_script,
    put,
    repo,
    review_mod,
    truth_mod,
)



# --------------------------------------------------------------------------
# catch: the ladder, and the rung that must not fire
# --------------------------------------------------------------------------

def case_a_hook_that_refuses_is_read_as_before_write(t):
    repo(t)
    hook_script(t, "hooks/no.py", BLOCKER)
    pre = catch_mod.wired(t, "PreToolUse")
    if len(pre) != 1:
        return f"read {len(pre)} PreToolUse hook(s) from settings.json, expected 1"
    blocked, _h, _said = catch_mod.fire(t, pre, {"tool_name": "Edit",
                                                 "tool_input": {}})
    if not blocked:
        return "a hook exiting 2 was not read as a block"
    return ""


def case_a_hook_that_denies_in_json_is_also_a_block(t):
    """Two spellings are in use. A probe that knew one would report a working
    guard as absent."""
    repo(t)
    hook_script(t, "hooks/no.py",
                "import sys, json\n"
                "sys.stdin.read()\n"
                "print(json.dumps({'permissionDecision': 'deny',\n"
                "                  'permissionDecisionReason': 'nope'}))\n")
    blocked, _h, said = catch_mod.fire(t, catch_mod.wired(t, "PreToolUse"),
                                       {"tool_name": "Edit", "tool_input": {}})
    if not blocked:
        return "a hook denying in JSON on stdout was not read as a block"
    if "nope" not in said:
        return f"the reason was lost: {said!r}"
    return ""


def case_a_quiet_hook_is_not_a_block(t):
    """The inverse, and the one that turns the whole ladder into a lie if it
    breaks: a hook that allows must not be scored as a catch."""
    repo(t)
    hook_script(t, "hooks/ok.py", QUIET)
    blocked, _h, _s = catch_mod.fire(t, catch_mod.wired(t, "PreToolUse"),
                                     {"tool_name": "Edit", "tool_input": {}})
    if blocked:
        return "a hook that exited 0 was scored as refusing the action"
    return ""


def case_settings_local_is_read_and_marked(t):
    """A hook only in `settings.local.json` protects its author and nobody
    else, which is worth reporting rather than silently counting."""
    repo(t)
    put(t, ".claude/settings.local.json", json.dumps({
        "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
            {"type": "command", "command": "true"}]}]}}))
    pre = catch_mod.wired(t, "PreToolUse")
    if len(pre) != 1 or not pre[0]["local"]:
        return "a hook wired only in settings.local.json was missed or unmarked"
    return ""


def case_a_repository_with_no_suite_is_scored_not_skipped(t):
    """Absent in the repository, not absent on this machine.

    `no runnable test command` covered two situations: a toolchain this
    machine lacks, and a repository with no test file anywhere. The first is
    an abstention. The second was reported the same way, so the one
    repository dimension 2 should have been loudest about was the one it
    said nothing about -> 0047"""
    repo(t)
    put(t, "src/a.py", "def f():\n    return 2\n")
    commit(t, "feat: a")
    put(t, "src/a.py", "def f():\n    return 3\n")
    commit(t, "fix: f returned the wrong number")
    found = history_mod.mine(t)
    defects = {"replayable": 0, "fix_no_test": 1,
               "has_test_files": found["has_test_files"],
               "shallow": found["shallow"]}
    if defects["has_test_files"]:
        return "the fixture has a test file, so this proves nothing"
    d = dim_mod.change_validation(
        defects, None, "cannot judge: no runnable test command — pass "
        "--test-command", catch_mod.LADDER)
    if d["state"] != "measured":
        return f"no suite in the tree was reported as {d['state']!r}"
    row = next((r for r in d["rows"]
                if r["label"] == "a suite in the repository"), None)
    if row is None or row["flag"] != "bad":
        return f"no red row for the missing suite: {row}"
    items, _un = review_mod.collect({"dimensions": [d]})
    if "2.4" not in [i["id"] for i in items]:
        return "the missing suite reaches no sub-item, so it is never scored"
    # And under --no-full, which costs nothing extra, the same row.
    d = dim_mod.change_validation(defects, None, "", catch_mod.LADDER)
    if d["state"] != "measured":
        return "under --no-full the missing suite went back to being silent"

    # The other case keeps abstaining: a test file exists and the toolchain
    # to run it does not.
    put(t, "tests/test_a.py", "def test_f():\n    assert True\n")
    commit(t, "test: a")
    found = history_mod.mine(t)
    defects["has_test_files"] = found["has_test_files"]
    d = dim_mod.change_validation(
        defects, None, "cannot judge: no runnable test command (pytest "
        "needs pytest, which is not on PATH)", catch_mod.LADDER)
    if d["state"] != "abstained":
        return ("a suite this machine cannot run was scored as "
                f"{d['state']!r}")
    return None


def case_a_repository_with_no_pipeline_is_scored_not_skipped(t):
    """Same rule, dimension 3. `pipeline.py` reads one host and abstains on
    the others, which is right when a Jenkinsfile is there and wrong when
    nothing is: 3.3 to 3.6 were absent for a repository with no CI, which
    is the repository they were written for."""
    repo(t)
    put(t, "src/a.py", "def f():\n    return 2\n")
    commit(t, "feat: a")
    log = history_mod.commits(t)
    d = dim_mod.reliable_delivery(t, log, (), None, None)
    row = next((r for r in d["rows"]
                if r["label"] == "changes that run no check"), None)
    if row is None or row["flag"] != "bad" or "no pipeline" not in row["value"]:
        return f"no pipeline at all left 3.3 blank: {row}"
    items, _un = review_mod.collect({"dimensions": [d]})
    if "3.3" not in [i["id"] for i in items]:
        return "the missing pipeline reaches no sub-item"
    # With a pipeline of a host pipeline.py does not read, the row is not
    # printed: that is unread, not absent.
    put(t, "Jenkinsfile", "pipeline { agent any }\n")
    commit(t, "ci: jenkins")
    d = dim_mod.reliable_delivery(t, history_mod.commits(t), (), None, None)
    if any(r["label"] == "changes that run no check" for r in d["rows"]):
        return "a Jenkinsfile nobody read was scored as no pipeline"
    return None


def case_a_repository_that_writes_nothing_down_is_scored(t):
    """4.1's value was the kinds of memory joined with spaces, and a
    repository with none produced an empty string, which the reading drops
    as an abstention. Nothing written down is a measurement."""
    repo(t)
    put(t, "src/a.py", "def f():\n    return 2\n")
    commit(t, "feat: a")
    truth = truth_mod.assess(t)
    if truth is None:
        return "truth could not read an ordinary repository"
    if any(truth["thickness"].values()):
        return f"the fixture writes something down: {truth['thickness']}"
    d = dim_mod.repository_memory(t, history_mod.commits(t), (), truth)
    row = next((r for r in d["rows"] if r["label"] == "what it writes down"),
               None)
    if row is None or not review_mod.measured(row):
        return f"nothing written down was dropped as an abstention: {row}"
    if row["flag"] != "bad":
        return f"nothing written down is not red: {row['flag']}"
    return None


def case_no_hooks_and_a_real_defect_lands_on_the_suite(t):
    """The end-to-end shape, with the answer known in advance: a repository
    with tests and no hooks catches its defects at `local-suite`.

    The fixture runs its test through a `Makefile` and the standard library,
    not through pytest. The first version needed pytest, which is not on a
    fresh runner's ambient interpreter, so the one case that exercises the
    whole ladder was the one case CI could not run -- and the failure looked
    like a broken ladder rather than a missing package. A selftest for an
    assessment may not depend on anything the assessment does not."""
    if shutil.which("make") is None:
        return ""                       # no runner; not a verdict about anything
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
    put(t, "tests/case_f.py", "# the test moved with the fix\n")
    commit(t, "fix: f returned the wrong number")

    work = os.path.join(t, ".work")
    r, why = catch_mod.assess(t, 1, work)
    if r is None:
        return f"could not run the ladder at all: {why}"
    rungs = [row["rung"] for row in r["rows"]]
    if rungs != ["local-suite"]:
        return (f"a repository with tests and no hooks put its defect on "
                f"{rungs}, not ['local-suite'] — detail: "
                f"{[str(row['detail'])[:70] for row in r['rows']]}")
    return ""

def case_a_hook_wired_after_the_defect_did_not_catch_it(t):
    """The hooks were read once, from the subject at HEAD, and fired in a
    bench parked at commits from before those hook scripts existed. Python
    exits 2 for `can't open file`, the probe read 2 as a refusal, and this
    repository reported every replayed defect caught at `before-write` -- by
    a hook that was not there -- with a `false_block` on every row, because
    the same absent script "refused" the fix too.

    The wiring that counts is the one in the parked tree. A hook committed
    after the defect is absent at the defect, and the defect has to walk on
    to the suite."""
    repo(t)
    put(t, "app/__init__.py", "")
    put(t, "app/calc.py", "def add(a, b):\n    return a - b\n")
    put(t, "test_calc.py",
        "import sys, os\n"
        "sys.path.insert(0, os.path.dirname(__file__))\n"
        "from app.calc import add\n"
        "sys.exit(0 if add(2, 3) == 5 else 1)\n")
    commit(t, "feat: a calculator")
    put(t, "app/calc.py", "def add(a, b):\n    return a + b\n")
    put(t, "test_calc.py",
        open(os.path.join(t, "test_calc.py")).read()
        + "sys.exit(0 if add(1, 1) == 2 else 1)\n")
    fix = commit(t, "fix: add was subtracting")
    # Wired at HEAD only, through the variable Claude Code sets, so the
    # command resolves inside whatever tree it is fired in.
    put(t, "hooks/no.py", BLOCKER)
    put(t, ".claude/settings.json", json.dumps({
        "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
            {"type": "command",
             "command": 'python3 "${CLAUDE_PROJECT_DIR}/hooks/no.py"'}]}],
                  "PostToolUse": [{"matcher": "*", "hooks": [
            {"type": "command",
             "command": 'python3 "${CLAUDE_PROJECT_DIR}/hooks/no.py"'}]}]}}))
    commit(t, "chore: a guard, long after the fix")

    r, why = catch_mod.assess(t, 1, os.path.join(t, ".work"),
                              command=[sys.executable, "test_calc.py"])
    if r is None:
        return f"could not run the ladder: {why}"
    if [row["sha"] for row in r["rows"]] != [fix[:10]]:
        return f"the replay picked {[row['sha'] for row in r['rows']]}"
    row = r["rows"][0]
    if row["rung"] in ("before-write", "same-turn"):
        return (f"a hook that did not exist at the defect's commit was "
                f"credited with catching it at {row['rung']}: {row['detail']}")
    if row["rung"] not in ("local-suite", "ci", "never"):
        return f"the defect landed on {row['rung']!r}: {row['detail']}"
    if row.get("false_block"):
        return (f"an absent hook was reported as refusing the fix: "
                f"{row['false_block']}")
    at = row.get("hooks") or {}
    if at.get("PreToolUse", 1) or at.get("PostToolUse", 1):
        return f"the row counts hooks the parked tree does not wire: {at}"
    if r["hooks"]["PreToolUse"] != 1 or r["hooks"]["PostToolUse"] != 1:
        return f"the HEAD count is no longer honest either: {r['hooks']}"
    return None


def case_a_hook_whose_script_is_missing_broke_and_did_not_block(t):
    """`python3 missing.py` exits 2, and 2 is the exit code of a refusal. A
    hook that could not start has not refused anything; it goes with the
    ones that crashed, where the report can say so."""
    repo(t)
    put(t, ".claude/settings.json", json.dumps({
        "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
            {"type": "command",
             "command": f'python3 "{os.path.join(t, "hooks/missing.py")}"'}]}]}}))
    pre = catch_mod.wired(t, "PreToolUse")
    blocked, _h, said, broke = catch_mod.fire_ex(
        t, pre, {"tool_name": "Edit", "tool_input": {}})
    if blocked:
        return f"a hook whose script is absent was read as a block: {said!r}"
    if len(broke) != 1:
        return f"the absent script was not reported as a hook that broke: {broke}"
    if "open file" not in broke[0][1] and "No such file" not in broke[0][1]:
        return f"the report does not say what went wrong: {broke[0][1]!r}"
    # ...and a script that is there and refuses is still a refusal.
    hook_script(t, "hooks/no.py", BLOCKER)
    blocked, _h, _said, broke = catch_mod.fire_ex(
        t, catch_mod.wired(t, "PreToolUse"), {"tool_name": "Edit",
                                              "tool_input": {}})
    if not blocked or broke:
        return "a genuine exit-2 refusal stopped being read as a block"
    return None


CASES = [
    ('a repository with no suite is scored, not skipped',
     case_a_repository_with_no_suite_is_scored_not_skipped),
    ('a repository with no pipeline is scored, not skipped',
     case_a_repository_with_no_pipeline_is_scored_not_skipped),
    ('a repository that writes nothing down is scored',
     case_a_repository_that_writes_nothing_down_is_scored),
    ('a hook exiting 2 reads as a refusal',
     case_a_hook_that_refuses_is_read_as_before_write),
    ('a hook denying in JSON reads as a refusal, with its reason',
     case_a_hook_that_denies_in_json_is_also_a_block),
    ('a hook that allows is not scored as a catch',
     case_a_quiet_hook_is_not_a_block),
    ('a hook wired only in settings.local.json is read, and marked',
     case_settings_local_is_read_and_marked),
    ('tests and no hooks put a real defect on the local suite',
     case_no_hooks_and_a_real_defect_lands_on_the_suite),
    ('a hook wired after the defect did not catch it',
     case_a_hook_wired_after_the_defect_did_not_catch_it),
    ('a hook whose script is missing broke and did not block',
     case_a_hook_whose_script_is_missing_broke_and_did_not_block),
]
