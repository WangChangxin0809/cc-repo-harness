# The synthesis brief, and the Dreams API

## A brief you can adapt

Whatever performs the synthesis — the Dreams API, a subagent, you — gets this.
It is thematic on purpose. Line-level imperatives ("do not delete item 7") do
nothing to a synthesis pass; statements about what the corpus *is* and what
matters in it are what steer one.

> This is a working notebook accumulated by an agent over months of building one
> software project. It was written incrementally, never revised, and it
> contradicts itself in places. Produce a merged version.
>
> What makes these notes worth anything is the measurements. Timings, token
> counts, file counts, commit hashes, exact file paths, version numbers — these
> are load-bearing and must be reproduced character for character. Paraphrasing
> a number destroys it: "noticeably slower" cannot be compared against a later
> reading, and a rounded commit hash cannot be checked out. A measurement whose
> commit is recorded stays checkable; one without it has already expired.
>
> Entries recording a belief that turned out to be wrong are among the most
> valuable, not the least. Keep the belief, keep why it was held, and keep the
> evidence that overturned it. "We used to think X because of Y; that stopped
> being true at 4f2a91c" prevents a repetition that "X is false" does not. Mark
> these by tense rather than deleting them.
>
> Where two entries conflict, prefer the later one, but say that the earlier one
> existed and what changed. Where two entries say the same thing in different
> words, merge them and keep the more specific phrasing.
>
> Most of this describes the repository rather than the person working in it.
> That material is destined for the repository's own documentation, so keep each
> entry's concrete detail intact — a generalized version cannot be turned into a
> document, a guard, or a directory-scoped rule.

Then read the diff anyway. The brief improves the odds; it does not remove the
need to look at what was dropped.

## The mechanics, by hand

```bash
python3 scripts/consolidate.py prepare --notes .agent-notes --sessions .agent-sessions
# the synthesis reads .consolidation/BRIEF.md and writes ONLY to .consolidation/candidate/
python3 scripts/consolidate.py diff
```

`prepare` copies and then chmods the snapshot read-only. That is not paranoia
about permissions: it is what makes the invariant in `SKILL.md` a property of
the filesystem rather than of everyone's discipline, and the reason it is worth
that is stated there.

`diff` leads with what is **gone**: every measurement, commit hash, and path
that appears in the snapshot and not in the candidate, quoted in full. That
comparison is by content, not by filename — consolidation *merges*, so an entry
that moved from `cache.md` into `perf.md` reads as moved, and a number
deleted during that move must not read as a move.

It then lists entries that survived with no `ROUTE:` line, and only then the
per-file unchanged / rewritten / dropped / new breakdown.

## The managed Dreams API

Claude's Dreams API is a research preview implementing the same shape natively.
Worth using when the pile is large enough that a hand pass will not be run.

- **Both** beta headers: `managed-agents-2026-04-01,dreaming-2026-04-21`. The
  managed-agents header on its own does not grant access to dreams.
- Inputs: exactly one memory store, plus 1–100 sessions. A `model` is required.
- Output: a **new, independent** store. The input is never modified — the
  invariant is enforced by the API rather than by you remembering it.
- `instructions` steers the synthesis, ≤4096 characters. The brief above fits.
- Asynchronous: `pending → running → completed | failed | canceled`, polled by
  id, minutes to hours. While `running`, the dream's `session_id` points at the
  session executing the pipeline, so you can stream its events and watch what it
  reads and writes.

The sessions are not a secondary input. The store is what gets deduplicated; the
transcripts are where a pattern nobody wrote down is still visible. `consolidate.py`
takes `--sessions` for the same reason, and the brief tells the synthesis to
read them.

Because the output is a separate store, adoption is still a decision: diff it
against the input, read what was dropped, and only then point anything at it.

## Routing, which is the actual point

A consolidation that produces a cleaner note pile has moved nothing. Every
surviving entry gets a destination, and most destinations are not notes — see
the table in the skill body. `consolidate.py` supports `ROUTE:` lines in a candidate
entry for exactly this:

```
ROUTE: docs/troubleshooting/verifier-cache.md
ROUTE: guard
ROUTE: src/billing/CLAUDE.md
ROUTE: memory
```

`memory` should be the shortest list. Repo-scoped knowledge left in a private
note pile is invisible to review, cannot be corrected by a teammate, and dies
with the machine.
