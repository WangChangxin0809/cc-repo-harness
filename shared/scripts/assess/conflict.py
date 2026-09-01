#!/usr/bin/env python3
"""Where two documents in this repository disagree with each other.

    python3 assess/conflict.py [--root .] [--json OUT]
    python3 assess/conflict.py --brief RUN.json
    python3 assess/conflict.py --grade RUN.json --answers ANSWERS.json

Exit codes:
    0 = the pairs were narrowed, or the answers were graded
    2 = cannot judge (fewer than two documents)

## Two stages, because every pair is O(n squared)

After ConflictRAG (arXiv:2605.17301), whose result that carries over here is
not the classifier but the shape: a cheap filter first, a model only on what
survives. They report 62% fewer API calls at 90.8% detection accuracy. Thirty
one documents is 465 pairs, and handing all of them to an agent is a bill
nobody will pay twice.

Their cheap stage is an embedding classifier. That is not available here --
`shared/` is standard library only, offline -- so ours is lexical and weaker:
two documents are a candidate only when they **name the same thing and attach
different values to it**. Weaker in the sense that it misses conflicts phrased
without a shared token. It is not weaker at what it is for, which is refusing
to spend an agent on 460 pairs that share nothing.

## What counts as naming the same thing

Not words. Code-shaped tokens: things in backticks, paths with a slash, CLI
flags, filenames with an extension, identifiers with an underscore. Prose
overlap between two documents in one repository is total and meaningless --
every document says "the repository" -- while `--mutate`, `shared/scripts/`
and `exit 2` are things a repository can hold exactly one truth about.

## What counts as disagreeing

**A different number for the same subject.** `--mutate` defaults to 30 in one
document and 25 in another. This is the strongest signal and the least
arguable.

A third rule was tried and cut: *a different path for the same subject* and
*one negates what the other asserts*. The first was meant to catch a directory
that moved and was updated in one document only; it produced 772 pairs
comparing paths that merely happened to sit near the same flag. The second
produced 552, because one document saying "X does not do Y" and another saying
"X does Z" is two different predicates, and nothing lexical can tell that from
a contradiction.

Both signals are real and neither is expressible here. What is left is one
rule that fires **once** on this repository, on a genuine inconsistency
between an agent definition and the skill it invokes. One precise rule beats
three that bury it: a filter whose own author's repository produces 553 hits
has not narrowed anything, it has moved the reading problem somewhere else.

**One negates what the other asserts.** Same subject, one sentence carrying a
negation. Noisiest of the three, so it is marked as the weakest class rather
than mixed in.

## Supersession is not conflict

A decision record that replaces an earlier one contradicts it **on purpose**,
and a repository that keeps its history will have many. Reporting those is
worse than reporting nothing: it buries the real findings under the ones the
authors are proudest of.

So documents that declare a supersession relationship -- `Supersedes 0031`,
`Status: superseded`, `Replaced by` -- are not paired with each other. This
was not a hypothetical: run against this repository before the rule existed,
the loudest candidates were 0031 against 0033, which is the system working.

## What is ranked, and why anything is

When two documents disagree, something has to say which one to believe, or
the finding is only *these two differ* and the reader has to go and look
anyway. The paper scores source credibility. Ours are three signals a
repository already has: which was written last, which one is on the floor
(paid for on every turn, so its claim reaches the agent whether or not anybody
opened it), and which one the code agrees with. None of them decides; all
three are handed over with the pair.
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

SKIP_DIRS = ("node_modules", "vendor", "venv", "dist", "build", "target",
             "__pycache__", "third_party", "external", "fixtures", "testdata")

MAX_BYTES = 300_000
MAX_DOCS = 400

# A token a repository can hold exactly one truth about. Prose words are
# excluded by construction: every document in a repository says "the
# repository", and overlap on that is not evidence of anything.
_BACKTICK = re.compile(r"`([^`\n]{2,60})`")
_PATHY = re.compile(r"\b([\w.-]+/[\w./-]+)\b")
_FLAG = re.compile(r"(--[a-z][\w-]{1,30})")
_DOTTED = re.compile(r"\b(\w+\.(?:py|js|ts|go|rs|java|json|yml|yaml|toml|md|sh))\b")
_NUMBER = re.compile(r"\b(\d+(?:\.\d+)?)\b")
_NEGATION = re.compile(r"\b(never|not|no|cannot|can't|must not|does not|"
                       r"doesn't|without|refuses?|forbidden)\b", re.I)

_SUPERSEDE = re.compile(r"^\s*(supersedes?|superseded by|replaces?|replaced by|"
                        r"status:\s*superseded)\b(.*)$", re.I | re.M)
_DOC_ID = re.compile(r"\b(\d{4})\b")

# Numbers that mean nothing on their own and would pair every document with
# every other: years, small ordinals used for lists, markdown heading levels.
_NOISE_NUMBERS = {"0", "1", "2", "3", "20", "100"}


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(MAX_BYTES)
    except OSError:
        return ""


def _tracked(root):
    """What the repository actually keeps, or None if it is not a checkout.

    Untracked and ignored files are not this repository's memory. `tmp/` here
    holds throwaway assessment pages that nobody committed on purpose, and
    comparing them against the documents is comparing a draft against the
    thing it was drafting."""
    r = subprocess.run(["git", "ls-files"], cwd=root,
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return {line.strip() for line in (r.stdout or "").splitlines() if line.strip()}


def documents(root):
    """Every prose document, with its text. Not code: this compares what the
    repository *says* against what it says elsewhere, and 4.3 is the separate
    and much dearer question of what it says against what it does."""
    out = []
    keeps = _tracked(root)
    for base, dirs, names in os.walk(root):
        # Dot-directories go too, and that is not tidiness. This repository
        # keeps a corpus of *other people's cloned repositories* under
        # `eval/.work/`, and the first run of this module compared 355 of
        # their documents against each other and reported the findings as
        # this repository's. A document somebody else wrote is not this
        # repository's memory, and the same holds for anything fetched,
        # vendored or checked out beneath us.
        dirs[:] = sorted(d for d in dirs
                         if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(names):
            if not name.endswith((".md", ".mdx", ".rst", ".txt")):
                continue
            rel = os.path.relpath(os.path.join(base, name), root)
            rel = rel.replace(os.sep, "/")
            if keeps is not None and rel not in keeps:
                continue
            text = _read(os.path.join(base, name))
            if text.strip():
                out.append({"path": rel, "text": text})
            if len(out) >= MAX_DOCS:
                return out
    return out


# A subject has to be a thing a repository can hold exactly one truth about:
# a flag, a path, a filename, a snake_case or dotted identifier. Backticks
# alone are not enough -- they hold markdown headings, colour literals and
# shell fragments, and every one of those paired documents that have nothing
# to do with each other.
_SUBJECT_OK = re.compile(r"""^(?:
      --[a-z][\w-]{1,30}                    # a CLI flag
    | [\w][\w.-]*(?:/[\w.-]+)+             # a path
    | [\w-]+\.[A-Za-z]{1,5}                 # a filename with an extension
    | [a-z_][a-z0-9_]*_[a-z0-9_]+           # a snake_case identifier
    | [a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*    # a dotted identifier
    )$""", re.X)


def subjects(text):
    """Code-shaped tokens this document names."""
    got = set()
    for pattern in (_BACKTICK, _PATHY, _FLAG, _DOTTED):
        for m in pattern.finditer(text):
            token = m.group(1).strip().strip(".,;:")
            if len(token) >= 3 and _SUBJECT_OK.match(token):
                got.add(token)
    return got


def _sentences(text):
    for chunk in re.split(r"(?<=[.!?])\s+|\n\s*\n|\n\s*[-*|]\s*", text):
        chunk = chunk.strip()
        if chunk:
            yield chunk


# How close a number has to sit to a subject to be that subject's value.
# Sentence scope was tried first and it is far too wide: a sentence naming
# `shared/scripts/` and counting nine gates elsewhere in the same breath is
# not attaching nine to the path. Measured on this repository, sentence scope
# made 1051 candidates out of 1891 document pairs -- more than half of every
# pair, which is a filter that has stopped filtering.
WINDOW = 60


def claims(text):
    """{subject: {"numbers": set, "paths": set, "where": str}}

    A claim is a subject and a value found **beside each other**, not merely
    in the same sentence. The window is what makes this a filter rather than a
    coincidence detector, and it is the single number the precision of the
    whole module rests on."""
    out = {}
    for subject in subjects(text):
        try:
            hits = [m.start() for m in
                    re.finditer(re.escape(subject), text)][:20]
        except re.error:
            continue
        for at in hits:
            near = text[max(0, at - WINDOW):at + len(subject) + WINDOW]
            # The number has to be *attached*, not nearby. `--budget 3000` is
            # a value; a `--json` flag with the words "Stage 5" eleven
            # characters away is not, and a window alone cannot tell them
            # apart -- it made 1050 candidates out of 1891 document pairs,
            # which is a filter that has stopped filtering.
            after = text[at + len(subject):at + len(subject) + 16]
            # The separators include the closing backtick and quote. Subjects
            # are usually written as `retry_limit`, so a rule that allowed
            # only whitespace between the name and its value silently matched
            # nothing but bare occurrences -- under-reporting that looks
            # exactly like a clean repository.
            numbers = {m.group(1) for m in
                       re.finditer(r"^[`'\"\s=:,]{0,4}(\d+(?:\.\d+)?)\b",
                                   after)
                       if m.group(1) not in _NOISE_NUMBERS}
            paths = {p for p in _PATHY.findall(near)
                     if "/" in p and p != subject}
            slot = out.setdefault(subject, {"numbers": set(), "paths": set(),
                                            "where": ""})
            slot["numbers"] |= numbers
            slot["paths"] |= paths
            if not slot["where"]:
                slot["where"] = " ".join(near.split())[:200]
    return out


def supersession(docs):
    """Which documents replace which, so they are not reported as disagreeing.

    Keyed by the four-digit id decision records carry, because that is how
    they refer to each other -- `Supersedes 0031`, not by filename."""
    ids, links = {}, set()
    for doc in docs:
        m = _DOC_ID.search(os.path.basename(doc["path"]))
        if m:
            ids.setdefault(m.group(1), doc["path"])
    for doc in docs:
        mine = _DOC_ID.search(os.path.basename(doc["path"]))
        head = doc["text"][:1500]
        for m in _SUPERSEDE.finditer(head):
            for other in _DOC_ID.findall(m.group(2) or ""):
                if other in ids:
                    links.add(frozenset((doc["path"], ids[other])))
            # `Status: superseded` with no id names nothing, but it does say
            # this document is not current -- enough to stop pairing it with
            # anything, since the reader has already been told not to trust it.
            if mine and "supersede" in m.group(1).lower() and not m.group(2).strip():
                links.add(frozenset((doc["path"], doc["path"])))
    return links


def _recency(root, path):
    r = subprocess.run(["git", "log", "-1", "--format=%ct", "--", path],
                       cwd=root, capture_output=True, text=True)
    try:
        return int((r.stdout or "0").strip() or 0)
    except ValueError:
        return 0


def _on_floor(path):
    """Loaded on every turn whether or not anybody opened it.

    A claim on the floor reaches the agent regardless; a claim in a document
    nobody opened does not. So when two disagree, which of them is on the
    floor is not a tiebreak on correctness -- it is which one is currently
    doing damage."""
    base = os.path.basename(path)
    return base in ("CLAUDE.md", "AGENTS.md") or path in ("CLAUDE.md",
                                                          "AGENTS.md")


def _code_says(root, token, values):
    """Which of two disputed values the code itself contains.

    Not authoritative -- a value can appear in code for unrelated reasons --
    and it is the only one of the three signals that looks outside the
    documents at all, which is why it is worth the grep."""
    hits = {}
    for value in values:
        r = subprocess.run(
            ["git", "grep", "-l", "--fixed-strings", "-e", str(value),
             "--", "*.py", "*.js", "*.ts", "*.go", "*.rs", "*.json",
             "*.yml", "*.yaml", "*.toml"],
            cwd=root, capture_output=True, text=True)
        files = [f for f in (r.stdout or "").split() if f]
        if files:
            hits[str(value)] = files[:3]
    return hits


def narrow(root, docs=None):
    """Stage one. Pairs that name the same thing and attach different values.

    Everything here is lexical and nothing is judged. A pair reaching the
    output means only that an agent should look at it."""
    docs = docs if docs is not None else documents(root)
    if len(docs) < 2:
        return None, "cannot judge: fewer than two documents to compare"

    excluded = supersession(docs)
    indexed = [(d["path"], claims(d["text"])) for d in docs]

    # A token most documents name says nothing about which pair to open.
    # `CLAUDE.md` is in almost every file here and produced 27 of the first 40
    # candidates on its own. This is the oldest trick in retrieval and it
    # applies unchanged: a term with no discriminating power is not evidence,
    # however code-shaped it looks.
    seen = {}
    for _path, cl in indexed:
        for subject in cl:
            seen[subject] = seen.get(subject, 0) + 1
    ceiling = max(2, int(0.4 * len(docs)))
    common = {s for s, n in seen.items() if n > ceiling}

    pairs = []
    for i in range(len(indexed)):
        for j in range(i + 1, len(indexed)):
            a_path, a = indexed[i]
            b_path, b = indexed[j]
            if frozenset((a_path, b_path)) in excluded:
                continue
            if frozenset((a_path, a_path)) in excluded or \
               frozenset((b_path, b_path)) in excluded:
                continue
            shared = (set(a) & set(b)) - common
            if not shared:
                continue
            for subject in sorted(shared):
                ca, cb = a[subject], b[subject]
                kind = value_a = value_b = None
                # Disjoint, not merely unequal. `{600}` against `{077, 600}`
                # is one document giving more context than the other, and
                # reporting it as a contradiction is how a filter fills a
                # page with pairs that agree.
                if ca["numbers"] and cb["numbers"] and \
                        ca["numbers"].isdisjoint(cb["numbers"]):
                    kind = "different number"
                    value_a, value_b = sorted(ca["numbers"]), sorted(cb["numbers"])
                if not kind:
                    continue
                pairs.append({
                    "subject": subject, "kind": kind,
                    "a": {"path": a_path, "value": value_a,
                          "says": ca["where"]},
                    "b": {"path": b_path, "value": value_b,
                          "says": cb["where"]},
                })

    pairs.sort(key=lambda p: p["subject"])

    for pair in pairs[:40]:
        for side in ("a", "b"):
            pair[side]["last_changed"] = _recency(root, pair[side]["path"])
            pair[side]["on_floor"] = _on_floor(pair[side]["path"])
        if pair["kind"] == "different number":
            pair["code_says"] = _code_says(
                root, pair["subject"],
                set(pair["a"]["value"]) | set(pair["b"]["value"]))

    return {"documents": len(docs),
            "possible_pairs": len(docs) * (len(docs) - 1) // 2,
            "excluded_by_supersession": len(excluded),
            "candidates": pairs[:40],
            "candidates_total": len(pairs)}, ""


BRIEF = """\
# Two documents in this repository disagree

Each pair below **names the same thing and attaches a different value to it**.
That is a lexical filter, not a judgement: it refuses to spend you on the
hundreds of pairs that share nothing, and it is wrong often enough that your
first job on each pair is to decide whether it is a conflict at all.

Common ways a candidate is not a conflict:

* the two sentences are about different contexts that happen to share a token
* one is an example and the other a default
* the number is incidental to both sentences
* they described the same thing at different times and both are marked as such

## For each pair you judge real, say which one to believe

Three signals come with the pair and none of them decides:

* **last changed** -- later is usually righter, and is not evidence on its own
* **on the floor** -- a claim in a file loaded on every turn reaches the agent
  whether or not anybody opened it. This is not about which is correct; it is
  about which one is currently doing damage
* **the code contains** -- which of the disputed values appears in the source.
  The strongest of the three and still not proof: a value can be in the code
  for an unrelated reason

## What to answer

    {"pairs": [{"subject": "...", "a": "path", "b": "path",
                "real": true, "believe": "path or null",
                "why": "one sentence"}]}

`real: false` for a pair that is not a conflict -- those are as useful to
record as the true ones, because they are what the filter should learn to
stop emitting. `believe: null` when it is a real conflict and you cannot tell
which side is right from what is here.

## Candidates
"""


def brief(r):
    if not r or not r.get("candidates"):
        return ""
    out = [BRIEF, "\n%d document(s), %d possible pairs, %d candidate(s)"
           % (r["documents"], r["possible_pairs"], r["candidates_total"])]
    if r["excluded_by_supersession"]:
        out.append(", %d pair(s) excluded as supersession"
                   % r["excluded_by_supersession"])
    out.append("\n")
    for i, p in enumerate(r["candidates"], 1):
        out.append("\n### %d. `%s` -- %s\n\n" % (i, p["subject"], p["kind"]))
        for side in ("a", "b"):
            s = p[side]
            out.append("- **%s** says %s%s\n  > %s\n"
                       % (s["path"], ", ".join(str(v) for v in s["value"]),
                          "  *(on the floor)*" if s.get("on_floor") else "",
                          s["says"].replace("\n", " ")[:180]))
        if p.get("code_says"):
            out.append("- the code contains: %s\n" % "; ".join(
                "`%s` in %s" % (k, ", ".join(v))
                for k, v in sorted(p["code_says"].items())))
    return "".join(out)


def grade(r, answers):
    """What came back. Never a verdict nobody gave."""
    if not isinstance(answers, dict) or not isinstance(answers.get("pairs"), list):
        return None, "the answers are not {\"pairs\": [...]}"
    real, dismissed = [], []
    for item in answers["pairs"]:
        if not isinstance(item, dict):
            continue
        (real if item.get("real") else dismissed).append(item)
    if not real and not dismissed:
        return None, "no pair was judged either way"
    unresolved = [p for p in real if not p.get("believe")]
    return {"real": real, "dismissed": dismissed,
            "unresolved": len(unresolved),
            "judged": len(real) + len(dismissed),
            "pending": max(0, len(r.get("candidates") or [])
                           - len(real) - len(dismissed))}, ""


def render(r, judged=None):
    if not r:
        return "document conflicts: could not judge\n"
    out = ["do the documents contradict each other?",
           "  %d document(s), %d possible pairs" % (r["documents"],
                                                    r["possible_pairs"]),
           "  %d candidate(s) after the lexical filter" % r["candidates_total"]]
    if r["excluded_by_supersession"]:
        out.append("  %d pair(s) excluded as supersession, not conflict"
                   % r["excluded_by_supersession"])
    kinds = {}
    for p in r["candidates"]:
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    for kind in sorted(kinds):
        out.append("     %-22s %d" % (kind, kinds[kind]))
    if judged:
        out.append("  judged: %d real, %d dismissed, %d could not be resolved"
                   % (len(judged["real"]), len(judged["dismissed"]),
                      judged["unresolved"]))
    else:
        out.append("  not yet judged -- a candidate is not a conflict")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", default="")
    ap.add_argument("--brief", default="")
    ap.add_argument("--grade", default="")
    ap.add_argument("--answers", default="")
    a = ap.parse_args()

    if a.brief:
        with open(a.brief, encoding="utf-8") as fh:
            run = json.load(fh)
        text = brief(run.get("conflict") if "conflict" in run else run)
        if not text:
            print("cannot judge: no candidates in that run", file=sys.stderr)
            return 2
        sys.stdout.write(text)
        return 0

    if a.grade:
        with open(a.grade, encoding="utf-8") as fh:
            run = json.load(fh)
        with open(a.answers, encoding="utf-8") as fh:
            judged, why = grade(run.get("conflict") or run, json.load(fh))
        if not judged:
            print("cannot judge: " + why, file=sys.stderr)
            return 2
        sys.stdout.write(json.dumps(judged, indent=2) + "\n")
        return 0

    r, why = narrow(os.path.abspath(a.root))
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
