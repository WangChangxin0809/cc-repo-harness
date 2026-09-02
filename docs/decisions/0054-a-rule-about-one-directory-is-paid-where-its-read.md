# 0054 — A rule about one directory is paid where it is read

Date: 2026-09-02
Status: accepted

## Context

This repository's own assessment scored dimension 5.1 at 6.5/10. The finding:
the always-on floor is root `CLAUDE.md` alone, and roughly a quarter of it was
sentences true of exactly one directory — paid on every turn of every session
whether or not that directory was touched. The file's own "Does not cover"
line already said this class of sentence does not belong here. Three
candidates were named:

- hard rule 5's wiring paragraph, including the `session_brief.py` sentence
  (~103 tokens), true only of `.claude/settings.json` and the generated
  `scripts/context/session_brief.py`
- hard rule 1, *anything under `shared/` ships to strangers* (~24 tokens)
- the sentence naming *the other five skills* as payload, restated with more
  detail in `shared/skills/CLAUDE.md`

## Decision

**Rule 5 moves, to `.claude/rules/wiring.md` scoped by `paths:` to the two
files it is about.** It is a fact about our own wiring — not about `shared/`
— so neither nested `CLAUDE.md` under `shared/` is the right audience: both
open with *written for a repository you have never seen*, and rule 5 is the
opposite of that. Root keeps one line saying the rule exists and where it
lives, which is what stops a reader concluding the numbering skipped a step.

**Rule 1 stays, and this is the part worth writing down.** It is the rule
that decides where a new file goes, and that decision is made *before* any
file under `shared/` is opened. A `.claude/rules/` file with `paths:` loads
when Claude reads a matching file — not when it creates one, and not when it
writes through the shell. This repository measures that gap on its own fact
sheet, in dimension 1: *a scoped rule loads when Claude READS a matching file
… Nothing here fills that gap.* Moving rule 1 behind that mechanism would
have paid ~24 tokens a turn to relocate the one rule whose whole job is to be
known in advance.

The skills sentence is trimmed from root, keeping the half about the plugin's
own `skills/` directory; the other half is already in `shared/skills/CLAUDE.md`
in more detail.

## Rejected

**Moving rule 1 to the nested `CLAUDE.md` files.** The content is already
there, so the move looked free. It is not: a nested `CLAUDE.md` loads when a
file under it enters context, which is after the placement decision, not
before. The saving was ~24 tokens a turn against a rule that governs every
new file in the tree.

**Renumbering the rules after a move.** Hard rule 4 is cited by number in
`ARCHITECTURE.md`, `hooks/first_look.py`, and five decision records; rule 2
is "the second hard rule" in 0023. A number that moves makes seven documents
wrong, or makes seven documents need editing every time a rule moves. Rule 5
keeps its number and its position, as a pointer.

**Leaving rule 5 in root as a short stub.** A stub costs nearly what the
sentence costs, and a session not editing the wiring still pays it. The line
that remains is one clause, not a summary of the rule.

## Consequences

The charged floor drops from 70 to 64 lines by `check_context_budget.py`'s
own count. A session that never opens `.claude/settings.json` or the
generated `session_brief.py` no longer pays for a fact it cannot act on; one
that does gets the full paragraph, unchanged, at the moment it matters.

`.claude/rules/wiring.md` is the first rule file scoped to exact paths rather
than to a document type — `for-a-person.md` matches `README.md` and
`guide/**/*.md`. Nothing in the gate or the loader distinguishes the two.

## Evidence status

| Claim | Grade |
|---|---|
| The floor drops from 70 to 64 charged lines | **measured**, `check_context_budget.py --cap 0` before and after |
| Hard rule 4 and "the second hard rule" are cited by number in seven files outside `CLAUDE.md` | **measured**, by grep |
| A scoped rule does not load when a file is created or written through the shell | **measured**, and on this repository's own fact sheet as dimension 1's open row |
