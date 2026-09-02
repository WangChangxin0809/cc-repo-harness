#!/usr/bin/env python3
"""Assessment selftest cases: value: what the standing context is spent ON (part 2).

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
    HERE,
    LONG_A,
    LONG_B,
    PARENT,
    TABLE,
    WORKFLOW,
    _doc,
    _run_with,
    _subjects_of,
    _unit,
    commit,
    conflict_mod,
    dim_mod,
    git,
    observe_mod,
    pipeline_rows,
    promises_mod,
    put,
    repo,
    review_mod,
    surface_mod,
    truth_mod,
    units_mod,
)





def case_a_value_must_be_attached_not_merely_nearby(t):
    """The single number the precision of the whole module rests on.

    Sentence scope, then a sixty-character window, both produced more than a
    thousand candidates from under two thousand document pairs — more than
    half of every pair, which is a filter that has stopped filtering. A
    `--json` flag with the words "Stage 5" eleven characters away is not a
    flag with the value 5."""
    # `--budget` carries its value; `--json` has a step number nearby and
    # carries nothing. Both flags appear in two documents, so the only thing
    # separating them is attachment.
    _doc(t, "a.md", "Run `query.py --budget 3000` for a wide map.\n")
    _doc(t, "c.md", "The default is `--budget 2000` and always has been.\n")
    _doc(t, "b.md", "Use `--json` at step 5 of the guide.\n")
    _doc(t, "d.md", "Use `--json` at step 9 of the guide.\n")
    r, _why = conflict_mod.narrow(t)
    got = _subjects_of(r)
    if got != ["--budget"]:
        return (f"expected only the attached pair, got {got} — a number "
                f"merely near a flag was read as its value")
    return None


def case_overlapping_values_are_agreement_not_conflict(t):
    """`{600}` against `{077, 600}` is one document giving more context.

    Requiring the value sets to be *unequal* rather than *disjoint* reported
    every such pair as a contradiction, which is how a filter fills a page
    with documents that agree."""
    _doc(t, "a.md", "The file is written with `chmod_mode` 600.\n")
    _doc(t, "b.md", "Written `chmod_mode` 600 by default. "
                    "In strict mode, `chmod_mode` 077.\n")
    r, _why = conflict_mod.narrow(t)
    if _subjects_of(r):
        return ("documents whose values overlap were reported as "
                "contradicting: " + repr(_subjects_of(r)))
    return None


def case_a_token_every_document_names_is_not_evidence(t):
    """The oldest rule in retrieval, and it applies unchanged.

    `CLAUDE.md` is named in almost every document here and produced 27 of the
    first 40 candidates on its own. A term with no discriminating power is not
    evidence, however code-shaped it looks."""
    for i in range(6):
        _doc(t, "d%d.md" % i,
             "Everything is described in `CLAUDE.md` %d.\n" % (100 + i))
    _doc(t, "rare_a.md", "The knob `retry_limit` 7 is what we use.\n")
    _doc(t, "rare_b.md", "The knob `retry_limit` 9 is what we use.\n")
    r, _why = conflict_mod.narrow(t)
    got = _subjects_of(r)
    if "CLAUDE.md" in got:
        return "a token named by most documents was still used to pair them"
    if got != ["retry_limit"]:
        return f"the discriminating subject was lost too: {got}"
    return None


def case_only_what_the_repository_keeps_is_its_memory(t):
    """An untracked draft is not what the repository says.

    `tmp/` here holds throwaway assessment pages nobody committed on purpose,
    and comparing them against the documents is comparing a draft against the
    thing it was drafting."""
    subprocess.run(["git", "init", "-q"], cwd=t, check=True)
    _doc(t, "kept.md", "The knob `retry_limit` 7 is what we use.\n")
    _doc(t, "scratch.md", "The knob `retry_limit` 9, scribbled.\n")
    subprocess.run(["git", "add", "kept.md"], cwd=t, check=True)
    r, _why = conflict_mod.narrow(t)
    if _subjects_of(r):
        return ("an untracked file was compared as though the repository "
                "kept it: " + repr(_subjects_of(r)))
    return None


def case_somebody_elses_cloned_repository_is_not_ours(t):
    """355 documents from other people's repositories, reported as ours.

    This repository keeps a corpus of cloned repositories under `eval/.work/`.
    The first run of this module compared their documents against each other
    and presented the result as a finding about this tree."""
    _doc(t, "eval/.work/someone__else/A.md",
         "The knob `retry_limit` 7 is what we use.\n")
    _doc(t, "eval/.work/someone__else/B.md",
         "The knob `retry_limit` 9 is what we use.\n")
    _doc(t, "ours.md", "Nothing controversial here.\n")
    r, why = conflict_mod.narrow(t)
    if r and _subjects_of(r):
        return ("a cloned repository's documents were compared as ours: "
                + repr(_subjects_of(r)))
    return None



def case_a_pass_to_fail_discards_the_whole_claim(t):
    """The guard, and the part of CASCADE easiest to drop.

    A test the real code passed and the document-derived code fails means that
    implementation is incomplete, so its passing of the fail-to-pass tests is
    evidence about nothing. Dropping this condition turns the method back into
    "a model said the code was wrong", which the paper measures at 0.53
    precision -- about 27 false positives per 71 real ones."""
    real = {"one": 1, "two": 0}
    got, counts = promises_mod.verdict(real, {"one": 0, "two": 1})
    if got == "inconsistent":
        return ("a claim with a pass-to-fail test was still reported: "
                + repr(counts))
    if counts.get("p2f") != 1 or counts.get("f2p") != 1:
        return f"the crossing itself is wrong: {counts}"
    got, _ = promises_mod.verdict(real, {"one": 0, "two": 0})
    if got != "inconsistent":
        return f"with no pass-to-fail it should be a finding, got {got!r}"
    return None


def case_a_test_the_documents_own_code_also_fails_is_not_a_finding(t):
    """f2f is the row that would otherwise be the false positive.

    There are more wrong tests than there are inconsistencies, which is the
    whole reason the second round exists."""
    got, _ = promises_mod.verdict({"a": 1, "b": 0}, {"a": 1, "b": 0})
    if got != "the test was wrong":
        return f"a test both versions fail was reported as {got!r}"
    if promises_mod.verdict({"a": 0, "b": 0}, None)[0] != "consistent":
        return "all-passing was not read as consistent"
    if promises_mod.verdict({"a": 1}, None)[0] != "pending":
        return "a failure with no second round was not left pending"
    return None


def case_a_test_that_vanished_between_runs_counts_in_neither(t):
    """Pairing the runs by position would let one crash shift every verdict.

    A test that failed to run at all in the second round is absent, not
    failing, and counting it as failing would manufacture a pass-to-fail and
    silently discard a real finding."""
    counts = promises_mod.cross({"a": 1, "b": 0, "c": 0}, {"a": 0, "b": 0})
    if counts != {"p2p": 1, "f2f": 0, "f2p": 1, "p2f": 0}:
        return f"a missing test was counted somewhere: {counts}"
    return None


def case_a_fenced_example_is_not_a_promise(t):
    """A fence is an example, and it is where a document is most often right.

    Testing fences would spend the budget on the claims least likely to be
    wrong, and the sentence that matters is usually the prose beside it."""
    _doc(t, "d.md", "# Guide\n\n"
                    "The runner exits 2 when `dispatch.py` cannot see its "
                    "subject and must never return 0 in that case.\n\n"
                    "```\n"
                    "`build.py` always writes 0 and never exits 9 here\n"
                    "```\n")
    subprocess.run(["git", "init", "-q"], cwd=t, check=True)
    subprocess.run(["git", "add", "-A"], cwd=t, check=True)
    got = promises_mod.claims(t)
    if not got:
        return "the prose claim outside the fence was lost too"
    if any("build.py" in c["says"] for c in got):
        return "a sentence inside a fenced block was taken as a promise"
    return None


def case_a_claim_has_to_name_something_executable(t):
    """Otherwise every emphatic sentence in the repository is a claim.

    "This must never happen" is a promise about nothing a test can reach, and
    an agent asked to write a test for it will write one for whatever it
    imagines the subject to be."""
    _doc(t, "d.md", "# Guide\n\n"
                    "This must never happen and the team always agrees on "
                    "that, which is why it matters so much to everyone.\n\n"
                    "The tool exits 2 when `dispatch.py` cannot see its "
                    "subject and must never return 0 in that case.\n")
    subprocess.run(["git", "init", "-q"], cwd=t, check=True)
    subprocess.run(["git", "add", "-A"], cwd=t, check=True)
    got = promises_mod.claims(t)
    if len(got) != 1:
        return ("expected only the sentence naming something executable, got "
                + repr([c["says"][:50] for c in got]))
    if got[0]["kind"] != "exit code":
        return f"an exit-code promise was ranked as {got[0]['kind']!r}"
    return None




def case_a_test_that_does_not_parse_never_became_evidence(t):
    """CASCADE drops an uncompilable test; Python has to be told to.

    A test with a syntax error exits non-zero on both runs, so it crosses as
    `f2f` and reaches the right verdict -- but only after a second agent round
    has been spent on the claim. Worse, a claim whose *only* failing tests were
    typos goes `pending`, which is what schedules that round. Parsing costs
    nothing and answers before the bill."""
    ok, dropped = promises_mod.runnable([
        {"name": "good", "source": "print('fine')\n"},
        {"name": "typo", "source": "def broken(:\n"},
    ])
    if [c["name"] for c in ok] != ["good"]:
        return f"a test that does not parse was kept: {[c['name'] for c in ok]}"
    if [d["name"] for d in dropped] != ["typo"]:
        return f"the unparseable test was not reported: {dropped}"
    return None


def case_a_missing_import_is_the_finding_and_is_never_dropped(t):
    """The drop is syntax only, and widening it would delete the findings.

    A test that reaches for something the document promised and the code does
    not have fails at import time. That failure is exactly what dimension 4.3
    is looking for -- round two decides whether the document or the test was
    wrong -- so it has to run. A filter that also dropped tests which fail to
    import would silently make the method incapable of reporting the most
    common inconsistency there is."""
    ok, dropped = promises_mod.runnable([
        {"name": "absent", "source": "import a_module_that_is_not_here\n"},
        {"name": "attr", "source": "import os\nos.promised_by_the_doc()\n"},
    ])
    if dropped:
        return f"a test that parses was dropped before it ran: {dropped}"
    if len(ok) != 2:
        return "a runnable test was lost"
    return None


def case_a_claim_whose_tests_all_failed_to_parse_is_untested(t):
    """Not `pending`, which would buy it a second agent round for nothing.

    The paper's equivalent returns negative when nothing compiled after three
    repairs. Reporting it as pending instead would spend the most expensive
    round on the page to discover that the agent typed a bracket wrong."""
    claims = [{"id": 1, "doc": "d.md", "says": "it exits 2", "names": ["x.py"],
               "kind": "exit code"}]
    got = promises_mod.check(t, claims, {"tests": [
        {"claim_id": 1, "targets": "x.py",
         "cases": [{"name": "one", "source": "def (:\n"}]}]}, t)
    if got[0].get("verdict") != "not tested":
        return ("a claim with no parseable test was reported as "
                + repr(got[0].get("verdict")))
    if not got[0].get("dropped"):
        return "the claim does not say which tests were dropped"
    return None



def case_a_claim_still_waiting_on_round_two_is_not_a_pass(t):
    """The one direction this row cannot afford to be wrong in.

    A `pending` claim is one whose test the real code *failed*; what has not
    happened is the round that decides whether the document or the test was
    at fault. Counting it under `ok` beside "the code passed it" turns the
    most expensive measurement on the page into a clean bill for the exact
    repository it was run to catch."""
    def row_for(verdict):
        got = dim_mod.repository_memory(
            t, None, promises=[{"doc": "d.md", "says": "it exits 2",
                                "verdict": verdict}])
        for r in got.get("rows", []):
            if "promises the code does not keep" in r.get("label", ""):
                return r
        return None

    if (row_for("consistent") or {}).get("flag") != "ok":
        return "a claim the real code passed was not reported as ok"
    row = row_for("pending")
    if row is None:
        return "the promises row vanished once a claim had been run"
    if row.get("flag") == "ok":
        return "a claim whose test the real code failed was reported as ok"
    if "passed it" in row.get("note", ""):
        return "a pending claim was described as the code having passed"
    return None

def case_briefs_are_written_by_dimension_and_name_their_flag(t):
    """One call per dimension, and each file says where its answer goes.

    The reader that answers a dimension used to need five module names and
    five flags. A brief that does not name the flag its answer feeds is a
    reading that reaches the page only if somebody remembers -> 0048"""
    import briefs as briefs_mod
    run = {"probe": {"root": t}, "root": t,
           "observe": {a: [] for a in observe_mod.ANGLES},
           "permitted": {"ci_commands": [{"command": "make test",
                                          "from": "ci.yml"}],
                         "documented_commands": [], "hooks": {}},
           "truth": None, "conflict": None, "mutants": None}
    out = os.path.join(t, "d1")
    got = briefs_mod.write(run, 1, out, t)
    names = sorted(w["name"] for w in got)
    if names != ["observe", "permitted"]:
        return f"dimension 1 wrote {names}, not observe and permitted"
    for w in got:
        if not os.path.isfile(w["path"]):
            return f"{w['name']} was reported and not written"
        if not w["flag"].startswith("--") or not w["answer"].endswith(
                ".answers.json"):
            return f"{w['name']} does not say where its answer goes: {w}"
    flags = {w["name"]: w["flag"] for w in got}
    if flags != {"observe": "--observe-answers",
                 "permitted": "--legitimate-actions"}:
        return f"the wrong flags were named: {flags}"
    if briefs_mod.write(run, 3, os.path.join(t, "d3"), t):
        return "dimension 3 wrote a brief, and it has nothing to answer"
    if briefs_mod.write(run, 4, os.path.join(t, "d4"), t):
        return "dimension 4 wrote a brief with no candidates to judge"
    return None


def case_a_run_is_read_back_instead_of_re_measured(t):
    """The second pass applies answers to a run; it does not run the suite.

    Every answer flag re-ran the whole instrument to put one reading on the
    page, minutes of somebody's tests per answer. A run is a record. What
    is checked here: a saved run reloads with its dimensions rebuilt from
    the same facts, and a file that is not a run is refused."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "factsheet", os.path.join(HERE, "factsheet.py"))
    fs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fs)
    repo(t)
    put(t, "src/a.py", "def f():\n    return 2\n")
    put(t, "CLAUDE.md", "# t\n\nA repository.\n")
    commit(t, "feat: a")
    work = os.path.join(t, ".work")
    r = fs.gather(t, False, 1, work)
    if r is None:
        return "the instrument could not read the fixture"
    r["root"] = t
    first = fs.dimensions_of(r)
    path = os.path.join(t, "run.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({**r, "dimensions": first}, fh)
    back, why = fs.reload(path, "")
    if back is None:
        return f"a saved run did not reload: {why}"
    if "dimensions" in back:
        return "the old page came back with the run instead of being rebuilt"
    second = fs.dimensions_of(back)
    got = [(d["n"], d["state"], [row["label"] for row in d["rows"]])
           for d in second]
    want = [(d["n"], d["state"], [row["label"] for row in d["rows"]])
            for d in first]
    if got != want:
        return f"the run read back does not rebuild the same page: {got}"
    bad = os.path.join(t, "not-a-run.json")
    with open(bad, "w", encoding="utf-8") as fh:
        json.dump({"items": []}, fh)
    back, why = fs.reload(bad, "")
    if back is not None or "not factsheet" not in why:
        return f"a file that is not a run was accepted: {why!r}"
    return None


def case_coverage_takes_its_own_command_when_the_suite_cannot_be_wrapped(t):
    """One string, two consumers, and only one of them could use it.

    The replay is right to run `for f in ...; do python3 "$f"; done` as
    written. No coverage tool wraps a shell loop, so 2.1 abstained on every
    repository whose suite was a shell line -- this one included. Coverage
    now takes its own plain command when given one, and the replay keeps
    the loop."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "factsheet", os.path.join(HERE, "factsheet.py"))
    fs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fs)
    repo(t)
    put(t, "src/a.py", "def f():\n    return 2\n")
    put(t, "tests/test_a.py", "from src.a import f\n\ndef test_f():\n"
                              "    assert f() == 2\n")
    commit(t, "feat: a")
    seen = {}

    def fake_cover(bench, command, work):
        seen["command"] = command
        return None, "cannot judge: stubbed"

    def fake_catch(root, instances, work, command=None):
        seen["replay"] = command
        return None, "cannot judge: stubbed"

    real_cover, real_catch = fs.cover_mod.assess, fs.catch_mod.assess
    fs.cover_mod.assess, fs.catch_mod.assess = fake_cover, fake_catch
    try:
        loop = 'for f in tests/*.py; do python3 "$f" || exit 1; done'
        fs.gather(t, True, 1, os.path.join(t, ".work"), loop, 0,
                  coverage_command="pytest -q")
    finally:
        fs.cover_mod.assess, fs.catch_mod.assess = real_cover, real_catch
    if seen.get("replay") != loop:
        return f"the replay did not get the suite as written: {seen}"
    if seen.get("command") != ["pytest", "-q"]:
        return f"coverage did not get its own command: {seen.get('command')}"
    # Without one, coverage gets what the replay got.
    seen.clear()
    fs.cover_mod.assess, fs.catch_mod.assess = fake_cover, fake_catch
    try:
        fs.gather(t, True, 1, os.path.join(t, ".work2"), "pytest -q", 0)
    finally:
        fs.cover_mod.assess, fs.catch_mod.assess = real_cover, real_catch
    if seen.get("command") != "pytest -q":
        return f"without its own command coverage lost the suite's: {seen}"
    return None


def case_shipping_is_read_from_the_default_branch(t):
    """A branch that bumped the manifest is supposed to be ahead of the tag.

    3.6 read the checkout: on a feature branch with the version raised, the
    manifest disagreed with the latest tag, and a tag made on main after
    the branch was cut was not reachable. Both are the ordinary look of
    open work; a reader of this repository's own page called the row
    noise, and it was. Shipping now reads the default branch."""
    repo(t)

    def tag(name, day):
        # Annotated, with a tagger date: two lightweight tags made in the
        # same second tie on creatordate and "latest" is then whichever git
        # lists first, which made this case pass and fail by the clock.
        subprocess.run(["git", "tag", "-a", name, "-m", name], cwd=t,
                       capture_output=True, text=True, timeout=60,
                       env={**os.environ,
                            "GIT_COMMITTER_DATE": f"2026-01-0{day}T00:00:00",
                            "GIT_COMMITTER_NAME": "t",
                            "GIT_COMMITTER_EMAIL": "t@example.invalid"})

    put(t, "src/app.py", "x = 1\n")
    put(t, ".claude-plugin/plugin.json",
        json.dumps({"name": "p", "version": "1.0.0"}))
    put(t, ".github/workflows/ci.yml", WORKFLOW % ("", "      - run: pytest\n"))
    commit(t, "feat: app")
    tag("v1.0.0", 1)
    # A feature branch raises the version; main also releases a patch after
    # the branch was cut, bumping its own manifest and tagging it.
    git(["checkout", "-q", "-b", "feature"], t)
    put(t, ".claude-plugin/plugin.json",
        json.dumps({"name": "p", "version": "1.1.0"}))
    commit(t, "feat: bump")
    git(["checkout", "-q", "main"], t)
    put(t, "src/app.py", "x = 2\n")
    put(t, ".claude-plugin/plugin.json",
        json.dumps({"name": "p", "version": "1.0.1"}))
    commit(t, "fix: x")
    tag("v1.0.1", 2)
    git(["checkout", "-q", "feature"], t)
    rows = pipeline_rows(t)
    row = rows.get("the latest tag is on this branch")
    if not row or row["flag"] != "ok":
        return f"a tag on main read as unreachable from a feature branch: {row}"
    row = rows.get("the manifest agrees with the latest tag")
    if not row or row["flag"] != "ok":
        return f"a branch that bumped the version read as a mismatch: {row}"
    # And on main, a version raised without a tag is still the finding.
    git(["checkout", "-q", "main"], t)
    put(t, ".claude-plugin/plugin.json",
        json.dumps({"name": "p", "version": "2.0.0"}))
    commit(t, "feat: two")
    row = pipeline_rows(t).get("the manifest agrees with the latest tag")
    if not row or row["flag"] != "warn":
        return f"a bump on main with no tag was not reported: {row}"
    return None


def case_the_blind_agent_cannot_read_the_repository(t):
    """The tool list is the experiment, not a sentence in the prompt.

    A test written after reading the implementation agrees with it by
    construction. `assess-promise-tester` is given `Write` and nothing else so
    that the blind is a fact about what it can do -- an instruction asking it
    not to look is one an agent can talk itself out of, and the whole method
    is worthless the moment it does."""
    import re as _re
    plugin = os.path.dirname(os.path.dirname(PARENT))
    path = os.path.join(plugin, "agents", "assess", "promise-tester.md")
    if not os.path.exists(path):
        return "the agent that writes the tests is missing"
    head = open(path, encoding="utf-8").read().split("---")[1]
    m = _re.search(r"^tools:\s*(.+)$", head, _re.M)
    if not m:
        return "the agent declares no tool list, so it inherits everything"
    tools = {x.strip() for x in m.group(1).split(",")}
    can_read = tools & {"Read", "Grep", "Glob", "Bash", "Task", "WebFetch",
                        "NotebookEdit", "Edit"}
    if can_read:
        return ("the blind agent can reach the code it is not allowed to "
                "read: " + ", ".join(sorted(can_read)))
    return None



def case_a_document_nobody_loads_is_not_a_context_cost(t):
    """A guide is read the way any file is read: somebody opens it.

    This dimension is about text the harness puts in front of the model
    without anyone asking. Sweeping every markdown file in the tree charges a
    repository for having explained itself, and reported this project's own
    assessment guide as the most expensive file it owns -- 4.6x the median
    document, and nothing loads it. That is not an over-count, it is the wrong
    population.

    The fixture makes the un-loaded file enormous on purpose: if it were in,
    it would dominate."""
    repo(t)
    _unit(t, "CLAUDE.md", "# rules\n\nKeep it short.\n")
    _unit(t, "guide/1-assess.md", "# guide\n\n" + ("A long explanation. " * 900))
    _unit(t, "docs/decisions/0001-a-thing.md", "# 0001\n\n" + ("Because. " * 900))
    _unit(t, "README.md", "# readme\n\n" + ("Welcome here. " * 900))
    commit(t, "docs: a small floor and three long documents")
    r, why = units_mod.measure(t)
    if r is None:
        return f"nothing was measured at all: {why}"
    seen = {u["path"] for u in r["units"]}
    leaked = sorted(seen & {"guide/1-assess.md", "README.md",
                            "docs/decisions/0001-a-thing.md"})
    if leaked:
        return "documents nobody loads were charged as context: " + repr(leaked)
    if "CLAUDE.md" not in seen:
        return "the one file that is loaded was dropped along with them"
    return None


def case_a_skills_reference_is_loaded_and_is_counted(t):
    """The other side of the same line, and the reason it is a line not a rule
    about directories.

    A skill's `references/` reach the model when the skill fires, so they are
    in. A document sitting beside them is not. Dropping the whole of a skill
    directory would lose the finding this dimension is best at -- the same
    paragraph in a SKILL.md and in its own reference, paid for twice whenever
    that skill runs and free to drift apart."""
    repo(t)
    _unit(t, "CLAUDE.md", "# rules\n\nKeep it short.\n")
    shared = ("Every check must be watched failing before it counts as a "
              "check, because a check nobody has seen turn red is a file.\n")
    _unit(t, "skills/writing/SKILL.md", "# writing\n\n" + shared + "\nMore.\n")
    _unit(t, "skills/writing/references/kinds.md",
          "# kinds\n\n" + shared + "\nOther things.\n")
    commit(t, "docs: a skill and its reference share a sentence")
    r, why = units_mod.measure(t)
    if r is None:
        return f"nothing was measured at all: {why}"
    seen = {u["path"] for u in r["units"]}
    if "skills/writing/references/kinds.md" not in seen:
        return "a skill reference was dropped as though nothing loads it"
    dup = r.get("duplicated_sentences") or []
    if not dup:
        return ("the sentence shared by a skill and its own reference was not "
                "reported as paid for twice")
    return None


def case_a_repeated_table_is_not_a_repeated_paragraph(t):
    """Two files sharing a reference table are usually sharing it on purpose.

    And a markdown table flattens into one enormous pseudo-sentence, so the
    first version of this reported a garbled table row as the duplicated
    prose. Duplication here is about paragraphs: the same paragraph in two
    loaded files is the thing that drifts."""
    # On rule paths, not docs/: a document nobody loads is outside this
    # dimension entirely, so a fixture written in docs/ measures nothing.
    _unit(t, ".claude/rules/a.md", "# A\n\n" + TABLE + "\n" + LONG_A)
    _unit(t, ".claude/rules/b.md", "# B\n\n" + TABLE + "\n" + LONG_B)
    subprocess.run(["git", "init", "-q"], cwd=t, check=True)
    subprocess.run(["git", "add", "-A"], cwd=t, check=True)
    r, why = units_mod.measure(t)
    if not r:
        return f"nothing was read: {why}"
    if r["duplicated_sentences"]:
        return ("a shared table was counted as a repeated paragraph: %d"
                % r["duplicated_sentences"])

    _unit(t, ".claude/rules/b.md", "# B\n\n" + TABLE + "\n" + LONG_A)
    subprocess.run(["git", "add", "-A"], cwd=t, check=True)
    r, _why = units_mod.measure(t)
    if r["duplicated_sentences"] != 1:
        return ("a paragraph in two files was not counted: %d"
                % r["duplicated_sentences"])
    return None


def case_a_file_is_compared_to_its_own_kind(t):
    """A skill is not large because decision records are small.

    Comparing across genres would report every skill as an outlier in a
    repository whose documents are short, which is a fact about the two
    genres and not about the repository."""
    for i in range(4):
        _unit(t, "docs/d%d.md" % i, "# D\n\n" + LONG_A * 3)
    for i in range(3):
        _unit(t, "skills/s%d/SKILL.md" % i, "# S\n\n" + LONG_B * 40)
    subprocess.run(["git", "init", "-q"], cwd=t, check=True)
    subprocess.run(["git", "add", "-A"], cwd=t, check=True)
    r, _why = units_mod.measure(t)
    flagged = {o["path"] for o in r["outliers"]
               if any("median" in w for w in o["why"])}
    if flagged:
        return ("files were called outliers against another genre's median: "
                + repr(sorted(flagged)))
    _unit(t, "skills/big/SKILL.md", "# S\n\n" + LONG_B * 400)
    subprocess.run(["git", "add", "-A"], cwd=t, check=True)
    r, _why = units_mod.measure(t)
    flagged = {o["path"] for o in r["outliers"]
               if any("median" in w for w in o["why"])}
    if flagged != {"skills/big/SKILL.md"}:
        return f"the skill unlike other skills was not found: {sorted(flagged)}"
    return None


def case_a_small_file_is_never_an_outlier_for_being_large(t):
    """Three times nothing is still nothing.

    Without a floor, a repository of one-paragraph rules reports the
    two-paragraph one as four times the median — true, and not worth anybody
    reading a row about."""
    for i in range(4):
        _unit(t, ".claude/rules/r%d.md" % i, "Keep it short.\n")
    _unit(t, ".claude/rules/big.md", LONG_A * 4)
    subprocess.run(["git", "init", "-q"], cwd=t, check=True)
    subprocess.run(["git", "add", "-A"], cwd=t, check=True)
    r, _why = units_mod.measure(t)
    if any("median" in w for o in r["outliers"] for w in o["why"]):
        return ("a file under the size floor was reported for being unlike "
                "its neighbours: " + repr(r["outliers"]))
    return None


def case_an_untracked_file_is_not_loadable_context(t):
    """The same rule 4.4 needs, for the same reason.

    A draft nobody committed is not what the repository loads, and counting
    it moves every median."""
    _unit(t, ".claude/rules/kept.md", LONG_A * 2)
    _unit(t, ".claude/rules/scratch.md", LONG_A * 2)
    subprocess.run(["git", "init", "-q"], cwd=t, check=True)
    subprocess.run(["git", "add", ".claude/rules/kept.md"], cwd=t,
                   check=True)
    r, _why = units_mod.measure(t)
    if [u["path"] for u in r["units"]] != [".claude/rules/kept.md"]:
        return ("an untracked draft was counted as loadable context: "
                + repr([u["path"] for u in r["units"]]))
    return None


def case_an_abstention_does_not_become_a_number(t):
    """The one thing the reading is not allowed to do.

    Every other guard on this page keeps `could not judge` off it. This is the
    last place it could get back on, and it is the worst place: a number on a
    chart is indistinguishable from a measurement, so scoring an abstention
    turns `we could not run your tests` into `your tests are bad` with nothing
    in between.

    An abstention and an ordinary fact share the `info` flag, which is why the
    check is on the value."""
    run = _run_with([
        {"label": "an agent finding its way", "value": "not probed",
         "flag": "info", "note": ""},
        {"label": "documents that contradict each other",
         "value": "1 candidate(s), not yet judged", "flag": "info", "note": ""},
        {"label": "refused before they happen", "value": "3/6",
         "flag": "warn", "note": ""},
    ])
    items, unmapped = review_mod.collect(run)
    ids = [i["id"] for i in items]
    if ids != ["1.1"]:
        return "abstentions were handed over to be scored: " + repr(ids)
    if unmapped:
        return "an abstention was reported as an unmapped row: " + repr(unmapped)

    text, _why = review_mod.brief(run)
    for gone in ("finding its way", "contradict each other"):
        if gone in text:
            return f"the brief asked about an abstention: {gone!r}"
    return None


def case_a_reading_of_the_candidates_can_be_recorded(t):
    """A list nobody can answer is a list everybody re-reads.

    4.4 got an answers file and 4.2 did not, so the same 24 candidates came
    back on every run of every assessment forever -- and each reader paid
    again to rediscover that most of them name a path a scaffolded repository
    has and this one deliberately does not. The reading was happening; only
    the record of it was missing.

    Three things the channel has to hold, and each is a way it could quietly
    lie. An id nobody handed over is an invented answer. Answering none of
    them is not the same as dismissing all of them. And an unanswered id is
    pending rather than dismissed, because an unread candidate and a
    considered one are different states."""
    r = {"candidates": [
        {"tier": 1, "file": "a.md", "claim": "two hooks", "why": "4 in hooks/"},
        {"tier": 2, "file": "b.md", "claim": "scripts/guards/", "why": "gone"},
        {"tier": 3, "file": "c.md", "claim": "moved", "why": "stale"}]}

    got, why = truth_mod.grade(r, {"candidates": [
        {"id": 0, "real": False, "why": "hooks.json is not a hook"},
        {"id": 2, "real": True, "why": "the guide never got the new section"},
        {"id": 99, "real": True, "why": "a candidate nobody was handed"}]})
    if got is None:
        return "a well-formed reading was refused: " + why
    if len(got["real"]) != 1 or len(got["dismissed"]) != 1:
        return ("the verdicts did not survive: %d real, %d dismissed"
                % (len(got["real"]), len(got["dismissed"])))
    if got["pending"] != 1:
        return "an unanswered candidate was not left pending: %d" % got["pending"]
    if got["judged"] != 2:
        return "an invented id was counted as judged: %d" % got["judged"]
    if got["real"][0]["candidate"]["file"] != "c.md":
        return "a verdict was attached to the wrong candidate"

    for bad, what in (({"candidates": []}, "an empty reading"),
                      ({"pairs": []}, "the wrong shape"),
                      ([], "a list")):
        if truth_mod.grade(r, bad)[0] is not None:
            return what + " was accepted as a judgement"

    # A tier-3 reading expires when the document it was about changes, and
    # only then. Its claim counts commits to what the document *points at*, so
    # it moves whenever somebody else's file is touched -- keying the answer to
    # it would expire every verdict on every commit. Keying it to nothing would
    # apply a reading of last week's document to this week's.
    moved = {"candidates": [
        {"tier": 3, "file": "d.md", "claim": "2 commit(s) ...", "moved": 100}]}
    answer = [{"id": 0, "file": "d.md", "tier": 3, "moved": 100,
               "real": False, "why": "the churn is its subjects working"}]
    got, _why = truth_mod.grade(moved, {"candidates": answer})
    if not got or len(got["dismissed"]) != 1:
        return "a reading of an unchanged document did not stand"

    churned = {"candidates": [dict(moved["candidates"][0],
                                   claim="9 commit(s) ...")]}
    got, _why = truth_mod.grade(churned, {"candidates": answer})
    if not got or len(got["dismissed"]) != 1:
        return "a reading expired because somebody else committed"

    rewritten = {"candidates": [dict(moved["candidates"][0], moved=200)]}
    got, why = truth_mod.grade(rewritten, {"candidates": answer})
    if got is not None:
        return "a reading of a document that has since changed was still applied"

    # ...and the questions have to carry the ids the answers use.
    text = truth_mod.brief(r)
    for n in ("## 0", "## 1", "## 2"):
        if n not in text:
            return "the brief did not offer id " + n
    if truth_mod.brief({"candidates": []}):
        return "a brief was produced with nothing to ask about"
    return None


def case_the_surface_is_coverage_not_a_count(t):
    """The test 0025 used, applied to the row that came after it.

    0025 refused to score a repository on what it keeps, and the case that
    settled it was 0024: deleting five skills cut the standing cost by 81%,
    and any measure calling that a regression is measuring the wrong thing.
    So this row is present/absent per mechanism and never a quantity -- six
    skills are the same coverage as one, and deleting five of them cannot
    move it.

    Two more ways it could quietly become what 0025 rejected. A skill a
    plugin installed is on somebody's laptop, not in this tree, so counting
    it would let the instrument reward its own presence -- and a teammate
    without the plugin gets nothing. And a `.claude/rules` file with no
    `paths:` frontmatter loads at launch: it is a slower entry file rather
    than a scoped rule, which is why the budget gate counts it on the
    floor."""
    def probe_with(**over):
        base = {"moments": {"1_always": [{"file": "CLAUDE.md", "lines": 9}],
                            "4_subtree": [], "2_session_start": 0,
                            "3_prompt": 0, "6_after_action": 0,
                            "5_before_action": {"PreToolUse": 0,
                                                "permissions_deny": 0},
                            "7_on_request": []},
                "discipline": {"other_hooks": {}}}
        base["moments"].update(over)
        return base

    one = surface_mod.assess(t, probe_with(
        **{"7_on_request": [{"origin": "repo"}]}))
    six = surface_mod.assess(t, probe_with(
        **{"7_on_request": [{"origin": "repo"}] * 6}))
    if one["reached"] != six["reached"]:
        return ("six skills scored differently from one — this is a count, "
                "and 0024 would read as a regression")

    plugin_only = surface_mod.assess(t, probe_with(
        **{"7_on_request": [{"origin": "plugin"}] * 3}))
    if plugin_only["have"]["skills"]:
        return "a skill installed by a plugin was counted as the repository's"

    # A deny rule reaches the same moment a PreToolUse hook does.
    hook = surface_mod.assess(t, probe_with(
        **{"5_before_action": {"PreToolUse": 1, "permissions_deny": 0}}))
    deny = surface_mod.assess(t, probe_with(
        **{"5_before_action": {"PreToolUse": 0, "permissions_deny": 4}}))
    if not (hook["have"]["before"] and deny["have"]["before"]):
        return "a repository that can refuse an action was reported as unable"

    # `.claude/rules` without `paths:` loads at launch: an entry file, not a
    # scoped rule.
    os.makedirs(os.path.join(t, ".claude", "rules"), exist_ok=True)
    put(t, ".claude/rules/loose.md", "# always on\n")
    if surface_mod.assess(t, probe_with())["have"]["scoped"]:
        return "an unscoped rule was credited as path-scoped coverage"
    put(t, ".claude/rules/scoped.md", "---\npaths: src/**\n---\n\nhere\n")
    if not surface_mod.assess(t, probe_with())["have"]["scoped"]:
        return "a rule with `paths:` was not seen"

    # ...and every absence has to say what it costs, or the row is a scold.
    for a in surface_mod.assess(t, probe_with())["absent"]:
        if not a["costs"] or not a["where"]:
            return "an absence was reported without what it costs: " + a["what"]
    return None


CASES = [
    ('a reading of the candidates can be recorded',
     case_a_reading_of_the_candidates_can_be_recorded),
    ('an abstention does not become a number',
     case_an_abstention_does_not_become_a_number),
    ('briefs are written by dimension and name their flag',
     case_briefs_are_written_by_dimension_and_name_their_flag),
    ('a run is read back instead of re-measured',
     case_a_run_is_read_back_instead_of_re_measured),
    ('coverage takes its own command when the suite cannot be wrapped',
     case_coverage_takes_its_own_command_when_the_suite_cannot_be_wrapped),
    ('shipping is read from the default branch, not the checkout',
     case_shipping_is_read_from_the_default_branch),
    ('a document nobody loads is not a context cost',
     case_a_document_nobody_loads_is_not_a_context_cost),
    ("a skill's reference is loaded and is counted",
     case_a_skills_reference_is_loaded_and_is_counted),
    ('a repeated table is not a repeated paragraph',
     case_a_repeated_table_is_not_a_repeated_paragraph),
    ('a file is compared to its own kind',
     case_a_file_is_compared_to_its_own_kind),
    ('a small file is never an outlier for being large',
     case_a_small_file_is_never_an_outlier_for_being_large),
    ('an untracked file is not loadable context',
     case_an_untracked_file_is_not_loadable_context),
    ('a pass-to-fail discards the whole claim',
     case_a_pass_to_fail_discards_the_whole_claim),
    ("a test the document's own code also fails is not a finding",
     case_a_test_the_documents_own_code_also_fails_is_not_a_finding),
    ('a test that vanished between runs counts in neither',
     case_a_test_that_vanished_between_runs_counts_in_neither),
    ('a fenced example is not a promise',
     case_a_fenced_example_is_not_a_promise),
    ('a claim has to name something executable',
     case_a_claim_has_to_name_something_executable),
    ('a test that does not parse never became evidence',
     case_a_test_that_does_not_parse_never_became_evidence),
    ('a missing import is the finding and is never dropped',
     case_a_missing_import_is_the_finding_and_is_never_dropped),
    ('a claim whose tests all failed to parse is untested',
     case_a_claim_whose_tests_all_failed_to_parse_is_untested),
    ('a claim still waiting on round two is not a pass',
     case_a_claim_still_waiting_on_round_two_is_not_a_pass),
    ('the blind agent cannot read the repository',
     case_the_blind_agent_cannot_read_the_repository),
    ('a value must be attached, not merely nearby',
     case_a_value_must_be_attached_not_merely_nearby),
    ('overlapping values are agreement, not conflict',
     case_overlapping_values_are_agreement_not_conflict),
    ('a token every document names is not evidence',
     case_a_token_every_document_names_is_not_evidence),
    ('only what the repository keeps is its memory',
     case_only_what_the_repository_keeps_is_its_memory),
    ("somebody else's cloned repository is not ours",
     case_somebody_elses_cloned_repository_is_not_ours),
    ('the surface it uses is coverage, not a count',
     case_the_surface_is_coverage_not_a_count),
]
