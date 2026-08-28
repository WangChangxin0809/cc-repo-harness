# 0001 — The retrieval layer is measured, and it does not yet earn its place

Date: 2026-08-28
Status: accepted

## Context

Every claim in this plugin is argued from first principles and none of them had
been measured. That is the plugin's own standard turned inward: *a check nobody
has watched fail is a file, not a check* — so a harness nobody has measured is a
belief, not a harness. Tier C's install list has said "a gold set for the
harness itself" since the first release and it was never built.

Two open questions forced the issue. RepoGraph
([arXiv:2410.14684](https://arxiv.org/abs/2410.14684)) ablated hop count on
SWE-bench Lite and found 2-hop retrieval scoring *below* its no-graph baseline,
while 1-hop was the best of everything tried. It did not test PageRank — it
inherited it from Aider and dropped it without a comparison. So this index's two
central choices, PageRank as the default and k-hop as the cheap tier, had no
evidence behind them in either direction.

## Decision

Ship `scripts/index/benchmark.py`: leave-one-out co-change prediction against
git history, with two controls, and no model in the loop.

A commit touching {A, B, C} is a statement by someone who knew the codebase that
those files matter together. Seed the graph with A, ask whether B and C come
back in the top k, average over trials. That is `recall@k`.

Two controls are what make the number mean anything:

- **`random`** — the floor. A strategy that cannot beat uniform sampling is
  measuring nothing.
- **`frequency`** — the k most-churned files, *ignoring the seed entirely*,
  counted leave-one-out so the commit under test cannot vote for itself.

## Result, on Flask at `d318b683` (800 commits, 300 trials, k=10)

| strategy | recall@10 | vs random |
|---|---|---|
| frequency | **0.3774** | 5.15x |
| pagerank | 0.3417 | 4.66x |
| hops1 | 0.3171 | 4.33x |
| hops2 | 0.3038 | 4.14x |
| random | 0.0733 | — |

Three things follow, and the second is not comfortable.

**The graph carries real signal.** 4.7x the floor is not noise.

**It does not beat churn.** `frequency` wins while ignoring the seed and costing
nothing to compute. On this repository the index does not earn the seconds it
takes to build or the complexity it adds.

**The internal ranking question is settled, in the default's favour.**
`pagerank > hops1 > hops2`, consistently and in that order. RepoGraph's finding
that more hops is worse reproduces here on a different graph, a different
corpus, and a different metric — and PageRank, which they never tested, is
better than both. `--hops 2` should be treated as an experiment, not a setting.

## Rejected

- **Running RepoGraph's benchmark instead.** It is not a reusable benchmark; it
  is an experiment bound to forks of Agentless and SWE-agent, measuring
  end-to-end issue resolve rate with GPT-4o. Using it means plugging this index
  into their forks and running 300 SWE-bench instances per arm — their own paper
  reports 2–10 hours and $0.34–$2.69 per instance, so roughly $100–800 and a day
  per configuration. That price buys one number about an agent, dominated by the
  model, and cannot answer "is PageRank better than 1-hop *for this graph*"
  without a full run per arm. It is the right instrument for their claim and the
  wrong one for this question.
- **Excluding nothing.** Unfiltered, `frequency` scores 0.5555 against
  PageRank's 0.2144 — but almost entirely on `CHANGES.rst`, which appears in 30%
  of Flask commits. A tool answering "you edited `blueprints.py`, also look at
  the changelog" has said nothing about the code. Files appearing in more than
  15% of commits are excluded from ground truth, `--exclude-ubiquitous 1.0`
  disables it, and both numbers are recorded here because the filter flatters
  the graph and hiding that would be the more comfortable choice.
- **Tuning the ranking until it wins.** The benchmark was built before the
  result was known and its parameters have not been touched since. A benchmark
  edited until the incumbent wins measures the editor.

## What this does not measure

Co-change is partly a process artifact — same author, same release, same test
file — and a structural graph should not be expected to dominate it. The index's
stated job is *"where does X happen and what would break"*, which is closer to
localisation than to co-change. So this is a proxy, and a proxy the incumbent
loses on is evidence, not proof.

It says nothing at all about the rest of the harness. Guards, gates, delivery
moments, and `CLAUDE.md` placement are claims about agent behaviour and need a
different instrument entirely.

## Revisit when

- A localisation benchmark exists — seed from an issue's text, score against the
  files a real patch touched. That is RepoGraph's Table 3, it needs no model,
  and it measures the task the index actually claims.
- The result reverses on a second repository. One corpus is one corpus, and
  Flask is small, flat, and changelog-heavy. If the graph beats churn on a large
  layered codebase, the conclusion here is about Flask, not about the index.
- The index stops being tier C. It is currently installed only for large
  repositories, which is the regime this measurement did not cover.
