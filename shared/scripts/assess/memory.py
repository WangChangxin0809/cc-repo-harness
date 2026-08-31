#!/usr/bin/env python3
"""Dimension 4: can an agent that has never seen this repository find its way?

    python3 assess/memory.py --prepare --root . --work DIR   # build the brief
    python3 assess/memory.py --score   --work DIR            # grade the answers

This module never spawns anything. It prepares two copies of the repository and
a list of questions with their answer keys, and later grades the answers that
come back. Something with an agent in it -- `/assess`, or the `repo-assessor`
agent -- does the asking. Keeping the two apart is what lets the grading be
tested: a scorer with a model inside it cannot be watched failing.

## The measurement is a difference, not a score

The same questions are asked of two copies:

    with/     the repository as it is
    without/  the same tree, minus CLAUDE.md, .claude/ and the nested CLAUDE.md
              files -- everything the repository keeps in order to explain
              itself

The difference between the two runs is the memory. Counting what a repository
keeps would grade it on whether it adopted somebody else's conventions, would
reward this plugin's own presence, and would call 0024 -- which cut the standing
cost by 81% -- a regression while dimension 5 called it an improvement. A
difference has none of those problems: a thin CLAUDE.md that halves the search
beats six skills that change nothing, and adding files cannot raise it.

-> docs/decisions/0025

## The probe cannot reach the history, by construction

Both copies are made **without `.git`**, and the probe agent is given no Bash.
A rule saying "do not read the history" is a rule that can be broken silently --
one `git log --grep` answers every micro question, and the run would look like a
brilliant result rather than a cheat. So the history is not forbidden, it is
absent.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import history as history_mod  # noqa: E402

# Above this, "did you find the right files?" stops meaning anything: a commit
# touching thirty files is answered correctly by naming almost any of them.
# Dimensions 2 and 3 draw the same line, and dimension 4 not drawing it is the
# bug that made every repository's biggest router look like its most reworked
# file -> docs/decisions/0025
FOCUSED = 3

# A squash merge leaves `(#123)` on the subject. It is a cross-reference
# handle, not a description of the change, and leaving it in turns part of the
# question into "can you look up pull request 123" -- which a probe with no
# history cannot do, and which is not what is being measured. A live probe
# reported using exactly this to tell two commits apart.
PR_SUFFIX = re.compile(r"\s*\(#\d+\)\s*$")

# What a repository keeps in order to explain itself. Removed for the second
# run; the difference the two runs make is the whole measurement.
MEMORY_PATHS = ("CLAUDE.md", ".claude", "AGENTS.md", ".cursorrules",
                ".github/copilot-instructions.md")

# Never copied into either tree: somebody else's code, build output, and the
# history the probe must not have.
SKIP_DIRS = (".git", "node_modules", "vendor", "venv", ".venv", "dist",
             "build", "target", "__pycache__", ".tox", ".next", "coverage")

MACRO = [
    ("components", "What are this project's main components or modules?",
     "judge"),
    ("flow", "What is the core data or control flow through it?", "judge"),
    ("truth", "Which directories or files are the source of truth?", "judge"),
    ("generated", "Which parts are generated or derived rather than written "
                  "by hand? List paths.", "generated"),
    ("tests", "Where are the tests, and what command runs them? List the "
              "directories and the entry point.", "tests"),
    ("constraints", "What constraints are specific to this repository -- "
                    "things that would not be true of a similar project?",
     "judge"),
]


def _relevant(paths):
    return [p for p in paths if history_mod.is_source(p)
            and not history_mod.TEST_PATH.search(p)]


def pick_commits(root, k=3):
    """The most recent focused commits, and the files each one touched.

    The commit's own diff is the answer key, which is why this measurement
    costs nothing to ground: the repository wrote its own exam. Only commits
    whose files still exist are usable -- the probe reads the tree as it is
    today, so a question whose answer was deleted has no answer."""
    log = history_mod.commits(root)
    if log is None:
        return None
    out = []
    for sha, subject, paths in log:
        src = _relevant(paths)
        if not src or len(src) > FOCUSED:
            continue
        alive = [p for p in src if os.path.exists(os.path.join(root, p))]
        if not alive:
            continue
        out.append({"sha": sha, "subject": PR_SUFFIX.sub("", subject),
                    "files": sorted(alive)})
        if len(out) >= k:
            break
    return out


def _tracked(root):
    """What git tracks, which is the only honest definition of "the repository".

    Walking the tree instead copies build output, dependencies, and -- on this
    project -- 25 cloned repositories under `eval/.work/` that are somebody
    else's code entirely. A probe reading those is answering questions about
    the wrong repository, and the copy was 252MB. `-z` because without it git
    wraps any non-ASCII path in quotes and the path stops resolving."""
    out = subprocess.run(
        ["git", "-c", "core.quotePath=false", "ls-files", "-z"],
        cwd=root, capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        return None
    return [p for p in out.stdout.split("\0") if p]


def _copy_tree(root, dest, paths, strip=()):
    strip = {s.rstrip("/") for s in strip}
    for rel in paths:
        parts = rel.split("/")
        # A nested CLAUDE.md is memory too, wherever it sits, so the basename
        # is tested as well as every prefix of the path.
        if parts[-1] in strip or rel in strip:
            continue
        if any(("/".join(parts[:i]) in strip or parts[i - 1] in SKIP_DIRS)
               for i in range(1, len(parts))):
            continue
        src = os.path.join(root, rel.replace("/", os.sep))
        if not os.path.isfile(src):
            continue
        target = os.path.join(dest, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        try:
            shutil.copy2(src, target)
        except OSError:
            pass


def prepare(root, work, k=3):
    """Two copies and a brief. Returns the brief, and writes it to `work`."""
    commits = pick_commits(root, k)
    paths = _tracked(root)
    if commits is None or paths is None:
        return None
    for name, strip in (("with", ()), ("without", MEMORY_PATHS)):
        dest = os.path.join(work, name)
        shutil.rmtree(dest, ignore_errors=True)
        os.makedirs(dest, exist_ok=True)
        _copy_tree(root, dest, paths, strip)

    removed = sorted(
        p for p in MEMORY_PATHS
        if os.path.exists(os.path.join(root, p))
        and not os.path.exists(os.path.join(work, "without", p)))

    brief = {
        "trees": {"with": os.path.join(work, "with"),
                  "without": os.path.join(work, "without")},
        "removed_for_without": removed,
        "macro": [{"id": i, "question": q} for i, q, _kind in MACRO],
        "micro": [{"id": f"micro{n}", "subject": c["subject"]}
                  for n, c in enumerate(commits, 1)],
        "key": {"micro": {f"micro{n}": c["files"]
                          for n, c in enumerate(commits, 1)},
                "commits": commits},
    }
    with open(os.path.join(work, "brief.json"), "w", encoding="utf-8") as fh:
        json.dump(brief, fh, indent=2, ensure_ascii=False)
    return brief


def _files_in(answer):
    """Paths named anywhere in a free-text answer."""
    if isinstance(answer, list):
        text = " ".join(str(a) for a in answer)
    else:
        text = str(answer or "")
    return {m.group(0).lstrip("./")
            for m in re.finditer(r"[\w][\w./-]*\.[A-Za-z][A-Za-z0-9]{0,5}",
                                 text)}


def score_micro(brief, run):
    """Grade one run's micro answers against the commits that wrote them."""
    rows = []
    for qid, want in sorted(brief["key"]["micro"].items()):
        named = _files_in((run.get("answers") or {}).get(qid))
        hit = [w for w in want if w in named or
               any(n.endswith("/" + w) or w.endswith("/" + n) for n in named)]
        rows.append({"id": qid,
                     "subject": next(m["subject"] for m in brief["micro"]
                                     if m["id"] == qid),
                     "found": len(hit), "of": len(want),
                     # Recall alone is gameable: an answer listing two hundred
                     # files finds everything. Reporting how many were named
                     # says so without inventing a threshold nobody agreed to.
                     "named": len(named),
                     "files": want, "hit": hit,
                     "tool_calls": (run.get("tool_calls") or {}).get(qid)})
    return rows


def compare(brief, with_run, without_run):
    """The difference between the two runs, which is the memory.

    Reported as rows, never as a rate. Three questions do not support a
    percentage, and `66%` from a sample of three is a number invented to look
    like a measurement -> docs/decisions/0025"""
    a = score_micro(brief, with_run)
    b = score_micro(brief, without_run)
    by_id = {r["id"]: r for r in b}
    rows = []
    for r in a:
        o = by_id.get(r["id"], {})
        rows.append({
            "subject": r["subject"],
            "with": {"found": r["found"], "of": r["of"],
                     "named": r["named"], "tool_calls": r["tool_calls"]},
            "without": {"found": o.get("found"), "of": o.get("of"),
                        "named": o.get("named"),
                        "tool_calls": o.get("tool_calls")},
        })
    lift = sum(r["with"]["found"] for r in rows) - sum(
        (r["without"]["found"] or 0) for r in rows)
    return {"rows": rows, "lift": lift,
            "removed": brief.get("removed_for_without", [])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--work", required=True)
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--with-answers")
    ap.add_argument("--without-answers")
    ap.add_argument("--commits", type=int, default=3)
    a = ap.parse_args()

    if a.prepare:
        os.makedirs(a.work, exist_ok=True)
        brief = prepare(os.path.abspath(a.root), a.work, a.commits)
        if brief is None:
            print("the history cannot be read -- COULD NOT JUDGE",
                  file=sys.stderr)
            return 2
        if not brief["micro"]:
            print("no commit focused enough to ask about -- COULD NOT JUDGE",
                  file=sys.stderr)
            return 2
        print(json.dumps(brief, indent=2, ensure_ascii=False))
        return 0

    if a.score:
        with open(os.path.join(a.work, "brief.json"), encoding="utf-8") as fh:
            brief = json.load(fh)
        with open(a.with_answers, encoding="utf-8") as fh:
            w = json.load(fh)
        with open(a.without_answers, encoding="utf-8") as fh:
            o = json.load(fh)
        print(json.dumps(compare(brief, w, o), indent=2, ensure_ascii=False))
        return 0

    ap.error("one of --prepare or --score is required")


if __name__ == "__main__":
    sys.exit(main())
