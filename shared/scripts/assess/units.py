#!/usr/bin/env python3
"""The floor, one file at a time instead of as a total.

    python3 assess/units.py [--root .] [--json OUT]

Exit codes:
    0 = the units were read
    2 = cannot judge (no loadable context found)

## Why a total hides the thing worth finding

Dimension 5 counts the tokens that reach the model before anybody has typed
anything. That number is right and it is not actionable: a repository paying
1200 tokens a turn across twenty lean files is in a different position from
one paying 1200 across nineteen lean files and one bloated one, and the sum
is identical. Nobody can act on a sum. Everybody can act on *this file is
four times the size of every other one*.

So the same measurement, per unit -- per rule, per document, per skill, per
CLAUDE.md.

## Four things a machine can say about one file

**Its size against its neighbours.** Not against a threshold: a good size for
a rule file is whatever the other rule files in that repository are, and a
number chosen here would be a number chosen for a repository nobody has seen.
The comparison is to the median of its own kind.

**What its sentences are.** Prohibition, requirement, or plain statement, the
split from 0029. A file that is nine-tenths *don't* has a different problem
from one that is nine-tenths description.

**How much of it is fenced.** A document that is mostly code blocks is mostly
examples, and examples are the part an agent can usually reconstruct.

**Sentences it repeats from another file.** The sharpest of the four and the
only one that is certain rather than suggestive: the same paragraph in two
loaded files is paid for twice on every turn, and one of the two copies is
going to drift.

## What is deliberately not decided here

Whether a long file has earned its length. Some of them have; a file that is
four times the median because it is the one place a genuinely intricate
constraint is written down is doing its job. The machine says which files are
unlike their neighbours and in what way; whether that is a fault is a
judgement about content, and it goes to an agent with the rows already sorted.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from value import FENCE, classify                          # noqa: E402

SKIP_DIRS = ("node_modules", "vendor", "venv", "dist", "build", "target",
             "__pycache__", "third_party")

ROOT_INSTRUCTIONS = ("CLAUDE.md", "AGENTS.md")

# Short lines match across unrelated files for uninteresting reasons -- a
# heading, a one-line warning, a licence stub. Sixty characters is where a
# repeated sentence starts being a paragraph somebody wrote twice.
DUPLICATE_MIN = 60

# Unlike its neighbours, and large enough for the difference to cost anything.
OUTLIER_FACTOR = 3.0
OUTLIER_FLOOR = 400


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(400_000)
    except OSError:
        return ""


def _tracked(root):
    r = subprocess.run(["git", "ls-files"], cwd=root,
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return {x.strip() for x in (r.stdout or "").splitlines() if x.strip()}


# --- what the harness delivers, and what a person opens ------------------
#
# This dimension is about text that reaches the model because the harness put
# it there, not about every document in the tree. A guide, a decision record
# and a README are read the way any file is read: somebody opens them. Their
# size is a fact about the writing, and charging it here says a repository is
# expensive for having explained itself.
#
# Measured on this repository the first time it swept everything: the largest
# "context cost" in the tree was the assessment guide, which nothing loads.
# That is not an over-count, it is the wrong population.
DELIVERED = ("root instruction", "nested instruction", "rule", "skill",
             "skill reference", "agent", "command")

_SKILLS_DIR = re.compile(r"(?:^|/)skills/")
_AGENTS_DIR = re.compile(r"(?:^|/)agents/")
_COMMANDS_DIR = re.compile(r"(?:^|/)commands/")


def kind_of(rel):
    """Which population this file's size should be compared against.

    Comparing a skill to a decision record would report every skill as small
    and every decision as huge, which is a fact about the two genres and not
    about this repository.

    Anything that returns `document` is outside the measurement entirely --
    see DELIVERED above."""
    base = os.path.basename(rel)
    if base in ROOT_INSTRUCTIONS and "/" not in rel:
        return "root instruction"
    if base in ROOT_INSTRUCTIONS:
        return "nested instruction"
    if rel.startswith(".claude/") or "/.claude/" in rel:
        return "rule"
    if _SKILLS_DIR.search(rel):
        # A skill's references reach the model when the skill fires, which is
        # why they are in and a document beside them is not.
        return "skill" if base == "SKILL.md" else "skill reference"
    if _AGENTS_DIR.search(rel):
        return "agent"
    if _COMMANDS_DIR.search(rel):
        return "command"
    return "document"


def units(root, everything=False):
    """Every file the harness itself puts in front of the model, with its kind.

    `everything=True` keeps the documents too, which is only useful for
    showing what was left out."""
    keeps = _tracked(root)
    out = []
    for base, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS
                         and (not d.startswith(".") or d == ".claude"))
        for name in sorted(names):
            if not name.endswith(".md"):
                continue
            rel = os.path.relpath(os.path.join(base, name), root)
            rel = rel.replace(os.sep, "/")
            if keeps is not None and rel not in keeps:
                continue
            kind = kind_of(rel)
            if not everything and kind not in DELIVERED:
                continue
            text = _read(os.path.join(base, name))
            if text.strip():
                out.append({"path": rel, "kind": kind, "text": text})
    return out


def _fenced_share(text):
    total = fenced = 0
    inside = False
    for line in text.splitlines():
        if FENCE.match(line):
            inside = not inside
            continue
        if not line.strip():
            continue
        total += 1
        if inside:
            fenced += 1
    return (fenced / total) if total else 0.0


def _normal(sentence):
    return re.sub(r"[^a-z0-9 ]+", "", sentence.lower()).strip()


def measure(root, found=None):
    found = found if found is not None else units(root)
    if not found:
        return None, ("cannot judge: no markdown that could be loaded as "
                      "context")

    seen = {}
    for u in found:
        u["tokens"] = max(1, len(u["text"]) // 4)
        u["fenced"] = round(_fenced_share(u["text"]), 2)
        kinds = {"prohibition": 0, "requirement": 0, "statement": 0,
                 "both": 0}
        for row in classify(u["text"]):
            kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
            if row["text"].count("|") > 2:
                # A markdown table flattens into one enormous pseudo-sentence,
                # and two files sharing a reference table are usually sharing
                # it on purpose. Duplication here is about prose: the same
                # paragraph in two loaded files is the thing that drifts.
                continue
            flat = _normal(row["text"])
            if len(flat) >= DUPLICATE_MIN:
                seen.setdefault(flat, set()).add(u["path"])
        u["sentences"] = kinds
        del u["text"]

    shared = {flat: paths for flat, paths in seen.items() if len(paths) > 1}
    for u in found:
        u["repeats"] = sorted(
            {p for flat, paths in shared.items() if u["path"] in paths
             for p in paths if p != u["path"]})
        u["repeated_sentences"] = sum(1 for paths in shared.values()
                                      if u["path"] in paths)

    # Median of its own kind, so a skill is compared to skills.
    by_kind = {}
    for u in found:
        by_kind.setdefault(u["kind"], []).append(u["tokens"])
    medians = {}
    for kind, sizes in by_kind.items():
        sizes = sorted(sizes)
        mid = len(sizes) // 2
        medians[kind] = (sizes[mid] if len(sizes) % 2 else
                         (sizes[mid - 1] + sizes[mid]) / 2.0)

    outliers = []
    for u in found:
        median = medians[u["kind"]] or 1
        u["times_median"] = round(u["tokens"] / median, 1)
        why = []
        if u["tokens"] > OUTLIER_FLOOR and u["times_median"] >= OUTLIER_FACTOR:
            why.append("%.1fx the median %s" % (u["times_median"], u["kind"]))
        if u["repeated_sentences"] >= 2:
            why.append("%d sentence(s) also in %s"
                       % (u["repeated_sentences"], ", ".join(u["repeats"][:2])))
        n = u["sentences"]
        if n["prohibition"] > 8 and n["prohibition"] > 3 * max(1, n["requirement"]):
            why.append("%d prohibitions to %d requirements"
                       % (n["prohibition"], n["requirement"]))
        if u["fenced"] >= 0.6 and u["tokens"] > OUTLIER_FLOOR:
            why.append("%d%% fenced" % round(100 * u["fenced"]))
        if why:
            outliers.append({"path": u["path"], "kind": u["kind"],
                             "tokens": u["tokens"], "why": why})

    outliers.sort(key=lambda o: -o["tokens"])
    return {"units": found, "medians": medians, "outliers": outliers,
            "duplicated_sentences": len(shared)}, ""


def render(r):
    if not r:
        return "context units: could not judge\n"
    out = ["the floor, one file at a time",
           "  %d unit(s), %d sentence(s) appearing in more than one"
           % (len(r["units"]), r["duplicated_sentences"])]
    for kind in sorted(r["medians"]):
        n = sum(1 for u in r["units"] if u["kind"] == kind)
        out.append("     %-20s %2d file(s), median ~%d tokens"
                   % (kind, n, r["medians"][kind]))
    if not r["outliers"]:
        out.append("  no file is unlike its neighbours")
    for o in r["outliers"][:8]:
        out.append("  %-46s ~%5d  %s" % (o["path"][:46], o["tokens"],
                                         "; ".join(o["why"])))
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    r, why = measure(os.path.abspath(a.root))
    if not r:
        print(why, file=sys.stderr)
        return 2
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=1)
    sys.stdout.write(render(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
