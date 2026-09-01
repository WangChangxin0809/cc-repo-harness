#!/usr/bin/env python3
"""Are the instructions written in a shape a model can follow?

Every other measurement in dimension 4 asks *what* the repository writes down
-- which kinds of memory exist, whether their references resolve, whether two
documents contradict each other. None of them look at the sentences.

That gap matters because instruction form is not a matter of taste. Mishra,
Khashabi, Baral, Choi and Hajishirzi, *Reframing Instructional Prompts to
GPTk's Language* (Findings of ACL 2022, arXiv:2109.07830) rewrote task
instructions without changing what they asked for, and the rewrites moved
task performance by a wide margin across model sizes -- including on models
large enough that people assumed the wording had stopped mattering. Four of
their reframing operations survive translation from a benchmark prompt to a
repository's standing instructions:

* **Itemizing.** A paragraph carrying several requirements becomes a list, one
  requirement per item. A requirement in the middle of a long sentence is a
  requirement competing with its neighbours for attention.
* **Decomposition.** A directive that bundles several steps becomes the steps.
* **Low-level patterns.** An abstract requirement ("follow the house style")
  becomes the concrete shape of the output.
* **Specialization**, and the part this file weighs most: their paper reports
  that *negations are the hard case* -- a constraint stated only as what not to
  do leaves the actual target unstated, and they recommend restating it as a
  positive assertion.

## What this measures and what it refuses to

It measures **candidates**, one per operation, and it judges none of them.
A repository's `CLAUDE.md` may be one long paragraph on purpose; a bare
prohibition may be the whole of what there is to say. Which of these are worth
rewriting is a reading, and the agent does the reading -- the same division of
labour as `judge.py`, `observe.py` and `conflict.py`.

What it deliberately does not do is score prose quality, count adverbs, or
grade readability. Those measure writing. This measures four specific
transformations with a published effect on whether an instruction is followed,
and reports where each one has an opening.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import units as units_mod  # noqa: E402

CITATION = ("Mishra et al., Reframing Instructional Prompts to GPTk's "
            "Language, Findings of ACL 2022, arXiv:2109.07830")

# A sentence that tells the reader to do, or not do, something. The
# distinction that matters here is deontic against alethic: "you must not
# swallow the status" is an instruction, "the two cannot drift" is a fact
# about how something works. Only the first is a thing reframing can change,
# and an early version of this file counted both -- 116 findings across 19
# files, most of them prose describing the repository to itself.
_DIRECTIVE = re.compile(
    r"\b(?:must|shall|should|do not|don't|may not|required to|"
    r"make sure|be sure to)\b|^\s*(?:[-*+]\s*)?(?:Use|Write|Put|Run|Keep|"
    r"Read|Check|Prefer|Never|Always|Avoid|Ensure|Do)\b", re.I | re.M)

# The prohibition half, which is what the paper singles out. Every entry is
# addressed at whoever is reading: an imperative, or an obligation modal, or a
# rule about what is permitted. `cannot` and `does not` are deliberately
# absent -- they describe.
_PROHIBITION = re.compile(
    r"\b(?:must not|must never|may not|shall not|is forbidden|are forbidden|"
    r"not allowed|do not|don't)\b"
    r"|\bno\s+\w+(?:\s+\w+)?\s+may\b"
    r"|(?:^|[.;:]\s+|\*\*)\s*(?:Never|Avoid|Do not|Don't)\b", re.M)

# The repair: what to do instead, anywhere in the immediate neighbourhood. A
# prohibition followed by `Instead, ...` is already reframed, and so is one
# whose alternative came *first* -- "it fails open on purpose, so a broken
# guard must not become a wall" states the behaviour before ruling out its
# opposite. Reading only the sentence the negation sits in reported both.
_REPAIR = re.compile(
    r"\b(?:instead|rather than|in its place|use\b|write\b|put\b|call\b|"
    r"prefer\b|the fix is|the remedy is|go through|belongs? in|"
    r"go(?:es)? (?:in|to)|lives? in|the (?:right|correct) place|"
    r"on purpose|deliberately|by design|which is why)\b", re.I)

_LIST_ITEM = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|\|)", re.M)
# A markdown table row is data laid out in columns, not a sentence addressed to
# anybody -- and a header cell reading "The thing you want to forbid" is a
# column label. Sixth in the family of things this project keeps rediscovering.
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.M)
_FENCE = re.compile(r"^```", re.M)
_HEADING = re.compile(r"^#{1,6}\s", re.M)

# An instruction whose object is a quality rather than an artefact. These are
# the ones with no output shape to show, which is what "low-level patterns"
# asks for.
_ABSTRACT = re.compile(
    r"\b(?:appropriate|appropriately|properly|correctly|reasonable|"
    r"good|clean|idiomatic|sensible|as needed|where appropriate|"
    r"best practice|high quality|carefully|consistent(?:ly)?)\b", re.I)

# How many requirements a paragraph may carry before it wants to be a list.
CROWDED = 2
# Below this, a paragraph is a sentence and itemizing it changes nothing.
LONG_ENOUGH = 45


def _blocks(text):
    """Paragraphs, with fenced code removed and their line numbers kept.

    Code inside a fence is an example of the output, not an instruction about
    it -- and a matcher that reads its own examples as findings is the failure
    this project has now shipped five times."""
    lines = text.splitlines()
    out, cur, start, fenced = [], [], 1, False
    for i, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            if cur:
                out.append((start, "\n".join(cur)))
                cur = []
            continue
        if fenced:
            continue
        if not line.strip():
            if cur:
                out.append((start, "\n".join(cur)))
                cur = []
            continue
        if _TABLE_ROW.match(line):
            continue
        if not cur:
            start = i
        cur.append(line)
    if cur:
        out.append((start, "\n".join(cur)))
    return out


def _sentences(block):
    return [s.strip() for s in re.split(r"(?<=[.!?;])\s+", block) if s.strip()]


def _snip(text, n=110):
    flat = " ".join(text.split())
    return flat if len(flat) <= n else flat[:n - 1] + "…"


# A clause boundary. The alternative to a prohibition lives on the far side of
# one -- "do not commit it; write it into build/" -- and the prohibition's own
# verb lives on the near side.
_CLAUSE = re.compile(r"[,;:]|--| -- |\u2014")


def _around(prev, sent, match, nxt):
    """The text a repair may legitimately live in, given a prohibition at
    `match` inside `sent`.

    Everything except the prohibition's own clause. `use`, `write`, `put` and
    `call` are how an alternative is usually phrased, and they are also the
    verbs prohibitions are built from: "do not **put** a rule in two places"
    suppressed itself, and so did every "do not use", "do not write" and "do
    not call" in the tree. The clause the negation sits in is exactly the part
    that cannot count."""
    tail = sent[match.end():]
    cut = _CLAUSE.search(tail)
    same = tail[cut.end():] if cut else ""
    return " ".join((prev, same, nxt))


def openings(unit):
    """Every reframing opening in one unit. No verdicts, only locations."""
    found = []
    for line_no, block in _blocks(unit["text"]):
        if _HEADING.match(block) or _FENCE.search(block):
            continue
        words = len(block.split())
        directives = _DIRECTIVE.findall(block)
        listed = bool(_LIST_ITEM.search(block))

        # Itemizing: several requirements, in prose, long enough that they are
        # competing rather than one requirement stated twice.
        if not listed and words >= LONG_ENOUGH and len(directives) >= CROWDED:
            found.append({
                "operation": "itemize", "line": line_no, "words": words,
                "why": "{0} requirements in one {1}-word paragraph".format(
                    len(directives), words),
                "text": _snip(block)})

        sents = _sentences(block)
        for i, sent in enumerate(sents):
            # The sentences either side of a prohibition are where the
            # alternative lives -- `Instead, ...` after it, or the behaviour it
            # is ruling out the opposite of, before it.
            nxt = sents[i + 1] if i + 1 < len(sents) else ""
            prev = sents[i - 1] if i else ""
            m = _PROHIBITION.search(sent)
            if m and not _REPAIR.search(_around(prev, sent, m, nxt)):
                found.append({
                    "operation": "positive", "line": line_no,
                    "why": "states what not to do, and not what to do instead",
                    "text": _snip(sent)})
            if _DIRECTIVE.search(sent) and _ABSTRACT.search(sent):
                found.append({
                    "operation": "concrete", "line": line_no,
                    "why": "asks for a quality, without the shape it takes here",
                    "text": _snip(sent)})
    return found


def measure(root, found=None):
    us = found if found is not None else units_mod.units(root)
    if not us:
        return {"could_not_judge": "no instruction units to read"}
    per = []
    for u in us:
        got = openings(u)
        if got:
            per.append({"path": u["path"], "kind": u["kind"], "openings": got})
    counts = {}
    for u in per:
        for o in u["openings"]:
            counts[o["operation"]] = counts.get(o["operation"], 0) + 1
    return {"units": len(us), "with_openings": len(per),
            "counts": counts, "files": per, "citation": CITATION}


OPERATIONS = (
    ("positive", "prohibitions with no stated alternative",
     "the paper's hardest case: a constraint given only as a negation leaves "
     "the target unstated"),
    ("itemize", "paragraphs carrying several requirements at once",
     "one requirement per item; in prose they compete for attention"),
    ("concrete", "requirements asking for a quality, not a shape",
     "replace the adjective with the output pattern it means here"),
)


def render(r):
    """The rows dimension 4 prints. Candidates, for an agent to read."""
    if "could_not_judge" in r:
        return [{"label": "the form of the instructions",
                 "value": "could not judge", "flag": "info",
                 "note": r["could_not_judge"]}]
    rows = [{
        "label": "the form of the instructions",
        "value": "{0} of {1} unit(s) have an opening".format(
            r["with_openings"], r["units"]),
        # `info`, never `bad`. Every row here is a candidate for a rewrite
        # somebody has to agree with, and flagging it red would make the
        # measurement an instruction to change prose nobody has read.
        "flag": "info",
        "note": "four rewrites that do not change what is asked, from " +
                CITATION + ". Which are worth making is a reading."}]
    for op, label, why in OPERATIONS:
        n = r["counts"].get(op, 0)
        if not n:
            continue
        # Two locations, not forty. The page orients; the reading is done
        # against `reframe.py --json`, and saying so beats printing a list
        # nobody can act on from inside a summary.
        where = []
        for f in r["files"]:
            for o in f["openings"]:
                if o["operation"] == op and len(where) < 2:
                    where.append("{0}:{1}".format(f["path"], o["line"]))
        rows.append({
            "label": "  " + label, "value": str(n), "flag": "info",
            "note": "{0}. {1}{2}".format(
                why, ", ".join(where) + " and the rest from "
                if where else "",
                "`python3 shared/scripts/assess/reframe.py --json`"),
            "detail": where})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = measure(os.path.abspath(a.root))
    if a.json:
        print(json.dumps(r, indent=2))
        return 0
    for row in render(r):
        print("{0:52} {1}".format(row["label"], row.get("value", "")))
        if row.get("note"):
            print("    {0}".format(row["note"]))
        for d in row.get("detail") or []:
            print("      {0}".format(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
