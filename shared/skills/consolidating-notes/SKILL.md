---
name: consolidating-notes
description: Fold a pile of agent notes, memories or scratch files back into the repository: freeze the input, synthesize separately, diff, and route each surviving entry to a doc, a guard, a subtree CLAUDE.md, or the little that is truly personal. Use when notes contradict each other or name things that no longer exist, or when asked to clean up or compact memory.
---

# Consolidation

Governs: scripts/consolidate.py

Notes accumulate faster than they are corrected. After a few months a pile
contains contradictions, entries about flags that were removed, and — buried in
it — the measurements that are the only reason any of it is worth keeping.

The mechanism that fixes this is a synthesis pass over a frozen input, producing
a separate output you compare before adopting. Claude's Dreams API implements
exactly this shape and never mutates its input; the same shape works by hand,
and is what the scripts here do.

## The invariant

**Write the synthesis to a new file and leave the input untouched.** Adoption is
then a decision you make after reading a diff of the two. In-place editing
destroys the evidence needed to tell a good merge from a lossy one, and lossy
merges are the normal failure — they read beautifully.

```bash
python3 scripts/consolidate.py prepare --notes .agent-notes --sessions .agent-sessions
# snapshot is chmod'd read-only; the synthesis writes to .consolidation/candidate/ only
python3 scripts/consolidate.py diff
```

`diff` reports three things, in the order they matter:

1. **What is gone.** Every measurement, commit hash, and path present in the
   input and absent from the candidate, quoted. This is the check the whole
   invariant exists to enable, and it is mechanical — the tool finds these, a
   careful reading of the candidate does not.
2. **What has no destination.** Entries that survived without a `ROUTE:` line.
   A consolidation whose output is a tidier pile of notes has moved nothing.
3. **Unchanged / rewritten / dropped / new**, by name.

Read 1 and 2. Skim 3.

## What must survive verbatim

Two things, and they are the two most likely to be smoothed away because they
read as noise:

**Measurements and identifiers.** `87ms`, `3.6s`, `9de1104`, a file path, a
version. Paraphrasing a number destroys it — "noticeably slower" cannot be
compared against a later reading, and a rounded commit hash cannot be checked
out. Every reading carries the commit it was taken on, or it expires silently.

**The belief that turned out to be wrong, and why it was held.** A note saying
"X is true" is worth less than one saying "we believed X because of Y; it is
false, here is the measurement". The second one stops the idea coming back. A
synthesis that keeps only current conclusions loses precisely the part that
prevents repetition.

Both of these read as clutter to a summarizer. Say so explicitly in the
instructions you give it.

## Route every survivor

Consolidation that produces a cleaner note pile has moved nothing. Each entry
gets a destination, and most destinations are not notes:

| The entry is… | Goes to |
|---|---|
| A fact about this repo | `docs/reference/` or `docs/troubleshooting/` |
| A rule an action can violate | A guard — see `writing-checks` |
| True only inside one directory | That directory's `CLAUDE.md` |
| A road tried and abandoned | `docs/decisions/`, as a record |
| Debt found in passing | `docs/exec-plans/tech-debt-tracker.md` |
| About *this user*, not this repo | Stays a note — and this is a short list |

Repo-scoped knowledge left in private notes is invisible to review and dies with
the machine. The routing step is the point of the whole exercise; the tidier
pile is a side effect.

Mark superseded entries by tense rather than deleting them: *"we used to believe
… this stopped being true at `4f2a91c`"*. A deleted mistake gets rediscovered.

## Consolidating docs and code

The same pass, run against different piles, catches different rot. Run it
periodically — the natural trigger is after a large merge:

- **Docs**: files no document routes to, `how-to/` steps whose commands no
  longer exist, generated files whose source is gone, plans in
  `exec-plans/` whose work shipped.
- **Code**: symbols with no inbound edges in the graph (`repo-index` computes
  this directly), dead feature flags, `.bak` files, scripts nothing calls.

Both produce a *report*, not a deletion. The output goes into
`docs/exec-plans/tech-debt-tracker.md` with the reading that revealed it and the
blast radius, and gets scheduled. An automatic pass that deletes will eventually
delete the one thing that had a caller the graph could not see — and the failure
mode of a report is a stale line in a tracker.

A dead link has two causes that look identical: the file was deleted, or the
worktree it lived in was removed. One command separates them:

```bash
git cat-file -e HEAD:<path>   # exit 0 → restore the file; non-zero → fix the link
```

## Writing the instructions

Whatever performs the synthesis — the Dreams API, a subagent, you — gets a brief
that is thematic, not procedural. Line-level imperatives ("do not delete item
7") do nothing to a synthesis pass; statements about what the corpus *is* and
what matters in it steer it.

State: what this pile is, that measurements and commit hashes are load-bearing
and must be copied exactly, that superseded beliefs are kept with their reason,
and that entries about the repository are destined for the repository. Then read
the diff anyway.

## References

| File | Read when |
|---|---|
| `references/dreams.md` | A ready synthesis brief, and the managed Dreams API |

Related skills: `writing-docs` (the destinations), `writing-checks` (entries
that become guards), `repo-index` (inbound-edge counts for the code pass).
