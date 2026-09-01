#!/usr/bin/env python3
"""What the standing context is spent ON, not just how much of it there is.

    python3 assess/value.py [--root .] [--json OUT]

Exit codes:
    0 = the standing context was read
    2 = cannot judge (nothing is loaded on every turn)

## Why a token count is not enough

Dimension 5 measured the bill and never the goods. Two repositories with an
identical thousand-token floor are not in the same position: one spends it on
four constraints an agent could not guess, and the other on forty prohibitions
against things nobody was going to do.

Everything here is about the **floor** -- text paid for on every turn of every
session, whether or not the turn has anything to do with it. Text that arrives
only when asked for is not this dimension's business; that is the escape hatch,
and 0024's whole point.

## Three questions a machine can ask about a sentence

**Is it a prohibition or a requirement?** Both are legitimate. The reason to
count them separately is that a prohibition earns its place only against a
mistake somebody actually makes, while a requirement is doing work every time
the thing it requires comes up. A floor that is nine-tenths *don't* is usually
a list of one-off incidents nobody deleted.

**Is it already enforced?** This is the sharp one, and it is machine-checkable
by cross-referencing dimension 1. A rule saying *never force-push to main* in a
repository whose hooks already refuse force-pushes to main is paying tokens on
every turn to restate a thing that cannot happen. The guard is strictly better:
it is not optional, it does not depend on the agent having read anything, and
it costs nothing until it fires.

**Is it scoped, but loaded anyway?** A paragraph about the frontend build,
loaded on every turn including the ones that never leave the database layer.
Not wrong, just misfiled: the same text under a path-scoped rule costs nothing
until somebody touches that path.

## What is left over is for an agent

A machine cannot tell whether a constraint is one an agent could have guessed,
or whether an example earns its lines. What it can do is hand over the floor,
already split, with the enforced ones marked -- which is a far better question
than *read this and tell me what you think*.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# A sentence that forbids. Deliberately narrow: these are the spellings that
# are unambiguous, because a false positive here reads as an accusation that
# somebody's documentation is wasteful.
# `cannot` and `can't` are deliberately absent. They are almost always
# *alethic* -- a statement about how something works ("it parses the workflow,
# so the two cannot drift") rather than an instruction to anybody. Counting
# them made two sentences describing a script read as two unenforced rules on
# this repository's own floor, which is the same conflation `reframe.py` was
# built after hitting: 116 findings, most of them a repository describing
# itself.
PROHIBIT = re.compile(
    r"\b(?:never|do not|don't|must not|no longer|avoid|"
    r"refuse|forbidden|prohibited|not allowed|under no circumstances|"
    r"stop )\b", re.I)
REQUIRE = re.compile(
    r"\b(?:must|always|should|required|ensure|make sure|remember to|"
    r"be sure to|has to|have to|need to|shall)\b", re.I)

# What a rule is talking about, when it is talking about something a guard
# could enforce. Each entry is (label, pattern) and the label is what gets
# matched against the guards the repository actually ships.
ENFORCEABLE = (
    ("force push", re.compile(r"force[- ]?push|push\s+--force|-f\b.*push", re.I)),
    ("protected branch", re.compile(
        r"\b(?:push|commit|merge)\b[^.\n]{0,40}\b(?:to\s+)?"
        r"(?:main|master|trunk|the default branch)\b", re.I)),
    ("destructive restore", re.compile(
        r"git\s+(?:checkout|restore|reset\s+--hard)|\breset --hard\b", re.I)),
    ("secrets", re.compile(
        r"\b(?:secret|credential|api[- ]?key|token|password|\.env)\b"
        r"[^.\n]{0,50}\b(?:commit|check in|push|hardcode)\b|"
        r"\b(?:commit|check in|hardcode)\b[^.\n]{0,50}"
        r"\b(?:secret|credential|api[- ]?key|password|\.env)\b", re.I)),
    ("rm -rf", re.compile(r"\brm\s+-[a-z]*[rf]", re.I)),
    ("piped outbound", re.compile(r"curl[^|\n]*\||\|\s*(?:curl|wget|nc)\b", re.I)),
    # The vocabulary has to keep up with the guards that ship. This repository
    # states "no check may swallow a status with `|| true`" on its floor and
    # ships `no_silenced_check.py` to enforce it -- and the rule was still
    # counted as unenforced, because there was no label here to match it
    # against. A missing label reads exactly like a missing guard.
    ("silenced check", re.compile(
        r"\|\|\s*true|\bset\s+\+e\b|continue-on-error|"
        r"\bswallow\w*\b[^.\n]{0,40}\b(?:status|failure|error)\b", re.I)),
    ("computed delete", re.compile(
        r"\brm\b[^.\n]{0,30}\$\(|\brm\b[^.\n]{0,30}\$\{?[A-Z]|"
        r"\bfind\b[^.\n]{0,40}-delete\b", re.I)),
)

SCOPED_HINT = re.compile(
    r"^\s*(?:in|under|within|inside|for|when (?:editing|working|touching))\s+"
    r"[`\"']?([\w./-]+/[\w./-]*)", re.I | re.M)
PATH_IN_SENTENCE = re.compile(r"`([\w.-]+/[\w./-]*)`")

FENCE = re.compile(r"^\s*(```+|~~~+)")


def sentences(text):
    """Prose sentences, with fenced blocks removed.

    Fences are commands and examples. A `git push --force` inside a code block
    is a demonstration, and counting it as a prohibition would classify every
    document that shows what not to do as being made of prohibitions."""
    out, fenced = [], False
    for para in text.split("\n\n"):
        lines = []
        for line in para.split("\n"):
            if FENCE.match(line):
                fenced = not fenced
                continue
            if not fenced:
                lines.append(line)
        block = " ".join(lines).strip()
        if not block:
            continue
        for s in re.split(r"(?<=[.!?])\s+", block):
            s = re.sub(r"^\s*[-*+]\s*|^\s*\d+\.\s*|^#+\s*", "", s).strip()
            if 12 <= len(s) <= 400:
                out.append(s)
    return out


def classify(text):
    """Every floor sentence, tagged prohibition / requirement / neither."""
    rows = []
    for s in sentences(text):
        p, r = bool(PROHIBIT.search(s)), bool(REQUIRE.search(s))
        kind = ("prohibition" if p and not r else
                "requirement" if r and not p else
                "both" if p else "statement")
        rows.append({"text": s, "kind": kind})
    return rows


# Dimension 1's probe names, mapped to the rule topics above. The mapping is
# explicit rather than fuzzy because a wrong match here tells somebody their
# documentation is redundant when it is not, and that is the kind of error
# that gets a whole page dismissed.
FROM_BLAST = {
    "force-push the default branch": ("force push", "protected branch"),
    "rewrite published history": ("force push",),
    "discard uncommitted work": ("destructive restore",),
    "delete tracked work": ("rm -rf",),
    "commit a credential": ("secrets",),
    # Empty for as long as no guard here could refuse it. One can now, and a
    # map left behind reads exactly like a guard that does not exist: the
    # repository states the rule on its floor, ships `no_silenced_check.py` to
    # enforce it, is measured refusing the probe -- and the rule still counted
    # as unenforced, on every assessment, because this line said nothing.
    "silence a failing check": ("silenced check",),
}


def guards_from_blast(blast):
    """What dimension 1 measured this repository actually refusing.

    Measured, not configured: a guard that exists and does not fire is not in
    this set, because a prohibition restating a guard that does not work is
    the one sentence on the floor that is definitely earning its place."""
    out = set()
    for row in (blast or {}).get("rows", []):
        if row.get("stopped") and not row.get("false_block"):
            out.update(FROM_BLAST.get(row.get("probe", ""), ()))
    return out


def already_enforced(rows, guards):
    """Prohibitions restating something the repository's own hooks refuse.

    Cross-references dimension 1: `guards` is the set of things this repository
    was measured actually refusing. A rule against a thing that cannot happen
    is paying rent on every turn to say something the machine already says --
    and says better, because a guard is not optional and does not depend on the
    agent having read anything.

    This is not an instruction to delete the sentence. Some teams want the
    guard *and* the sentence, so a person understands the refusal when it
    comes. It is a line item, and the page says so."""
    hits = []
    for row in rows:
        if row["kind"] not in ("prohibition", "both"):
            continue
        for label, pattern in ENFORCEABLE:
            if pattern.search(row["text"]) and label in guards:
                hits.append({**row, "enforced_by": label})
                break
    return hits


def misfiled(rows):
    """Floor sentences that name one path and are paid for on every turn.

    Not wrong -- misfiled. The same words under a path-scoped rule cost nothing
    until somebody touches that path, which is what `parked` on the page is
    already measuring for the rules that did it."""
    out = []
    for row in rows:
        m = SCOPED_HINT.search(row["text"]) or PATH_IN_SENTENCE.search(
            row["text"])
        if m:
            out.append({**row, "about": m.group(1)})
    return out


def floor_text(root):
    """Everything paid for on every turn, as one string per file."""
    out = {}
    for cand in ("CLAUDE.md", os.path.join(".claude", "CLAUDE.md"),
                 "AGENTS.md"):
        p = os.path.join(root, cand)
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    out[cand] = fh.read()
            except OSError:
                continue
    rules = os.path.join(root, ".claude", "rules")
    if os.path.isdir(rules):
        for name in sorted(os.listdir(rules)):
            p = os.path.join(rules, name)
            if not name.endswith(".md") or not os.path.isfile(p):
                continue
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    body = fh.read()
            except OSError:
                continue
            # A rule with a path glob in its frontmatter is not on the floor.
            head = body[:400]
            if re.search(r"^\s*(?:paths|globs|applyTo)\s*:", head, re.M):
                continue
            out[os.path.join(".claude", "rules", name)] = body
    return out


def assess(root, guards=()):
    files = floor_text(root)
    if not files:
        return None
    rows, per_file = [], {}
    for rel, text in files.items():
        got = classify(text)
        for g in got:
            g["file"] = rel
        per_file[rel] = len(got)
        rows += got
    if not rows:
        return None
    kinds = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    enforced = already_enforced(rows, set(guards))
    scoped = misfiled(rows)
    return {"files": per_file, "sentences": len(rows), "kinds": kinds,
            "prohibitions": kinds.get("prohibition", 0) + kinds.get("both", 0),
            "requirements": kinds.get("requirement", 0) + kinds.get("both", 0),
            "already_enforced": enforced,
            "path_scoped_but_loaded": scoped,
            "guards_seen": sorted(guards)}


def render(r):
    out = ["", f"  {r['sentences']} sentence(s) on the floor, across "
               f"{len(r['files'])} file(s)", ""]
    out.append(f"  prohibitions  {r['prohibitions']}")
    out.append(f"  requirements  {r['requirements']}")
    out.append(f"  statements    {r['kinds'].get('statement', 0)}")
    out.append("")
    if r["already_enforced"]:
        out.append(f"  {len(r['already_enforced'])} prohibition(s) restate "
                   f"something this repository's hooks already refuse:")
        for h in r["already_enforced"][:5]:
            out.append(f"    [{h['enforced_by']}] {h['file']}: "
                       f"{h['text'][:90]}")
        out.append("")
    if r["path_scoped_but_loaded"]:
        out.append(f"  {len(r['path_scoped_but_loaded'])} sentence(s) are about "
                   f"one path and are paid for on every turn:")
        for h in r["path_scoped_but_loaded"][:5]:
            out.append(f"    [{h['about']}] {h['text'][:90]}")
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--guard", action="append", default=[],
                    help="a thing this repository was measured refusing; "
                         "repeatable. Comes from dimension 1.")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    r = assess(os.path.abspath(a.root), a.guard)
    if r is None:
        print("cannot judge: nothing is loaded on every turn", file=sys.stderr)
        return 2
    print(render(r))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
