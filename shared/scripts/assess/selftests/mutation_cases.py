#!/usr/bin/env python3
"""Assessment selftest cases: mutation: the operators, the suppression, and the ways it lies.

Split out of ``assess/selftest.py`` to keep every file under this
repository's line-count ceiling; see that file for the CLI, exit codes, and
why this selftest exists. Every case here is unchanged from the original --
same name, body, docstring, comments -- and this module's own ``CASES`` list
keeps them in the same order relative to each other that the original single
list held. ``selftest.py`` concatenates every case module's list, so all 192
cases still run, each exactly once.
"""

from __future__ import annotations


import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _support import (
    arid_mod,
    git,
    judge_mod,
    mutate_mod,
    put,
    repo,
    run_mod,
)



# --------------------------------------------------------------------------
# mutation: the operators, the suppression, and the ways it lies
# --------------------------------------------------------------------------

def case_every_operator_offers_every_alternative(t):
    """Mothra replaces an operator with each other operator of its class.

    Getting this wrong is invisible: the tool still produces mutants, still
    runs them, still reports a number. It only shows up against the paper --
    a one-partner AOR gave a 2x reduction in the RQ1 study where the paper
    reports 117x, because a strategy that generates few mutants has little
    left to suppress. The control arm has to be the real control arm."""
    src = "def f(a, b):\n    return a + b\n"
    ops = [m for m in mutate_mod.candidates("f.py", src) if m.op == "AOR"]
    if len(ops) != len(mutate_mod.ARITH) - 1:
        return (f"`a + b` produced {len(ops)} AOR mutant(s); Mothra's AOR "
                f"offers each of the other {len(mutate_mod.ARITH) - 1} "
                f"arithmetic operators")
    src = "def f(a, b):\n    return a < b\n"
    ror = [m for m in mutate_mod.candidates("f.py", src) if m.op == "ROR"]
    if len(ror) != len(mutate_mod.RELATE) - 1:
        return f"`a < b` produced {len(ror)} ROR mutant(s), not 5"
    return None


def case_abs_is_not_an_operator_here(t):
    """The paper excludes ABS, and adding it back would be inventing.

    Their Table 1 lists five operators and says of ABS that it "predominantly
    creates unproductive mutants". A reimplementation that quietly adds a sixth
    because it seemed useful is no longer a reimplementation."""
    src = ("def f(a, b):\n    x = a + b\n    if a < b and a:\n"
           "        return -a\n    return x\n")
    ops = {m.op for m in mutate_mod.candidates("f.py", src)}
    if not ops:
        return "nothing was generated at all"
    if not ops <= {"AOR", "LCR", "ROR", "UOI", "SBR"}:
        return f"an operator outside the paper's five appeared: {ops}"
    return None


def case_the_three_rules_that_paid_for_everything_fire(t):
    """LOG, TIME and FLAG carry the paper's 15% -> 80%, so each must work.

    Not a formality. The LOG rule is two clauses -- a name starting with `log`,
    or a receiver called `logger` -- and it is the one rule the paper validated
    by sampling, at 99 of 100. If it silently matched nothing, everything below
    it in the report would still look plausible."""
    for src, want in (
            # The receiver clause: an object called `logger`.
            ('logger.info("x %s", a + b)\n', "LOG"),
            ('log.debug("x")\n', "LOG"),
            ('logging.warning("x")\n', "LOG"),
            # The **name-prefix** clause, which is the half of the rule the
            # paper validated by sampling. Without a case that reaches it, the
            # prefix regex can be broken outright and every log case still
            # passes through the receiver clause -- which is exactly what
            # happened when this was planted.
            ('log_request(a + b)\n', "LOG"),
            ('logAudit(a + b)\n', "LOG"),
            ('time.sleep(5 * 2)\n', "TIME"),
            ('parser.add_argument("--n", default=1000 * 1000)\n', "FLAG"),
    ):
        hit = arid_mod.arid_line(src, 1)
        if not hit:
            return f"nothing fired on {src.strip()!r}; expected {want}"
        if hit[0] != want:
            return f"{src.strip()!r} fired {hit[0]}, not {want}"
    # And a plain arithmetic line must NOT be arid, or everything is suppressed
    # and the tool reports a clean sheet on every repository.
    if arid_mod.arid_line("total = price * quantity\n", 1):
        return ("an ordinary arithmetic line was marked arid — a rule that "
                "fires on everything suppresses everything")
    return None


def case_a_suppressed_mutant_is_counted_not_discarded(t):
    """The paper never measures what its unsound rules cost. We must.

    Their own words: "Sound heuristics are demonstrably correct, but we have
    had much more important improvements ... from unsound heuristics." An
    unsound rule can suppress a productive mutant, and there is no figure
    anywhere in the paper for how often. Copying the rules is right; copying
    the silence is not, so suppressions are returned with their soundness."""
    src = 'def f(a):\n    logger.info("x %s", a + 1)\n    return a + 1\n'
    mutants = mutate_mod.candidates("f.py", src)
    kept, dropped = mutate_mod.suppress(mutants, {"f.py": src})
    if not dropped:
        return "a mutation inside a logging call was not suppressed at all"
    if not kept:
        return "everything was suppressed, including the line outside the log"
    for _m, hit in dropped:
        if not isinstance(hit, tuple) or len(hit) != 2:
            return f"a suppression came back without its soundness: {hit!r}"
    ids = {h[0] for _m, h in dropped}
    if "LOG" not in ids:
        return f"the logging line was suppressed by {ids}, not LOG"
    return None


def case_only_covered_lines_are_mutated(t):
    """A file the suite never entered is outside the measurement, not inside it.

    This was live and it inverted the policy. When coverage was supplied but a
    file had no entry, `generate` fell through to `lines = None` and mutated
    the file **entirely**. Measured on `tenacity`: every single survivor was in
    `doc/source/conf.py`, a Sphinx config no test executes and none should."""
    repo(t)
    put(t, "app/covered.py", "def f(a, b):\n    return a + b\n")
    put(t, "app/never.py", "def g(a, b):\n    return a * b\n")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "feat: two files"], t)
    covered = {"app/covered.py": {2}}
    mutants, _d, _s = mutate_mod.generate(
        t, ["app/covered.py", "app/never.py"], covered, "arid")
    touched = {m.path for m in mutants}
    if "app/never.py" in touched:
        return ("a file with no coverage entry was mutated — the covered-line "
                "restriction is inverted, which is the bug that put every "
                "survivor in a Sphinx config")
    if "app/covered.py" not in touched:
        return "the covered file was not mutated either"
    return None


def case_a_broken_suite_is_not_a_killed_mutant(t):
    """A mutant that stops the suite loading has tested nothing.

    From outside, a suite that will not import looks exactly like a suite that
    caught something: both are a non-zero exit. Counting the first as a kill
    inflates the score with mutants nothing examined. The paper's own Go
    heuristic A.5.2 exists for this: "the mutant appears killed because the
    test fails (to build)".

    A suite that *hangs* is a third thing again, and it is not hypothetical:
    measured on `tenacity`, a retry library, flipping one comparison in a
    backoff loop ran for 166 seconds against a 2.8 second baseline. Behaviour
    changed observably, and no test asserted anything, so it is neither."""
    put(t, "src.py", "x = 1\n")
    put(t, "suite.py", "import nosuchmodule_xyz\n")
    verdict, _d = run_mod.run_one(t, "src.py", "x = 2\n",
                                  [sys.executable, "suite.py"], "x = 1\n")
    if verdict != "broken":
        return (f"a suite that could not import came back {verdict!r}; a "
                f"mutant that stops the suite loading tested nothing")

    put(t, "slow.py", "import time\ntime.sleep(30)\n")
    verdict, _d = run_mod.run_one(t, "src.py", "x = 2\n",
                                  [sys.executable, "slow.py"], "x = 1\n",
                                  budget=2)
    if verdict != "timeout":
        return (f"a suite that hung came back {verdict!r}, not 'timeout' — a "
                f"hang credits the suite with a catch it did not make")

    # And the original file must be back on disk either way.
    with open(os.path.join(t, "src.py"), encoding="utf-8") as fh:
        if fh.read() != "x = 1\n":
            return "the mutated file was not restored after the run"
    return None


def case_module_level_statements_are_not_deleted(t):
    """A.1.12 excludes declaration statements, and in Python that is module
    scope.

    Measured on `tenacity`: 15 of 40 mutants came back `broken`, and all
    fifteen were module-level deletions or insertions in `__init__.py` --
    deleting `WrappedFn = t.TypeVar("WrappedFn")` does not test anything, it
    stops the module importing, and every test then reports a failure."""
    src = ('import typing as t\n'
           'WrappedFn = t.TypeVar("WrappedFn")\n'
           '_unset = object()\n\n'
           'def f(a, b):\n'
           '    x = a + b\n'
           '    return x\n')
    mutants = mutate_mod.candidates("m.py", src)
    bad = [m for m in mutants if m.line in (2, 3)]
    if bad:
        return (f"module-level declarations were offered for mutation: "
                f"{[(m.line, m.op) for m in bad]}")
    inside = [m for m in mutants if m.line in (6, 7)]
    if not inside:
        return "nothing inside the function body was offered either"
    return None


def case_a_mutant_is_applied_on_the_tree_not_the_text(t):
    """A textual replacement hits the operator inside a string on the same line.

    `return a + b  # use + not -` has three `+` in it and only one of them is
    the operator. Replacing text produces a mutant that compiles, runs, and
    tests something other than what the report says it tested."""
    src = 'def f(a, b):\n    return a + b  # always + here, never -\n'
    ms = [m for m in mutate_mod.candidates("f.py", src)
          if m.op == "AOR" and m.after == "-"]
    if not ms:
        return "no AOR mutant was generated to apply"
    got = run_mod.apply(src, ms[0])
    if got is None:
        return "the mutation could not be applied at all"
    if "a - b" not in got:
        return f"the operator was not the thing that changed: {got!r}"
    return None


def case_an_unplaceable_mutant_is_counted_as_neither(t):
    """A mutation that could not be applied did not happen.

    Scoring it killed inflates the result and scoring it survived deflates it.
    It has to come back as its own thing so the denominator stays honest."""
    src = "def f(a, b):\n    return a + b\n"
    ms = mutate_mod.candidates("f.py", src)
    if not ms:
        return "nothing generated"
    ghost = mutate_mod.Mutant("f.py", 999, 0, "AOR", "+", "-")
    if run_mod.apply(src, ghost) is not None:
        return "a mutation at a line that does not exist was applied anyway"
    return None


def case_a_redundant_short_circuit_guard_is_suppressed(t):
    """The one rule here that came from our own feedback, not the appendix.

    A second pass over 13 surviving mutants in `tenacity` judged 7
    unproductive, and 4 of those 7 were one pattern written twice: an
    `if acc: break` under `acc = acc or f(x)`. The `or` has already stopped
    evaluating, so neither the guard nor the break can change what is
    returned; every mutant on those lines is equivalent.

    That is the paper's own process -- "if we decide a certain mutation is not
    productive ... the rule is added to the expert function" -- and it is the
    only rule in `arid.py` not transcribed from Appendix A, which is why it
    needs a case of its own.

    The second half is what keeps it from becoming a rule that suppresses
    every loop: a guard whose condition is computed *inside* the loop decides
    something, and must survive."""
    redundant = ("def f(rs):\n"
                 "    result = False\n"
                 "    for r in rs:\n"
                 "        result = result or check(r)\n"
                 "        if result:\n"
                 "            break\n"
                 "    return result\n")
    hit = arid_mod.arid_lines(redundant)
    if hit.get(5) is None or hit[5][0] != "SHORTCIRCUIT":
        return (f"the redundant `if result: break` was not suppressed: "
                f"{hit.get(5)}")

    mirror = redundant.replace("result = False", "result = True").replace(
        "result or check(r)", "result and check(r)").replace(
        "if result:", "if not result:")
    if (arid_mod.arid_lines(mirror).get(5) or ("", ""))[0] != "SHORTCIRCUIT":
        return "the `and`/`not` mirror of the same pattern was not suppressed"

    # A guard that decides something must survive, or this rule has silently
    # turned off mutation of every loop in every repository.
    load_bearing = ("def f(items):\n"
                    "    found = False\n"
                    "    for i in items:\n"
                    "        found = check(i)\n"
                    "        if found:\n"
                    "            break\n"
                    "    return found\n")
    if arid_mod.arid_lines(load_bearing).get(5) is not None:
        return ("a guard whose condition is computed inside the loop was "
                "suppressed — that guard decides when the loop stops")

    # And the rule must declare itself unsound, because the loop body could
    # have a side effect the early exit skips.
    if arid_mod.RULES["SHORTCIRCUIT"]["sound"]:
        return "SHORTCIRCUIT claims to be sound; it cannot see side effects"
    return None


def case_productivity_is_reported_with_its_judge_named(t):
    """The paper's 82% comes from the developers who wrote the lines. Ours
    does not, and the page has to say so.

    A number that looks like theirs, computed from a different judge, and
    printed without that difference attached, is the most misleading thing this
    whole module could produce."""
    run = {"rows": [
        {"path": "a.py", "line": 2, "operator": "AOR", "before": "+",
         "after": "-", "verdict": "survived", "detail": ""},
        {"path": "a.py", "line": 5, "operator": "ROR", "before": "<",
         "after": "<=", "verdict": "survived", "detail": ""},
        {"path": "a.py", "line": 9, "operator": "SBR", "before": "x = 1",
         "after": "(deleted)", "verdict": "killed", "detail": ""},
    ]}
    g = judge_mod.grade(run, {"verdicts": [
        {"id": 0, "verdict": "productive", "why": "the boundary is a promise"},
        {"id": 1, "verdict": "unproductive", "why": "off by one epsilon"}]})
    if g["survivors"] != 2:
        return f"killed mutants leaked into the judged set: {g['survivors']}"
    if abs(g["productivity"] - 0.5) > 1e-9:
        return f"productivity computed as {g['productivity']}, not 0.5"
    if "agent" not in g["judge"] or "wrote" not in g["judge"]:
        return "the judge is not named in the output"
    text = judge_mod.render(g)
    if "70" not in text or "MISSED" not in text:
        return "the bar and whether it was met are not both printed"
    return None
# --------------------------------------------------------------------------
# the second injection, on the page
# --------------------------------------------------------------------------


CASES = [
    ('every operator offers every alternative, as Mothra does',
     case_every_operator_offers_every_alternative),
    ('ABS is not an operator here, because the paper excludes it',
     case_abs_is_not_an_operator_here),
    ('the three heuristics that carried 15% -> 80% all fire',
     case_the_three_rules_that_paid_for_everything_fire),
    ('a suppressed mutant is counted with its soundness, not discarded',
     case_a_suppressed_mutant_is_counted_not_discarded),
    ('only covered lines are mutated, and an uncovered file is skipped',
     case_only_covered_lines_are_mutated),
    ('a suite that could not load is not a killed mutant',
     case_a_broken_suite_is_not_a_killed_mutant),
    ('module-level declarations are not deleted',
     case_module_level_statements_are_not_deleted),
    ('a mutant is applied on the tree, not on the text',
     case_a_mutant_is_applied_on_the_tree_not_the_text),
    ('a mutation that could not be placed is counted as neither',
     case_an_unplaceable_mutant_is_counted_as_neither),
    ('a redundant short-circuit guard is suppressed, a real one is not',
     case_a_redundant_short_circuit_guard_is_suppressed),
    ('productivity is reported with its judge named',
     case_productivity_is_reported_with_its_judge_named),
]
