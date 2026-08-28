#!/usr/bin/env python3
"""Measure whether the graph earns its place, against baselines that do not use it.

    python3 scripts/index/benchmark.py [--root .] [--k 10] [--commits 300]

    0 = measured    2 = cannot judge (no graph, or too few trials to mean anything)

## The question, made falsifiable

The index claims to answer *"given that I am here, what else matters"*. Git
history already contains thousands of answers to exactly that: every commit
touching more than one file is a statement that those files matter together,
written by someone who knew the codebase.

So, **leave-one-out co-change prediction**. Take a commit touching {A, B, C}.
Seed the graph with A. Ask whether B and C come back in the top k. Average
over every trial. That is `recall@k`, and it is the same shape as RepoGraph's
localisation-coverage table (arXiv:2410.14684 Table 3).

## What this is not

It is co-change prediction from the *current* graph, not a simulation of
retrieval as it stood at each commit -- rebuilding the graph per commit means a
checkout per commit, and the result would answer a question nobody has. Files
absent from the graph today are dropped from both the seeds and the ground
truth. That makes this a statement about coupling the graph can see now, and it
is stated here rather than in a footnote because a benchmark whose scope is
misread is worse than no benchmark.

It also cannot tell you whether the *harness* has value. It measures one
component: retrieval. The claims about delivery moments need agent behaviour,
not recall.

## Why the baselines are the point

A retrieval number alone is unfalsifiable -- 0.42 is good or bad depending on
what else was available. Two controls make it mean something:

* `random` — the floor. If a strategy cannot beat uniform sampling, it is
  measuring nothing, and every other number here is an artefact.
* `frequency` — the k most-frequently-changed files, ignoring the seed
  entirely. This is the baseline that embarrasses retrieval systems: a handful
  of files change in half of all commits, and predicting them wins more often
  than anyone expects. A graph that cannot beat it is not earning its cost.
  Counted leave-one-out: the commit under test does not contribute to the
  ranking used to predict it, or the control is reading the answer.

## Ubiquitous co-changers are excluded, and this is a claim about the task

A changelog co-changes with everything by convention, not by structure. In
Flask, `CHANGES.rst` appears in 30% of commits; a tool answering "you edited
blueprints.py, also look at CHANGES.rst" has told you nothing about the code,
and a `frequency` control scores heavily on it for free.

Files appearing in more than `--exclude-ubiquitous` of commits are therefore
dropped from the ground truth and from the frequency ranking, and the ones
dropped are printed. That is a decision about what the benchmark is *for*, and
it flatters the graph, so it is stated loudly and it is reversible: run with
`--exclude-ubiquitous 1.0` for the unfiltered number, and report both if you
are making a claim.
"""

from __future__ import annotations

import argparse
import collections
import heapq
import importlib.util
import json
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_query_module():
    spec = importlib.util.spec_from_file_location(
        "index_query", os.path.join(HERE, "query.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def commits_with_files(root, limit):
    """[(sha, [paths])] newest first, from --name-only log output."""
    out = subprocess.run(
        ["git", "log", f"-n{limit}", "--no-merges", "--format=%H",
         "--name-only", "--diff-filter=AMR"],
        cwd=root, capture_output=True, text=True)
    if out.returncode != 0:
        return None
    commits, sha, files = [], None, []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) == 40 and all(c in "0123456789abcdef" for c in line):
            if sha:
                commits.append((sha, files))
            sha, files = line, []
        else:
            files.append(line)
    if sha:
        commits.append((sha, files))
    return commits


def rank_paths(q, graph, seed_node, mode, adj):
    """Ranked file paths for one seed, best first, seed excluded."""
    seeds = {seed_node: 1.0}
    if mode == "pagerank":
        rank = q.pagerank(graph, seeds, adj=adj)
    else:
        rank = q.neighbourhood(graph, seeds, int(mode[-1]), adj=adj)
    out, seen = [], set()
    for nid, score in sorted(rank.items(), key=lambda kv: (-kv[1], kv[0])):
        d = graph["nodes"].get(nid)
        if not d or score <= 0.0:
            continue
        path = d.get("path")
        if path and path not in seen:
            seen.add(path)
            out.append(path)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--graph", default=".index/graph.json")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--commits", type=int, default=300)
    ap.add_argument("--min-files", type=int, default=2)
    ap.add_argument("--max-files", type=int, default=12,
                    help="commits larger than this are refactors and renames; "
                         "they say more about a sweep than about coupling")
    ap.add_argument("--max-fraction", type=float, default=0.25,
                    help="also skip commits touching more than this fraction of "
                         "the repository, whatever their absolute size. An "
                         "initial commit touches everything and is a statement "
                         "about nothing; an absolute cap cannot see that, "
                         "because 12 files is a sweep in a small repo and a "
                         "normal change in a large one")
    ap.add_argument("--exclude-ubiquitous", type=float, default=0.15,
                    help="drop files appearing in more than this fraction of "
                         "commits from ground truth and from the frequency "
                         "control -- changelogs and version files co-change "
                         "with everything and are not retrieval targets. Use "
                         "1.0 to disable. Whatever is dropped is printed.")
    ap.add_argument("--min-trials", type=int, default=25)
    ap.add_argument("--sample", type=int, default=400,
                    help="cap on trials, sampled deterministically. A full "
                         "PageRank runs per trial, so this is what decides "
                         "whether the measurement gets taken at all. Reported.")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    q = load_query_module()
    graph = q.load(root, a.graph)
    if graph is None:
        print(f"cannot judge: no graph at {a.graph} — run build.py first",
              file=sys.stderr)
        return 2

    in_graph = {d["path"] for d in graph["nodes"].values()
                if d["kind"] in ("file", "doc") and d.get("path")}
    node_of = {d["path"]: nid for nid, d in graph["nodes"].items()
               if d["kind"] in ("file", "doc") and d.get("path")}

    commits = commits_with_files(root, a.commits)
    if commits is None:
        print("cannot judge: not a git repository", file=sys.stderr)
        return 2

    sweep_cap = max(a.min_files, int(len(in_graph) * a.max_fraction))

    freq = collections.Counter()
    for _sha, files in commits:
        freq.update({f for f in files if f in in_graph})
    ubiquitous = sorted(p for p, c in freq.items()
                        if c > a.exclude_ubiquitous * len(commits))
    in_graph -= set(ubiquitous)
    for p in ubiquitous:
        del freq[p]

    trials = []          # (seed_path, truth set, the commit's own file set)
    dropped = collections.Counter()
    for _sha, files in commits:
        kept = sorted({f for f in files if f in in_graph})
        if len(kept) < a.min_files:
            dropped["too small"] += 1
            continue
        if len(kept) > a.max_files:
            dropped["over --max-files"] += 1
            continue
        if len(kept) > sweep_cap:
            dropped["a sweep: over --max-fraction of the repo"] += 1
            continue
        for seed in kept:
            truth = set(kept) - {seed}
            if truth:
                trials.append((seed, truth, frozenset(kept)))

    if len(trials) < a.min_trials:
        why = (f"{len(ubiquitous)} of the repository's files were excluded as "
               f"ubiquitous; try --exclude-ubiquitous 1.0"
               if len(ubiquitous) > len(in_graph)
               else "this repository does not have enough multi-file history "
                    "for the number to mean anything")
        print(f"cannot judge: {len(trials)} trials from {len(commits)} commits, "
              f"need {a.min_trials}. {why}.", file=sys.stderr)
        return 2

    population = len(trials)
    if population > a.sample:
        trials = random.Random(0).sample(trials, a.sample)
        trials.sort()

    all_paths = sorted(in_graph)
    strategies = ["pagerank", "hops1", "hops2", "frequency", "random"]
    hits = {s: 0.0 for s in strategies}
    adj = q.build_adjacency(graph, only_known=True)

    for i, (seed, truth, own) in enumerate(trials):
        rng = random.Random(i)          # deterministic: CI must reproduce this
        for s in strategies:
            if s == "random":
                pool = [p for p in all_paths if p != seed]
                got = rng.sample(pool, min(a.k, len(pool)))
            elif s == "frequency":
                # Leave-one-out: this commit does not get to vote for itself.
                got = heapq.nlargest(
                    a.k + 1,
                    ((freq[p] - (1 if p in own else 0), p) for p in all_paths),
                    key=lambda t: (t[0], t[1]))
                got = [p for _c, p in got if p != seed][:a.k]
            else:
                got = [p for p in rank_paths(q, graph, node_of[seed], s, adj)
                       if p != seed][:a.k]
            hits[s] += len(truth & set(got)) / len(truth)

    n = len(trials)
    result = dict(trials=n, trial_population=population, k=a.k,
                  commits_scanned=len(commits),
                  files_in_graph=len(in_graph), sweep_cap=sweep_cap,
                  commits_dropped=dict(dropped), ubiquitous_excluded=ubiquitous,
                  recall={s: round(hits[s] / n, 4) for s in strategies})

    if a.json:
        print(json.dumps(result, indent=2))
        return 0

    sampled = f" (sampled from {population})" if population > n else ""
    print(f"\n{n} trials{sampled} · k={a.k} · {len(commits)} commits · "
          f"{len(in_graph)} files in graph\n")
    # A benchmark that bounds its own input and does not say so reports a
    # number for a population nobody chose.
    if ubiquitous:
        print(f"  excluded as ubiquitous (>{a.exclude_ubiquitous:.0%} of commits, "
              f"not retrieval targets):")
        for p in ubiquitous:
            print(f"      {p}")
    for why, count in sorted(dropped.items(), key=lambda kv: -kv[1]):
        print(f"  dropped {count:>4} commit(s): {why}")
    if dropped:
        print(f"  (sweep cap: {sweep_cap} files = {a.max_fraction:.0%} of the repo)\n")
    print(f"  {'strategy':<12} {'recall@' + str(a.k):>10}   vs random")
    floor = result["recall"]["random"] or 1e-9
    for s in strategies:
        r = result["recall"][s]
        note = "— the floor" if s == "random" else f"{r / floor:.2f}x"
        print(f"  {s:<12} {r:>10.4f}   {note}")

    graph_best = max(result["recall"][s] for s in ("pagerank", "hops1", "hops2"))
    print()
    if graph_best <= result["recall"]["random"]:
        print("  The graph does not beat uniform sampling. Nothing else in this\n"
              "  table means anything until that is explained.")
    elif graph_best <= result["recall"]["frequency"]:
        print("  The graph does not beat 'return the most-churned files', which\n"
              "  ignores the seed entirely and costs nothing to compute. On this\n"
              "  repository the index is not earning its place.")
    else:
        print("  The graph beats both controls on this repository.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
