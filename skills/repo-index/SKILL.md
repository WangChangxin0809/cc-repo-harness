---
name: repo-index
description: Give a repository a code-and-docs graph an agent can query — tree-sitter symbols, import and call edges, doc-to-code edges, ranked by personalized PageRank from whatever the current task touches. Use this when an agent cannot find the relevant code in a large repo, when grep returns hundreds of hits or none, when someone asks for RAG / semantic search / a code index / an embedding store for their codebase, when onboarding to unfamiliar code, and when you need to know what a change would break.
---

# One graph, two tiers

Governs: shared/scripts/index/

Retrieval fails in repositories for a specific reason: the useful unit is not a
paragraph, it is a symbol and its neighbourhood. A chunk-and-embed pipeline
returns files that talk *about* authentication; what the task needs is the four
functions that would break.

So: **one graph, built from source, queried two ways.** Not a stack of
retrievers — an extra retriever whose results have to be merged is a second
ranking problem on top of the one you had.

## The graph

Nodes are `file:<path>`, `sym:<path>:<name>`, and `doc:<path>`. Edges:

| Edge | From | Weight |
|---|---|---|
| defines | file → symbol | tree-sitter tags |
| references | file → symbol | tree-sitter tags, split across definers |
| imports | file → file | resolved import statements |
| calls | symbol → symbol | call sites inside a definition's span |
| governs | doc → path | a `Governs: src/billing/` line in the doc's head |
| supersedes | doc → doc | `Supersedes: 0004` |

**A symbol node is keyed by the file that defines it.** Keying by bare name
merges every definition sharing it, and the merged node then dominates the
graph: in this plugin's own repository `sym:main` — sixteen unrelated
`def main()` — had a higher degree than any real file, and seeding on one guard
ranked an *empty template* second because five guards define `check`. Bare names
are still how a reference resolves and how `--seed` matches; they are just no
longer the node. A reference to an ambiguous name contributes `1/N` to each
candidate, and `--report` lists which names are ambiguous.

`Governs:` is the edge that makes documents reachable from code. Without it,
docs and code are two disconnected components and no amount of ranking bridges
them. It is a plain line in the document's first **60** lines — no `---` fence
needed. Targets are matched by path segment, so `Governs: src/bill` covers
`src/bill` and `src/bill/…` and does *not* reach `src/billing_old/`; a trailing
slash is allowed and changes nothing. See `writing-docs` for the convention.

```bash
python3 scripts/index/build.py            # full rebuild, from source only
python3 scripts/index/query.py --seed src/billing/invoice.py --budget 2000
```

**Full rebuild, no incremental state.** An index that updates incrementally
develops a divergence between itself and the tree, and that divergence is
silent — you get confidently wrong answers, which is worse than no answers. If
a full rebuild is too slow to run on demand, the repository is tier C and the
rebuild belongs in a `PostToolUse` hook, still full.

## Ranking

Personalized PageRank, seeded by the files the current task already touches, and
truncated to a token budget. This is Aider's repomap construction and it earns
its place: it answers *"given that I am here, what else matters"*, which is the
actual question, rather than *"what is globally important"*, which returns the
same five files for every task.

`query.py` is the one entry point. Callers differ only in the seed:

- a `UserPromptSubmit` hook seeds from paths named in the prompt
- a `PostToolUse` hook seeds from the file just edited
- the `repo-explorer` subagent seeds from wherever its investigation has reached

One entry means one ranking to tune, one set of edges to trust, and one place a
bug can hide.

## Two tiers of use

**Reflex** — deterministic, milliseconds, no model call. Fires at moments 3 and
6. It never decides anything; it puts a ranked list of paths in front of the
agent and lets the agent decide. Being cheap is what makes it acceptable to run
on every turn, and being unreliable is acceptable because nothing depends on it
alone. This is where the earlier generation of RAG belongs, scoped down to what
it is actually good at.

**Use `--hops 1`.** RepoGraph ([arXiv:2410.14684](https://arxiv.org/abs/2410.14684))
ablated exactly this on SWE-bench Lite and the result is the most useful number
anyone has published about repository graphs:

| Retrieval | Resolve rate |
|---|---|
| no graph (baseline) | 27.33% |
| **1-hop, flattened** | **29.67%** |
| 2-hop, summarized by an LLM | 28.67% |
| 1-hop, summarized | 28.33% |
| 2-hop, flattened | **26.00%** — *below the baseline* |

Two hops averaged 54.5 nodes against one hop's 11.6, and the extra context was
worse than no context at all. Feeding an agent more of the neighbourhood is not
a free improvement with a diminishing return; past one hop it is a net loss that
an LLM summarisation pass only partly repairs.

What transfers and what does not, stated honestly: their graph is unweighted,
successors-only, and unranked, while this one weights edges, walks both
directions, decays by `w/(depth+1)²`, and truncates to a token budget — all of
which are plausibly the mitigations their 2-hop result calls for, and **none of
which have been measured here**. What does transfer is the direction. Treat
`--hops 2` as an experiment you are running, not a better setting.

They did **not** test PageRank; they inherited it from Aider and dropped it
without a comparison. So nothing above argues for or against the default — which
is why `benchmark.py` exists.

## The default was measured, and it wins the internal comparison

```bash
python3 scripts/index/benchmark.py --k 10
```

Leave-one-out co-change prediction against git history, with two controls and no
model in the loop. A commit touching {A, B, C} is a statement by someone who knew
the codebase; seed on A and ask whether B and C come back. On Flask at
`d318b683` (800 commits, 300 trials, k=10):

| strategy | recall@10 | vs random |
|---|---|---|
| frequency | **0.3774** | 5.15x |
| pagerank | 0.3417 | 4.66x |
| hops1 | 0.3171 | 4.33x |
| hops2 | 0.3038 | 4.14x |
| random | 0.0733 | — |

Two readings, and the second is the uncomfortable one. **`pagerank > hops1 >
hops2`, in that order** — RepoGraph's finding that more hops is worse reproduces
on a different graph, a different corpus, and a different metric, and the default
beats the thing they never compared it against. And **the graph does not beat
churn**: `frequency` wins while ignoring the seed entirely and costing nothing.
On that repository this index does not earn its build time.

`random` is the floor and `frequency` the bar, because a retrieval number alone
is unfalsifiable — 0.34 is good or bad depending on what else was available.
Full reasoning, including what the ubiquity filter does to the numbers in both
directions, is in `docs/decisions/0001-retrieval-is-measured-not-argued.md` in
this repository.

**Deliberate** — the `repo-explorer` subagent (`${CLAUDE_PLUGIN_ROOT}/agents/repo-explorer.md`).
Given a question, it queries the graph, reads what the graph pointed at,
follows edges the graph got wrong, and returns a conclusion with citations. It
runs on a cheap model and in its own context, so the twenty files it read never
enter the main conversation — only the answer and the paths do.

Delegate to it when the question is *"where does X happen and what would break"*
and not when you already know the file. The rule of thumb: if you would have to
read more than three files to answer, delegate.

## Prove the graph still says what it claims

```bash
python3 scripts/index/selftest.py --verbose
```

The index is the one component here whose defects are *invisible*. A broken gate
turns red. A broken guard fails open and its selftest catches it. A graph that
ranks the wrong file returns a confident, plausible, wrong answer, and nobody
goes and checks — which is why this shipped with three real defects and no
error message between them. Each case plants a structure and asserts a property
of the result, not that it did not crash:

| Case | The defect it was written against |
|---|---|
| symbol names are not merged into one hub | ranking flowed through `sym:main` |
| a reference resolves to a later-scanned definition | one pass, so edges depended on `git ls-files` order |
| `Governs:` is directory-aware | prefix matching, so `src/bill` claimed `src/billing_old/` |
| an unresolvable `Governs:` target is reported | a stale target vanished silently |
| an unmatched seed cannot judge | a silent degrade to the global ranking looks like an answer |
| a bare symbol name still resolves as a seed | path-keying the nodes nearly broke seeding by name |
| the benchmark separates signal from noise | a benchmark whose floor is level with its subject reports artefacts |
| both readers of `Governs:` scan the same window | `build.py` read 60 lines and `after_edit.py` read 40, so a line between them made an edge with no hint |

Two of those cases passed *vacuously* when first written — the fixture used a
trailing slash, and put the definer earlier in sort order, so the broken and
correct implementations agreed. They only became checks after an injection
showed them staying green.

## The negative control

Every index must record what it cannot see. `build.py --report` writes:

- files skipped for lack of a parser, by extension and count
- dynamic dispatch sites found but unresolvable
- imports that did not resolve to a file in the tree

This is the difference between a tool with known limits and a tool that lies.
An agent told "reflection-based registrations are invisible to this graph" goes
and greps; an agent told nothing concludes the code does not exist. Keep the
report in `docs/generated/` where the empty-diff gate applies to it.

## What this replaces, and what it does not

It replaces grep-by-guess and file-tree wandering. It does not replace reading:
the graph's output is a set of paths, and the paths still have to be read. Any
design where the graph's *summary* is consumed instead of the code is a design
that will hand you a confident description of code that changed last month.

Documents remain retrievable but never load-bearing. A rule that must not be
missed is a guard — see `writing-checks`. Retrieval is best-effort by
construction, and building anything critical on it converts a hard guarantee
into a probability.

## References

`build.py`'s own docstring carries the language table and the node/edge schema;
it lands in the repository, so it stays with the code it describes.

Related skills: `writing-docs` (`Governs:` frontmatter),
`bootstrap-repo-harness` (this is tier C only).
