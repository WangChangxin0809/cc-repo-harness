# 0027 — Thickness is the denominator, and falsity is the score

Date: 2026-09-01
Status: accepted
Amends 0025. Dimension 4 keeps the two-agent navigation probe as an opt-in
half, and gains a half that costs nothing: **not how much the repository writes
down, but how much of it is still true.**

## Context

0025 replaced Learning Capture with Repository Memory and measured it by
running two agents — one on the tree, one on a copy with the standing context
removed — and reporting the difference. That is the right measurement. It is
also expensive, non-deterministic, and a single reading of a noisy thing: its
first live run produced a difference of zero on a repository both agents
navigated easily, and only the run told us the scoring was wrong.

0025 also rejected counting what a repository keeps, for three reasons that all
still hold:

1. It is resemblance scoring — grading a repository on whether it adopted our
   conventions.
2. It rewards this plugin's own presence.
3. It contradicts dimension 5 on the same change: 0024 cut the standing cost
   from ~888 to ~173 tokens a turn, which a thickness count scores as a loss.

## What changed

A count used as a **denominator** has none of those three properties. It cannot
be raised by adding files, because it is never in the numerator. What it does
is turn *four references do not resolve* into *four of ninety*, which is the
difference between a fact and a fact somebody can act on.

And the numerator is worth having on its own. A `CLAUDE.md` that confidently
describes a directory deleted last spring is **worse than no `CLAUDE.md`**,
because an agent believes it — measured elsewhere: retrieval returning only
stale context put stale references into 15 of 17 outputs, against zero with no
retrieval at all. Thickness cannot see that. It scores the stale file as
memory.

## The decision

Dimension 4 has two halves.

| half | cost | what it asks |
|---|---|---|
| truth | nothing, every run | is what it writes down still true? |
| navigation | two agents, opt-in | can an agent that has never seen it find its way? |

And five tiers, with a line through them:

    T0  a markdown link whose target is absent   PROVEN
    ---------------- above this line a machine is certain ----------------
    T1  a count the tree disagrees with                  CANDIDATE
    T2  a backticked path resolving nowhere              CANDIDATE
    T3  a document the code moved out from under         CANDIDATE
    T4  two documents giving one token two values        CANDIDATE

## Where the line sits was decided by being wrong three times

This is the part worth keeping. Every one of these looked correct in design and
failed on contact with one repository.

**Backticked paths began above the line.** 23 rows here, nearly all false:
`scaffold.py` lives one directory down, `permissions.deny` is a JSON key, `.py`
is an extension, `WangChangxin0809/agent-harness` is a GitHub slug.

**Counts began above the line, and failed more instructively.** The arithmetic
was never wrong; the *binding* was. "two agents" meant two agent runs and was
checked against the three files in `agents/`. "six skills" meant
`shared/skills/` while the tree also has a `skills/`. "three gates" was a skill
describing what it creates in *your* repository, where the number is a promise
rather than a description. No tightening fixes that, because the failures are
semantic.

**Markdown links survived — and then reported three broken links that were all
inside fenced examples or `<placeholder>` spans.** A link inside ``` is being
shown, not followed. Stripping fences and placeholders took the proven tier to
zero false positives on this repository.

The published number for not filtering at all is a **98% flag rate**: an LLM
asked directly whether code and its documentation agree flags 98% of functions
as inconsistent, which is not a finding, it is a rate of nothing. Filtering
first takes that to a 14% flag rate at 0.63 precision. **The filter is the
product**, and a filter that promotes its own guesses to findings has stopped
being one.

## Two bugs the cases caught, not the author

**`_resolvable` returned None the moment its *second* resolution candidate
escaped the tree**, so `../docs/x.md` written from `docs/` was unverifiable —
the whole of tier 0 switched off by one early return, in a module whose tier 0
was the only thing above the line.

**The candidate cap was applied to the tiers concatenated in order.** T1 and T2
filled all 24 slots, so T3 and T4 — staleness and contradiction, the two tiers
the module was asked for — were computed, ranked, and silently discarded.
Nothing failed. The page was simply missing two tiers. The budget is shared
round-robin now: a budget one tier can eat is not a budget.

## Staleness needs two factors, not one

Ranking by a document's own age produced noise: on an active repository the top
of the list was a file edited that morning, because everything was. Age alone
measures how busy the repository is.

    (commits to what the document points at, since it last moved)
      x  (days the document has sat still)

And *what it points at*, not the directory it sits in — a root document's
directory is the whole repository, which put `CODE_OF_CONDUCT.md` at the top of
the list. A document that references nothing that exists has no subject here,
and no score.

## Consequences

**Dimension 4 stops abstaining wholesale.** Its cheap half runs every time, so
a page that was previously all abstention now reports on every document in the
tree.

**The navigation half is unchanged and still opt-in**, still two agents, still
the only non-deterministic dimension. 0025's argument for it stands; what
changed is that it is no longer the only thing dimension 4 has.

**Candidates are capped at 24 and go to an agent.** That is the same shape as
the mutation second pass in 0028 — machines narrow, agents judge — and the two
should stay the same shape.

## Evidence status

| Claim | Grade |
|---|---|
| A denominator cannot be gamed by adding files | **checked** by a case that adds six empty documents and asserts the findings do not move |
| Backticked paths are unusable as a proven tier | **measured** — 23 rows on this repository, of which the ones inspected were all false |
| Counts are unusable as a proven tier | **measured** — every hit on this repository was a semantic mis-binding |
| Fenced links are illustrations | **measured** — three of three proven findings were inside fences or placeholders; stripping them gave zero |
| Tier 0 still fires | **checked** — a planted broken link is reported, and a real broken link outside a fence is not swallowed by the stripping |
| The contradiction tier can fire | **checked** by a planted disagreement; it finds none on this repository, which is a reading and not a proof of correctness |
| Staleness ranks something worth reading | **argued** — the ranking is defensible and no one has yet acted on a T3 candidate and reported back |
