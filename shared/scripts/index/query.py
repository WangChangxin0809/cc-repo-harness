#!/usr/bin/env python3
"""Rank the graph from where you already are. One entry point; callers differ
only in the seed.

    python3 query.py --seed src/billing/invoice.py [--seed pay_invoice] \\
                     [--budget 2000] [--paths-only]
    python3 query.py --stats

    0 = ranked    2 = cannot judge (no graph — run build.py)

Personalized PageRank, seeded by what the current task already touches. The
question worth answering is "given that I am here, what else matters", not
"what is globally important" -- the latter returns the same five files for every
task, which is why global importance rankings feel useless in practice.

Seeds may be paths, path fragments, or symbol names. Unmatched seeds are
reported rather than ignored: a query that silently matched nothing returns the
graph's global ranking, which looks like a real answer.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict

DAMPING = 0.85
ITERATIONS = 30
# Reverse edges get a fraction of the weight. A file that references a symbol
# should surface the symbol strongly; the symbol should surface its other
# referents weakly, or every common helper drags in half the repository.
REVERSE = 0.25


def load(root, path):
    p = path if os.path.isabs(path) else os.path.join(root, path)
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def divergence(root, g):
    """Files that have moved under the graph since it was built.

    Returns (changed, gone) as sorted path lists, or None when the graph
    carries no stamp -- a graph built by an older `build.py`, which is a fact
    worth reporting rather than a reason to guess.

    Only files the graph already knows about are stat'ed. Detecting *added*
    files would mean re-running `git ls-files` and reapplying build.py's
    exclusion rules here, which is a second copy of a decision that already
    exists in one place -- and this repository has already been bitten once by
    exactly that (two readers of `Governs:` with two different window sizes).
    An added file is not silent anyway: seeding on one produces `seed not found
    in graph`, which is louder than anything this function would print."""
    st = (g.get("meta") or {}).get("stamp")
    if not st or "files" not in st:
        return None
    changed, gone = [], []
    for rel, (mtime, size) in st["files"].items():
        try:
            now = os.stat(os.path.join(root, rel))
        except OSError:
            gone.append(rel)
            continue
        if now.st_mtime_ns != mtime or now.st_size != size:
            changed.append(rel)
    return sorted(changed), sorted(gone)


def report_divergence(root, g, seeds, stream=sys.stderr):
    """Say how stale the graph is, and never refuse because of it.

    Refusing was the first design and it is wrong. `after_edit.py` queries this
    on PostToolUse -- immediately after an edit -- so the file the agent just
    touched is always among the changed ones. A staleness check that exits
    non-zero there would silence the hint for the entire rest of the session,
    starting from the first edit, which is worse than answering from a graph
    that is one file out of date.

    Any threshold ("too stale to answer") would be an invented number, and an
    invented number in a check is the thing people route around. Staleness is
    reported; whether it is disqualifying is the caller's judgement, and the
    caller has context this does not."""
    d = divergence(root, g)
    if d is None:
        print("# graph carries no build stamp — it predates staleness "
              "detection, and how far the tree has moved since is unknown",
              file=stream)
        return
    changed, gone = d
    if not changed and not gone:
        return

    st = g["meta"]["stamp"]
    age = ""
    if st.get("built_at"):
        mins = max(0, int(time.time()) - st["built_at"]) // 60
        age = (f", built {mins // 1440}d ago" if mins >= 1440 else
               f", built {mins // 60}h ago" if mins >= 60 else
               f", built {mins}m ago")
    parts = []
    if changed:
        parts.append(f"{len(changed)} changed")
    if gone:
        parts.append(f"{len(gone)} gone")
    print(f"# graph is stale: {', '.join(parts)} since it was built{age}. "
          f"Rebuild with build.py for current answers.", file=stream)

    # The actionable half. A seed among the changed files means the ranking
    # started from a node describing a version of that file which no longer
    # exists, and that is a different quality of wrong from a stale file
    # somewhere out in the neighbourhood.
    moved = set(changed) | set(gone)
    hit = sorted({p for n in seeds
                  for p in [(g["nodes"].get(n) or {}).get("path")]
                  if p in moved})
    if hit:
        print(f"# and the seed itself moved: {', '.join(hit[:5])}"
              + (f" (+{len(hit) - 5} more)" if len(hit) > 5 else ""),
              file=stream)


def resolve_seeds(g, seeds):
    """Match a seed to nodes. A seed is a path, a path fragment, or a symbol
    name.

    Symbol nodes are keyed `sym:<path>:<name>`, so a bare name matches every
    file that defines it. That is the correct behaviour and not a fallback: the
    caller knows a name, not which definition it meant, and splitting a seed's
    mass across the candidates says exactly that. One seed always contributes a
    total mass of 1 however many nodes it matched, so a common name cannot
    outvote a precise one."""
    hits, missed = {}, []
    for s in seeds:
        found = []
        for prefix in ("file:", "doc:"):
            if f"{prefix}{s}" in g["nodes"]:
                found.append(f"{prefix}{s}")
        found += [n for n, d in g["nodes"].items()
                  if d["kind"] == "symbol" and d.get("name") == s]
        if not found:
            low = s.lower()
            found = [n for n, d in g["nodes"].items()
                     if low in d.get("path", "").lower()
                     or low == d.get("name", "").lower()]
        if found:
            for n in found:
                hits[n] = hits.get(n, 0.0) + 1.0 / len(found)
        else:
            missed.append(s)
    return hits, missed


def build_adjacency(g, only_known=False):
    """node -> [(neighbour, weight)], forward and reverse.

    Extracted so a caller running thousands of queries against one graph pays
    for it once. A single query does not care; benchmark.py runs one per trial
    and rebuilding this per call is the difference between two minutes and two
    hours -- which is the difference between a measurement that gets taken and
    one that does not."""
    adj = defaultdict(list)
    for a, b, _kind, w in g["edges"]:
        if only_known and not (a in g["nodes"] and b in g["nodes"]):
            continue
        adj[a].append((b, w))
        adj[b].append((a, w * REVERSE))
    return adj


def neighbourhood(g, seeds, hops, adj=None):
    """Breadth-first expansion from the seeds, scored by 1/distance.

    This is the reflex tier. It costs one pass over the edge list rather than
    thirty, which is the difference between something that can run on every turn
    and something that cannot -- see the measurements in the repo-index skill.
    It answers a strictly weaker question ("what is adjacent") than PageRank
    ("what matters given where I am"), and that is the correct trade when the
    output is a hint the agent is free to ignore.
    """
    if adj is None:
        adj = build_adjacency(g)

    score = dict(seeds)
    frontier = set(seeds)
    for depth in range(1, hops + 1):
        nxt = set()
        for n in frontier:
            for m, w in adj.get(n, ()):
                gain = w / (depth + 1) ** 2
                if score.get(m, 0.0) < gain:
                    score[m] = gain
                    nxt.add(m)
        frontier = nxt
    return score


def pagerank(g, seeds, iterations=ITERATIONS, adj=None):
    out = build_adjacency(g, only_known=True) if adj is None else adj

    total = sum(seeds.values()) or 1.0
    personal = {n: v / total for n, v in seeds.items()}
    rank = {n: personal.get(n, 0.0) for n in g["nodes"]}
    if not any(rank.values()):
        rank = {n: 1.0 / len(g["nodes"]) for n in g["nodes"]}
        personal = {n: 1.0 / len(g["nodes"]) for n in g["nodes"]}

    for _ in range(iterations):
        nxt = defaultdict(float)
        leaked = 0.0
        for n, r in rank.items():
            targets = out.get(n)
            if not targets:
                leaked += r
                continue
            tw = sum(w for _, w in targets)
            for m, w in targets:
                nxt[m] += r * w / tw
        for n in rank:
            rank[n] = (1 - DAMPING) * personal.get(n, 0.0) \
                + DAMPING * (nxt[n] + leaked * personal.get(n, 0.0))
    return rank


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--graph", default=".index/graph.json")
    ap.add_argument("--seed", action="append", default=[])
    ap.add_argument("--budget", type=int, default=2000,
                    help="approximate token budget for the printed map")
    ap.add_argument("--paths-only", action="store_true")
    ap.add_argument("--iterations", type=int, default=ITERATIONS,
                    help="fewer iterations trade ranking precision for latency; "
                         "the reflex tier runs on every turn and cannot afford "
                         "the default on a large repository")
    ap.add_argument("--hops", type=int, default=0,
                    help="reflex tier: N-hop neighbourhood instead of PageRank. "
                         "One pass over the edges rather than thirty. Use 1: "
                         "two hops measured WORSE than no graph at all "
                         "(arXiv:2410.14684).")
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    g = load(root, a.graph)
    if g is None:
        print(f"cannot judge: no graph at {a.graph} — run build.py first",
              file=sys.stderr)
        return 2

    if a.stats:
        m = dict(g["meta"])
        blind = m.pop("blind", {})
        # `stamp` holds one entry per indexed file. Printed raw it buries every
        # other row under thousands of lines of mtimes.
        m.pop("stamp", None)
        for k, v in m.items():
            print(f"{k:<12} {v}")
        print(f"{'blind':<12} {blind.get('unresolved_import_count', 0)} unresolved "
              f"imports, {blind.get('dynamic_dispatch_count', 0)} dynamic sites")
        d = divergence(root, g)
        if d is None:
            print(f"{'stale':<12} unknown — graph carries no build stamp")
        else:
            changed, gone = d
            print(f"{'stale':<12} {len(changed)} changed, {len(gone)} gone "
                  f"since build" if changed or gone
                  else f"{'stale':<12} no — every indexed file is as built")
        return 0

    seeds, missed = resolve_seeds(g, a.seed)
    if missed:
        # Loud on purpose: an unmatched seed silently degrades to a global
        # ranking, which is indistinguishable from an answer.
        print(f"# seed not found in graph: {', '.join(missed)}", file=sys.stderr)
    if not seeds and a.seed:
        print("cannot judge: no seed matched anything in the graph",
              file=sys.stderr)
        return 2

    report_divergence(root, g, seeds)

    if a.hops > 1:
        # The one published ablation of this exact choice found 2-hop flattened
        # retrieval scoring BELOW its no-graph baseline (26.00 vs 27.33 on
        # SWE-bench Lite), while 1-hop was the best of everything tried. The
        # weighting and budget here may or may not repair that; nobody has
        # measured it. Say so rather than let the flag read as a dial.
        print(f"# --hops {a.hops}: beyond one hop the neighbourhood grew faster "
              f"than its usefulness in the one published ablation "
              f"(arXiv:2410.14684). Unmeasured here.", file=sys.stderr)

    if a.hops:
        rank = neighbourhood(g, seeds, a.hops)
    else:
        rank = pagerank(g, seeds, iterations=a.iterations)
    ranked = sorted(rank.items(), key=lambda kv: (-kv[1], kv[0]))

    # A symbol node carries the path that defines it, because its id is keyed
    # by that path. This used to need a full inversion of the defines edges --
    # 17k x 160k on a real repository if done per symbol, which turned a
    # one-second query into eighty.

    # ~4 chars per token; each printed line is roughly one path plus its symbols.
    remaining = a.budget * 4
    by_file = defaultdict(list)   # symbols to annotate each path with
    listed = set()                # paths already placed in `order`
    order = []
    for nid, score in ranked:
        d = g["nodes"].get(nid)
        if d is None:
            # An edge endpoint with no node: a `Governs:` line naming a path
            # that is not tracked, usually a glob or a stale path. build.py
            # counts these; here they are simply not rankable.
            continue
        if d["kind"] in ("file", "doc"):
            # `listed`, not `by_file` -- the symbol branch below populates
            # by_file for a path before that path's own node is reached, and
            # testing membership there drops the file from the output entirely.
            # In --hops mode symbols outrank their files, so the whole result
            # comes back empty, with exit 0.
            if d["path"] not in listed:
                listed.add(d["path"])
                order.append((d["path"], score, d["kind"]))
        elif d["kind"] == "symbol":
            p = d.get("path")
            if p and len(by_file[p]) < 8:
                by_file[p].append(d["name"])
                if p not in listed:
                    listed.add(p)
                    order.append((p, score, "file"))

    for path, score, _kind in order:
        syms = by_file.get(path) or []
        line = (path if a.paths_only
                else f"{path}  [{score:.4f}]" + (f"  {' '.join(syms)}" if syms else ""))
        if remaining - len(line) < 0:
            break
        remaining -= len(line) + 1
        print(line)

    if not order:
        # A ranking that produced nothing is a broken query, not a repository
        # with no relevant code. Saying so is the difference between the caller
        # widening the seed and the caller concluding the code does not exist.
        print("cannot judge: ranking produced no files — the seed resolved but "
              "reached nothing. Widen --hops, or check the graph is current.",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
