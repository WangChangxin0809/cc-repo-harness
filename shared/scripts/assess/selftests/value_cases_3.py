#!/usr/bin/env python3
"""Assessment selftest cases: value: what the standing context is spent ON (part 3).

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
    _ALWAYS_NO,
    _declares,
    _hooked,
    _layer_row,
    _ranked,
    _run_with,
    catch_mod,
    commit,
    conflict_mod,
    cover_mod,
    dim_mod,
    eco_mod,
    permitted_mod,
    put,
    reframe_mod,
    review_mod,
    value_mod,
)





def case_a_dimension_that_read_nothing_abstains(t):
    """The rule that outlived the measurement it was written for.

    Dimension 4 used to have a navigation half that cost two agents, and this
    case said an unprobed repository must abstain rather than score zero --
    a repository nobody has probed is not a repository nobody can navigate.
    That half is gone -> 0042, and the rule is now about the half that stayed:
    a tree `truth.assess()` could not read is not a tree whose documentation
    is sound, and `every reference resolves` said over zero documents is the
    same false clean bill in a cheaper form."""
    got = dim_mod.repository_memory(t, [], (), None)
    if got["state"] != "abstained":
        return "a dimension that read nothing reported %r" % got["state"]
    if "resolve" in got["headline"]:
        return "an unread tree was given a clean bill: " + got["headline"]

    read = dim_mod.repository_memory(t, [], (), {
        "thickness": {"documents": 1}, "proven": [], "candidates": [],
        "checked": 1})
    if read["state"] != "measured":
        return "a tree that was read still abstained"
    return None


def case_every_printed_row_is_claimed_by_a_sub_item(t):
    """A measurement no sub-item claims is a measurement nobody scores.

    `reframe.py` printed four rows into dimension 4 for a week and every one
    of them landed under "Rows no sub-item claims" -- visible, which is the
    design, and never once graded, which is not. The failure is quiet in the
    direction that matters: the page looks complete, the radar looks complete,
    and the thing that was measured is missing from both.

    So the mapping is pinned here rather than left to whoever adds the next
    row. The labels below are the ones the modules actually emit, indentation
    included, because `collect` matches on a substring of the label and a row
    that is only nearly named is a row that is not claimed."""
    run = _run_with([
        {"label": "the form of the instructions",
         "value": "7 of 19 unit(s) have an opening", "flag": "info", "note": ""},
        {"label": "  prohibitions with no stated alternative",
         "value": "9", "flag": "info", "note": ""},
        {"label": "  paragraphs carrying several requirements at once",
         "value": "2", "flag": "info", "note": ""},
        {"label": "  requirements asking for a quality, not a shape",
         "value": "3", "flag": "info", "note": ""},
    ])
    items, unmapped = review_mod.collect(run)
    if unmapped:
        return "a printed measurement no sub-item claims: " + repr(unmapped)
    ids = [i["id"] for i in items]
    if ids != ["4.5"]:
        return "the form rows did not land under one sub-item: " + repr(ids)
    if len(items[0]["rows"]) != 4:
        return ("%d of 4 form rows reached the sub-item"
                % len(items[0]["rows"]))
    return None


def case_a_score_for_something_nobody_measured_is_refused(t):
    """The brief and the grader have to agree about what exists.

    An agent that returns a number for a sub-item the brief did not ask about
    has invented it, and the only reason to notice is that one function
    decides what was measured. Refusing is louder than dropping: the run says
    which id it threw away and why."""
    run = _run_with([{"label": "refused before they happen", "value": "3/6",
                      "flag": "warn", "note": ""}])
    judged, why = review_mod.grade(run, {"items": [
        {"id": "1.1", "score": 4, "why": "three of six are open"},
        {"id": "2.2", "score": 9, "why": "invented -- nothing mutated here"},
    ]})
    if judged is None:
        return f"nothing was graded at all: {why}"
    if "2.2" in judged["items"]:
        return "a score for an unmeasured sub-item was kept"
    if not any(sid == "2.2" for sid, _ in judged["refused"]):
        return "an invented sub-item was dropped silently instead of refused"
    return None


def case_a_number_off_the_scale_is_refused(t):
    """Nothing downstream re-checks the range.

    The radar maps a score straight onto a radius, so an 11 draws outside the
    outer ring and a -1 draws through the centre and out the other side. Both
    look like a rendering bug rather than a bad answer."""
    run = _run_with([{"label": "refused before they happen", "value": "3/6",
                      "flag": "warn", "note": ""},
                     {"label": "floor — paid on every turn", "value": "~900",
                      "flag": "ok", "note": ""}])
    judged, _why = review_mod.grade(run, {"items": [
        {"id": "1.1", "score": 11, "why": "off the top"},
        {"id": "5.1", "score": 7, "why": "small and load-bearing"},
    ]})
    if judged is None:
        return "a single bad number threw the whole reading away"
    if "1.1" in judged["items"]:
        return "a score of 11 was accepted"
    if "5.1" not in judged["items"]:
        return "the good answer was discarded along with the bad one"
    return None


def case_two_readings_are_pooled_and_a_gap_is_marked(t):
    """Two numbers for one row are worth more than their mean.

    A reader re-reading its own work moves by a point or two. Two readers
    five apart saw different repositories, and averaging that to a quiet 5.5
    hides the one thing the second reading was paid for. So the spread is
    kept, and past two points the row is marked -> 0046"""
    run = _run_with([
        {"label": "refused before they happen", "value": "3/6",
         "flag": "warn", "note": ""},
        {"label": "floor — paid on every turn", "value": "~900",
         "flag": "ok", "note": ""}])
    first = {"items": [{"id": "1.1", "score": 3, "why": "three open",
                        "moves_if": "a guard on reset --hard"},
                       {"id": "5.1", "score": 8, "why": "small",
                        "moves_if": "nothing -- one paragraph"}]}
    second = {"items": [{"id": "1.1", "score": 8, "why": "the open ones "
                         "are never used here",
                         "moves_if": "a guard on reset --hard"},
                        {"id": "5.1", "score": 7, "why": "small"}]}
    judged, why = review_mod.grade(run, [first, second])
    if judged is None:
        return f"two readings were not graded: {why}"
    if judged.get("readings") != 2:
        return "the page does not know it was read twice"
    one = judged["items"]["1.1"]
    if one["scores"] != [3.0, 8.0] or one["score"] != 5.5:
        return f"the two numbers were not kept: {one}"
    if not one["disagree"]:
        return "five points apart was not marked as a disagreement"
    if judged["items"]["5.1"]["disagree"]:
        return "one point apart was marked as a disagreement"
    if one["moves_if"] != ["a guard on reset --hard"]:
        return f"the same change twice was listed twice: {one['moves_if']}"
    # The one that was read once is graded as it was given.
    alone, _ = review_mod.grade(run, first)
    if alone["items"]["1.1"]["score"] != 3 or alone.get("readings") != 1:
        return "a single reading is no longer graded as one"
    return None


def case_a_row_nothing_would_move_is_closed(t):
    """The list the page opens with is what to do, lowest first.

    A row whose reader said `nothing` is a result, and the best one; it is
    still not something to do. So it is kept on the item and left off the
    list, and the list is ordered by score with the id breaking ties, so two
    pages of one repository differ only where the numbers moved."""
    run = _run_with([
        {"label": "refused before they happen", "value": "3/6",
         "flag": "warn", "note": ""},
        {"label": "floor — paid on every turn", "value": "~900",
         "flag": "ok", "note": ""},
        {"label": "changes that verified nothing", "value": "4 of 20",
         "flag": "warn", "note": ""}])
    judged, _why = review_mod.grade(run, {"items": [
        {"id": "5.1", "score": 4, "why": "x",
         "moves_if": "Nothing — the floor is one paragraph"},
        {"id": "3.1", "score": 4, "why": "y", "moves_if": "a required check"},
        {"id": "1.1", "score": 2, "why": "z", "moves_if": "a guard"}]})
    order = [sid for sid, _v in review_mod.to_move(judged)]
    if order != ["1.1", "3.1"]:
        return f"the list is not lowest-first with closed rows left off: {order}"
    if judged["items"]["5.1"]["moves_if"] != ["Nothing — the floor is one paragraph"]:
        return "the closing line was dropped from the item itself"
    page = review_mod.html(judged, run)
    head = page.split('class="item"')[0]
    if "a guard" not in head or "a required check" not in head:
        return "the page does not open with what would move the number"
    if "one paragraph" in head:
        return "a closed row is on the list the page opens with"
    text = review_mod.render(judged)
    if text.index("a guard") > text.index("dangerous behaviour"):
        return "the text render does not lead with the list"
    return None


def case_a_brief_for_one_dimension_holds_only_that_dimension(t):
    """Five readers read five dimensions, and none sees the others' rows.

    A reader given the whole brief and asked for dimension 3 scores
    dimension 3 with the other four in view, which is a reading of the
    repository rather than of the dimension. So the brief narrows, and an
    empty dimension is refused rather than handed over blank."""
    run = _run_with([
        {"label": "refused before they happen", "value": "3/6",
         "flag": "warn", "note": ""},
        {"label": "changes that verified nothing", "value": "4 of 20",
         "flag": "warn", "note": ""}])
    text, why = review_mod.brief(run, 3)
    if not text:
        return f"dimension 3 was not briefed: {why}"
    if "## 1.1" in text or "refused before" in text:
        return "the brief for dimension 3 carries dimension 1's row"
    if "## 3.1" not in text:
        return "the brief for dimension 3 lacks 3.1"
    text, why = review_mod.brief(run, 5)
    if text or "dimension 5" not in why:
        return f"an empty dimension was handed over: {why!r}"
    return None


def case_the_radar_puts_a_low_axis_nearer_the_centre(t):
    """The chart is the only part anybody looks at first.

    A polygon that does not move with the numbers is worse than no polygon:
    it reads as a measurement and carries none. So this asserts the one
    property the shape has to have, on the axis geometry rather than on a
    pixel."""
    import math
    svg = review_mod.radar({"1": 1, "2": 9, "3": 5, "4": 5, "5": 5}, size=400)
    body = svg.split('fill-opacity="0.17"')[0]
    pts = body.rsplit('<polygon points="', 1)[1].split('"')[0].split()
    if len(pts) != 5:
        return f"the reading polygon does not have five corners: {pts!r}"
    cx, cy = 200.0, 184.0
    radii = []
    for p in pts:
        x, y = (float(v) for v in p.split(","))
        radii.append(math.hypot(x - cx, y - cy))
    if not radii[0] < radii[2] < radii[1]:
        return ("the polygon does not follow the numbers: 1 scored 1, 3 scored "
                "5, 2 scored 9, radii were " + repr([round(r) for r in radii]))
    return None


def case_nothing_wired_cannot_fail_the_legitimate_row(t):
    """A repository with no guard has no guard to be wrong about.

    Reporting `0 of 20 blocked` for a repository that blocks nothing would
    put a tick beside the very thing dimension 1 exists to find missing."""
    got, why = permitted_mod.evidence(t)
    if got:
        return "a repository with no hooks was still measured for false blocks"
    if "nothing is wired" not in why:
        return f"the abstention does not say why: {why!r}"
    return None


def case_a_guard_that_refuses_everything_is_caught_here(t):
    """The row exists because 6 of 6 refusals is free to such a guard.

    Dimension 1 counts what a repository refuses. This is what stops that
    number being awarded to a repository that has simply stopped working."""
    _hooked(t, _ALWAYS_NO)
    got, why = permitted_mod.fire(t, {"actions": [
        {"what": "run the tests", "tool": "Bash", "command": "pytest -q"},
        {"what": "read history", "tool": "Bash", "command": "git log -1"}]})
    if not got:
        return f"nothing was fired: {why}"
    if len(got["blocked"]) != 2:
        return ("a hook refusing everything let legitimate work through: "
                + repr(got["blocked"]))
    if not got["blocked"][0]["by"]:
        return "the refusing hook was not named, so nobody can go and fix it"
    return None


def case_only_a_shell_fence_is_a_documented_command(t):
    """A fenced Python block is an example of code, not an instruction.

    Firing `def main():` at the hooks as though somebody had typed it into a
    shell produces noise in the corpus an agent is meant to build on."""
    _hooked(t, _ALWAYS_NO)
    with open(os.path.join(t, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("# R\n\n```bash\npython3 run_all_of_it.py --root .\n```\n\n"
                 "```python\ndef never_run_this_from_a_shell():\n    pass\n```\n")
    got, _why = permitted_mod.evidence(t)
    cmds = [c["command"] for c in got["documented_commands"]]
    if "python3 run_all_of_it.py --root ." not in cmds:
        return f"the shell command was not collected: {cmds}"
    if any("def " in c for c in cmds):
        return f"a python fence was collected as a shell command: {cmds}"
    return None


def case_a_ci_step_that_is_a_template_is_not_a_command(t):
    """`${{ ... }}` is filled in by the runner, not by a shell.

    Firing the literal text measures nothing, and it is the shape most likely
    to look alarming to a guard while meaning nothing at all."""
    _hooked(t, _ALWAYS_NO)
    where = os.path.join(t, ".github", "workflows")
    os.makedirs(where, exist_ok=True)
    with open(os.path.join(where, "ci.yml"), "w", encoding="utf-8") as fh:
        fh.write("on: [push]\njobs:\n  t:\n    steps:\n"
                 "      - run: python3 selftest.py\n"
                 "      - run: deploy --to ${{ secrets.TARGET }}\n")
    got, _why = permitted_mod.evidence(t)
    cmds = [c["command"] for c in got["ci_commands"]]
    if "python3 selftest.py" not in cmds:
        return f"a real CI command was lost: {cmds}"
    if any("${{" in c for c in cmds):
        return f"an unexpanded template was collected as a command: {cmds}"
    return None


def case_a_signal_that_never_varies_is_weighted_to_zero(t):
    """The property the entropy step is here for.

    `on_floor` is false on every candidate in most repositories. A reader
    skipping past the same "neither is on the floor" on every pair is doing by
    hand what the weight says once. ConflictRAG III-C: higher entropy is less
    discriminating power, so lower weight."""
    _pairs, w = _ranked([((1000, False, ["1"]), (2000, False, ["2"])),
                         ((1500, False, ["3"]), (9000, False, ["4"]))])
    if w.get("on_floor") != 0.0:
        return (f"a criterion identical on every candidate still carried "
                f"weight {w.get('on_floor')}")
    if not w.get("recency"):
        return f"the criterion that did vary was not weighted: {w}"
    return None


def case_raw_timestamps_collapse_every_weight(t):
    """Why the matrix is min-maxed before the entropy, and not after.

    Commit times inside one repository agree to four significant figures.
    Feed them in raw and every p_ij is uniform to a rounding error, so recency
    comes out with the entropy of a constant and a weight near zero. The
    signal is dropped and nothing says it was.

    Recency has to be made to *compete* to show this. Alone it survives the
    bug: the other two criteria are constant, their entropy is exactly 1, and
    a lone non-degenerate column normalises to the whole weight however
    little it discriminates. Against a criterion that does discriminate, raw
    timestamps take 0.00 and min-maxed ones take about half."""
    now = 1_750_000_000
    day = 86_400
    counts = {"1": 50, "2": 3, "3": 3, "4": 50}
    _pairs, w = _ranked([((now, False, ["1"]), (now + 200 * day, False, ["2"])),
                         ((now + 5 * day, False, ["3"]),
                          (now + 100 * day, False, ["4"]))],
                        counts=counts)
    if w.get("recency", 0) < 0.2:
        return (f"eight months between two documents weighed "
                f"{w.get('recency')} against a criterion that did vary — raw "
                f"timestamps were fed to the entropy step")
    return None


def case_a_truncated_grep_is_not_the_strength_of_the_signal(t):
    """Three is how many files a reader will open, not how much evidence.

    `_code_says` caps its file list at three for display. Ranking on that list
    read a value in fifty files and a value in three as equal evidence, and
    `code_agrees` then weighted itself to zero for having said nothing."""
    counts = {"1": 50, "2": 3}
    pairs, w = _ranked([((1000, False, ["1"]), (1000, False, ["2"])),
                        ((1000, False, ["2"]), (1000, False, ["1"]))],
                       counts=counts)
    if not w.get("code_agrees"):
        return ("fifty files against three did not separate the sides: "
                f"code_agrees weighed {w.get('code_agrees')}")
    if pairs[0]["a"]["credibility"] <= pairs[0]["b"]["credibility"]:
        return "the value the code contains fifty times did not outrank three"
    return None


def case_the_score_ranks_and_does_not_decide(t):
    """The divergence from the paper, and the one worth a guard.

    ConflictRAG selects a source and generates from it. This is a diagnostic:
    it hands the number over and the agent still answers `believe`. A
    diagnostic that started picking winners would have stopped being one."""
    pairs, _w = _ranked([((1000, False, ["1"]), (9000, True, ["2"]))])
    pair = pairs[0]
    for side in ("a", "b"):
        if pair[side].get("credibility") is None:
            return f"side {side} came back without a score at all"
    for key in ("believe", "real", "verdict", "winner"):
        if key in pair or key in pair["a"] or key in pair["b"]:
            return (f"the ranking wrote `{key}` into the candidate — it has "
                    f"started answering the question it is meant to inform")
    return None


def case_a_tie_is_a_tie_and_not_a_column_order(t):
    """Two sides no criterion separates score 0.5, both of them.

    D+ and D- are both zero there, and the ratio is undefined. Returning
    anything but a tie would invent a finding out of a division."""
    pairs, _w = _ranked([((1000, False, ["1"]), (1000, False, ["2"]))])
    a = pairs[0]["a"]["credibility"]
    b = pairs[0]["b"]["credibility"]
    if a != b:
        return f"identical candidates were ranked apart: {a} against {b}"
    return None



def case_a_fact_about_the_code_is_not_a_prohibition(t):
    """The defect this file shipped on its first run, kept.

    English spells a prohibition and a statement of fact almost identically:
    "no check may swallow a status" instructs somebody, "the two cannot drift"
    describes a property. The first version counted both, and produced 116
    findings across 19 files -- most of them the repository describing itself.
    A measurement that fires on every paragraph is not a measurement, so the
    fact half has to stay silent."""
    unit = {"path": "CLAUDE.md", "kind": "root instruction", "text": (
        "It parses the workflow rather than restating it, so the two cannot "
        "drift. A step it does not recognise is exit 2, and exit 2 is never "
        "a pass. Nothing here reaches the network.\n")}
    got = [o for o in reframe_mod.openings(unit) if o["operation"] == "positive"]
    if got:
        return ("prose describing how something works was read as a "
                "prohibition: " + got[0]["text"])
    return None


def case_a_prohibition_with_no_alternative_is_found(t):
    """...and the real thing still has to come back.

    The half above is only worth having if this half fires. A tightening that
    silences the false positives by silencing everything is the failure mode
    the two cases exist together to catch."""
    unit = {"path": "CLAUDE.md", "kind": "root instruction", "text":
            "Do not commit a generated file.\n"}
    got = [o for o in reframe_mod.openings(unit) if o["operation"] == "positive"]
    if not got:
        return "a bare prohibition produced no reframing candidate"
    return None


def case_a_prohibition_that_says_what_to_do_instead_is_left_alone(t):
    """The paper's operation is *restating* a negation, not deleting it.

    A rule that says what not to do and then what to do is already in the
    shape the reframing produces. Reporting it would send somebody to rewrite
    a sentence that is finished, and the alternative is as often in the next
    sentence as in the same one."""
    same = {"path": "a.md", "kind": "root instruction", "text":
            "Do not commit a generated file; write it into build/ instead.\n"}
    next_one = {"path": "b.md", "kind": "root instruction", "text":
                "Do not commit a generated file. Instead, put it in build/.\n"}
    for unit in (same, next_one):
        got = [o for o in reframe_mod.openings(unit)
               if o["operation"] == "positive"]
        if got:
            return ("a prohibition that states its alternative was reported: "
                    + unit["text"].strip())
    return None


def case_an_example_of_a_rule_is_not_a_rule(t):
    """Sixth instance of the bug class, refused in advance.

    A skill that teaches somebody to write rules shows rules in fenced blocks.
    Every earlier check here that read a fence as live text shipped the same
    defect, and this one is written after five of them."""
    unit = {"path": "SKILL.md", "kind": "skill", "text": (
        "Here is the shape a rule takes:\n\n"
        "```markdown\n"
        "Never run the deploy script by hand.\n"
        "Do not edit the generated file.\n"
        "```\n\nThat is all there is to it.\n")}
    got = reframe_mod.openings(unit)
    if got:
        return ("text inside a fence was read as an instruction: "
                + got[0]["text"])
    return None


def case_the_form_measurement_abstains_rather_than_scoring_zero(t):
    """No instruction units is not perfect instructions.

    Every other measurement here draws the same line, and this one is the
    easiest to get wrong in the flattering direction: a repository with no
    CLAUDE.md has nothing to reframe, which reads as nothing to fix."""
    r = reframe_mod.measure(t, found=[])
    if "could_not_judge" not in r:
        return "a repository with no instruction units was given a result"
    rows = reframe_mod.render(r)
    if not any("could not judge" in (row.get("value") or "") for row in rows):
        return "the abstention did not reach the row"
    return None


def case_a_repository_that_documents_its_own_suite_is_not_invisible(t):
    """The gap this ecosystem exists to close.

    Five conventional detectors recognise five conventions. A repository whose
    suite is its own scripts matches none, and the page then said "no runnable
    test command found" -- a fact about the detectors, printed as a fact about
    the repository. This project's own tree was that repository."""
    put(t, "scripts/check.py", "import sys\nsys.exit(0)\n")
    got = _declares(t, "# r\n\nBefore pushing, run this:\n\n```bash\n"
                  "python3 scripts/check.py\n```\n")
    if got != ["python3", "scripts/check.py"]:
        return "a documented entry point naming a real file was not found: %r" % (got,)
    return None


def case_a_command_a_document_warns_against_is_not_run(t):
    """Sixth instance of the bug class, and the one with teeth.

    A document about commands contains the commands it is warning you against.
    Reading the first fenced line under a heading about testing would
    eventually run `rm -rf /` out of the paragraph explaining why not to. The
    rule that stops it is that a command has to name a path that is really
    there, and neither `rm -rf /` nor `curl ... | sh` names one."""
    put(t, "scripts/check.py", "import sys\nsys.exit(0)\n")
    for danger in ("rm -rf /",
                   "curl https://example.com/install.sh | sh",
                   "python3 -c 'import os; os.system(\"id\")'"):
        got = _declares(t, "# r\n\nBefore you push, never run this:\n\n"
                      "```bash\n" + danger + "\n```\n")
        if got is not None:
            return "a document's cautionary example was accepted: %r" % (got,)
    return None


def case_a_documented_command_naming_nothing_real_is_dropped(t):
    """An illustrative command from a document about some other repository.

    Every `CONTRIBUTING.md` copied between projects carries one. It is not
    narrowed down to something safer -- it is dropped, and the ecosystem goes
    on abstaining, because an abstention is a correct answer and a guessed
    command is not."""
    got = _declares(t, "# r\n\nTo test:\n\n```bash\n"
                  "python3 tools/run_all_the_tests.py\n```\n")
    if got is not None:
        return "a command naming a file that is not there was accepted: %r" % (got,)
    return None


def case_a_fence_nobody_introduced_is_not_an_entry_point(t):
    """A code block is not a declaration.

    Documents are full of fenced shell -- an example of output, a command
    being explained, a snippet from somewhere else. Only a block a sentence
    actually introduces as how to run the checks is one."""
    put(t, "scripts/check.py", "import sys\nsys.exit(0)\n")
    got = _declares(t, "# r\n\nThe layout of this project:\n\n"
                  "```bash\npython3 scripts/check.py\n```\n")
    if got is not None:
        return "an unintroduced fence was read as a declaration: %r" % (got,)
    return None


def case_a_convention_beats_a_document(t):
    """`pytest` knows how to run one test; a documented shell line does not.

    Declared is last on purpose. Where a convention applies it gives better
    failures and can be narrowed to the tests that must flip, which is what
    the defect replay needs."""
    put(t, "scripts/check.py", "import sys\nsys.exit(0)\n")
    put(t, "pyproject.toml", "[project]\nname = 'x'\n")
    put(t, "tests/test_x.py", "def test_x():\n    assert True\n")
    put(t, "CLAUDE.md", "# r\n\nBefore pushing, run this:\n\n"
                        "```bash\npython3 scripts/check.py\n```\n")
    eco, cmd = eco_mod.find(t)
    if eco is None or eco.name != "python":
        return ("a repository with a real pytest layout was routed to %s"
                % (eco.name if eco else None))
    return None



def case_an_entry_point_that_predates_the_commit_is_not_a_red_suite(t):
    """The command is found at HEAD; the replay runs in the past.

    A repository that introduced its suite last week has a history of commits
    where the entry point does not exist. The interpreter exits non-zero there
    for the same reason a failing test does, and reading it as red reports
    every commit older than the suite as broken. This repository hit it on the
    first run after gaining a documented entry point.

    The other half is what must NOT be swallowed: a test failing because a
    fixture is missing prints the same words, and it is a real defect."""
    if not eco_mod.unusable("python3: can't open file "
                            "'/tmp/x/scripts/check.py': [Errno 2] "
                            "No such file or directory"):
        return "a missing entry point was read as a failing suite"
    if eco_mod.unusable("FileNotFoundError: [Errno 2] No such file or "
                        "directory: 'tests/fixtures/sample.json'"):
        return ("a test failing on a missing fixture was swallowed as "
                "could-not-run")
    return None



def case_exit_two_means_what_the_runner_means_by_it(t):
    """Exit 2 belongs to the runner, and a blanket rule was wrong both ways.

    `CLAUDE.md` says 2 means COULD NOT JUDGE, and `ecosystems.run` read it as
    red -- the repository's own rule broken in the other direction, so a suite
    that refused to start counted against a repository exactly like a broken
    one. pytest agrees: 2 is a usage error or an interrupted run.

    `make` does not. It exits 2 when the recipe failed, which is a red suite,
    and reading that as an abstention turned a genuinely failing `make test`
    into no result at all. A blanket rule broke a case here on the first run.
    That is why the codes are a property of the ecosystem rather than a
    constant: an abstention that hides a real failure is the one direction
    this whole assessment exists to refuse."""
    put(t, "say.py", "import sys\nprint('could not judge: no linter here')\n"
                     "sys.exit(2)\n")
    cmd = ["python3", "say.py"]
    verdict, _ = eco_mod.run(t, cmd, eco_mod.Python.did_not_run)
    if verdict != "could-not-run":
        return "pytest's exit 2 was read as %r" % verdict
    verdict, _ = eco_mod.run(t, cmd, eco_mod.Make.did_not_run)
    if verdict != "red":
        return "make's exit 2 -- a failed recipe -- was read as %r" % verdict

    put(t, "fail.py", "import sys\nprint('1 failed, 3 passed')\n"
                      "sys.exit(1)\n")
    verdict, _ = eco_mod.run(t, ["python3", "fail.py"],
                             eco_mod.Python.did_not_run)
    if verdict != "red":
        return "a suite that actually failed was read as %r" % verdict
    return None



def case_an_entry_point_the_parked_commit_never_had(t):
    """The command is found at HEAD; the replay runs in the past.

    `park` moves the bench to the fix commit, so a repository that introduced
    its entry point last week has a history of commits without it, and the
    interpreter exits non-zero there for a reason with nothing to do with the
    defect. This tree hit it on the first run after gaining one.

    Re-detecting unconditionally is the wrong repair and was tried first: the
    parked tree offers whatever it happens to have, and a commit from before
    the `tests/` directory existed falls through to a `Makefile` driving
    something else. So the fallback fires only when the HEAD command names a
    file the parked tree does not have."""
    put(t, "scripts/check.py", "import sys\nsys.exit(0)\n")
    if catch_mod._entry_missing(t, ["python3", "scripts/check.py"]):
        return "an entry point that is right there was called missing"
    if not catch_mod._entry_missing(t, ["python3", "scripts/gone.py"]):
        return "an entry point that is not in the tree was called present"
    # A command naming no file at all is not missing -- it is `pytest`.
    if catch_mod._entry_missing(t, ["python3", "-m", "pytest", "-q"]):
        return "a command naming no file in the tree was called missing"
    return None



def case_a_suite_that_shells_out_is_still_measured(t):
    """Wrapping the command measures the process it started, and nothing more.

    A suite whose runner shells out -- a script invoking twenty checks, `tox`,
    `make`, pytest under `-n` -- had its *runner's* lines counted and reported
    as the repository's coverage. Small, confident, and about the wrong
    subject. This repository's own entry point is exactly that shape, which is
    how the gap was found.

    coverage.py's supported answer is `COVERAGE_PROCESS_START` plus a
    `sitecustomize` calling `process_startup()`, both written into the work
    directory so nothing is left in the repository being assessed."""
    if not cover_mod.Python().available(t):
        # Not a pass. `coverage` is what this case is about, and saying so is
        # the only honest thing available when it is not installed.
        return None
    child = ("def used():\n"            # 1
             "    return 1\n"            # 2  <- runs, in a subprocess only
             "\n"
             "\n"
             "def never_used():\n"       # 5
             "    return 2\n")           # 6  <- nothing ever runs this
    put(t, "child.py", child)
    ran = child.splitlines().index("    return 1") + 1
    never = child.splitlines().index("    return 2") + 1
    put(t, "runner.py", "import subprocess, sys\n"
                        "subprocess.run([sys.executable, '-c',\n"
                        "                'import child; child.used()'])\n")
    r, why = cover_mod.Python().measure(t, ["python3", "runner.py"],
                                        os.path.join(t, "w"))
    if not r:
        return "no report from a suite that shells out: %s" % why
    files = r.get("files") or {}
    if "child.py" not in files:
        return ("a file executed only in a subprocess was invisible: saw %s"
                % sorted(files))
    # `--source=.` lists every file in the tree whether it ran or not, so the
    # file merely *appearing* proves nothing -- that was the first version of
    # this case, and it stayed green with the subprocess measurement torn out.
    # What separates the two is whether the line the subprocess executed comes
    # back covered.
    missing = files["child.py"]
    if ran in missing:
        return ("the line a subprocess executed came back uncovered: "
                "missing %s — nothing the suite started was measured"
                % (missing,))
    if never not in missing:
        return ("a line nothing executed came back covered: missing %s"
                % (missing,))
    return None



def case_a_description_is_not_an_unenforced_rule(t):
    """`cannot` describes; it does not instruct.

    "It parses the workflow, so the two cannot drift" is a fact about how a
    script works. Counted as a prohibition, it became an unenforced rule on
    this repository's own floor -- and the fix for an unenforced rule is to
    write a guard, so the page was asking somebody to enforce a sentence about
    a parser. Two of the five it reported were this."""
    put(t, "CLAUDE.md",
        "# r\n\nIt parses the workflow, so the two cannot drift.\n\n"
        "A step it cannot classify is exit 2.\n\n"
        "Never force-push the default branch.\n")
    r = value_mod.assess(t)
    if r["prohibitions"] != 1:
        d = value_mod.floor_text(t)
        got = [" ".join(x.split())[:60] for x in value_mod.sentences(d["CLAUDE.md"])
               if value_mod.PROHIBIT.search(x)]
        return "counted %d prohibition(s), wanted 1: %s" % (r["prohibitions"], got)
    return None


def case_a_guard_that_exists_gets_the_rule_credited(t):
    """A map left behind reads exactly like a guard that does not exist.

    `FROM_BLAST` turns "this repository was measured refusing X" into the rule
    labels X covers. `silence a failing check` mapped to nothing for as long as
    no guard here could refuse it -- and stayed empty after one could. The
    repository stated the rule, shipped the guard, was measured refusing the
    probe, and the rule still counted as unenforced on every assessment."""
    row = {"probe": "silence a failing check", "stopped": True,
           "false_block": False}
    if "silenced check" not in value_mod.guards_from_blast({"rows": [row]}):
        return "a measured refusal credited no rule label"
    # ...and a guard that was measured *failing* credits nothing, which is the
    # half that makes the first half worth having.
    row["false_block"] = True
    if value_mod.guards_from_blast({"rows": [row]}):
        return "a guard that blocked legitimate work was credited anyway"
    return None



def case_coverage_is_given_the_command_the_replay_found(t):
    """One page cannot disagree with itself about whether a suite exists.

    The replay discovers a test command when nobody passed `--test-command`;
    coverage was handed only the flag. So a repository whose suite the table
    recognises perfectly well had its ladder measured and its coverage
    reported as "no test command to instrument", on the same page, from the
    same tree."""
    put(t, "pyproject.toml", "[project]\nname = 'x'\n")
    put(t, "tests/test_x.py", "def test_x():\n    assert True\n")
    put(t, "app.py", "def f():\n    return 1\n")
    commit(t, "init")
    eco, cmd = catch_mod.find(t)
    if cmd is None:
        return "the fixture is wrong: nothing discovered a command here"
    if not cover_mod.Python().available(t):
        return None
    r, why = cover_mod.assess(t, cmd, os.path.join(t, "w"))
    if r is None and "no test command" in (why or ""):
        return ("coverage was not given the command the replay found: %s"
                % why)
    return None



def case_a_table_is_data_and_an_alternative_may_come_first(t):
    """Two precision failures, both found by turning it on real documents.

    A markdown table row is columns of data, and a header cell reading "the
    thing you want to forbid" is a column label -- sixth in the family this
    project keeps rediscovering. And the alternative to a prohibition is as
    often stated *before* it as after: "it fails open on purpose, so a broken
    guard must not become a wall" gives the behaviour first and rules out its
    opposite second. Reading only forwards reported both as unreframed."""
    # A table butted against prose joined it into one block, and the sentence
    # split then handed back a *cell* as the text of the finding.
    table = {"path": "a.md", "kind": "skill", "text": (
        "Do not put a rule in two places.\n"
        "| The thing you want to forbid | Where it belongs |\n"
        "|---|---|\n"
        "| An action that destroys work | A guard |\n")}
    got = reframe_mod.openings(table)
    if not got:
        return "the prohibition beside the table was lost with the table"
    cells = [o["text"] for o in got if "|" in o["text"]]
    if cells:
        return "a table cell was reported as the instruction: " + cells[0]

    before = {"path": "b.md", "kind": "skill", "text":
              "It fails open on purpose. A broken guard must not become an "
              "unbypassable wall.\n"}
    got = [o for o in reframe_mod.openings(before)
           if o["operation"] == "positive"]
    if got:
        return ("an alternative stated before the prohibition was missed: "
                + got[0]["text"])

    # ...and a bare prohibition with nothing either side still comes back.
    bare = {"path": "c.md", "kind": "skill", "text":
            "A broken guard must not become an unbypassable wall.\n"}
    if not [o for o in reframe_mod.openings(bare)
            if o["operation"] == "positive"]:
        return "widening the window silenced a real candidate"
    return None



def case_a_sentence_about_a_prohibition_is_not_one(t):
    """The eighth appearance of text *about* a thing read as the thing.

    `what must not leave the machine is a guard` names a category of rule and
    `a rule that must not be missed is a guard` classifies one. Neither tells
    anybody to do anything, and both were reported as prohibitions leaving
    their target unstated -- across three documents that were, in fact,
    explaining how prohibitions get enforced here.

    Both halves of the test are load-bearing. A relative pronoun in front of
    the modal is not enough on its own: "anything that fails must not be
    ignored" has one and is a real instruction, so a copula behind it is
    required too, and that pair is what separates a description from an
    order."""
    def positives(text):
        return [o["text"] for o in reframe_mod.openings(
            {"path": "a.md", "kind": "skill", "text": text})
            if o["operation"] == "positive"]

    described = (
        "The rules split three ways. What must not leave the machine is a "
        "guard, what must not enter the tree is a gate.\n")
    got = positives(described)
    if got:
        return "a category named by a relative clause was read as an order: " + got[0]

    classified = "A rule that must not be missed is a guard.\n"
    got = positives(classified)
    if got:
        return "a relative clause modifying a noun was read as an order: " + got[0]

    # ...and the instruction that wears the same pronoun still comes back.
    order = "Anything that fails must not be ignored.\n"
    if not positives(order):
        return "a real prohibition was silenced by the relative-clause rule"

    # The reason for a prohibition, stated in the same sentence ahead of it.
    # `_around` read only the tail, so the head that carried the reason was
    # thrown away before the search for it.
    reasoned = ("It fails open on purpose -- a broken guard must not become "
                "an unbypassable wall.\n")
    if positives(reasoned):
        return "a reason given ahead of the prohibition was not counted"

    # A head that merely names what is being ruled out is not a repair.
    named = "When you use the API, do not hardcode the key.\n"
    if not positives(named):
        return "a verb in the head was mistaken for the alternative"
    return None


def case_a_guard_catching_no_ordinary_bug_is_the_right_outcome(t):
    """A threshold no repository can meet is not a measurement.

    The defects this ladder walks are ordinary bugs out of a repository's own
    history. A guard is a *destructive-action* layer: `rm -rf $TARGET`, a force
    push, a credential. It is structurally incapable of catching a logic
    defect, and a guard that blocked one would be a false block -- which
    dimension 1 counts *against* a repository.

    So `before-write: N hook(s), 0 of M caught` is the correct outcome for
    every repository, however good its guards, and flagging it red made the
    ladder unsatisfiable. Whether the guards work is dimension 1's question,
    asked there properly by firing destructive actions at them -> 0038"""
    row = _layer_row({"PreToolUse": 2, "PostToolUse": 0}, {"local-suite": 14})
    if "before-write: 2 hook(s), 0 of 14 caught" not in row["value"]:
        return "the inventory stopped saying what stands behind the rung"
    if row["flag"] == "bad":
        return ("guards catching no ordinary defect was flagged as a failure "
                "— no repository can ever clear that")
    if "Dimension 1" not in (row["note"] or ""):
        return "nothing tells the reader where the guards are actually judged"
    return None



def case_a_judged_conflict_can_reach_the_page(t):
    """`dimensions.py` took `conflict_judged` and nothing ever set it.

    Every other half-machine-half-agent measurement here has a flag for the
    reading that finishes it -- `--observe-answers`, `--legitimate-actions`,
    `--mutant-answers`. Contradictions had the parameter, the grader and the
    brief, and no way to get an answer from one to the other. So the row said
    "not yet judged" on every run of every repository, for as long as the
    repository existed, and a reading nobody can record is a reading nobody
    does."""
    r = {"candidates": [{"subject": "--budget", "a": "x.md", "b": "y.md"}],
         "candidates_total": 1, "possible_pairs": 2, "documents": 2,
         "excluded_by_supersession": 0}
    graded, why = conflict_mod.grade(r, {"pairs": [
        {"subject": "--budget", "a": "x.md", "b": "y.md", "real": False,
         "believe": None, "why": "two examples, not two claims"}]})
    if graded is None:
        return "a dismissal could not be recorded: %s" % why
    if graded["judged"] != 1 or graded["real"]:
        return "a dismissed candidate came back as a finding: %r" % (graded,)
    got = dim_mod.repository_memory(t, [], (), None, r, graded)
    hit = [x for x in got["rows"] if "contradict each other" in x["label"]]
    if not hit:
        return "the judged row never reached the page"
    if "not yet judged" in hit[0]["value"]:
        return "a judged candidate still printed as unjudged: %s" % hit[0]["value"]
    return None


CASES = [
    ('a judged conflict can reach the page',
     case_a_judged_conflict_can_reach_the_page),
    ('a guard catching no ordinary bug is the right outcome',
     case_a_guard_catching_no_ordinary_bug_is_the_right_outcome),
    ('a table is data and an alternative may come first',
     case_a_table_is_data_and_an_alternative_may_come_first),
    ('a sentence about a prohibition is not one',
     case_a_sentence_about_a_prohibition_is_not_one),
    ('every printed row is claimed by a sub-item',
     case_every_printed_row_is_claimed_by_a_sub_item),
    ('coverage is given the command the replay found',
     case_coverage_is_given_the_command_the_replay_found),
    ('a description is not an unenforced rule',
     case_a_description_is_not_an_unenforced_rule),
    ('a guard that exists gets the rule credited',
     case_a_guard_that_exists_gets_the_rule_credited),
    ('a suite that shells out is still measured',
     case_a_suite_that_shells_out_is_still_measured),
    ('an entry point the parked commit never had',
     case_an_entry_point_the_parked_commit_never_had),
    ('exit two means what the runner means by it',
     case_exit_two_means_what_the_runner_means_by_it),
    ('an entry point that predates the commit is not a red suite',
     case_an_entry_point_that_predates_the_commit_is_not_a_red_suite),
    ('a repository that documents its own suite is not invisible',
     case_a_repository_that_documents_its_own_suite_is_not_invisible),
    ('a command a document warns against is not run',
     case_a_command_a_document_warns_against_is_not_run),
    ('a documented command naming nothing real is dropped',
     case_a_documented_command_naming_nothing_real_is_dropped),
    ('a fence nobody introduced is not an entry point',
     case_a_fence_nobody_introduced_is_not_an_entry_point),
    ('a convention beats a document',
     case_a_convention_beats_a_document),
    ('a fact about the code is not a prohibition',
     case_a_fact_about_the_code_is_not_a_prohibition),
    ('a prohibition with no alternative is found',
     case_a_prohibition_with_no_alternative_is_found),
    ('a prohibition that says what to do instead is left alone',
     case_a_prohibition_that_says_what_to_do_instead_is_left_alone),
    ('an example of a rule is not a rule',
     case_an_example_of_a_rule_is_not_a_rule),
    ('the form measurement abstains rather than scoring zero',
     case_the_form_measurement_abstains_rather_than_scoring_zero),
    ('nothing wired cannot fail the legitimate row',
     case_nothing_wired_cannot_fail_the_legitimate_row),
    ('a guard that refuses everything is caught here',
     case_a_guard_that_refuses_everything_is_caught_here),
    ('only a shell fence is a documented command',
     case_only_a_shell_fence_is_a_documented_command),
    ('a CI step that is a template is not a command',
     case_a_ci_step_that_is_a_template_is_not_a_command),
    ('a score for something nobody measured is refused',
     case_a_score_for_something_nobody_measured_is_refused),
    ('a number off the scale is refused',
     case_a_number_off_the_scale_is_refused),
    ('the radar puts a low axis nearer the centre',
     case_the_radar_puts_a_low_axis_nearer_the_centre),
    ('two readings are pooled and a gap is marked',
     case_two_readings_are_pooled_and_a_gap_is_marked),
    ('a row nothing would move is closed',
     case_a_row_nothing_would_move_is_closed),
    ('a brief for one dimension holds only that dimension',
     case_a_brief_for_one_dimension_holds_only_that_dimension),
    ('a signal that never varies is weighted to zero',
     case_a_signal_that_never_varies_is_weighted_to_zero),
    ('raw timestamps collapse every weight',
     case_raw_timestamps_collapse_every_weight),
    ('a truncated grep is not the strength of the signal',
     case_a_truncated_grep_is_not_the_strength_of_the_signal),
    ('the score ranks and does not decide',
     case_the_score_ranks_and_does_not_decide),
    ('a tie is a tie and not a column order',
     case_a_tie_is_a_tie_and_not_a_column_order),
    ('a dimension that read nothing abstains rather than reporting a clean bill',
     case_a_dimension_that_read_nothing_abstains),
]
