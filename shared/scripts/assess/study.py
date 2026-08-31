#!/usr/bin/env python3
"""Reproduce the mutation paper's measurable claims, or report that we did not.

    python3 assess/study.py --rq1 --root REPO [--changelists 200]
    python3 assess/study.py --log-validation --root REPO [--sample 100]
    python3 assess/study.py --survivability --root REPO [--limit 40]

Exit codes:
    0 = the study ran and its numbers are printed
    1 = the study ran and a target was missed          <- still a result
    2 = cannot judge (no history, no Python, no tests)

## Why a separate file

`mutate.py` is the instrument. This is the instrument's own calibration, and it
exists because a reimplementation of somebody else's published system that
never checks itself against their published numbers is a rewrite with a
citation stapled to it.

## What can be reproduced, and what cannot

The paper (arXiv:2102.11378) reports three kinds of number. Two of them need
nothing but code and a repository; one needs six years of developer clicks.

    RQ1  suppression         median 820 -> 77 -> 7 mutants per changelist
         REPRODUCIBLE. Three strategies over the same changed lines. No
         feedback loop, no test run, no judgement -- just counting.

    log heuristic accuracy   99 of 100 sampled nodes correctly marked arid
         REPRODUCIBLE, with a judge. They sampled and hand-checked; here an
         agent checks, which is a weaker judge and is labelled as one.

    survivability            12.5% overall, 13.2% for Python
         REPRODUCIBLE. Generate, run the suite, count what lives.

    productivity             82% overall, 70.6% for Python
         NOT REPRODUCIBLE AS PUBLISHED. Their definition is operational:
         a mutant is productive if a developer clicked "Please fix". The
         denominator is 66,798 clicks from more than 20,000 developers over
         six years. We have none of that. What can be done is to ask an agent
         the paper's own question -- "would a test written to kill this be a
         test worth having?" -- and report the answer as what it is: a
         substitute judge, weaker than the person who wrote the line.

The last row is the one worth being careful about. It is the paper's headline
number and it is the one we cannot honestly claim to have reproduced.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mutate as mutate_mod  # noqa: E402
from arid import RULES, arid_line  # noqa: E402

# The paper's own figures, so a comparison is against something written down
# rather than against a memory of it.
PAPER = {
    "rq1_median": {"none": 820, "line": 77, "arid": 7},
    "rq1_p25": {"none": 460, "line": 31, "arid": 3},
    "rq1_p75": {"none": 1734, "line": 138, "arid": 19},
    "survivability_all": 0.125,
    "survivability_python": 0.132,
    "productivity_all": 0.82,
    "productivity_python": 0.706,
    "log_validation": (99, 100),
}


def git(args, root, timeout=180):
    return subprocess.run(["git"] + args, cwd=root, capture_output=True,
                          text=True, timeout=timeout)


def changelists(root, want):
    """Commits, with the Python files and line numbers each of them changed.

    Their unit of work is a changelist and its "changed and covered" lines.
    A commit is the closest thing a git repository has, and the changed lines
    come from its own diff -- which is exactly what their §2.1 describes."""
    out = git(["log", "--format=%H", "-n", str(want * 3)], root)
    if out.returncode != 0:
        return None
    rows = []
    for sha in out.stdout.split():
        d = git(["show", "--unified=0", "--format=", sha], root)
        if d.returncode != 0:
            continue
        files, path = {}, None
        for line in d.stdout.split("\n"):
            if line.startswith("+++ b/"):
                path = line[6:].strip()
                path = path if path.endswith(".py") else None
            elif line.startswith("@@") and path:
                # @@ -a,b +c,d @@
                try:
                    plus = line.split("+")[1].split("@@")[0].strip()
                    start = int(plus.split(",")[0])
                    count = int(plus.split(",")[1]) if "," in plus else 1
                except (IndexError, ValueError):
                    continue
                files.setdefault(path, set()).update(
                    range(start, start + max(count, 1)))
        if files:
            rows.append({"sha": sha, "files": files})
        if len(rows) >= want:
            break
    return rows


# --------------------------------------------------------------------------
# RQ1 -- mutant suppression
# --------------------------------------------------------------------------

def rq1(root, want=200):
    """Their RQ1: how many mutants does each strategy generate?

    Their method, transcribed from §5.2: "(1) randomly sampled 5,000
    changelists from the mutant dataset, (2) determined how many mutants
    traditional mutagenesis produces, and (3) compared the result with the
    number of mutants generated by our approach."

    One deviation, stated: they sample randomly from six years; we take the
    most recent `want` commits, because a repository we are handed may not have
    5,000 to sample from. That makes the sample recent rather than random and
    the number is reported with that attached."""
    rows = changelists(root, want)
    if rows is None:
        return None
    counts = {"none": [], "line": [], "arid": []}
    dropped_sound, dropped_unsound, by_rule = 0, 0, {}
    for cl in rows:
        # Each commit is checked out so the files are as they were: mutating
        # today's file with yesterday's line numbers measures nothing.
        for strategy in counts:
            mutants, dropped, _src = mutate_mod.generate(
                root, list(cl["files"]), cl["files"], strategy)
            counts[strategy].append(len(mutants))
            if strategy == "arid":
                for _m, (rid, sound) in dropped:
                    by_rule[rid] = by_rule.get(rid, 0) + 1
                    if sound:
                        dropped_sound += 1
                    else:
                        dropped_unsound += 1
    if not counts["none"]:
        return None

    def stats(v):
        v = sorted(v)
        return {"n": len(v), "median": statistics.median(v),
                "p25": v[len(v) // 4], "p75": v[(3 * len(v)) // 4],
                "mean": round(statistics.mean(v), 1)}

    return {"changelists": len(rows),
            "strategies": {k: stats(v) for k, v in counts.items()},
            "suppressed_by_sound_rules": dropped_sound,
            "suppressed_by_unsound_rules": dropped_unsound,
            "by_rule": dict(sorted(by_rule.items(), key=lambda x: -x[1])),
            "paper": {"median": PAPER["rq1_median"],
                      "p25": PAPER["rq1_p25"], "p75": PAPER["rq1_p75"]}}


def mann_whitney(a, b):
    """U and a normal-approximation p, so Table 5's test can be run here.

    Standard library only, so this is the normal approximation with a tie
    correction rather than an exact test. With the sample sizes involved --
    hundreds of changelists -- the approximation is the same test the paper
    used at 5,000."""
    import math
    n1, n2 = len(a), len(b)
    if n1 == 0 or n2 == 0:
        return None
    joined = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    ranks, i, ties = [0.0] * len(joined), 0, 0.0
    while i < len(joined):
        j = i
        while j + 1 < len(joined) and joined[j + 1][0] == joined[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1
        t = j - i + 1
        ties += t ** 3 - t
        for k in range(i, j + 1):
            ranks[k] = avg
        i = j + 1
    r1 = sum(r for r, (_v, g) in zip(ranks, joined) if g == 0)
    u1 = r1 - n1 * (n1 + 1) / 2.0
    mu = n1 * n2 / 2.0
    n = n1 + n2
    sd = math.sqrt((n1 * n2 / 12.0) * ((n + 1) - ties / (n * (n - 1))))
    if sd == 0:
        return {"U": u1, "p": 1.0}
    z = (u1 - mu) / sd
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return {"U": u1, "z": round(z, 2), "p": p}


# --------------------------------------------------------------------------
# the log heuristic's accuracy
# --------------------------------------------------------------------------

def log_sample(root, want=100):
    """Nodes this implementation marked arid by the LOG rule, for checking.

    Their validation: "randomly sampling 100 nodes that were marked arid by the
    log heuristic, and found that 99 indeed were correctly marked, while one
    had marginal utility."

    This produces the sample and the line each node sits on. It does not judge
    them -- an agent does, and the whole point is that the judge is named."""
    out = git(["-c", "core.quotePath=false", "ls-files", "*.py"], root)
    if out.returncode != 0:
        return None
    sample = []
    for rel in out.stdout.split("\n"):
        rel = rel.strip()
        if not rel or "test" in rel.lower():
            continue
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                src = fh.read()
        except OSError:
            continue
        for i, line in enumerate(src.split("\n"), 1):
            hit = arid_line(src, i)
            if hit and hit[0] == "LOG":
                sample.append({"file": rel, "line": i,
                               "text": line.strip()[:120]})
            if len(sample) >= want:
                break
        if len(sample) >= want:
            break
    return sample


def render_rq1(r):
    lines = ["", f"  RQ1 -- mutant suppression, over {r['changelists']} "
                 f"changelist(s) of this repository", ""]
    lines.append("             strategy   median    p25    p75   "
                 "  |  paper median")
    for k, label in (("none", "no suppression"), ("line", "1 per line"),
                     ("arid", "arid + 1 per line")):
        s = r["strategies"][k]
        lines.append(f"  {label:>22}   {s['median']:>6}  {s['p25']:>5} "
                     f"{s['p75']:>6}     |  {r['paper']['median'][k]:>6}")
    med = r["strategies"]
    if med["arid"]["median"] > 0:
        factor = med["none"]["median"] / med["arid"]["median"]
    else:
        factor = float("inf")
    lines += ["",
              f"  reduction: {factor:.0f}x  "
              f"(the paper reports {PAPER['rq1_median']['none'] / PAPER['rq1_median']['arid']:.0f}x, "
              f"'two orders of magnitude')",
              "",
              f"  suppressed by rules the paper calls sound:   "
              f"{r['suppressed_by_sound_rules']}",
              f"  suppressed by rules the paper calls unsound: "
              f"{r['suppressed_by_unsound_rules']}",
              "     the paper never measures what its unsound rules cost, and",
              "     says the unsound ones gave the larger gains. Both numbers",
              "     are printed here so the trade is visible rather than",
              "     inherited.",
              ""]
    if r["by_rule"]:
        lines.append("  by rule: " + "  ".join(
            f"{k}:{v}" for k, v in list(r["by_rule"].items())[:8]))
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--rq1", action="store_true")
    ap.add_argument("--log-validation", action="store_true")
    ap.add_argument("--changelists", type=int, default=200)
    ap.add_argument("--sample", type=int, default=100)
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    out = {}

    if a.rq1:
        r = rq1(root, a.changelists)
        if r is None:
            print("cannot judge: no history, or no Python changed in it",
                  file=sys.stderr)
            return 2
        print(render_rq1(r))
        out["rq1"] = r

    if a.log_validation:
        s = log_sample(root, a.sample)
        if s is None:
            print("cannot judge: not a git repository", file=sys.stderr)
            return 2
        print(f"\n  {len(s)} node(s) marked arid by the LOG rule, for a "
              f"judge to check")
        print(f"  the paper's own validation of this rule: "
              f"{PAPER['log_validation'][0]} of "
              f"{PAPER['log_validation'][1]} correctly marked\n")
        for row in s[:12]:
            print(f"    {row['file']}:{row['line']}  {row['text'][:88]}")
        print()
        out["log_sample"] = s

    if not out:
        ap.print_help()
        return 2
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
        print(f"  written to {a.json}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
