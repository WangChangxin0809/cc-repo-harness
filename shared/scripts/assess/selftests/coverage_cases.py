#!/usr/bin/env python3
"""Assessment selftest cases: coverage: what the ladder cannot speak about.

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
import subprocess

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _support import (
    BLOCKER,
    HERE,
    _DFX,
    _layer_row,
    _mutable_repo,
    blast_mod,
    catch_mod,
    commit,
    dim_mod,
    git,
    hook_script,
    judge_mod,
    put,
    repo,
    run_mod,
)



# --------------------------------------------------------------------------
# coverage: what the ladder cannot speak about
# --------------------------------------------------------------------------


def case_a_wired_layer_that_caught_nothing_is_not_an_absent_one(t):
    """`before-write: 0` meant two different things and printed one character.

    Either nothing is wired at that moment, or several hooks are wired and not
    one of them caught anything. The second is much the worse finding and it
    was indistinguishable from the first, because a rung cannot be read without
    knowing what stands behind it. Measured on this repository the day the row
    was added: two PreToolUse hooks wired, zero of 26 injected defects caught
    by either."""
    # `same-turn` rather than `before-write`, deliberately. A PostToolUse hook
    # runs the repository's checks, so one that catches nothing while defects
    # walk past it is exactly the finding this row exists for. `before-write`
    # cannot be read that way and has a case of its own below.
    silent = _layer_row({"PreToolUse": 0, "PostToolUse": 2},
                        {"local-suite": 14})
    if "2 hook(s), 0 of 14 caught" not in silent["value"]:
        return (f"a wired hook that caught nothing is not reported as wired: "
                f"{silent['value']!r}")
    if "before-write: none wired" not in silent["value"]:
        return "a moment with no hooks is not reported as unwired"
    if silent["flag"] != "bad":
        return ("a layer that is wired and silent is not flagged — that is "
                "the worse of the two readings and it has to outrank the "
                "layer that simply does not exist")

    absent = _layer_row({"PreToolUse": 0, "PostToolUse": 0},
                        {"local-suite": 14})
    if "same-turn: none wired" not in absent["value"]:
        return f"an absent layer is reported as present: {absent['value']!r}"
    if absent["flag"] == "bad":
        return ("a repository with nothing wired is flagged as harshly as one "
                "whose wiring does not work")

    # And a third state the first version of this row got wrong. The walk
    # stops at the first red, so when the top rungs catch everything the ones
    # below them show 0 because nothing ever reached them. Flagging that would
    # report a repository that catches defects early as one whose suite is
    # broken -- the exact opposite of the truth.
    early = _layer_row({"PreToolUse": 2, "PostToolUse": 1},
                       {"before-write": 3, "same-turn": 1}, ci="ci.sh")
    if "local-suite" not in early["value"] or "nothing reached it" not in \
            early["value"]:
        return (f"a rung nothing reached is reported as a rung that failed: "
                f"{early['value']!r}")
    if early["flag"] == "bad":
        return ("a repository that caught every defect before it was written "
                "is flagged for the rungs those defects never reached")
    return None


def case_a_rule_is_a_layer_with_no_rung(t):
    """A sentence saying *never do X* is trying to stop the same defect.

    It cannot be measured by injection -- firing a payload at a document does
    nothing -- so it is counted and marked, and given no rung. Testing it
    honestly would mean handing an agent the rule and the task and seeing
    whether it writes the defect anyway: stochastic, expensive, unrepeatable.
    Counting it as a rung would credit the repository for a layer nobody can
    show working."""
    value = {"prohibitions": 5, "already_enforced": [{"text": "x"}]}
    row = _layer_row({"PreToolUse": 1, "PostToolUse": 0},
                     {"before-write": 1}, value)
    if "rule: 4 unenforced" not in row["value"]:
        return (f"the 4 prohibitions no guard backs were not counted: "
                f"{row['value']!r}")
    if "no rung" not in row["value"]:
        return "a rule was listed without saying it has no rung"
    for k in catch_mod.LADDER:
        if f"rule: 4 unenforced, {k}" in row["value"]:
            return "a rule was given a rung on the ladder"

    covered = {"prohibitions": 2,
               "already_enforced": [{"text": "x"}, {"text": "y"}]}
    row2 = _layer_row({"PreToolUse": 1, "PostToolUse": 0},
                      {"before-write": 1}, covered)
    if "rule:" in row2["value"]:
        return ("prohibitions a guard already enforces were counted as an "
                "unenforced layer as well — they are the guard, twice")
    return None


def case_a_hook_that_could_not_run_is_not_a_layer_that_failed(t):
    """A `matcher: "Bash"` guard is never asked about an edit.

    The ladder introduces defects by editing files, so it fires Edit payloads.
    Claude Code would never send one to a hook wired for Bash. Firing it anyway
    does two wrong things at once: it counts a layer as wired that cannot see
    this class of defect at all, and if such a hook ever did block, the ladder
    would record a `before-write` catch that could not happen in reality.

    Measured on this repository, whose destructive-command guards are Bash-only
    by design: the inventory row read `before-write: 2 hook(s), 0 of 16 caught`
    when only one of the two could ever have run. That is an accusation against
    a guard for not doing a job it was never given."""
    if catch_mod.matches("Bash", "Edit"):
        return "a Bash-only hook is treated as applying to an edit"
    if not catch_mod.matches("Bash|Write|Edit|MultiEdit", "Edit"):
        return "an alternation naming Edit is not treated as applying to it"
    for wide in ("", "*", ".*"):
        if not catch_mod.matches(wide, "Edit"):
            return f"the catch-all matcher {wide!r} excluded a tool"

    repo(t)
    put(t, "app.py", "def add(a, b):\n    return a + b\n")
    put(t, ".claude/block.py", BLOCKER)
    put(t, ".claude/settings.json", json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [
            {"type": "command",
             "command": f'python3 "{os.path.join(t, ".claude/block.py")}"'}]}]}}))
    commit(t, "chore: a Bash-only guard")
    pre = catch_mod.applicable(catch_mod.wired(t, "PreToolUse"), "Edit")
    if pre:
        return (f"{len(pre)} Bash-only hook(s) were selected for an Edit "
                f"payload — the ladder would ask them a question Claude Code "
                f"never asks")
    if not catch_mod.applicable(catch_mod.wired(t, "PreToolUse"), "Bash"):
        return "the Bash-only hook was excluded from Bash payloads too"
    return None


def case_the_default_branch_is_not_the_one_that_happens_to_be_out(t):
    """A clone inherits the source's checkout as its `origin/HEAD`.

    Cloning from a local path copies the source repository's *checked-out
    branch* into `origin/HEAD`, not its default. So a clone taken while
    somebody was on a feature branch reports that feature branch as the
    default, the force-push probe is aimed at a branch nothing protects, the
    guard correctly allows it, and the page says `force-push the default
    branch: nothing stops it` about a repository that refuses exactly that.

    Found by assessing a clone of this repository: dimension 1 read 1 of 6
    with three working guards in the tree. A wrong headline produced by a
    correct guard is the worst kind, because nothing looks broken."""
    src = os.path.join(t, "src")
    os.makedirs(src)
    repo(src)
    put(src, "a.txt", "x\n")
    commit(src, "feat: first")
    git(["branch", "feature/work"], src)
    git(["checkout", "-q", "feature/work"], src)
    put(src, "b.txt", "y\n")
    commit(src, "feat: second")

    dst = os.path.join(t, "clone")
    git(["clone", "-q", src, dst], t)
    head = git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
               dst).stdout.strip()
    if not head.endswith("feature/work"):
        return (f"the fixture was supposed to produce a clone whose "
                f"origin/HEAD is the feature branch and gave {head!r}")

    got = blast_mod.default_branch(dst)
    if got != "main":
        return (f"the probe would be aimed at {got!r} — a branch nothing "
                f"protects — so a repository that refuses force-pushes to "
                f"main would be reported as refusing nothing")

    git(["checkout", "-q", "main"], dst)
    if blast_mod.default_branch(dst) != "main":
        return "standing on the default branch changed what the default is"

    # And where `origin` is a real remote, `origin/HEAD` must still be
    # trusted: a repository whose default is genuinely `develop` or
    # `release` must not be dragged to `main` because the name exists.
    git(["remote", "set-url", "origin", "https://example.invalid/x.git"], dst)
    if blast_mod.default_branch(dst) != "feature/work":
        return ("with a real remote, origin/HEAD was overruled — a repository "
                "whose default is not conventionally named would be measured "
                "on the wrong branch")
    return None


def case_mutation_reaches_the_page_only_when_asked(t):
    """`--mutate` is off by default, and off has to mean the page says so.

    The replay's cost is bounded by the page -- three defects, three suite
    runs. Mutation's is chosen by the caller, so it is the one thing here that
    must be asked for. What must NOT happen is the page quietly reading the
    same either way: a dimension that shows the same rows whether or not the
    expensive half ran is a dimension nobody can tell has abstained."""
    cmd = _mutable_repo(t)
    off = dim_mod.change_validation(_DFX, None, "", catch_mod.LADDER)
    how = [r for r in off["rows"] if r["label"] == "how the defect got in"]
    if not how or not how[0]["value"].startswith("1 way"):
        return f"without --mutate the page does not say one injection ran: {how}"

    run, why = run_mod.assess(t, 6, work=os.path.join(t, "..", "w-" +
                                                      os.path.basename(t)),
                              command=cmd)
    if run is None:
        return f"the fixture could not be mutated at all: {why}"
    on = dim_mod.change_validation(_DFX, None, "", catch_mod.LADDER, run)
    how = [r for r in on["rows"] if r["label"] == "how the defect got in"]
    if not how or not how[0]["value"].startswith("2 ways"):
        return f"with mutation the page still reports one injection: {how}"

    # The replay abstained in both calls. Mutation walked the ladder, so the
    # dimension WAS measured -- reporting it as unmeasured would throw away
    # something somebody paid for.
    if on["state"] != "measured":
        return (f"mutation walked the ladder and the dimension still reports "
                f"{on['state']!r}")
    if off["state"] == "measured":
        return "the dimension claims a measurement with neither injection run"

    # And off by default has to be the CLI's answer too, not only this
    # function's. The test command has to be supplied here or the check is
    # vacuous: the ecosystem table does not recognise this fixture, mutation
    # would abstain for that reason instead of for being switched off, and a
    # planted `default=8` sailed straight through this case.
    out = subprocess.run(
        [sys.executable, os.path.join(HERE, "factsheet.py"), "--root", t,
         "--no-full", "--test-command", " ".join(cmd)],
        capture_output=True, text=True, timeout=600)
    if "2 ways" in out.stdout:
        return "the default run mutated the repository without being asked"
    if "1 way" not in out.stdout:
        return "the default run says nothing about how a defect got in"
    return None


def case_a_mutant_walks_the_same_ladder_as_a_real_defect(t):
    """The whole point of the second injection, and what it got wrong first.

    A mutant was scored `killed` or `survived` -- did the test suite notice --
    which is a narrower question than this dimension's and answers it at one
    rung out of five. But a mutant is a change to a file, so every moment that
    can see a change can see it: a PreToolUse hook that refuses the write is a
    defect that never reached the disk, not a defect the suite missed.

    So the mutant walks the same five rungs a defect from the repository's own
    history walks, and both are counted in one ladder."""
    cmd = _mutable_repo(t)
    work = os.path.join(t, "..", "w-" + os.path.basename(t))

    # No hooks: the suite is the first thing that can catch anything.
    plain, why = run_mod.assess(t, 6, work=work + "-a", command=cmd)
    if plain is None:
        return f"the fixture could not be mutated at all: {why}"
    if not plain["ladder"].get("local-suite"):
        return (f"nothing reached the suite rung on a fixture whose tests do "
                f"assert: {plain['ladder']}")
    if plain["ladder"].get("before-write"):
        return "a rung fired with no hooks wired at all"

    # Now wire a hook that refuses every write. The same mutants must now be
    # caught at the TOP of the ladder, not at the suite.
    hook_script(t, ".claude/block.py", BLOCKER)
    commit(t, "chore: a hook that refuses writes")
    hooked, why = run_mod.assess(t, 6, work=work + "-b", command=cmd)
    if hooked is None:
        return f"the fixture stopped being mutable once a hook existed: {why}"
    if not hooked["ladder"].get("before-write") and not hooked["false_block"]:
        return (f"a hook that refuses every write caught nothing: "
                f"{hooked['ladder']}")
    return None


def case_a_hook_that_refuses_everything_gets_no_rung(t):
    """A guard that says no to the fix as well has discriminated nothing.

    `catch.false_block` asks this of a replayed defect, and it has to be asked
    of a mutant too. Otherwise the best rung on the ladder goes to the least
    discriminating check in the repository, and a repository could top the
    measurement by refusing all edits."""
    cmd = _mutable_repo(t)
    hook_script(t, ".claude/block.py", BLOCKER)
    commit(t, "chore: a hook that refuses writes")
    r, why = run_mod.assess(t, 6, work=os.path.join(t, "..", "w-" +
                                                    os.path.basename(t)),
                            command=cmd)
    if r is None:
        return f"nothing could be mutated: {why}"
    if not r["false_block"]:
        return ("a hook that refuses the original line too was not recorded "
                "as a false block")
    if r["ladder"].get("before-write"):
        return ("a hook that refuses everything was still given the top rung "
                "of the ladder")
    return None


def case_an_uncaught_mutant_is_pending_until_it_is_judged(t):
    """`never` is only a failure if the thing never caught was worth catching.

    A mutant nothing catches is not yet a defect: the paper's own figure says
    roughly three survivors in ten are lines nothing should assert about. So
    an unjudged one is reported `pending` and is NOT parked at `never` --
    counting it there would make a repository look worse for having bought a
    measurement nobody has finished reading. The agent's verdict is what turns
    it into a defect, or removes it from the count entirely."""
    cmd = _mutable_repo(t)
    run, why = run_mod.assess(t, 6, work=os.path.join(t, "..", "w-" +
                                                      os.path.basename(t)),
                              command=cmd)
    if run is None:
        return f"nothing could be mutated: {why}"
    if not run["survived"]:
        return ("nothing reached `never` on a fixture built to have a line "
                "the tests execute without asserting about")

    counts, pending, real, dropped = dim_mod.mutant_ladder(run, None)
    if counts.get("never"):
        return (f"{counts['never']} unjudged mutant(s) were parked at `never` "
                f"before anybody said they were defects")
    if pending != run["survived"]:
        return f"{run['survived']} uncaught, but {pending} reported pending"

    ids = [i for i in range(run["survived"])]
    yes = {"verdicts": [{"id": i, "verdict": "productive", "why": "real"}
                        for i in ids]}
    counts, pending, real, dropped = dim_mod.mutant_ladder(
        run, judge_mod.grade(run, yes))
    if counts.get("never") != run["survived"] or pending:
        return (f"judged real, they did not land at `never`: "
                f"{counts.get('never')} never, {pending} pending")

    no = {"verdicts": [{"id": i, "verdict": "unproductive", "why": "no test"}
                       for i in ids]}
    counts, pending, real, dropped = dim_mod.mutant_ladder(
        run, judge_mod.grade(run, no))
    if counts.get("never") or pending:
        return ("a change judged not worth a test still counts against the "
                "repository")
    if len(dropped) != run["survived"]:
        return f"{len(dropped)} dropped, expected {run['survived']}"
    return None


def case_a_caveat_outranks_the_figure_it_qualifies(t):
    """A ladder taken over a flaky suite is not a ladder.

    Both caveats are about the same failure: the mutation numbers look like
    the paper's and are not comparable to them. Printing them below the rows
    they disqualify invites exactly the comparison they exist to refuse."""
    run = {"killed": 8, "survived": 2, "generated": 10, "suppressed": 3,
           "broken": 0, "timeout": 0, "unplaceable": 0, "survivability": 0.2,
           "seconds": 4.0, "command": "pytest", "flaky": True,
           "false_block": 0,
           "ladder": {"before-write": 0, "same-turn": 0, "local-suite": 8,
                      "ci": 0, "never": 2},
           "coverage": "NOT available — the covered-line restriction was "
                       "dropped",
           "rows": [{"verdict": "survived", "path": "a.py", "line": 3,
                     "operator": "AOR", "before": "a + b", "after": "a - b"}]}
    rows = dim_mod.mutation_rows(run, catch_mod.LADDER, None)
    labels = [r["label"] for r in rows]
    body = labels.index("mutants nothing caught, awaiting judgement")
    for caveat in ("!! the suite is flaky", "!! coverage was not available"):
        if caveat not in labels:
            return f"the page does not carry the caveat {caveat!r} at all"
        if labels.index(caveat) > body:
            return f"{caveat!r} is printed below the rows it disqualifies"
        if [r for r in rows if r["label"] == caveat][0]["flag"] != "warn":
            return f"{caveat!r} is not flagged, so it reads as a footnote"

    clean = dict(run, flaky=False, coverage="measured — 40 line(s) executed")
    labels = [x["label"] for x in
              dim_mod.mutation_rows(clean, catch_mod.LADDER, None)]
    if [x for x in labels if x.startswith("!!")]:
        return f"a clean run still prints a caveat: {labels}"
    return None


def case_the_brief_asks_about_the_whole_ladder(t):
    """What the agent is judging changed, so what it is told had to change.

    It used to be handed changes "the suite did not notice". It is now handed
    changes NOTHING caught -- no hook before the write, no hook after, not the
    suite, not CI -- and told that its verdict decides whether each one counts
    as a defect at all. An agent judging the narrower question would be
    answering about a measurement that no longer exists."""
    cmd = _mutable_repo(t)
    run, why = run_mod.assess(t, 6, work=os.path.join(t, "..", "w-" +
                                                      os.path.basename(t)),
                              command=cmd)
    if run is None:
        return f"nothing could be mutated: {why}"
    got, _why = judge_mod.brief(run, t)
    if got is None or not got["index"]:
        return "no brief was produced for the uncaught changes"
    if "def " not in got["prompt"]:
        return ("the brief does not carry the enclosing code, so the judging "
                "pass would be guessing from a diff line")
    low = got["prompt"].lower()
    if "nothing in this repository caught" not in low:
        return "the brief still describes the narrower suite-only question"
    if "leaves the measurement" not in low:
        return ("the brief does not tell the judge that its verdict decides "
                "whether the change is a defect at all")
    return None


def case_an_unanswered_mutant_moves_the_score_neither_way(t):
    """Silence must not be scoreable.

    If unanswered counted as unproductive, a judge could raise productivity by
    answering less; if it counted as productive, by answering less still. Both
    make the number a property of the judge's diligence rather than of the
    mutants."""
    run = {"rows": [{"path": "a.py", "line": i, "operator": "AOR",
                     "before": "+", "after": "-", "verdict": "survived",
                     "detail": ""} for i in range(4)]}
    g = judge_mod.grade(run, {"verdicts": [
        {"id": 0, "verdict": "productive", "why": "x"}]})
    if g["judged"] != 1 or g["unanswered"] != 3:
        return f"judged={g['judged']} unanswered={g['unanswered']}, want 1 and 3"
    if g["productivity"] != 1.0:
        return (f"productivity {g['productivity']} — the three unanswered "
                f"mutants moved a score they should not touch")
    return None


CASES = [
    ('a wired layer that caught nothing is not an absent one',
     case_a_wired_layer_that_caught_nothing_is_not_an_absent_one),
    ('a rule is a layer with no rung',
     case_a_rule_is_a_layer_with_no_rung),
    ('a hook that could not have run is not a layer that failed',
     case_a_hook_that_could_not_run_is_not_a_layer_that_failed),
    ('the default branch is not whichever one happens to be checked out',
     case_the_default_branch_is_not_the_one_that_happens_to_be_out),
    ('mutation reaches the page only when it is asked for',
     case_mutation_reaches_the_page_only_when_asked),
    ('a mutant walks the same ladder as a real defect',
     case_a_mutant_walks_the_same_ladder_as_a_real_defect),
    ('a hook that refuses everything gets no rung',
     case_a_hook_that_refuses_everything_gets_no_rung),
    ('an uncaught mutant is pending until it is judged',
     case_an_uncaught_mutant_is_pending_until_it_is_judged),
    ('the brief asks about the whole ladder, not just the suite',
     case_the_brief_asks_about_the_whole_ladder),
    ('a caveat is printed above the figure it disqualifies',
     case_a_caveat_outranks_the_figure_it_qualifies),
    ('an unanswered mutant moves the score neither way',
     case_an_unanswered_mutant_moves_the_score_neither_way),
]
