# 0054 — A hard rule true of one directory is paid where it's read

Date: 2026-09-02
Status: accepted

## Context

This repository's own assessment scored dimension 5.1 (usage) at 6.5/10. The
finding: the always-on floor is root `CLAUDE.md` alone, about 1140 tokens by
the assessment's count, and roughly a quarter of it was sentences true of
exactly one directory — paid on every turn of every session whether or not
that directory was touched that turn. Three candidates, all inside "Hard
rules":

- rule 1, *anything under `shared/` ships to strangers* — true only when
  editing `shared/` (~24 tokens)
- rule 5's wiring paragraph, including the `session_brief.py` sentence — true
  only of `.claude/settings.json` and `scripts/context/session_brief.py`
  (~103 tokens)
- the sentence naming *the other five [skills]* as payload, in the paragraph
  under the three-identities table — true only of `shared/skills/`

The file's own "Does not cover" line already said this class of sentence
shouldn't be here — "anything true of one directory only (that directory's
own `CLAUDE.md`)" — these three had just never been checked against it.

## Decision

Move each sentence to where a session touching that directory already sees
it, choosing the mechanism per sentence rather than once:

- Rule 1's content was already fully present in `shared/scripts/CLAUDE.md`
  and `shared/skills/CLAUDE.md` — both predate this change and already say
  "written for a repository you have never seen" and "a tool only *we* need
  does not belong here." Rule 1 is deleted from root outright; a one-line
  backlink ("This is hard rule 1, at the point it's actually read") was
  added to both nested files so the pointer in root resolves to something.
- Rule 5 is about *us*, not about `shared/` — it says our own
  `.claude/settings.json` points at `shared/` as source, with one exception.
  Neither nested `shared/` `CLAUDE.md` is the right audience for a fact that
  is entirely about our own wiring, so it moves to a new
  `.claude/rules/wiring.md` with `paths: [".claude/settings.json",
  "scripts/context/session_brief.py"]` — loaded only when one of those two
  files is actually read.
- The skills sentence was already restated, with more detail, in
  `shared/skills/CLAUDE.md`'s first paragraph ("copied into a target
  repository's `.claude/skills/` ... at the tier that earns them (0024)").
  Root's paragraph is trimmed to the half that is actually about the
  plugin's own `skills/` directory (why it holds one skill), which is not
  `shared/`-specific and stays.

## The numbering problem, and why it wasn't solved by renumbering

Hard rule 4 is cited by number in `ARCHITECTURE.md`, `hooks/first_look.py`,
and five decision records (0022, 0024, 0030, 0033, 0040). Rule 2 is cited as
"the second hard rule" in 0023. Deleting rule 1 as a list item and
renumbering the rest would have meant either editing all seven of those —
rewriting decisions that record reasoning as it stood on the day they were
written, to track a label that had since moved — or leaving them wrong.
Both are worse than the sentence they'd fix.

Nothing needed to move. CommonMark or a numbered list takes its start value
from the first item's own number and increments from there regardless of
what's typed on the following lines; a list literally written `2.`, `3.`,
`4.` renders — and reads, in the raw source an agent sees — as 2, 3, 4, with
no item 1 or 5 required. "Hard rules" now opens with a one-line pointer
explaining the gap (*rules 1 and 5 are true of one directory only, so they
load where that directory is actually touched, not here*) and where each
one now lives, then the list starts at `2.`. Every existing "hard rule 4"
and "second hard rule" reference keeps pointing at the same words.

## Rejected

**Renumbering everywhere.** Correct once, and wrong again the next time a
rule moves — decision records would need to track a moving index forever,
which is exactly the kind of coupling this repository avoids elsewhere
(0037, 0043).

**Leaving rule 1 and 5 in root as short stubs.** A stub that says "see
`shared/scripts/CLAUDE.md`" costs almost as many tokens as the sentence it
replaces while a session not touching `shared/` still pays it every turn,
and 0024's own rejected-alternatives section already made this argument
once for skill descriptions.

**Putting rule 5 in a `shared/` `CLAUDE.md`.** Both existing nested files
open with "written for a repository you have never seen" — rule 5 is the
opposite of that, a fact about our own tree that would mislead a reader
copying `shared/scripts/` conventions into a stranger's repository.

## Consequences

Root `CLAUDE.md`'s charged floor drops from 70 to 64 lines by
`check_context_budget.py`'s own count (~913 to ~823 tokens by the same
word-based estimate the gate uses for skill descriptions, applied here for
comparison). A session that never opens `.claude/settings.json`,
`scripts/context/session_brief.py`, `shared/scripts/`, or `shared/skills/`
no longer pays for facts it cannot act on; a session that does open one of
those still gets the full sentence, unchanged, at the moment it matters.

`.claude/rules/wiring.md` is the first `.claude/rules/` file scoped to a
single file rather than a glob of a document type — `for-a-person.md`
matches `README.md` and `guide/**/*.md`; this one matches
`.claude/settings.json` and `scripts/context/session_brief.py` by exact
path. Nothing about `check_context_budget.py` or the native loader
distinguishes the two; a `paths:` list is a list of paths either way.

## Evidence status

| Claim | Grade |
|---|---|
| Root floor drops from 70 to 64 lines | **measured**, `check_context_budget.py --cap 0` before and after |
| Hard rule 4 / "second hard rule" are cited by number outside `CLAUDE.md` | **measured**, `grep -rn "hard rule 4\|second hard rule"` finds seven files |
| A list written `2.`, `3.`, `4.` reads as 2, 3, 4 with no `1.` present | **checked** against the rendered file and CommonMark's ordered-list start-number rule |
| Nothing already in the nested `CLAUDE.md` files needed to be added, only cross-referenced | **checked** by reading both files before writing this decision |
