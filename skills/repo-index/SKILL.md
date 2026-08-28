---
name: repo-index
description: Give a repository a code-and-docs graph an agent can query — tree-sitter symbols, import and call edges, doc-to-code edges, ranked by personalized PageRank from whatever the current task touches. Use this when an agent cannot find the relevant code in a large repo, when grep returns hundreds of hits or none, when someone asks for RAG / semantic search / a code index / an embedding store for their codebase, when onboarding to unfamiliar code, and when you need to know what a change would break.
---

# One graph, two tiers

Retrieval fails in repositories for a specific reason: the useful unit is not a
paragraph, it is a symbol and its neighbourhood. A chunk-and-embed pipeline
returns files that talk *about* authentication; what the task needs is the four
functions that would break.

So: **one graph, built from source, queried two ways.** Not a stack of
retrievers — an extra retriever whose results have to be merged is a second
ranking problem on top of the one you had.

## The graph

Nodes are files, symbols (`def`/`class`/`type`), and documents. Edges:

| Edge | From | Weight |
|---|---|---|
| defines | file → symbol | tree-sitter tags |
| references | file → symbol | tree-sitter tags |
| imports | file → file | resolved import statements |
| calls | symbol → symbol | call sites inside a definition's span |
| governs | doc → path | `Governs: src/billing/**` in doc frontmatter |
| supersedes | doc → doc | `Supersedes: 0004` |

`Governs:` is the edge that makes documents reachable from code. Without it,
docs and code are two disconnected components and no amount of ranking bridges
them.

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

**Deliberate** — the `repo-explorer` subagent (`<plugin>/agents/repo-explorer.md`).
Given a question, it queries the graph, reads what the graph pointed at,
follows edges the graph got wrong, and returns a conclusion with citations. It
runs on a cheap model and in its own context, so the twenty files it read never
enter the main conversation — only the answer and the paths do.

Delegate to it when the question is *"where does X happen and what would break"*
and not when you already know the file. The rule of thumb: if you would have to
read more than three files to answer, delegate.

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
