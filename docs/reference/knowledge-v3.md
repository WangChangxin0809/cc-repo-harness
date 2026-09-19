# Two knowledge stores, two jobs

The implementation preview keeps **experience memory** separate from **reviewed project knowledge**.

## Experience wiki

The experience wiki records successful strategies, failures, candidate skills, rejected proposals, and stale conclusions. It is private working material for improvement and is not injected wholesale into task execution or published to the documentation site.

## Reviewed knowledge

Reviewed knowledge is queryable by agents and publishable after approval. Each page points to an immutable source version, SHA-256 digest, and line range. A source update marks dependent pages stale; it does not silently rewrite the original evidence.

```text
ingest -> immutable source version
  ↓
draft  -> evidence-backed page candidate
  ↓
approve -> human review
  ↓
query   -> approved, non-stale pages only
  ↓
lint    -> stale evidence + structured conflicts
```

Citation validation can prove that a cited range exists in the supplied source; it cannot prove that the source logically entails every natural-language claim. Structured contradiction checks cover explicit keys, not general truth. Human review remains part of the contract.

Publication is whitelist-based: approved pages may be exported, while raw sources, session transcripts, tool outputs, unvalidated candidates, and the experience wiki stay private.

References: [WikiSkill](https://arxiv.org/html/2608.27454v1) and [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).
