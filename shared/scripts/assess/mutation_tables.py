#!/usr/bin/env python3
"""Row builders for dimension 2's coverage and mutation tables.

Split out of `dimensions.py`, which had grown past the line the Read tool
shows in one call -- see decision 0053. These four functions share no state
with the rest of that module: each turns one probe's raw structure (a
coverage report, a mutation run, a judged-mutant answer set) into the
`{label, value, flag, note}` rows the page renders, and nothing else in
`dimensions.py` reaches into them except by calling them.

`dimensions.py` imports every name here so `dim_mod.mutant_ladder` and
friends keep resolving for callers that never knew this file existed --
`assess/selftest.py` is one of them.
"""

from __future__ import annotations


def suite_rows(catch):
    """Which suites the ladder was measured on, and which it could not be.

    A repository with Python at the root and Go under `cli/` has two suites,
    and the page used to name one. Every suite `find_all` returns is run at
    each rung and the verdict is pooled -- red if any suite is red -- so the
    reader has to be told how many suites that pool holds.

    The second row is an abstention and reads as one: a suite whose toolchain
    this machine lacks is an absence on the machine, not in the repository,
    and a clone on a fully equipped machine would run it -> 0047. It is
    never flagged bad, and `review.measured` leaves its value unscored."""
    suites = (catch or {}).get("suites") or []
    if not suites:
        return []
    ran = [s for s in suites if s.get("ran")]
    idle = [s for s in suites if not s.get("ran")]
    rows = [{
        "label": "suites measured",
        "value": "%d — %s" % (len(ran), ", ".join(s["ecosystem"] for s in ran))
                 if ran else "0",
        "flag": "info",
        "note": "every suite the tree holds runs at each rung and the "
                "verdict is pooled: red if any suite is red, could not run "
                "only if none ran, green otherwise. A root Makefile or a "
                "documented command counts as the one suite that drives the "
                "rest"
                + (". Commands: " + "; ".join(s["command"] for s in ran
                                               if s.get("command"))
                   if len(ran) > 1 else "")}]
    if idle:
        rows.append({
            "label": "suites found but not run",
            "value": "; ".join("%s — not run: %s" % (s["ecosystem"], s["why"])
                               for s in idle),
            "flag": "info",
            "note": "an abstention for these suites, not a finding: what is "
                    "missing is on this machine, and a clone on one that has "
                    "it would run them -> 0047. The ladder below was measured "
                    "on the suites that ran, so a defect only one of these "
                    "would catch is invisible here, in neither direction"})
    return rows


def coverage_rows(c, why=""):
    """What the ladder cannot speak about, placed before it rather than after.

    Coverage predicts almost nothing in the direction people usually read it:
    for one project's one suite, its correlation with actually finding bugs is
    weak (Zhao, Zhou & Cohen 2026, r <= 0.481 pooled). Read the other way it is
    not a correlation at all but a guarantee -- a line no test executes cannot
    be caught at the `local-suite` rung, for any defect, ever.

    So these rows are the **denominator of the two injections below them**. The
    replay only reaches lines this repository's history put a bug in; mutation
    only touches lines the suite already executes. Coverage is the part both of
    them are silent about, and silence that is not stated reads as a pass.

    The numbers come from the ecosystem's own tool. A criterion that tool does
    not produce gets no row, and gets named in a row of its own instead: Go has
    no branch coverage at all, and a Go repository reading `0 of 0 branches`
    would be a lie about the language rather than a fact about the code."""
    if not c:
        if not why:
            return []
        return [{"label": "what no test executes", "value": "could not judge",
                 "flag": "info",
                 "note": why.replace("cannot judge: ", "")
                         + " — so the rows below are silent about an unknown "
                           "share of this repository, rather than about a "
                           "known one"}]

    LABEL = {"statement": "statements no test executes",
             "function": "functions no test enters",
             "branch": "branches never taken both ways",
             "mcdc": "conditions that never decided anything"}
    rows, criteria = [], c.get("criteria") or {}
    # Several suites, each measured by its own tool and summed. The note
    # says which suites a figure pools, and which of them produced this
    # criterion when not all did -- Go has no branch coverage, so a pooled
    # branch row beside a Go suite is Python's alone.
    pooled = c.get("pooled") or {}
    measured = pooled.get("measured") or []
    for key in ("statement", "function", "branch", "mcdc"):
        got = criteria.get(key)
        if not got:
            continue
        share = (1.0 - got["covered"] / got["total"]) if got["total"] else 0.0
        note = "%s, %s" % (c.get("tool", "the ecosystem's tool"),
                           c.get("how", "measured"))
        if measured:
            came = (pooled.get("criteria_from") or {}).get(key) or measured
            note += "; pooled over " + ", ".join(measured)
            if len(came) < len(measured):
                note += " — this criterion from " + ", ".join(came) + " only"
        rows.append({
            "label": LABEL[key],
            "value": "%d of %d  (%.0f%%)" % (got["missing"], got["total"],
                                             100 * share),
            "flag": "bad" if share > 0.5 else "info",
            "note": note})
    if pooled.get("not_measured") and rows:
        rows.append({
            "label": "suites the figure above does not cover",
            "value": "; ".join("%s — not measured: %s" % (s["ecosystem"],
                                                          s["why"])
                               for s in pooled["not_measured"]),
            "flag": "info",
            "note": "the figures pool %d of %d suites. What is missing for "
                    "the rest is a tool on this machine, which abstains, "
                    "not a fact about the repository -> 0047"
                    % (len(measured),
                       len(measured) + len(pooled["not_measured"]))})

    absent = [k for k in ("statement", "function", "branch", "mcdc")
              if k not in criteria]
    if absent and rows:
        rows.append({
            "label": "criteria this tool does not produce",
            "value": ", ".join(absent),
            "flag": "info",
            "note": "absent, not zero. No mainstream tool outside the "
                    "compilers computes MC/DC at all, and Go's tooling has no "
                    "branch coverage — so a missing row here is a fact about "
                    "the ecosystem, not about this repository"})
    return rows


def mutant_ladder(m, judged=None):
    """Where each mutant was first caught -- and which ones are defects.

    Three groups, and the difference between them is the whole design:

    * **Caught somewhere.** A hook refused it, or the suite went red, or CI
      did. Something asserted about that line, so the change is a real defect
      by construction and no second opinion is needed.
    * **Caught nowhere, and judged a defect.** An agent read the enclosing
      code and said a test catching this would be a test worth having. It
      belongs at `never`, and it is the most expensive row on the page.
    * **Caught nowhere, and judged not a defect.** It leaves the count
      entirely. `never` is only a failure if the thing that was never caught
      was worth catching, and the paper's own figure says three survivors in
      ten are not: an initial capacity, a log line, a default nobody promised.

    Unjudged survivors are in none of the three. They are `pending`, and they
    are reported as pending rather than parked at `never`, because counting
    them there would let a repository look worse for having bought a
    measurement nobody has finished reading."""
    counts = {k: 0 for k in m.get("ladder", {})} or {}
    for k in m.get("ladder", {}):
        counts[k] = m["ladder"][k]
    pending = counts.get("never", 0)
    counts["never"] = 0
    real, dropped = [], []
    for row in (judged or {}).get("rows", []):
        if row.get("judged") == "productive":
            real.append(row)
        elif row.get("judged") == "unproductive":
            dropped.append(row)
    counts["never"] = len(real)
    return counts, max(0, pending - len(real) - len(dropped)), real, dropped


def mutation_rows(m, ladder_names, judged=None):
    """The rows dimension 2 gains from the second injection.

    A surviving mutant is a **candidate**, never a finding. The paper this is
    copied from reports 70.6% of the survivors it showed Python developers
    being worth acting on, which also means most of the rest were not. Any row
    here that reads as a defect count would be wrong three times in ten, and
    the page has no way to tell which three -- only an agent that reads the
    enclosing code does, which is why the brief exists."""
    counted = m["killed"] + m["survived"]
    rows = []
    if not counted:
        rows.append({"label": "mutated lines", "value": "could not judge",
                     "flag": "info",
                     "note": "every mutant was unplaceable, or broke the "
                             "suite's own loading — neither is a verdict "
                             "about the repository"})
        return rows

    # The caveats come first on purpose. A figure taken over a flaky suite, or
    # over lines no test executes, is not the figure the paper reports, and
    # printing it above its own caveat invites the comparison it cannot
    # support.
    if m.get("flaky"):
        rows.append({
            "label": "!! the suite is flaky",
            "value": "not green on all 3 baseline runs",
            "flag": "warn",
            "note": "a mutant counts as caught whenever the suite goes red — "
                    "including when it would have gone red anyway. Every "
                    "mutation figure here is an upper bound on what this "
                    "repository really catches"})
    if not m.get("coverage", "").startswith("measured"):
        rows.append({
            "label": "!! coverage was not available",
            "value": "the covered-line restriction was dropped",
            "flag": "warn",
            "note": "so the mutated lines include lines no test executes, "
                    "which reach `never` by construction and say nothing "
                    "about this repository. Not comparable to the paper's "
                    "figure"})

    _c, pending, real, dropped = mutant_ladder(m, judged)
    if pending:
        rows.append({
            "label": "mutants nothing caught, awaiting judgement",
            "value": f"{pending} pending",
            "flag": "warn",
            "note": "NOT yet defects, and deliberately not counted at `never`. "
                    "Roughly three in ten will be lines nothing should assert "
                    "about, and this page cannot tell which — only something "
                    "that reads the enclosing code can. The brief for that "
                    "pass is in the JSON under `mutant_brief`; feed the "
                    "verdicts back with --mutant-answers"})
    if real or dropped:
        rows.append({
            "label": "of those, judged real defects",
            "value": f"{len(real)} of {len(real) + len(dropped)}",
            "flag": "bad" if real else "ok",
            "note": f"{len(dropped)} "
                    f"{'was' if len(dropped) == 1 else 'were'} judged not "
                    f"worth a test and left the "
                    f"count entirely — `never` is only a failure when the "
                    f"thing never caught was worth catching. Judged by an "
                    f"agent that did not write this code, which is a weaker "
                    f"judge than the paper's 66,798 developer clicks"
                    + ("; first: " + (real or dropped)[0].get("why", "")[:90]
                       if (real or dropped)[0].get("why") else "")})

    if m.get("suppressed"):
        rows.append({
            "label": "changes not worth making",
            "value": f"{m['suppressed']} suppressed",
            "flag": "info",
            "note": "mutants an arid-node rule threw away before running "
                    "anything — a changed log string, a timeout constant, a "
                    "flag default. 25 rules transcribed from the paper's "
                    "Appendix A; one was not, and is marked where it is "
                    "defined"})

    outside = []
    if m.get("broken"):
        outside.append(f"{m['broken']} broke the suite's loading")
    if m.get("timeout"):
        outside.append(f"{m['timeout']} hung past {m.get('budget_seconds')}s")
    if m.get("false_block"):
        outside.append(f"{m['false_block']} refused by a hook that refused the "
                       f"original line too")
    if outside:
        rows.append({
            "label": "mutants outside the ladder",
            "value": ", ".join(outside),
            "flag": "info",
            "note": "none of these is a catch. A suite that cannot import has "
                    "not detected anything, a hang is changed behaviour "
                    "nothing asserted, and a hook that refuses every edit to "
                    "a file has discriminated nothing"})
    return rows

