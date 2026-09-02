#!/usr/bin/env python3
"""Assessment selftest cases: dimensions: the five groups.

Split out of ``assess/selftest.py`` to keep every file under this
repository's line-count ceiling; see that file for the CLI, exit codes, and
why this selftest exists. Every case here is unchanged from the original --
same name, body, docstring, comments -- and this module's own ``CASES`` list
keeps them in the same order relative to each other that the original single
list held. ``selftest.py`` concatenates every case module's list, so all 192
cases still run, each exactly once.
"""

from __future__ import annotations

import subprocess

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _support import (
    CRASHES,
    HERE,
    PARENT,
    QUIET,
    catch_mod,
    commit,
    dim_mod,
    dim_repo,
    dims_of,
    git,
    load_probe,
    put,
    repo,
)



# --------------------------------------------------------------------------
# dimensions: the five groups, and the states each of them can lose
# --------------------------------------------------------------------------


def case_a_guard_that_crashes_is_not_read_as_allowed(t):
    """A hook that exits 1 with a traceback decided nothing.

    Claude Code treats any non-zero exit other than 2 as a non-blocking error:
    the action proceeds. Before this, such a hook was folded into `allowed`,
    so a guard with a missing import and no guard at all produced the same
    page -- and the first of those is worse, because everybody believes they
    are covered."""
    dim_repo(t, hook=CRASHES)
    rows = dims_of(t)[1]["rows"]
    broke = [r for r in rows if "broke" in r["label"]]
    if not broke:
        return "a guard that crashed was not reported as broken"
    if broke[0]["flag"] != "bad":
        return f"a broken guard was flagged {broke[0]['flag']!r}, not 'bad'"
    return None


def case_a_guard_that_allows_is_not_reported_as_broken(t):
    """The twin. Without it the case above passes on a probe that shouts
    'broken' at every repository."""
    dim_repo(t, hook=QUIET)
    rows = dims_of(t)[1]["rows"]
    if [r for r in rows if "broke" in r["label"]]:
        return "a working guard that allowed the action was reported broken"
    return None


def case_a_scoped_rule_with_nothing_delivering_it_is_reported(t):
    """A rule carrying `paths:` loads when Claude READS a matching file -- not
    when it creates one, and not when it writes through the shell. If nothing
    fills that gap, the rule is silent at the two moments it is worth most."""
    dim_repo(t, files=[(".claude/rules/api.md",
                        "---\npaths:\n  - \"src/**/*.py\"\n---\n\nrule\n")],
             hook=QUIET)
    rows = dims_of(t)[1]["rows"]
    scoped = [r for r in rows if "scoped" in r["label"]]
    if not scoped:
        return "a path-scoped rule with no delivery was not reported"
    if scoped[0]["flag"] != "warn":
        return f"flagged {scoped[0]['flag']!r}, not 'warn'"
    return None


def case_an_unconditional_rule_is_not_reported_as_undelivered(t):
    """A rule with no `paths:` loads at launch, every session. Its problem is
    cost, not delivery, and reporting it here would be an invented finding."""
    dim_repo(t, files=[(".claude/rules/all.md", "always do the thing\n")],
             hook=QUIET)
    rows = dims_of(t)[1]["rows"]
    if [r for r in rows if "scoped" in r["label"]]:
        return "an unconditional rule was reported as undelivered"
    return None


def case_verification_is_found_where_the_repository_put_it(t):
    """`tests/` is not the only shape verification takes.

    This defect was live: a matcher that knew only test-file names read this
    project's own history -- whose checks are called `selftest.py` and live in
    `gates/` -- as 33 code changes out of 33 with nothing behind them."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    # Named so that ONLY its directory makes it verification -- no `test_`,
    # no `check_`, no `selftest`. A matcher that reads file names alone will
    # miss it, which is the defect this case exists for.
    put(t, "tools/gates/thing.py", "def main():\n    return 0\n")
    commit(t, "feat: a change, with a check beside it")
    d3 = dims_of(t, with_blast=False)[3]
    bare = [r for r in d3["rows"] if "verified nothing" in r["label"]]
    if not bare:
        return "the coverage row is missing"
    if not bare[0]["value"].startswith("0/"):
        return (f"a change accompanied by a check in tools/gates/ counted as "
                f"unverified: {bare[0]['value']}")
    return None


def case_a_check_only_its_author_can_run_is_not_coverage(t):
    """A check that hardcodes a path into one person's home directory is inert
    for everybody else, while still looking from outside like coverage.

    Found in the wild by reading, not by measuring: a screenshot check whose
    Chrome path was `/home/<author>/.cache/ms-playwright/...`. It had an
    incident behind it and was counted as a point in the repository's favour.
    Nothing could run it."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    put(t, "scripts/viewcheck.mjs",
        # A placeholder name on purpose. The dimension-1 check reads the
        # *shape* of the path, so `you` exercises it exactly as a real
        # username would -- and a real-looking one in a committed fixture is
        # the thing check_no_machine_paths.py exists to stop.
        "const CHROME = '/home/you/.cache/chrome'\n")
    # The second shape, and the one a home-directory matcher misses. Both were
    # in one real repository: a Linux script and a Windows script, so no single
    # machine could run both, while from outside it looked like coverage.
    put(t, "scripts/shot.mjs",
        "const EDGE = 'C:\\\\Program Files (x86)\\\\Edge\\\\msedge.exe'\n")
    commit(t, "init")
    rows = dims_of(t, with_blast=False)[3]["rows"]
    hit = [r for r in rows if "one machine" in r["label"]]
    if not hit:
        return "a check hardcoding a path only one machine has passed"
    if hit[0]["flag"] != "bad":
        return f"flagged {hit[0]['flag']!r}, not 'bad'"
    if hit[0]["value"] != "2":
        return (f"found {hit[0]['value']} of the two pinned paths — a home "
                f"directory and an install root are the same defect")

    # An absolute path that is an argument, not an installed binary, is fine.
    put(t, "scripts/out.sh", "OUT='/tmp/shot.png'\n")
    commit(t, "chore: an output path")
    rows = dims_of(t, with_blast=False)[3]["rows"]
    again = [r for r in rows if "one machine" in r["label"]]
    if again and again[0]["value"] != "2":
        return f"an ordinary /tmp output path was counted: {again[0]['value']}"

    # A path that DOES resolve here is somebody's working setup, not a defect.
    # It has to match the same shape -- a directory INSIDE a home directory --
    # or this half passes because nothing matched, not because the check held.
    real = os.path.expanduser("~/.claude")
    if not os.path.isdir(real):
        real = os.path.join(os.path.expanduser("~"), os.listdir(
            os.path.expanduser("~"))[0])
    put(t, "scripts/viewcheck.mjs", f"const CHROME = {real!r}\n")
    commit(t, "chore: point it somewhere real")
    os.remove(os.path.join(t, "scripts", "shot.mjs"))
    commit(t, "chore: drop the windows one")
    rows = dims_of(t, with_blast=False)[3]["rows"]
    if [r for r in rows if "one machine" in r["label"]]:
        return "a pinned path that exists on this machine was called dead"
    return None


def case_an_unverified_change_to_the_machinery_is_singled_out(t):
    """Most unverified changes are not worth anyone's attention. A change to
    the thing that does the verifying is, because when it breaks, what would
    have caught the mistake is what changed."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    put(t, "tests/test_app.py", "def test_x():\n    assert True\n")
    commit(t, "init")
    put(t, "app.py", "x = 2\n")
    put(t, ".github/workflows/ci.yml", "on: push\n")
    commit(t, "ci: change the workflow and nothing else")
    rows = dims_of(t, with_blast=False)[3]["rows"]
    hit = [r for r in rows if "machinery" in r["label"]]
    if not hit:
        return "an unverified CI change was not singled out"

    # An ordinary unverified change must not land in that row.
    repo2 = t + "-plain"
    os.makedirs(repo2, exist_ok=True)
    repo(repo2)
    put(repo2, "app.py", "x = 1\n")
    put(repo2, "tests/test_app.py", "def test_x():\n    assert True\n")
    commit(repo2, "init")
    put(repo2, "app.py", "x = 2\n")
    commit(repo2, "feat: a small change with no test")
    rows = dims_of(repo2, with_blast=False)[3]["rows"]
    if [r for r in rows if "machinery" in r["label"]]:
        return "an ordinary unverified change was reported as machinery"
    return None


def case_a_test_suite_is_recognised_by_its_name(t):
    """The other half of the mechanism above: a directory nobody would call a
    check directory, recognised because test suites are named from a small and
    stable vocabulary."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    put(t, "spec/thing.rb", "describe 'x'\n")
    commit(t, "feat: a change, with a spec beside it")
    d3 = dims_of(t, with_blast=False)[3]
    bare = [r for r in d3["rows"] if "verified nothing" in r["label"]]
    if not bare[0]["value"].startswith("0/"):
        return (f"a change accompanied by spec/ counted as unverified: "
                f"{bare[0]['value']}")
    return None


def case_the_instrument_leaves_nothing_in_the_repository(t):
    """Assessing must not change the thing being assessed.

    `factsheet.py --full` defaulted its bench directory to `<root>/.assess`
    and left 2.6 MB of clone untracked in a repository whose own page says
    nothing in it was executed. Found by pointing the assessor at somebody
    else's repository and reading what it complained about afterwards."""
    repo(t)
    put(t, "app.py", "def double(n):\n    return n + n\n")
    put(t, "tests/test_app.py",
        "from app import double\n\n\ndef test_double():\n"
        "    assert double(2) == 4\n")
    commit(t, "feat: double")
    # A replayable defect, or the replay abstains before it ever builds the
    # bench directory this case exists to look for.
    put(t, "app.py", "def double(n):\n    return n * 2\n")
    put(t, "tests/test_app.py",
        "from app import double\n\n\ndef test_double():\n"
        "    assert double(3) == 6\n")
    commit(t, "fix: double was addition, which is only right for 2")
    before = sorted(os.listdir(t))

    out = subprocess.run(
        [sys.executable, os.path.join(HERE, "factsheet.py"), "--root", t,
         "--full"], capture_output=True, text=True, timeout=900)
    if out.returncode not in (0, 2):
        return f"factsheet exited {out.returncode}: {out.stderr[-200:]}"

    left = [n for n in sorted(os.listdir(t)) if n not in before]
    if left:
        return (f"the assessment left {left} behind in the repository it was "
                f"only supposed to read")

    dirty = git(["status", "--porcelain"], t).stdout.strip()
    if dirty:
        return f"the assessment left the working tree dirty: {dirty[:120]}"
    return None


def case_a_replay_that_could_not_run_is_not_a_clean_sheet(t):
    """A ladder of zeros is not a perfect score.

    This was live: a repository whose two replayable defects both failed for
    want of an installed dependency came out as "0 of 2 defects survive past
    the end of a session", flagged green. `catch.py` had reported both rows as
    unusable, with the missing module named; the dimension counted rungs and
    threw the reason away. Exit 2 means COULD NOT JUDGE, and so does this."""
    probe = load_probe().probe(dim_repo(t))
    unusable = {"rows": [
        {"sha": "aaaa", "subject": "x", "rung": None,
         "detail": "unusable — at the fix the tests are could-not-run: "
                   "No module named 'sqlalchemy'"},
        {"sha": "bbbb", "subject": "y", "rung": None, "detail": "unusable — x"},
    ]}
    supply = {"replayable": 2, "fix_no_test": 0, "has_test_files": True,
              "shallow": False}
    d2 = dim_mod.assess(t, probe, None, unusable, "", supply, None,
                        catch_mod.LADDER)[1]
    if d2["state"] != "abstained":
        return (f"two unusable replays produced state {d2['state']!r} and "
                f"headline {d2['headline']!r}, not an abstention")
    if not any("sqlalchemy" in r["note"] for r in d2["rows"]):
        return "the abstention does not say what stopped the replay"

    # And one usable row among unusable ones must still be measured, with the
    # unusable ones outside the count rather than inside it as successes.
    mixed = {"rows": [dict(unusable["rows"][0]),
                      {"sha": "cccc", "subject": "z", "rung": "never",
                       "detail": ""}]}
    d2 = dim_mod.assess(t, probe, None, mixed, "", supply, None,
                        catch_mod.LADDER)[1]
    if d2["state"] != "measured" or "1 of 1" not in d2["headline"]:
        return (f"a mix of one usable and one unusable replay gave "
                f"{d2['state']!r}: {d2['headline']!r}")
    return None


def case_a_rung_says_when_and_also_how_long(t):
    """A rung name says the order. Only seconds say the size of the step.

    The ladder's whole claim is that the gap between `local-suite` and `ci` is a
    cliff and not a slope, and a list of rung names cannot support that claim --
    `local-suite:1 ci:1` reads as two adjacent things. The seconds row is what
    makes the gap arguable, so it has to be on the page whenever any instance
    carries a time."""
    probe = load_probe().probe(dim_repo(t))
    supply = {"replayable": 2, "fix_no_test": 0, "has_test_files": True,
              "shallow": False}
    caught = {"ci_seconds": 512.0, "rows": [
        {"sha": "aaaa", "subject": "x", "rung": "local-suite", "detail": "",
         "seconds": 3.2},
        {"sha": "bbbb", "subject": "y", "rung": "ci", "detail": "",
         "seconds": 512.0},
    ]}
    d2 = dim_mod.assess(t, probe, None, caught, "", supply, None,
                        catch_mod.LADDER)[1]
    timed = [r for r in d2["rows"] if "how long" in r["label"]]
    if not timed:
        return ("two instances carried times and the page shows no seconds -- "
                "the cliff is then a claim with no number under it")
    value = timed[0]["value"]
    if "local-suite:3s" not in value or "ci:9m" not in value:
        return f"the seconds row reads {value!r}, which is not what was measured"
    return None


def case_ci_seconds_that_cannot_be_read_are_not_zero(t):
    """No CI history is an abstention, not a fast CI.

    The tempting shortcut is to time the CI command on this machine. That
    number is real and it is a measurement of the wrong thing: what a person
    waits for at rung 3 includes a queue and a runner that do not exist here,
    so a local timing makes the cliff look like a step. When the repository's
    own history cannot be read, the row must say so."""
    probe = load_probe().probe(dim_repo(t))
    supply = {"replayable": 1, "fix_no_test": 0, "has_test_files": True,
              "shallow": False}
    blind = {"ci_seconds": None, "rows": [
        {"sha": "aaaa", "subject": "x", "rung": "ci", "detail": "",
         "seconds": None}]}
    d2 = dim_mod.assess(t, probe, None, blind, "", supply, None,
                        catch_mod.LADDER)[1]
    timed = [r for r in d2["rows"] if "how long" in r["label"]]
    if timed:
        return (f"with no readable CI history the page still printed a time: "
                f"{timed[0]['value']!r}")

    # And `ci_seconds` itself must abstain rather than invent a number when the
    # subject has no runs to read -- a plain git repository with no remote.
    if catch_mod.ci_seconds(repo(t)) is not None:
        return "ci_seconds returned a number for a repository with no CI runs"
    return None


def case_the_page_says_there_is_only_one_way_in(t):
    """One injection is a finding about the instrument, and must be printed.

    Dimension 2 replays defects this repository actually shipped, which makes
    every instance real -- and means the page is silent about every failure mode
    that never became a commit here. A reader who is not told that reads a good
    ladder as "this repository catches defects", when what it says is "this
    repository catches the kind of defect it has already caught once"."""
    probe = load_probe().probe(dim_repo(t))
    supply = {"replayable": 3, "fix_no_test": 0, "has_test_files": True,
              "shallow": False}
    d2 = dim_mod.assess(t, probe, None, None, "", supply, None,
                        catch_mod.LADDER)[1]
    said = [r for r in d2["rows"] if "how the defect got in" in r["label"]]
    if not said:
        return "the page does not say how the defect was introduced at all"
    note = said[0]["value"] + " " + said[0]["note"]
    if "1 way" not in said[0]["value"]:
        return f"the count of injection routes is not stated: {said[0]['value']!r}"
    if "mutated" not in note:
        return ("the row does not say what is NOT done -- a reader cannot tell "
                "which failure modes this page never looked for")
    return None


def case_the_replay_runs_unless_it_is_refused(t):
    """`--full` was opt-in, and dimension 2 therefore abstained almost always.

    A flag guarding the page's headline measurement, which nobody remembers to
    pass, is a measurement that does not happen. It is on by default now, and
    the cost is announced before it is spent rather than explained afterwards.
    This case holds both halves: the default, and the pre-flight line."""
    src = os.path.join(PARENT, "assess", "factsheet.py")
    out = subprocess.run([sys.executable, src, "--help"],
                         capture_output=True, text=True, timeout=120)
    if "--no-full" not in out.stdout:
        return "there is no --no-full: the replay cannot be refused"
    if "--full " in out.stdout.replace("--no-full", ""):
        return ("--full is still a flag, so the replay is still opt-in and "
                "dimension 2 will keep abstaining by default")
    return None


CASES = [
    ('a guard that crashes is not read as having allowed the action',
     case_a_guard_that_crashes_is_not_read_as_allowed),
    ('a guard that allows is not reported as broken',
     case_a_guard_that_allows_is_not_reported_as_broken),
    ('a path-scoped rule with nothing delivering it is reported',
     case_a_scoped_rule_with_nothing_delivering_it_is_reported),
    ('an unconditional rule is not reported as undelivered',
     case_an_unconditional_rule_is_not_reported_as_undelivered),
    ('verification is found where the repository put it',
     case_verification_is_found_where_the_repository_put_it),
    ('a check only one machine can run is not counted as coverage',
     case_a_check_only_its_author_can_run_is_not_coverage),
    ('an unverified change to the machinery itself is singled out',
     case_an_unverified_change_to_the_machinery_is_singled_out),
    ('a test suite is recognised by its name, wherever it lives',
     case_a_test_suite_is_recognised_by_its_name),
    ('the instrument leaves nothing behind in the repository it read',
     case_the_instrument_leaves_nothing_in_the_repository),
    ('a replay that could not run is not scored as a clean sheet',
     case_a_replay_that_could_not_run_is_not_a_clean_sheet),
    ('a rung says when a defect was caught, and also how long that took',
     case_a_rung_says_when_and_also_how_long),
    ('a CI time that cannot be read abstains rather than reading as fast',
     case_ci_seconds_that_cannot_be_read_are_not_zero),
    ('the page says there is only one way a defect is introduced',
     case_the_page_says_there_is_only_one_way_in),
    ('the defect replay runs unless it is explicitly refused',
     case_the_replay_runs_unless_it_is_refused),
]
