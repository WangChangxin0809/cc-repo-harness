#!/usr/bin/env python3
"""Assessment selftest cases: value: what the standing context is spent ON (part 1).

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
    GCOV,
    GOCOVER,
    HERE,
    LCOV,
    _bare_row,
    _doc,
    _intercept,
    _observable_repo,
    _report,
    _subjects_of,
    _traceable_repo,
    _typed_history,
    _workflow,
    catch_mod,
    commit,
    conflict_mod,
    cover_mod,
    dim_mod,
    dim_repo,
    dims_of,
    git,
    merge_mod,
    observe_mod,
    put,
    repo,
    run_mod,
    value_mod,
)



# --------------------------------------------------------------------------
# value: what the standing context is spent ON
# --------------------------------------------------------------------------

def case_a_supplied_test_command_is_used(t):
    """The ecosystem table is a fast path, not the only path.

    It knows a handful of conventions -- a `tests/` directory plus a packaging
    marker, a `package.json`, a `Cargo.toml`. Measured: of five real Python
    repositories cloned to test the mutation work, it produced a green suite
    for **one**. This repository is another miss; its suites are `selftest.py`
    scripts, so dimension 2 abstained on its own author while a perfectly good
    suite sat in the tree.

    Unit tests may also simply not exist, and reporting that is correct. What
    must not happen is abstaining because a table did not recognise a
    convention, when an agent could have read the CI file and said."""
    repo(t)
    put(t, "app/calc.py", "def add(a, b):\n    return a - b\n")
    # Named test-shaped so the history miner recognises the fix as one that
    # touched a test; kept OUT of a `tests/` directory so the ecosystem table
    # still cannot guess how to run it. The fixture has to defeat exactly one
    # of the two, or it is not testing what it says.
    put(t, "test_calc.py",
        "import sys, os\n"
        "sys.path.insert(0, os.path.dirname(__file__))\n"
        "from app.calc import add\n"
        "sys.exit(0 if add(2, 3) == 5 else 1)\n")
    put(t, "app/__init__.py", "")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "feat: a calculator"], t)
    put(t, "app/calc.py", "def add(a, b):\n    return a + b\n")
    put(t, "test_calc.py",
        open(os.path.join(t, "test_calc.py")).read()
        + "sys.exit(0 if add(1, 1) == 2 else 1)\n")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "fix: add was subtracting"], t)

    # The table cannot see this suite: no tests/ directory, no packaging marker.
    _eco, guessed = catch_mod.find(t)
    if guessed is not None:
        return (f"the fixture was supposed to defeat the ecosystem table and "
                f"did not: it guessed {guessed}")

    work = os.path.join(t, "..", "work-" + os.path.basename(t))
    r, why = catch_mod.assess(t, 1, work)
    if r is not None:
        return "the table found a command it should not have"
    if "--test-command" not in why:
        return (f"the abstention does not mention how to supply a command: "
                f"{why!r}")

    r, why = catch_mod.assess(t, 1, work + "-2",
                              command=[sys.executable, "test_calc.py"])
    if r is None:
        return f"a supplied test command was not used: {why}"
    if not r["rows"]:
        return "the command was accepted and nothing was replayed"
    return None


def case_a_prohibition_a_guard_enforces_is_named(t):
    """The sharpest row on dimension 5, and it needs dimension 1 to exist.

    A rule saying *never force-push to main* in a repository whose hooks were
    **measured refusing** force-pushes to main is paying tokens on every turn
    to restate a thing that cannot happen. The guard is strictly better: not
    optional, does not depend on the agent having read anything, costs nothing
    until it fires.

    The cross-reference is to what dimension 1 *measured*, not to what the
    settings claim. A prohibition restating a guard that does not fire is the
    one sentence on the floor that is definitely earning its place."""
    repo(t)
    put(t, "CLAUDE.md",
        "# Rules\n\n"
        "Never force-push to main. It overwrites other people's commits.\n\n"
        "Always run the tests before you open a pull request.\n\n"
        "The billing service talks to the ledger over gRPC.\n")
    stopped = {"rows": [{"probe": "force-push the default branch",
                         "stopped": True, "false_block": False}]}
    guards = value_mod.guards_from_blast(stopped)
    if "force push" not in guards:
        return f"dimension 1's refusal did not map to a rule topic: {guards}"
    r = value_mod.assess(t, guards)
    if not r["already_enforced"]:
        return ("a prohibition against the exact thing the hooks were measured "
                "refusing was not reported")

    # And a guard that does NOT fire must leave the sentence alone.
    open_ = {"rows": [{"probe": "force-push the default branch",
                       "stopped": False, "false_block": False}]}
    r2 = value_mod.assess(t, value_mod.guards_from_blast(open_))
    if r2["already_enforced"]:
        return ("a prohibition was called redundant while the guard it "
                "restates does not actually refuse anything")

    # A guard that refuses the legitimate action too has discriminated nothing
    # and must not count as enforcement either.
    false = {"rows": [{"probe": "force-push the default branch",
                       "stopped": True, "false_block": True}]}
    if value_mod.guards_from_blast(false):
        return "a guard that refuses everything was counted as enforcement"
    return None


def case_prohibitions_and_requirements_are_counted_apart(t):
    """Both are legitimate; they are not doing the same work.

    A prohibition earns its place against a mistake somebody actually makes. A
    requirement is working every time the thing it requires comes up. A floor
    that is nine-tenths `don't` is usually a list of one-off incidents nobody
    deleted, and a single token count cannot see the difference."""
    repo(t)
    put(t, "CLAUDE.md",
        "Never commit generated files.\n\n"
        "Do not edit the vendored code.\n\n"
        "Always regenerate the client after changing the schema.\n\n"
        "The parser lives in src/parse and is generated from grammar.ebnf.\n")
    r = value_mod.assess(t, ())
    if r is None:
        return "nothing was read from a CLAUDE.md that is plainly there"
    if r["prohibitions"] < 2:
        return f"two prohibitions were not counted: {r['kinds']}"
    if r["requirements"] < 1:
        return f"the requirement was not counted: {r['kinds']}"
    if r["kinds"].get("statement", 0) < 1:
        return ("the plain statement of fact was classified as an "
                "instruction — most of a good CLAUDE.md is neither")
    return None


def case_a_command_in_a_fence_is_not_a_prohibition(t):
    """A fenced block shows what to do; it does not instruct.

    A document demonstrating `git push --force` inside a code block would
    otherwise be classified as being made of prohibitions, which turns every
    well-written guide into a warning."""
    repo(t)
    put(t, "CLAUDE.md",
        "# How to release\n\n"
        "```bash\n"
        "# never do this by hand, and do not skip the checks\n"
        "git push --force origin main\n"
        "```\n\n"
        "Run the release script.\n")
    r = value_mod.assess(t, ())
    if r is None:
        return "nothing was read"
    for row in value_mod.classify(open(os.path.join(t, "CLAUDE.md")).read()):
        if "--force" in row["text"] or "never do this by hand" in row["text"]:
            return f"a fenced line was classified as prose: {row['text']!r}"
    return None


def case_a_path_scoped_sentence_on_the_floor_is_flagged(t):
    """Not wrong — misfiled, and the distinction is the whole row.

    A paragraph about the frontend build, paid for on every turn including the
    ones that never leave the database layer. The same words under a
    path-scoped rule cost nothing until somebody touches that path."""
    repo(t)
    put(t, "CLAUDE.md",
        "In `frontend/src/` the components must be function components.\n\n"
        "Write commit messages in the imperative mood.\n")
    r = value_mod.assess(t, ())
    if not r["path_scoped_but_loaded"]:
        return "a sentence about one directory was not flagged as misfiled"
    hit = r["path_scoped_but_loaded"][0]
    if "frontend" not in hit["about"]:
        return f"the wrong path was named: {hit['about']!r}"
    if len(r["path_scoped_but_loaded"]) > 1:
        return ("the general rule about commit messages was also flagged — "
                "a row that fires on everything says nothing")
    return None


def case_a_scoped_rule_file_is_not_on_the_floor(t):
    """A rule with a path glob is parked, and parked is not the bill.

    This is 0024's whole point measured from the other side: text that arrives
    only when asked for is not what dimension 5 is about, and counting it would
    make moving something off the floor look like no change at all."""
    repo(t)
    put(t, "CLAUDE.md", "Always write a test.\n")
    put(t, ".claude/rules/frontend.md",
        "---\npaths: [\"frontend/**\"]\n---\n"
        "Never use class components. Do not import from src/legacy.\n")
    r = value_mod.assess(t, ())
    if any("frontend.md" in f for f in r["files"]):
        return ("a path-scoped rule was charged to the floor — it arrives "
                "only when somebody touches that path")
    put(t, ".claude/rules/always.md", "Never commit secrets.\n")
    r2 = value_mod.assess(t, ())
    if not any("always.md" in f for f in r2["files"]):
        return "an unconditional rule was NOT charged to the floor"
    return None


def case_plugin_tokens_are_not_charged_to_the_repository(t):
    """Skill descriptions installed on this machine are real tokens and are
    reported -- but a repository judged on them is being scored for what
    somebody else installed."""
    dim_repo(t, files=[("CLAUDE.md", "x\n" * 400)])
    d5 = dims_of(t, with_blast=False)[5]
    floor = [r for r in d5["rows"] if r["label"].startswith("floor")][0]
    if "from this repository" not in floor["note"]:
        return "the floor does not say how much of it this repository owns"
    if "from this repository" not in d5["headline"]:
        return f"the headline does not scope the number: {d5['headline']!r}"
    return None


def case_a_pipeline_that_runs_nothing_is_not_a_verdict(t):
    """Having CI and running the tests are different facts.

    A pipeline that installs, lints, builds and deploys goes green on every
    push while never invoking a suite, and from outside -- from the tick on the
    pull request -- it is indistinguishable from one that runs everything. This
    is the failure the dimension is named after, so it may not be scored by the
    existence of `.github/workflows/`."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    put(t, "tests/test_app.py", "def test_app():\n    assert True\n")
    put(t, ".github/workflows/ci.yml",
        "name: ci\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - uses: actions/checkout@v4\n"
        "      - run: pip install -r requirements.txt\n"
        "      - run: ruff check .\n"
        "      - run: python -m build\n")
    commit(t, "feat: ship it")

    ci = [r for r in dims_of(t, with_blast=False)[3]["rows"]
          if r["label"] == "CI runs the suite"][0]
    if ci["flag"] != "bad":
        return (f"a pipeline that lints and builds without running the suite "
                f"was flagged {ci['flag']!r}, not 'bad'")
    if "ci.yml" not in ci["note"]:
        return "the row does not name the pipeline file it read"

    # Now let it run something. A repository whose verdict is a script it
    # wrote itself says none of the tool names, and must still count -- the
    # alternative is scoring a repository down for not being shaped like ours.
    put(t, ".github/workflows/ci.yml",
        "name: ci\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: python3 tests/run_everything.py\n")
    put(t, "tests/run_everything.py", "print('ok')\n")
    commit(t, "ci: actually run the checks")
    ci = [r for r in dims_of(t, with_blast=False)[3]["rows"]
          if r["label"] == "CI runs the suite"][0]
    if ci["flag"] != "ok":
        return (f"a pipeline invoking the repository's own suite was flagged "
                f"{ci['flag']!r}: {ci['value']!r}")
    return None


def case_the_page_names_where_it_looked_for_tests(t):
    """A percentage over matches nobody named cannot be contradicted.

    Every repository puts its tests somewhere different -- `frontend/`,
    `backend/`, `packages/*/`. When the instrument reports only "17% of changes
    verified nothing", a reader has no way to tell a repository with poor
    coverage from one where the suite lives in a subtree the matcher missed:
    the two produce the same number. Naming the directories turns an invisible
    miss into a correction somebody can make."""
    repo(t)
    put(t, "backend/app.py", "x = 1\n")
    put(t, "backend/tests/test_app.py", "def test_app():\n    assert 1\n")
    put(t, "frontend/src/__tests__/App.spec.js", "it('works', () => {})\n")
    put(t, "node_modules/left-pad/test/index.test.js", "// not ours\n")
    commit(t, "feat: two halves")

    row = [r for r in dims_of(t, with_blast=False)[3]["rows"]
           if r["label"] == "where the verdict is written"][0]
    if "backend/tests" not in row["value"]:
        return f"a suite under backend/ was not named: {row['value']!r}"
    if "frontend/src/__tests__" not in row["value"]:
        return f"a suite under frontend/ was not named: {row['value']!r}"
    if "node_modules" in row["value"]:
        return "a dependency's own tests were counted as this repository's"
    if row["flag"] != "ok":
        return f"two real suites were flagged {row['flag']!r}"
    return None


def case_a_record_nobody_reads_is_not_scored_as_learning(t):
    """A write-only record of mistakes is the failure that looks healthiest
    from outside: the file exists, it is long, and nothing has ever read it."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    put(t, "docs/postmortem-outage.md", "we broke it\n")
    commit(t, "init")
    rows = dims_of(t, with_blast=False)[4]["rows"]
    rec = [r for r in rows if "mistakes are written" in r["label"]][0]
    if rec["flag"] != "warn":
        return f"an unreferenced record was flagged {rec['flag']!r}, not 'warn'"

    put(t, "README.md", "see docs/postmortem-outage.md\n")
    commit(t, "docs: point at it")
    rows = dims_of(t, with_blast=False)[4]["rows"]
    rec = [r for r in rows if "mistakes are written" in r["label"]][0]
    if rec["flag"] != "ok":
        return "a record that README points at was still flagged as unread"
    return None


def case_the_instrument_does_not_find_its_own_vocabulary(t):
    """Every collector is a list of the names it looks for.

    So an instrument that reads its own source finds `grafana`, `jaeger` and
    `playwright` in a repository that has none of them, and reports a tree's
    observability as excellent on the strength of its own keyword table. This
    was live when the module was written: assessing this repository reported
    twenty logging findings, all of them the detector's own list.

    This one is measured the way it happens: the subject *contains* the
    instrument, which is the ordinary case when the assessment is run against
    the repository it ships from. The module's own directory is what gets
    excluded, so the case points that directory at a copy inside the fixture
    and insists every angle comes back empty."""
    inside = os.path.join(t, "shared", "scripts", "assess")
    shutil.copytree(HERE, inside)
    _observable_repo(t, **{"README.md": "a repository with no application in it"})
    was = observe_mod.HERE
    observe_mod.HERE = inside
    try:
        ev, why = observe_mod.assess(t)
    finally:
        observe_mod.HERE = was
    if ev is None:
        return f"nothing was collected at all: {why}"
    found = {a: len(ev[a]) for a in observe_mod.ANGLES if ev[a]}
    if found:
        return ("the instrument found itself: " + repr(found) +
                " -- its own keyword lists are not evidence about the subject")
    return None


def case_prose_about_a_logging_stack_is_not_a_logging_stack(t):
    """A design document naming Loki is not a repository that emits to Loki.

    The distinction is the whole difference between what a team wrote down and
    what the application does, and counting the first as the second puts a
    repository's ambitions on the page as its capabilities. Markdown is
    deliberately not scanned for this reason."""
    _observable_repo(t, **{
        "docs|observability.md": (
            "# Plan\n\nWe will ship logs to Loki via Vector, add "
            "opentelemetry tracing, and read them in Grafana. structlog is the "
            "library we picked.\n"),
    })
    ev, _ = observe_mod.assess(t)
    if ev is None:
        return "nothing was collected"
    if ev["logs"]:
        return ("a document describing a logging stack was counted as one: " +
                repr([i["detail"] for i in ev["logs"]]))
    return None


def case_a_test_target_is_not_a_way_to_run_the_thing(t):
    """This dimension is about the rung the test suite is not on.

    `make test` is dimension 2's business and is measured there. Counting it
    here would report every repository with a test target as one an agent can
    watch run, which is the opposite of what the row is for."""
    _observable_repo(t, **{"Makefile": "test:\n\tpytest\n\ncheck:\n\truff\n"})
    ev, _ = observe_mod.assess(t)
    if ev is None:
        return "nothing was collected"
    if ev["run"]:
        return ("a test target was counted as a way to run the application: " +
                repr([i["detail"] for i in ev["run"]]))
    return None


def case_a_literal_port_and_a_port_from_the_environment_differ(t):
    """The two shapes that decide whether a second agent can work at all.

    A hard-coded host port means the second concurrent instance collides, and
    the second agent gets a crash that looks like a bug in its own change --
    worse than no observability, because it is observability that lies. Both
    shapes must be reported, and reported as different things."""
    _observable_repo(t, **{
        "docker-compose.yml": ('services:\n  web:\n    container_name: fixed_web\n'
                               '    ports:\n      - "8080:8080"\n'),
        "app.py": 'import os\nPORT = os.environ.get("PORT", 8080)\n',
    })
    ev, _ = observe_mod.assess(t)
    if ev is None:
        return "nothing was collected"
    kinds = {i["kind"] for i in ev["isolation"]}
    for want in ("fixed-port", "fixed-name", "port-from-env"):
        if want not in kinds:
            return f"{want} was not reported; found {sorted(kinds)}"
    return None


def case_collecting_the_evidence_starts_nothing(t):
    """The promise the module's docstring makes, held by a case.

    Starting a stranger's application is a far larger promise than this
    assessment makes anywhere else, and 0026's pre-flight contract exists so
    that nothing executes without having been named first. The way this breaks
    is not malice -- it is somebody adding `run the dev target and read its
    output` because it would be better evidence."""
    proof = os.path.join(t, "it-ran")
    _observable_repo(t, **{
        "Makefile": "dev:\n\ttouch %s\n" % proof,
        "run.sh": "#!/bin/sh\ntouch %s\n" % proof,
    })
    observe_mod.assess(t)
    if os.path.exists(proof):
        return "collecting the evidence executed the repository's run target"
    return None


def case_an_unjudged_scan_carries_no_verdict(t):
    """A verdict nobody gave must not appear, in either direction.

    The page prints this row's prose verbatim, so a default here would put
    words on the page that no judge said. Absent, malformed and unsupported
    answers must all fail to produce one."""
    _observable_repo(t, **{"Makefile": "dev:\n\tpython3 app.py\n"})
    ev, _ = observe_mod.assess(t)
    if "not yet judged" not in observe_mod.render(ev):
        return "an unjudged scan rendered something other than 'not yet judged'"
    for bad in ({}, {"verdict": "excellent", "prose": "x"},
                {"verdict": "yes"}, {"verdict": "yes", "prose": "   "}, "yes"):
        judged, why = observe_mod.grade(bad)
        if judged is not None:
            return f"grade() accepted {bad!r} and returned {judged!r}"
    judged, why = observe_mod.grade(
        {"verdict": "partly", "prose": "the logs are unreachable"})
    if judged is None:
        return f"a well-formed answer was rejected: {why}"
    if "the logs are unreachable" not in observe_mod.render(ev, judged):
        return "the judge's prose did not reach the rendered row"
    return None


def case_the_brief_asks_about_every_angle(t):
    """A brief that has quietly lost an angle still reads as a full question.

    The agent answers what it was asked, so an angle missing from the brief is
    an angle nobody judges, and the row still prints a verdict as though the
    whole question had been put."""
    _observable_repo(t, **{"Makefile": "dev:\n\tpython3 app.py\n"})
    ev, _ = observe_mod.assess(t)
    text = observe_mod.brief(ev)
    # Not `a in text`: the brief's opening prose names all six angles, so a
    # membership test passes while the evidence section is missing one. What
    # the judge actually reads is the per-angle heading.
    missing = [a for a in observe_mod.ANGLES if ("### " + a) not in text]
    if missing:
        return "the brief carries no evidence section for: " + ", ".join(missing)
    if "nothing was started" not in text:
        return ("the brief does not tell the judge that nothing was run -- so "
                "an absent `logs` reads as an application that emits none, "
                "rather than as one nobody started")
    return None



def case_a_repository_of_scripts_is_runnable(t):
    """The collector's first version only knew application shapes.

    A Makefile, a compose file, a top-level app.py -- so it read `run: 0` on
    this repository, whose every file is executable from a shell, and the row
    would have said an agent could not watch its change run when running it is
    a single command. A tool, a library with a CLI and a directory of scripts
    are the common case, not the exception.

    Both directions: a module that says it can be run counts, and a library
    module that says nothing of the kind does not."""
    _observable_repo(t, **{
        "tool|cli.py": ('import sys\n\n\ndef main():\n    return 0\n\n\n'
                        'if __name__ == "__main__":\n    sys.exit(main())\n'),
        "tool|helpers.py": "def add(a, b):\n    return a + b\n",
        "pyproject.toml": ('[project]\nname = "tool"\n\n'
                           '[project.scripts]\nmytool = "tool.cli:main"\n'),
    })
    ev, _ = observe_mod.assess(t)
    if ev is None:
        return "nothing was collected"
    details = {i["detail"] for i in ev["run"]}
    if "python3 tool/cli.py" not in details:
        return ("a module with a __main__ guard was not counted as a way to "
                "run the thing: " + repr(sorted(details)))
    if "mytool" not in details:
        return "a console script in pyproject.toml was not counted"
    if any("helpers" in d for d in details):
        return "a library module with no entry point was counted as runnable"
    return None


def case_a_criterion_the_tool_does_not_produce_is_absent_not_zero(t):
    """Go's tooling computes no branch coverage. None. It is not a setting.

    A Go repository reading `0 of 0 branches never taken both ways` would be a
    statement about the language dressed up as a finding about the code, and
    the reader has no way to tell which it is. So a criterion the tool does not
    produce carries no row, and the criteria that are missing get named
    together in one row that says why."""
    _report(t, "coverage.out", GOCOVER)
    r, why = cover_mod.assess(t, None, os.path.join(t, "w"))
    if not r:
        return f"a valid coverprofile was not read: {why}"
    if r["criteria"].get("statement", {}).get("total") != 3:
        return f"statements came out as {r['criteria'].get('statement')}"
    for absent in ("branch", "function", "mcdc"):
        if absent in r["criteria"]:
            return f"{absent} was reported for a Go coverprofile, which has none"
    rows = dim_mod.coverage_rows(r)
    named = [x for x in rows if x["label"] == "criteria this tool does not produce"]
    if not named:
        return "the absent criteria were not named, so they read as zero"
    if "branch" not in named[0]["value"]:
        return "branch was not listed among the criteria this tool cannot give"
    return None


def case_lcov_carries_function_coverage(t):
    """The one common format with a first-class function counter.

    2.1 asks for line *and* function coverage. coverage.py has no function
    counter, so Python cannot answer that half; lcov's FNF/FNH means Node,
    Rust and C can. That asymmetry is real and it has to survive into the
    result rather than being smoothed over."""
    _report(t, "lcov.info", LCOV)
    r, why = cover_mod.assess(t, None, os.path.join(t, "w"))
    if not r:
        return f"a valid lcov report was not read: {why}"
    fn = r["criteria"].get("function")
    if not fn:
        return "lcov's FNF/FNH did not become function coverage"
    if (fn["total"], fn["covered"]) != (2, 1):
        return f"function coverage came out as {fn}"
    if r["criteria"].get("branch", {}).get("total") != 2:
        return "lcov's BRF/BRH did not become branch coverage"
    return None


def case_gcov_is_where_mcdc_comes_from(t):
    """The only on-disk format that carries the fourth criterion.

    Nothing outside the compilers computes MC/DC -- not coverage.py, not
    JaCoCo, not istanbul. GCC 14 added `-fcondition-coverage` and Clang 18
    `-fcoverage-mcdc`, both masking MC/DC, chosen independently. If this
    reader stops working, the criterion silently leaves the assessment for
    every language at once."""
    _report(t, "gcov.json", GCOV)
    r, why = cover_mod.assess(t, None, os.path.join(t, "w"))
    if not r:
        return f"a valid gcov report was not read: {why}"
    mc = r["criteria"].get("mcdc")
    if not mc:
        return "gcov's condition counts did not become MC/DC"
    if (mc["total"], mc["covered"]) != (2, 1):
        return f"MC/DC came out as {mc}"
    return None


def case_a_malformed_report_is_an_abstention_not_a_zero(t):
    """The failure that would be silent and would look like a finding.

    A truncated or half-written report parsed leniently yields small numbers,
    and small numbers here read as `almost nothing is tested` -- the worst
    possible reading to produce by accident."""
    for rel in ("coverage.json", "lcov.info", "coverage.xml", "coverage.out",
                "gcov.json"):
        _report(t, rel, "not a coverage report at all\n{oops")
    r, why = cover_mod.assess(t, None, os.path.join(t, "w"))
    if r:
        return f"garbage was read as a coverage result: {r.get('criteria')}"
    if "cannot judge" not in why:
        return f"the abstention did not say it could not judge: {why!r}"
    return None


def case_a_report_inside_a_dependency_is_not_this_repositorys(t):
    """A walk would find it. This does not walk, and that is the reason.

    A vendored package ships its own lcov.info more often than not, and a
    walk that finds it reports the dependency's coverage as the subject's --
    usually a high number, since libraries that ship coverage reports have
    good ones."""
    _report(t, "node_modules/left-pad/lcov.info", LCOV)
    _report(t, "vendor/thing/coverage.out", GOCOVER)
    r, why = cover_mod.assess(t, None, os.path.join(t, "w"))
    if r:
        return ("a dependency's coverage report was read as this "
                "repository's: " + str(r.get("report")))
    return None


def case_the_shape_of_the_suite_command_decides_if_it_can_be_wrapped(t):
    """Guessing at somebody's build is worse than saying you cannot.

    Three shapes are recognisable without reading the repository. A shell
    pipeline or a `make` target is not one of them, and wrapping it anyway
    produces a coverage number for a program that never ran."""
    py = cover_mod.Python()
    for command in ("pytest -q", "python3 -m pytest tests", "run_tests.py"):
        if not py.wrap(command):
            return f"a wrappable command was refused: {command!r}"
    for command in ("make test", "./ci.sh", "npm test && pytest", ""):
        if py.wrap(command):
            return (f"{command!r} was wrapped anyway -- the coverage number "
                    f"would be about a program that never ran")
    return None


def case_an_uninstalled_tool_names_itself_and_how_to_get_it(t):
    """`could not judge` is only useful when it says what would fix it.

    And the row it produces is a finding about the repository, not about this
    file: a Python repository with no coverage tool installed has no coverage
    tool. Nothing here installs one, because installing one changes what the
    subject contains.

    The absence is forced rather than borrowed from the machine. This case
    passed for a year because the box it ran on happened not to have
    `coverage`; installing it sent the fixture down the *available* path
    instead, where the message says something else entirely, and the case
    turned red for a reason that had nothing to do with the behaviour it
    guards. A case that depends on what is installed is testing the box."""
    for i in range(3):
        _report(t, "pkg/mod%d.py" % i, "def f():\n    return 1\n")
    was = cover_mod.Python.available
    cover_mod.Python.available = lambda self, root: False
    try:
        r, why = cover_mod.assess(t, "pytest -q", os.path.join(t, "w"))
    finally:
        cover_mod.Python.available = was
    if r:
        return "coverage was somehow produced with no tool and no report"
    if "coverage" not in why or "pip install" not in why:
        return f"the abstention names neither the tool nor how to get it: {why!r}"
    rows = dim_mod.coverage_rows(None, why)
    if not rows or rows[0]["flag"] != "info":
        return "an abstention rendered as something other than an info row"
    return None


def case_a_coverage_report_of_nothing_is_not_a_measurement(t):
    """`{app.py: set()}` is a run that did not happen, not a tested nothing.

    `coverage json` reports every source file it was pointed at whether or not
    a single line ran, so a failed `coverage run` still yields a well-formed
    report with empty executed-line sets. Returning it means every later
    intersection is empty, mutation abstains with `no mutable, covered,
    non-arid line`, and the page reads that as a fact about the repository:
    nothing here is worth mutating. It is a fact about the run.

    The tracer route is reached for real here -- only the two coverage calls
    are answered from the fixture -- so the case fails if the fallthrough is
    removed and also if the fallback itself stops working."""
    cmd = _traceable_repo(t)
    empty = ('{"files": {"app.py": {"executed_lines": []}, '
             '"suite.py": {"executed_lines": []}}}')
    was, seen = run_mod.sh, []
    run_mod.sh = _intercept(seen, empty)
    try:
        got = run_mod.covered_lines(t, cmd)
    finally:
        run_mod.sh = was
    if got is None:
        return "the fallback route was not reached at all"
    if not any(got.values()):
        return ("an empty coverage report was returned as a measurement: "
                + repr(got))
    if not got.get("app.py"):
        return f"the fallback ran but found nothing in app.py: {got!r}"
    return None


def case_coverage_run_is_not_handed_the_interpreter_twice(t):
    """`coverage run` supplies the interpreter, so the command must not.

    A test command arrives as `[python3, suite.py]` because that is what every
    other caller needs. Passing it through unchanged builds `python3 -m
    coverage run --source=. python3 suite.py`, which asks coverage to execute
    the interpreter binary as a Python script. It exits 1, collects nothing,
    and the report that follows is the empty one the case above is about --
    which is how this stayed invisible: two bugs, and the second one hid the
    first behind a plausible-looking abstention.

    The tracer route strips the interpreter and always did. This asserts the
    two routes are handed the same thing."""
    cmd = _traceable_repo(t)
    was, seen = run_mod.sh, []
    run_mod.sh = _intercept(seen, '{"files": {}}')
    try:
        run_mod.covered_lines(t, cmd)
    finally:
        run_mod.sh = was
    runs = [a for a in seen if a[1:3] == ["-m", "coverage"] and "run" in a]
    if not runs:
        return "the coverage route was never tried"
    for argv in runs:
        after = argv[argv.index("run") + 1:]
        interpreters = [x for x in after
                        if os.path.basename(x).startswith("python")]
        if interpreters:
            return ("`coverage run` was handed an interpreter to execute as a "
                    "script: " + repr(after))
        if "suite.py" not in after:
            return f"the suite never reached `coverage run`: {after!r}"
    return None


def case_a_rename_does_not_owe_a_test(t):
    """Tidying is not an untested change.

    Renaming a symbol across forty files, reformatting, and bumping a
    dependency all touch source, and no new test would make any of them safer.
    Counting them puts a repository's tidiest weeks against it and rewards
    leaving the mess alone -- which is the opposite of what this row is for.

    Six changes here, three of which add or repair behaviour. The denominator
    must be three."""
    _typed_history(t, ["feat: a new thing", "refactor: move it elsewhere",
                       "fix: a real defect", "chore(deps): bump a version",
                       "perf: make it faster", "style: reformat"])
    row = _bare_row(t)
    if not row["value"].endswith("/3  (100%)"):
        return ("the denominator counted tidying as a change owing a test: "
                + row["value"])
    return None


def case_an_untyped_subject_is_counted_rather_than_guessed(t):
    """The asymmetry the three-valued classifier exists for.

    A repository that does not type its subjects cannot be narrowed. Guessing
    from free-form English would shrink the denominator on every repository at
    once -- every score would improve and no repository would have changed,
    which is the most dangerous shape a measurement can take. So an untyped
    subject counts, and the row says which denominator it used."""
    _typed_history(t, ["added a new thing", "moved some files around",
                       "made it faster"])
    row = _bare_row(t)
    if not row["value"].endswith("/3  (100%)"):
        return ("untyped subjects were narrowed away on a guess: "
                + row["value"])
    if "not typed" not in row["note"]:
        return ("the row did not say it fell back to the wide denominator: "
                + row["note"])
    return None


def case_a_404_is_an_answer_and_a_403_is_not(t):
    """The distinction the whole module's honesty rests on.

    GitHub answers 404 `Branch not protected` for a branch with no protection
    rule -- that is a fact about the repository. A 403 is this tool lacking
    the right to look, and reporting it as `nothing is required` would be a
    confident claim about a repository nobody read. A tool that turns its own
    blindness into a finding is worse than one that abstains."""
    got = merge_mod.interpret(1, "", '{"message":"Branch not protected",'
                                    '"status":"404"}\ngh: Branch not protected')
    if not got.get("readable"):
        return "a 404 was treated as unreadable, but it is an answer"
    if got.get("protected"):
        return "a 404 was read as protected"

    for body in ('{"message":"Must have admin rights","status":"403"}',
                 '{"message":"Bad credentials","status":"401"}',
                 "gh: could not connect"):
        got = merge_mod.interpret(1, "", body)
        if got.get("readable"):
            return f"a failure to read was treated as an answer: {body!r}"
        if "required_checks" in got:
            return (f"an unreadable protection produced a required_checks "
                    f"field, which reads as `nothing is required`: {body!r}")

    got = merge_mod.interpret(0, json.dumps(
        {"required_status_checks": {"contexts": ["ci"]},
         "required_pull_request_reviews": {"x": 1}}), "")
    if got.get("required_checks") != ["ci"]:
        return f"a protected branch's required checks were lost: {got}"
    return None


def case_unreadable_protection_does_not_become_not_required(t):
    """The same rule one level up, where the state string is produced.

    A fixture with no remote at all: protection is a server-side fact and
    there is no server to ask. The state must say so, and must not say the
    checks are not required."""
    _workflow(t, "ci.yml", "on:\n  pull_request:\n\njobs:\n  t:\n"
                           "    runs-on: ubuntu-latest\n")
    r, why = merge_mod.assess(t)
    if not r:
        return f"nothing was read: {why}"
    if "not readable" not in r["state"]:
        return (f"with no remote to ask, the state came out as {r['state']!r} "
                f"— an unread server setting was turned into a finding")
    if r["protection"].get("readable"):
        return "protection was reported readable with no remote"
    return None


def case_a_workflow_on_push_only_is_not_a_merge_gate(t):
    """Running after the merge is not verification before it.

    A workflow triggered only on `push` to the default branch tells you the
    trunk broke. That is monitoring, and this row is about whether anything
    was obliged to look first."""
    _workflow(t, "nightly.yml", "on:\n  push:\n    branches: [main]\n  schedule:\n"
                                "    - cron: '0 0 * * *'\n\njobs:\n  t:\n"
                                "    runs-on: ubuntu-latest\n")
    r, why = merge_mod.assess(t)
    if not r:
        return f"nothing was read: {why}"
    if r["state"] != "nothing on pull requests":
        return (f"a push-only workflow was read as a merge gate: "
                f"{r['state']!r}")
    return None


def case_a_comment_about_swallowing_is_not_swallowing(t):
    """This repository was the false positive.

    ci.yml carries a line saying no step may swallow a status with `|| true`,
    and the first version of this reader flagged that sentence as a violation
    of itself. The reason beside a real one is carried instead, because every
    legitimate use this project has seen came with a sentence explaining why
    and every illegitimate one did not -- a signal an agent can use and a
    counter cannot."""
    _workflow(t, "ci.yml",
              "on:\n  pull_request:\n\njobs:\n  t:\n"
              "    runs-on: ubuntu-latest\n"
              "    steps:\n"
              "      # No step may swallow a status with || true\n"
              "      - run: pytest\n"
              "      # the corpus measurement must not fail the job\n"
              "      - name: measure\n"
              "        continue-on-error: true\n"
              "        run: python3 measure.py\n"
              "      - run: cleanup.sh || true\n")
    r, why = merge_mod.assess(t)
    if not r:
        return f"nothing was read: {why}"
    got = r["swallow_candidates"]
    if len(got) != 2:
        return ("expected the two real ones and not the comment, got: "
                + repr([(c["line"], c["text"]) for c in got]))
    with_reason = [c for c in got if c["reason_given"]]
    if len(with_reason) != 1:
        return ("the comment explaining a deliberate swallow was not carried "
                "to the one it explains: " + repr(got))
    if "corpus" not in with_reason[0]["reason_given"]:
        return "the wrong comment was attached: " + with_reason[0]["reason_given"]
    return None


def case_supersession_is_not_conflict(t):
    """The finding that would bury every other one.

    A decision record that replaces an earlier one contradicts it on purpose,
    and a repository that keeps its history has many. Run against this
    repository before the rule existed, the loudest candidates were 0031
    against 0033 — which is the system working, reported as the system
    broken."""
    _doc(t, "docs/0031-old.md", "# 0031\nStatus: accepted\n"
                                "Run with `--budget 2000` always.\n")
    _doc(t, "docs/0033-new.md", "# 0033\nStatus: accepted\nSupersedes 0031.\n"
                                "Run with `--budget 9000` instead.\n")
    r, why = conflict_mod.narrow(t)
    if r is None:
        return f"nothing was compared: {why}"
    if "--budget" in _subjects_of(r):
        return ("a document and the one that declares it superseded were "
                "reported as disagreeing")
    if not r["excluded_by_supersession"]:
        return "the supersession was not recognised at all"
    return None


CASES = [
    ('supersession is not conflict',
     case_supersession_is_not_conflict),
    ('a 404 is an answer and a 403 is not',
     case_a_404_is_an_answer_and_a_403_is_not),
    ('unreadable protection does not become `not required`',
     case_unreadable_protection_does_not_become_not_required),
    ('a workflow on push only is not a merge gate',
     case_a_workflow_on_push_only_is_not_a_merge_gate),
    ('a comment about swallowing is not swallowing',
     case_a_comment_about_swallowing_is_not_swallowing),
    ('a criterion the tool does not produce is absent, not zero',
     case_a_criterion_the_tool_does_not_produce_is_absent_not_zero),
    ('lcov carries function coverage',
     case_lcov_carries_function_coverage),
    ('gcov is where MC/DC comes from',
     case_gcov_is_where_mcdc_comes_from),
    ('a rename does not owe a test',
     case_a_rename_does_not_owe_a_test),
    ('an untyped subject is counted rather than guessed',
     case_an_untyped_subject_is_counted_rather_than_guessed),
    ('a coverage report of nothing is not a measurement',
     case_a_coverage_report_of_nothing_is_not_a_measurement),
    ('coverage run is not handed the interpreter twice',
     case_coverage_run_is_not_handed_the_interpreter_twice),
    ('a malformed report is an abstention, not a zero',
     case_a_malformed_report_is_an_abstention_not_a_zero),
    ("a report inside a dependency is not this repository's",
     case_a_report_inside_a_dependency_is_not_this_repositorys),
    ('the shape of the suite command decides if it can be wrapped',
     case_the_shape_of_the_suite_command_decides_if_it_can_be_wrapped),
    ('an uninstalled tool names itself and how to get it',
     case_an_uninstalled_tool_names_itself_and_how_to_get_it),
    ('a repository of scripts is runnable',
     case_a_repository_of_scripts_is_runnable),
    ('the instrument does not find its own vocabulary',
     case_the_instrument_does_not_find_its_own_vocabulary),
    ('prose about a logging stack is not a logging stack',
     case_prose_about_a_logging_stack_is_not_a_logging_stack),
    ('a test target is not a way to run the thing',
     case_a_test_target_is_not_a_way_to_run_the_thing),
    ('a literal port and a port from the environment differ',
     case_a_literal_port_and_a_port_from_the_environment_differ),
    ('collecting the evidence starts nothing',
     case_collecting_the_evidence_starts_nothing),
    ('an unjudged scan carries no verdict',
     case_an_unjudged_scan_carries_no_verdict),
    ('the brief asks about every angle',
     case_the_brief_asks_about_every_angle),
    ('a supplied test command is used when the table cannot guess',
     case_a_supplied_test_command_is_used),
    ('a prohibition a guard already enforces is named',
     case_a_prohibition_a_guard_enforces_is_named),
    ('prohibitions and requirements are counted apart',
     case_prohibitions_and_requirements_are_counted_apart),
    ('a command in a fence is not a prohibition',
     case_a_command_in_a_fence_is_not_a_prohibition),
    ('a path-scoped sentence on the floor is flagged as misfiled',
     case_a_path_scoped_sentence_on_the_floor_is_flagged),
    ('a scoped rule file is parked, not on the floor',
     case_a_scoped_rule_file_is_not_on_the_floor),
    ("an installed plugin's tokens are not charged to the repository",
     case_plugin_tokens_are_not_charged_to_the_repository),
    ('a pipeline that runs nothing is not counted as a verdict',
     case_a_pipeline_that_runs_nothing_is_not_a_verdict),
    ('the page names the directories it took the verdict from',
     case_the_page_names_where_it_looked_for_tests),
    ('a record of mistakes nobody reads is not scored as learning',
     case_a_record_nobody_reads_is_not_scored_as_learning),
]
