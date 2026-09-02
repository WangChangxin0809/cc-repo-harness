#!/usr/bin/env python3
"""Is what this repository writes down still true?

    python3 assess/truth.py [--root .] [--json OUT]

Exit codes:
    0 = the docs were read and judged
    2 = cannot judge (not a git repository, or git is unavailable)

## Why this exists

Dimension 4 used to answer this by running two agents -- one on the tree, one
on a copy with the standing context removed -- and scoring the difference. That
was the better question and it is gone: two runs of the same pair disagreed by
more than the effect being measured, so the number moved when nothing did
-> 0042. This module is what stayed, because it asks something a single
deterministic read can answer: **not how much the repository writes down, but
how much of it is still true.** A `CLAUDE.md` that confidently describes a directory that was
deleted last spring is worse than no `CLAUDE.md`, because an agent believes it.
There is measured harm here -- retrieval that returns only stale context put
stale references into 15 of 17 outputs, against zero with no retrieval at all.
Thickness cannot see that. It scores the stale file as memory.

So thickness is the **denominator** and never a score of its own. Adding files
cannot raise anything here. Adding *wrong* files lowers it -> 0027

## One proven tier, four candidate tiers

    T0  a markdown link whose target is absent   PROVEN, no judgement needed
    ---------------- above this line a machine is certain ----------------
    T1  a count the tree disagrees with                  CANDIDATE
    T2  a backticked path resolving nowhere              CANDIDATE
    T3  a document the code moved out from under         CANDIDATE
    T4  two documents giving one token two values        CANDIDATE

**Where that line sits was decided by being wrong about it twice**, and both
mistakes are worth keeping written down because both looked correct in the
design and failed on contact with one real repository.

T2 began above the line. It reported 23 broken paths here, of which nearly all
were false: `scaffold.py` lives one directory down, `permissions.deny` is a JSON
key, `.py` is an extension, and `WangChangxin0809/agent-harness` is a GitHub
slug.

T1 began above the line too, and failed differently and more instructively. Its
arithmetic was right every time; its *binding* was wrong. "two agents" in a
sentence about two agent runs was checked against the three files in `agents/`.
"six skills" was checked against the plugin's one `skills/` entry when the
sentence meant `shared/skills/`. A count is only a claim about the tree when a
reader can see that it is, and no regex knows which sentences those are.

What survives above the line is the one construct where the author's intent is
not in doubt: they typed a path inside `](...)`.

The published number for the naive alternative is 98%: an LLM asked directly
whether code and its documentation agree flags 98% of functions as inconsistent,
which is not a finding, it is a rate of nothing. Filtering first took that to a
14% flag rate at 0.63 precision. **The filter is the product**, and a filter
that promotes its own guesses to findings has stopped being one.

## The second pass

Everything below the line goes to an agent, with the sentence quoted and the
tree's own answer beside it, and the agent keeps only what is real. That is the
same shape as the mutation second pass in `mutate.py` and it is deliberate:
this project spends agents on judgement and machines on narrowing, and never
the other way round.

## What is not checked

**Documents whose job is to be historical.** A decision record saying the cost
used to be 888 tokens a turn is not stale, it is a record; the same sentence in
a `CLAUDE.md` is a lie. `historical()` decides which is which, and it is
deliberately generous -- a false *exclusion* costs one missed finding, a false
*inclusion* costs the reader's trust in every row on the page.
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

# What a stale number looks like. Reused from `consolidate.py`'s merge check,
# where the same tokens are the ones a summariser drops first: they are the
# claims that cannot survive paraphrase, which is also what makes them the
# claims worth cross-checking between two documents.
LOAD_BEARING = (
    ("measurement", re.compile(
        r"\b\d+(?:\.\d+)?\s?(?:ms|s|m|h|kb|mb|gb|k|%|x|ns|us|µs|"
        r"tokens?|files?|lines?|commits?)\b", re.I)),
    ("version", re.compile(r"\bv?\d+\.\d+(?:\.\d+)?\b")),
)

DOC_EXT = (".md", ".markdown", ".rst", ".txt")

# A document that is *supposed* to describe a past state. Generous on purpose:
# see the module docstring.
HISTORICAL_DIR = (
    "decisions", "decision", "adr", "adrs", "rfc", "rfcs", "changelog",
    "changelogs", "history", "archive", "archived", "postmortem",
    "postmortems", "incidents", "retro", "retros", "retrospectives",
    "meeting", "meetings", "journal", "journals", "releases", "news",
    "exec-plans", "plans",
)
HISTORICAL_NAME = (
    "changelog", "history", "news", "releases", "release-notes", "postmortem",
    "retro", "retrospective", "journal", "migration", "upgrading", "upgrade",
)
NUMBERED = re.compile(r"^\d{3,4}[-_]")

SKIP_DIRS = (".git", "node_modules", "vendor", "venv", ".venv", "dist",
             "build", "target", "__pycache__", ".tox", ".next", "coverage",
             ".mypy_cache", ".pytest_cache", "site-packages")

# What the repository keeps in order to explain itself. The denominator.
MEMORY_KINDS = (
    ("root instructions", ("CLAUDE.md", "AGENTS.md", ".cursorrules",
                           ".github/copilot-instructions.md")),
)

MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
BACKTICK_PATH = re.compile(r"`([^`\n]{2,120})`")
# A path shape, not a word: it has a separator or a known extension, and it is
# not a URL, an option, or a sentence with a slash in it.
PATH_SHAPE = re.compile(
    r"^(?!https?://)(?!-)[\w.@-]+(?:/[\w.@-]+)*/?$")
FENCE_LINE = re.compile(r"^\s*(```+|~~~+)")
PLACEHOLDER_SPAN = re.compile(r"<[^<>\n]{0,300}>")
COUNT_CLAIM = re.compile(
    r"\b(?:only\s+)?(one|two|three|four|five|six|seven|eight|nine|ten|\d{1,4})"
    r"\s+([a-z][a-z-]{2,24}s)\b", re.I)
CANDIDATE_CAP = 24
WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10}


# --------------------------------------------------------------------------
# the tree
# --------------------------------------------------------------------------

def tracked(root):
    """Every tracked path. Untracked files are not the repository's memory --
    they are somebody's scratch, and holding a repository to account for a file
    it never accepted is how an instrument earns a reputation for noise."""
    out = subprocess.run(
        ["git", "-c", "core.quotePath=false", "ls-files", "-z"],
        cwd=root, capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        return None
    return [p for p in out.stdout.split("\0") if p]


def historical(rel):
    """Is this document's job to describe a state that has since changed?

    Three signals, any of which is enough: it sits in a directory whose name
    says so, its own name says so, or it is a numbered record (`0026-...`),
    which is the shape every ADR convention converges on."""
    parts = rel.replace("\\", "/").lower().split("/")
    if any(p in HISTORICAL_DIR for p in parts[:-1]):
        return True
    stem = os.path.splitext(parts[-1])[0]
    if NUMBERED.match(parts[-1]):
        return True
    return any(h == stem or stem.startswith(h + "-") or stem.startswith(h + "_")
               for h in HISTORICAL_NAME)


def docs(root, paths):
    """[(rel, text)] for every non-historical document, largest first.

    Largest first because the tiers below are bounded, and a bound that drops
    the biggest `CLAUDE.md` in the tree in favour of six one-line READMEs has
    spent its budget on the files nobody reads."""
    out = []
    for rel in paths:
        if not rel.lower().endswith(DOC_EXT) or historical(rel):
            continue
        if any(part in SKIP_DIRS for part in rel.split("/")):
            continue
        try:
            with open(os.path.join(root, rel), encoding="utf-8",
                      errors="replace") as fh:
                out.append((rel, fh.read()))
        except OSError:
            continue
    out.sort(key=lambda p: -len(p[1]))
    return out


# --------------------------------------------------------------------------
# the denominator
# --------------------------------------------------------------------------

def prose(text):
    """The document minus everything it is only *showing*.

    Two things are stripped, and both were learned from false positives on this
    repository rather than reasoned out in advance:

    **Fenced blocks.** A link inside ``` is an illustration. `kinds.md` shows an
    example plan whose checklist links `steps/01-shadow-verify.md`; that file
    has never existed and is not supposed to. Following links into a fence is
    checking somebody's example against your tree.

    **Angle-bracket placeholders.** A template writes
    `<Three or four lines. Then: see [ARCHITECTURE.md](ARCHITECTURE.md).>`, and
    the brackets are the author saying *this is the shape, not the content*.

    Both are replaced by blank space of the same length rather than deleted, so
    any offset reported into the result still points at the right place."""
    out = []
    fenced = False
    for line in text.split("\n"):
        if FENCE_LINE.match(line):
            fenced = not fenced
            out.append("")
            continue
        out.append("" if fenced else PLACEHOLDER_SPAN.sub(
            lambda m: " " * len(m.group(0)), line))
    return "\n".join(out)


def thickness(root, paths, documents):
    """What the repository keeps in order to explain itself.

    This is a **denominator and nothing else**. It is never scored, never
    compared between repositories, and never reported as good or bad -- 0025
    set out at length why counting what a repository keeps grades it on whether
    it adopted our conventions, rewards this plugin's own presence, and calls a
    change that cut the standing cost by 81% a regression. All of that is still
    true. What changed is that a denominator does not have those properties: it
    turns `four references do not resolve` into `four of ninety`, which is the
    difference between a fact and a fact somebody can act on."""
    p = set(paths)
    nested = [x for x in p if x.endswith("CLAUDE.md") and x != "CLAUDE.md"]
    return {
        "documents": len(documents),
        "doc_bytes": sum(len(t) for _r, t in documents),
        "root instructions": sum(
            1 for names in MEMORY_KINDS for n in names[1] if n in p),
        "nested CLAUDE.md": len(nested),
        "hooks": len([x for x in p if "/hooks/" in x or x.startswith("hooks/")]),
        "settings": len([x for x in p if x.endswith(("settings.json",
                                                     "settings.local.json"))]),
        "skills": len([x for x in p if x.endswith("SKILL.md")]),
    }


# --------------------------------------------------------------------------
# T0 -- a reference that does not resolve
# --------------------------------------------------------------------------

def _resolvable(root, base, target):
    target = target.split("#")[0].strip()
    if not target or target.startswith(("http://", "https://", "mailto:",
                                        "#", "<")):
        return None                       # not ours to check
    # A template's own placeholder is not a broken link. `…`, `...`, `path/to`
    # and `<name>` are all somebody showing the shape of a link, not making a
    # claim that a file exists.
    if (target in ("…", "...", ".", "..") or "…" in target
            or "<" in target or target.lower().startswith(
                ("path/to", "your/", "some/", "example/"))):
        return None
    if target.startswith("$") or "${" in target or "*" in target:
        return None                       # a template, not a path
    root = os.path.abspath(root)
    here = os.path.dirname(base)
    inside = False
    # Two readings, because both are in use: relative to the document, and
    # relative to the repository root. A candidate that escapes the tree is
    # *skipped*, not fatal -- `../docs/x.md` from `docs/` is a perfectly good
    # in-tree link whose root-relative reading lands outside, and returning
    # None there made every such link unverifiable. That is the whole of tier
    # 0 turned off by one early return.
    for cand in (os.path.join(here, target), target):
        full = os.path.normpath(os.path.join(root, cand))
        if not full.startswith(root + os.sep) and full != root:
            continue
        inside = True
        if os.path.exists(full):
            return True
    return False if inside else None


def tier0(root, documents, limit=40):
    """Markdown links whose target is not there. This tier is *proven*.

    A markdown link is unambiguous: somebody typed a path inside `](...)` and
    meant a file. Nothing else in a document is. The first version of this also
    checked backticked path-shaped tokens and produced 23 rows on this
    repository of which nearly all were false -- `scaffold.py` lives one
    directory down, `permissions.deny` is a JSON key, `.py` is an extension,
    and `WangChangxin0809/agent-harness` is a GitHub slug. That is the 98%
    flag rate this module exists to avoid, reproduced in one afternoon.

    Backticked paths still get looked at, in `tier2_paths`, as candidates."""
    rows = []
    for rel, raw in documents:
        text, seen = prose(raw), set()
        for m in MD_LINK.finditer(text):
            tgt = m.group(1)
            if tgt in seen:
                continue
            seen.add(tgt)
            if _resolvable(root, rel, tgt) is False:
                rows.append({"tier": 0, "file": rel, "claim": tgt,
                             "why": "a link to a file that is not there"})
        if len(rows) >= limit:
            break
    return rows[:limit]


def tier2_paths(root, documents, paths, limit=12):
    """Backticked path-shaped tokens that resolve nowhere in the tree.

    A **candidate** tier, not a finding, and it is the one that taught this
    module what it is for. The rule that makes it survivable: resolve the
    *basename* anywhere in the tree, not just relative to the document. A
    `CLAUDE.md` saying `scaffold.py` is not wrong because the file sits under
    `shared/scripts/`; treating that as a broken reference is a checker telling
    somebody their correct documentation is false.

    What is left after that is genuinely unresolvable here and still often
    fine: a skill describing what it will create in *somebody else's*
    repository names `ci.sh` and `ARCHITECTURE.md`, and neither exists here
    because neither is supposed to. Only a reader can tell those from a real
    dangling reference, so they are handed on as candidates."""
    basenames = set()
    for rel in paths:
        parts = rel.split("/")
        basenames.add(parts[-1].lower())
        for i in range(len(parts)):
            basenames.add("/".join(parts[i:]).lower())
            basenames.add(parts[i].lower() + "/")
    rows = []
    for rel, raw in documents:
        text, seen = prose(raw), set()
        for m in BACKTICK_PATH.finditer(text):
            tok = m.group(1).strip()
            if tok in seen or not PATH_SHAPE.match(tok):
                continue
            seen.add(tok)
            bare = tok.strip("./")
            if "/" not in bare:
                continue           # a bare word or an extension, not a path
            segs = [x for x in bare.split("/") if x]
            if not re.search(r"\.\w{1,5}$", bare) and any(
                    len(x) < 2 for x in segs):
                continue           # `1/N` and `a/b` are notation, not paths
            low = tok.lower().lstrip("./")
            if low in basenames or low.rstrip("/") + "/" in basenames:
                continue
            if _resolvable(root, rel, tok) is not False:
                continue
            if os.path.basename(low.rstrip("/")) in basenames:
                continue           # named elsewhere in the tree; not dangling
            rows.append({"tier": 2, "file": rel, "claim": tok,
                         "why": "a path this document names that resolves "
                                "nowhere in the tree — often correct, when "
                                "the document is describing a repository "
                                "this is not"})
        if len(rows) >= limit:
            break
    return rows[:limit]


# --------------------------------------------------------------------------
# T1 -- a count the repository disagrees with
# --------------------------------------------------------------------------

def tier1(root, documents, paths, limit=12):
    """Counts stated in prose that the tree does not support. A **candidate**.

    This was written to be a proven tier and it is not one. The arithmetic is
    never wrong; the binding from a noun to a directory is wrong most of the
    time, and no tightening fixes it, because the failures are semantic:

    * "two agents" meant two agent *runs*; it was checked against `agents/`.
    * "six skills" meant `shared/skills/`; the tree also has a `skills/`.
    * "three gates" was a skill describing what it creates in *your* repository,
      where the number is a promise rather than a description.

    So it narrows and does not judge. Ambiguous nouns -- ones matching more than
    one directory in the tree -- are dropped outright, because a candidate that
    cannot even name which directory it means wastes the second pass."""
    dirs = {}
    for rel in paths:
        parts = rel.split("/")
        for i, part in enumerate(parts[:-1]):
            dirs.setdefault(part.lower(), set()).add("/".join(parts[:i + 2]))
    rows = []
    for rel, raw in documents:
        text = prose(raw)
        for m in COUNT_CLAIM.finditer(text):
            raw, noun = m.group(1).lower(), m.group(2).lower()
            said = WORD_NUM.get(raw)
            if said is None:
                try:
                    said = int(raw)
                except ValueError:
                    continue
            here = dirs.get(noun)
            if not here:
                continue
            # More than one directory of that name in the tree: the sentence
            # cannot be bound to one of them, so there is nothing to check.
            roots = {x.rsplit("/", 1)[0] for x in here}
            if len({r.rsplit("/", 1)[-1] for r in roots} | {noun}) > 1 and \
                    len(roots) > 1:
                continue
            depth = min(len(x.split("/")) for x in here)
            actual = len({x for x in here if len(x.split("/")) == depth})
            if actual and actual != said:
                rows.append({
                    "tier": 1, "file": rel, "claim": m.group(0),
                    "why": f"the tree has {actual} under {noun}/, not {said} — "
                           f"a candidate: the sentence may not be about the "
                           f"tree at all"})
        if len(rows) >= limit:
            break
    return rows[:limit]


# --------------------------------------------------------------------------
# T3 -- a document the code moved out from under it
# --------------------------------------------------------------------------

def _touched(root, rel, since_sha=None):
    out = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "--", rel],
        cwd=root, capture_output=True, text=True, timeout=120)
    try:
        return int((out.stdout or "0").strip())
    except ValueError:
        return 0


def _commits_since(root, paths, ts):
    if isinstance(paths, str):
        paths = [paths]
    if not paths:
        return 0
    out = subprocess.run(
        ["git", "rev-list", "--count", f"--since=@{ts}", "HEAD", "--"]
        + list(paths),
        cwd=root, capture_output=True, text=True, timeout=120)
    try:
        return int((out.stdout or "0").strip())
    except ValueError:
        return 0


def subject_of(root, rel, raw):
    """What a document is about: the paths it points at that actually exist.

    The obvious answer -- the directory the document sits in -- is wrong for
    exactly the documents that matter most. A root `CLAUDE.md`'s directory is
    the whole repository, so every commit anywhere counts as churn under it and
    it ranks stale on any active week. Worse, so does `CODE_OF_CONDUCT.md`,
    which describes nothing in the tree at all and can never be stale in this
    sense.

    A document's subject is what it references. If it references nothing that
    exists, it has no subject here, and no staleness score."""
    text = prose(raw)
    here = os.path.dirname(rel)
    found = set()
    for m in MD_LINK.finditer(text):
        tgt = m.group(1).split("#")[0].strip()
        if tgt and _resolvable(root, rel, tgt):
            found.add(os.path.normpath(os.path.join(here, tgt))
                      if not os.path.exists(os.path.join(root, tgt)) else tgt)
    for m in BACKTICK_PATH.finditer(text):
        tok = m.group(1).strip()
        if not PATH_SHAPE.match(tok) or "/" not in tok.strip("./"):
            continue
        for cand in (os.path.normpath(os.path.join(here, tok)), tok):
            if os.path.exists(os.path.join(root, cand)):
                found.add(cand.rstrip("/"))
                break
    # A document is not its own subject: a `CLAUDE.md` that links its own
    # directory would otherwise score every commit in the tree.
    return sorted(x for x in found if x and x != rel and x not in (".", "./"))


def tier3(root, documents, now, limit=8):
    """Documents ranked by how far the thing they describe has moved.

    The first version of this ranked by the document's own age and produced
    noise: on an active repository the top of the list was a file edited that
    morning, because *everything* had been edited that morning. Age alone
    measures how busy the repository is, not how stale the document is.

    The rank that works is a product of two things:

        (commits to what the document points at, since it last moved)
        x  (days the document has sat still)

    A document nothing has happened around scores zero however old it is, which
    is correct: an unchanged description of unchanged code is not stale. And a
    freshly-edited document scores near zero however much churn surrounds it,
    which is also correct -- somebody just looked at it.

    **These are candidates, not findings.** The score says where to look. It
    cannot say anything is wrong, and a page that prints it as a finding is
    claiming a certainty the arithmetic does not have."""
    rows = []
    for rel, raw in documents:
        subjects = subject_of(root, rel, raw)
        if not subjects:
            continue
        moved = _touched(root, rel)
        if not moved:
            continue
        churn = _commits_since(root, subjects[:20], moved)
        days = max(0.0, (now - moved) / 86400.0)
        score = churn * days
        if score <= 0:
            continue
        named = ", ".join(subjects[:3]) + (" …" if len(subjects) > 3 else "")
        rows.append({"tier": 3, "file": rel,
                     # When the document itself last moved. A reading of a
                     # tier-3 candidate is a reading of *this* document, and
                     # it stands for as long as the document does -- however
                     # much churn goes on around it. The claim cannot carry
                     # that: it counts commits to the subjects, so it changes
                     # every time one of them is touched, and an answer keyed
                     # to it would expire on somebody else's commit.
                     "moved": int(moved),
                     "claim": f"{churn} commit(s) to what it points at "
                              f"({named}) in the {days:.0f} days since this "
                              f"was touched",
                     "score": round(score, 1),
                     "why": "a candidate, not a finding: what it describes "
                            "moved and it did not"})
    rows.sort(key=lambda r: -r["score"])
    return rows[:limit]


# --------------------------------------------------------------------------
# T4 -- two documents giving one token two values
# --------------------------------------------------------------------------

def _sentences(text):
    for para in re.split(r"\n\s*\n", text):
        for s in re.split(r"(?<=[.!?])\s+|\n", para):
            s = s.strip()
            if 20 <= len(s) <= 400:
                yield s


def tier4(root, documents, limit=12):
    """Sentences in two documents that state different values for one subject.

    The machine's job here is only to find the *pair*. It keys a sentence by
    the content words around a load-bearing token -- a measurement or a version
    -- and reports two sentences that share a key and disagree on the number.

    That is a weak signal and it is meant to be. A pair can differ because one
    is wrong, because they are about different things, or because one is a
    range and the other a point. Only a reader can tell, so these are handed on
    as candidates with both sentences quoted, and the page says how many were
    handed on rather than pretending the count is a count of contradictions."""
    keyed = {}
    stop = set("the a an of to in is are was were and or for with that this it "
               "as at by on from be been being not no all any each per than "
               "then when which what how why into over under about".split())
    for rel, raw in documents:
        for s in _sentences(prose(raw)):
            for kind, pattern in LOAD_BEARING:
                nums = pattern.findall(s)
                if not nums:
                    continue
                words = [w for w in re.findall(r"[a-z][a-z-]{3,}", s.lower())
                         if w not in stop]
                if len(words) < 3:
                    continue
                key = (kind, tuple(sorted(set(words))[:4]))
                keyed.setdefault(key, []).append((rel, s, tuple(sorted(nums))))
    rows = []
    for (kind, _words), hits in keyed.items():
        if len(hits) < 2:
            continue
        values = {h[2] for h in hits}
        if len(values) < 2:
            continue
        files = {h[0] for h in hits}
        if len(files) < 2:
            continue                      # one document restating itself
        a = hits[0]
        b = next((h for h in hits if h[2] != a[2]), None)
        if b is None:
            continue
        rows.append({
            "tier": 4, "file": a[0], "other": b[0],
            "claim": f"{a[1][:110]}  ||  {b[1][:110]}",
            "why": f"two documents give this {kind} two values — a candidate "
                   f"for a reader, not a contradiction this can prove"})
        if len(rows) >= limit:
            break
    return rows[:limit]


# --------------------------------------------------------------------------

def _share(cap, tiers):
    """`cap` rows drawn round-robin, so no tier can starve the ones after it.

    A tier with nothing to say gives its share back rather than holding it."""
    out, i = [], 0
    tiers = [list(t) for t in tiers]
    while len(out) < cap and any(tiers):
        moved = False
        for t in tiers:
            if t and len(out) < cap:
                out.append(t.pop(0))
                moved = True
        if not moved:
            break
        i += 1
    return out


def assess(root, now=None):
    """Everything, or an abstention. Never a score computed from nothing."""
    import time
    paths = tracked(root)
    if paths is None:
        return None
    documents = docs(root, paths)
    if not documents:
        return {"thickness": thickness(root, paths, documents),
                "proven": [], "candidates": [], "checked": 0,
                "why": "no non-historical documentation to read"}
    proven = tier0(root, documents)
    # One cap for the whole second pass -- it is a single agent call, and a
    # hundred candidates is not a better question than twenty, it is the same
    # question asked past the point the answer is read.
    #
    # Shared **round-robin**, not by concatenation. Taking the first 24 of the
    # tiers in order let T1 and T2 fill every slot and starved T3 and T4
    # entirely, which silently deleted the two tiers that look for staleness
    # and contradiction -- the ones this module was asked for. A budget that
    # can be consumed by whichever tier happens to run first is not a budget.
    candidates = _share(CANDIDATE_CAP, [
        tier1(root, documents, paths),
        tier2_paths(root, documents, paths),
        tier3(root, documents, now or time.time()),
        tier4(root, documents)])
    return {"thickness": thickness(root, paths, documents),
            "proven": proven, "candidates": candidates,
            "checked": len(documents), "why": ""}


BRIEF = """\
# Which of these are real?

Each line below is a place a machine can point at and cannot judge. A count
that disagrees with the tree is usually the tree having moved and sometimes the
document being wrong about what it describes. A path that resolves nowhere is
usually a document about a repository this one scaffolds, where the path is
correct and simply not here.

So the tiers are where to look, and nothing else. Read the document, read what
it describes, and say which it is.

    T1  a count the document gives that the tree disagrees with
    T2  a path the document names that resolves nowhere
    T3  a document whose subject changed after the document last did
    T4  two documents giving one number two values

**A dismissal is an answer**, and the reason it is worth writing down is that
it does not survive otherwise: the same candidate comes back on every run of
every assessment forever, and each reader pays to rediscover that the path
belongs to somebody else's tree.

## Answer

    {"candidates": [
      {"id": 0, "file": "skills/bootstrap-repo-harness/SKILL.md", "real": false,
       "why": "scripts/guards/ is what a scaffolded repository gets. It is
               correct that it is absent here -- ours live under shared/."},
      {"id": 3, "file": "README.md", "real": true,
       "why": "README says the report is committed. build.py writes it into
               docs/generated/, which is not tracked."}
    ]}

Answer only the ids listed. One you leave out stays a candidate, which is
honest -- an unread candidate and a dismissed one are different things.

**`file` is not optional and it is not decoration.** The list is rebuilt from
the tree on every run, so an id is a position in *this* run and nothing more.
Fix one of these and the next run renumbers everything after it -- an answers
file carrying ids alone would then attach yesterday's verdicts to today's
candidates, quietly, in whichever direction the numbering shifted. So each
answer names the document it is about, and one whose id and file disagree is
matched by file or refused.

A T3 candidate additionally carries `moved`, the moment the document itself
last changed. Copy it into the answer. A T3 claim counts commits to what the
document points at, so it moves whenever *somebody else's* file is touched --
but the reading was of this document, and it stands for as long as this
document does. When the document itself changes the answer expires, because
what was read is no longer what is there.

---

"""


def brief(r):
    """The questions, with an id per candidate. Empty where there are none."""
    if not r or not r.get("candidates"):
        return ""
    out = [BRIEF]
    for i, row in enumerate(r["candidates"]):
        out.append('## %d — T%d  %s\n' % (i, row["tier"], row["file"]))
        out.append("%s\n" % row["claim"])
        if row.get("why"):
            out.append("_why it was flagged_: %s\n" % row["why"])
    return "\n".join(out)


def _locate(cands, item):
    """Which candidate an answer is about, or None.

    The id is a position in one run and the list is rebuilt from the tree on
    every run, so acting on a candidate renumbers every candidate after it.
    An answers file carrying ids alone would then hand yesterday's verdicts to
    today's candidates -- silently, and in whichever direction the numbering
    happened to shift. So the file an answer names is what identifies it, and
    the id is only the fast path: it is used when it agrees, and ignored when
    it does not."""
    def unexpired(n):
        """The candidate, unless the document has changed under the answer.

        Only tier 3 carries `moved`, and only tier 3 needs it: the other
        claims are properties of the document, and this one is a measurement
        of how far its subjects have run ahead of it."""
        was, now = item.get("moved"), cands[n].get("moved")
        return n if now is None or was == now else None

    i, named = item.get("id"), item.get("file")
    if isinstance(i, int) and 0 <= i < len(cands):
        if not named or cands[i]["file"] == named:
            return unexpired(i)
    if not named:
        # No file and no usable id. Refusing beats guessing: a verdict landing
        # on the wrong candidate is worse than one that did not land.
        return None
    # Narrowing, in order, and each step is only taken when the one before it
    # was ambiguous. The claim is the strongest identifier and the least
    # stable: a T3 claim reads "5 commit(s) to what it points at", so it
    # changes every time anything the document points at is touched -- which
    # is the condition that produced the candidate. Tier and file survive that.
    claim = (item.get("claim") or "").strip()
    tier = item.get("tier")
    same_file = [n for n, c in enumerate(cands) if c["file"] == named]
    for narrower in (
            lambda n: claim and cands[n]["claim"].strip() == claim,
            lambda n: tier is not None and cands[n]["tier"] == tier,
            lambda n: True):
        hits = [n for n in same_file if narrower(n)]
        if len(hits) == 1:
            return unexpired(hits[0])
    return None


def grade(r, answers):
    """What a reader said. Never a verdict nobody gave.

    The shape mirrors `conflict.grade` on purpose: both sub-items hand an
    agent a list a machine narrowed and neither may turn silence into a
    verdict. An id nobody answered stays pending, and pending is printed."""
    if not isinstance(answers, dict) or not isinstance(
            answers.get("candidates"), list):
        return None, "the answers are not {\"candidates\": [...]}"
    cands = r.get("candidates") or []
    total = len(cands)
    real, dismissed, seen, stale = [], [], set(), []
    for item in answers["candidates"]:
        if not isinstance(item, dict):
            continue
        i = _locate(cands, item)
        if i is None:
            # Either an id nobody was handed, or an answer about a document
            # that is no longer a candidate -- usually because somebody acted
            # on it. Both are recorded as stale rather than dropped: an
            # answers file quietly losing entries is how a reading rots.
            stale.append(item.get("file") or item.get("id"))
            continue
        if i in seen:
            continue
        seen.add(i)
        (real if item.get("real") else dismissed).append(
            {**item, "candidate": cands[i]})
    if not seen:
        return None, ("no candidate was judged either way"
                      + (" — %d answer(s) name nothing in this run, so the "
                         "file is for an older tree" % len(stale)
                         if stale else ""))
    return {"real": real, "dismissed": dismissed, "judged": len(seen),
            "stale": stale, "pending": max(0, total - len(seen))}, ""


def render(r):
    lines = ["", f"  {r['checked']} non-historical document(s) read"]
    t = r["thickness"]
    lines.append("  thickness  " + "  ".join(
        f"{k}:{v}" for k, v in t.items() if v))
    lines.append("")
    if not r["proven"]:
        lines.append("  every link in them resolves")
    for row in r["proven"]:
        lines.append(f"  !!  T{row['tier']}  {row['file']}")
        lines.append(f"          {row['claim'][:90]}  — {row['why']}")
    lines.append("")
    lines.append(f"  {len(r['candidates'])} candidate(s) for a reader — "
                 f"these are NOT findings")
    for row in r["candidates"][:6]:
        lines.append(f"   ?  T{row['tier']}  {row['file']}")
        lines.append(f"          {row['claim'][:100]}")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", default="")
    ap.add_argument("--brief", default="",
                    help="a run's JSON, or this module's — print the questions")
    a = ap.parse_args()

    if a.brief:
        with open(a.brief, encoding="utf-8") as fh:
            run = json.load(fh)
        text = brief(run.get("truth") if "truth" in run else run)
        if not text:
            print("cannot judge: no candidates in that run", file=sys.stderr)
            return 2
        sys.stdout.write(text)
        return 0

    root = os.path.abspath(a.root)
    r = assess(root)
    if r is None:
        print("cannot judge: not a git repository, or git is unavailable",
              file=sys.stderr)
        return 2
    print(render(r))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=2, ensure_ascii=False)
        print(f"  written to {a.json}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
