#!/usr/bin/env python3
"""Assessment selftest cases: truth: is what the repository writes down still true?.

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
    git,
    put,
    truth_mod,
    truth_repo,
)



# --------------------------------------------------------------------------
# truth: is what the repository writes down still true?
# --------------------------------------------------------------------------


def case_a_link_to_nothing_is_proven_wrong(t):
    """The one tier that needs no judgement, and it has to actually fire.

    Everything else this module does is a candidate handed to a reader. If the
    proven tier cannot catch a link typed at a file that is not there, the
    module has no floor and every row on it is a guess."""
    truth_repo(t)
    put(t, "docs/broken.md", "See [the plan](../docs/nowhere.md) for details.\n")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "docs: a link to nothing"], t)
    r = truth_mod.assess(t)
    hits = [x for x in r["proven"] if "nowhere.md" in x["claim"]]
    if not hits:
        return ("a markdown link to a file that does not exist was not "
                f"reported: proven={r['proven']}")
    if hits[0]["tier"] != 0:
        return f"the broken link came back as tier {hits[0]['tier']}, not 0"
    return None


def case_a_link_inside_a_fence_is_being_shown_not_followed(t):
    """A link inside ``` is an illustration, and checking it is noise.

    Live, on this repository: a skill showing an example plan linked
    `steps/01-shadow-verify.md`, a file that has never existed and is not meant
    to, and a template wrote `<... see [ARCHITECTURE.md](ARCHITECTURE.md).>`.
    Both were reported as broken references. Three of three proven findings
    were false, which is a proven tier that has proven nothing."""
    truth_repo(t)
    put(t, "docs/example.md",
        "Here is what a plan looks like:\n\n"
        "```markdown\n"
        "- [x] done [Shadow-verify](steps/01-shadow-verify.md)\n"
        "```\n\n"
        "And a template line:\n\n"
        "<Three lines. Then: see [ARCHITECTURE.md](ARCHITECTURE.md).>\n")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "docs: an example"], t)
    r = truth_mod.assess(t)
    false = [x for x in r["proven"]
             if "01-shadow-verify" in x["claim"] or "ARCHITECTURE" in x["claim"]]
    if false:
        return (f"links inside a fence or a <placeholder> were reported as "
                f"broken: {[x['claim'] for x in false]}")

    # And the stripping must not hide a real one on an ordinary line.
    put(t, "docs/example.md",
        open(os.path.join(t, "docs/example.md")).read()
        + "\nAnd really: [gone](../docs/gone.md).\n")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "docs: and a real one"], t)
    r = truth_mod.assess(t)
    if not any("gone.md" in x["claim"] for x in r["proven"]):
        return ("stripping fences also swallowed a broken link on an ordinary "
                "line — the filter is now hiding findings")
    return None


def case_a_historical_document_is_not_stale(t):
    """A decision record describing what used to be true is doing its job.

    The same sentence in a `CLAUDE.md` is a lie and in `docs/decisions/0004-...`
    is a record. A checker that cannot tell them apart reports every ADR a
    repository has ever written, which is the fastest way to be switched off."""
    truth_repo(t)
    put(t, "docs/decisions/0004-we-used-to-do-it-differently.md",
        "We used to keep it in [the old place](../../src/old/thing.py).\n")
    put(t, "CHANGELOG.md", "## 1.0\n- moved [it](src/old/thing.py)\n")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "docs: a record"], t)
    r = truth_mod.assess(t)
    leaked = [x for x in r["proven"] + r["candidates"]
              if "decisions/" in x["file"] or "CHANGELOG" in x["file"]]
    if leaked:
        return (f"historical documents were checked for staleness: "
                f"{[x['file'] for x in leaked]}")
    if not truth_mod.historical("docs/decisions/0004-a.md"):
        return "a numbered record under decisions/ is not read as historical"
    if truth_mod.historical("guide/1-assess.md"):
        return "an ordinary guide page is being excluded as historical"
    return None


def case_two_documents_disagreeing_is_a_candidate(t):
    """The contradiction tier has to be able to fire at all.

    A tier that returns nothing on every repository is indistinguishable from
    a tier that is broken, and this one returned nothing on the repository it
    was written in. So a disagreement is planted and it has to come back --
    as a candidate, never as a finding, because two documents giving a number
    two values may be two different numbers."""
    truth_repo(t)
    put(t, "docs/a.md",
        "The standing context budget for this repository is 800 tokens per "
        "turn, measured across every session on the machine.\n")
    put(t, "docs/b.md",
        "The standing context budget for this repository is 173 tokens per "
        "turn, measured across every session on the machine.\n")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "docs: two budgets"], t)
    r = truth_mod.assess(t)
    hits = [x for x in r["candidates"] if x["tier"] == 4]
    if not hits:
        return ("two documents stating the same budget as 800 and 173 tokens "
                "produced no contradiction candidate")
    if any(x["tier"] == 4 for x in r["proven"]):
        return "a contradiction candidate was reported as proven"
    return None


def case_thickness_is_a_denominator_and_never_a_score(t):
    """Counting what a repository keeps cannot raise anything here.

    0025 rejected thickness scoring for three reasons that all still hold: it
    grades a repository on adopting our conventions, it rewards this plugin's
    own presence, and it calls 0024 -- which cut the standing cost by 81% -- a
    regression while dimension 5 calls it an improvement. Thickness is kept as
    a denominator, and a denominator must not appear in the numerator."""
    truth_repo(t)
    thin = truth_mod.assess(t)
    for i in range(6):
        put(t, f"docs/extra{i}.md", "Some more prose about nothing.\n" * 20)
    put(t, "CLAUDE.md", "Rules.\n")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "docs: more of it"], t)
    thick = truth_mod.assess(t)
    if thick["thickness"]["documents"] <= thin["thickness"]["documents"]:
        return "the denominator did not move when documents were added"
    if len(thick["proven"]) < len(thin["proven"]):
        return ("adding documents that say nothing reduced the proven "
                "findings — thickness is leaking into the score")
    return None


def case_the_candidate_budget_is_shared_between_tiers(t):
    """A budget one tier can eat is not a budget.

    Live: the cap was applied to the tiers concatenated in order, T1 and T2
    filled all 24 slots, and T3 and T4 -- staleness and contradiction, the two
    tiers the module was asked for -- returned rows that were then silently
    discarded. Nothing failed; the page was simply missing two tiers."""
    got = truth_mod._share(5, [["a1", "a2", "a3", "a4", "a5", "a6"],
                               ["b1", "b2"], [], ["d1", "d2", "d3"]])
    if len(got) != 5:
        return f"the cap was not honoured: {got}"
    if "b1" not in got or "d1" not in got:
        return (f"a later tier was starved by an earlier one: {got}")
    # A tier with nothing to say gives its share back rather than holding it.
    if truth_mod._share(4, [["a1", "a2", "a3", "a4", "a5"], [], []]) != [
            "a1", "a2", "a3", "a4"]:
        return "an empty tier's share was not given back"
    return None


CASES = [
    ('a markdown link to a file that is not there is proven wrong',
     case_a_link_to_nothing_is_proven_wrong),
    ('a link inside a fence is being shown, not followed',
     case_a_link_inside_a_fence_is_being_shown_not_followed),
    ('a historical document is not checked for staleness',
     case_a_historical_document_is_not_stale),
    ('two documents disagreeing is a candidate, never a finding',
     case_two_documents_disagreeing_is_a_candidate),
    ('thickness is a denominator and never a score',
     case_thickness_is_a_denominator_and_never_a_score),
    ('the candidate budget is shared, so no tier starves another',
     case_the_candidate_budget_is_shared_between_tiers),
]
