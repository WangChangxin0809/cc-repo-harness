# D1 · Dispose of `index/`

Delete the precomputed graph, keep what it taught us. This is a deletion with an
argument, and the argument is written here because the component looks
sophisticated and will otherwise be rebuilt by someone who assumes it was
abandoned rather than refuted.

## Consulted

- **Existing skills**: `repo-index`, ours, which teaches the component being
  deleted and is why F7 exists.
- **Prior art**: RepoGraph's implementation, read in full. Its paper is better
  than ours; its code is not — it `exec()`s the target repository's imports to
  resolve symbols, mutilates strings to build node keys, keys nodes by bare
  name, and drops `async def`. This is the single strongest reason to trust code
  over papers, and it is why every `## Consulted` line above says *code*.
- **Research**: the same three papers as B1, pointing the same way: a
  precomputed retrieval index lost to grep-and-read in every comparison.

The decisive evidence is neither — it is our own benchmark, where personalized
PageRank over this graph scored below "the files that changed most recently".

## Why

- **It lost to a trivial baseline.** Our own benchmark had personalized PageRank
  over the graph scoring below "the files that changed most recently". Once that
  is true, the graph is paying build cost, rebuild cost and staleness cost to be
  worse than `git log`.
- **Three papers point the same way.** Agentic pull beat precomputed retrieval
  indexes in every comparison we read. Grep, Glob and Read are already that
  architecture, already present, and cost nothing to keep current.
- **The cost asymmetry is structural, not incidental.** `Governs:` is a line
  someone writes; it needs no build, no rebuild, no staleness detection. The
  graph needed all three, and the third arrived as its own pull request. That
  gap does not close with more engineering — it is what derived relations cost.

## What is kept

Not everything in `index/` is the graph.

- `Governs:` parsing — a declared relation, and the surviving idea. It moves to
  one implementation (D2) rather than being deleted with its host.
- The staleness design's one real finding: a check that runs on PostToolUse can
  never refuse on staleness, because the file just edited is always stale. That
  belongs in the script-kinds guidance (F2) where it applies to every future
  context script, not only to the deleted one.
- The benchmark. A deletion justified by a measurement should leave the
  measurement behind; otherwise the justification is a claim in prose.

## What has to happen before the delete

The component has readers. `repo-index` is a skill that teaches it, `before_write`
calls into it, `scaffold.py` ships it, `ci.sh` runs its selftest, and the
generated report is referenced from documents. Deleting the code and leaving any
of those is worse than leaving all of it — a skill teaching a component that no
longer exists actively misleads.

The `Governs:` consolidation (D2) lands **first**. Deleting one of three
implementations while the other two disagree is how the disagreement becomes
invisible instead of resolved.

## Done when

- [ ] D2 has landed: one `Governs:` implementation, and it is not this one
- [ ] A decision record exists carrying the argument above, including the
      benchmark result
- [ ] Every reader is updated or removed: `repo-index`, `before_write`,
      `scaffold.py`'s COPY table, `ci.sh`, docs routing
- [ ] The PostToolUse-staleness finding has landed in F2's guidance
- [ ] Full suite green with the directory gone

## Notes

*(Decisions land here as the step runs.)*
