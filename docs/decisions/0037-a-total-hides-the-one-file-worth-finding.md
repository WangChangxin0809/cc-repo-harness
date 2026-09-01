# 0037 — A total hides the one file worth finding

Date: 2026-09-01
Status: accepted
Dimension 5.2: the floor, one file at a time instead of as a sum.

## Context

Dimension 5 counts the tokens that reach the model before anybody has typed
anything. The number is right and it is not actionable. A repository paying
1200 tokens a turn across twenty lean files is in a different position from
one paying 1200 across nineteen lean files and one bloated one, and the sum
is identical.

Nobody can act on a sum. Everybody can act on *this file is four times the
size of every other one of its kind*.

## Decision

The same measurement per unit — per rule, per document, per skill, per
CLAUDE.md — with four things a machine can say about one file.

**Its size against its own kind, not against a threshold.** A good size for a
rule file is whatever the other rule files in that repository are. A number
chosen here would be a number chosen for a repository nobody has seen, and
comparing a skill to a decision record reports every skill as huge and every
decision as small, which is a fact about two genres.

**A floor under that comparison.** Three times nothing is still nothing:
without it, a repository of one-paragraph rules reports the two-paragraph one
as four times the median. True, and not worth a row.

**What its sentences are**, using 0029's prohibition / requirement / statement
split, and **how much of it is fenced** — a document that is mostly code
blocks is mostly examples, which is the part an agent can usually
reconstruct.

**Paragraphs it repeats from another loaded file.** The sharpest of the four
and the only one that is certain rather than suggestive: the same paragraph in
two loaded files is paid for twice on every turn, and one copy will drift.

**Tables are excluded from that last one.** Two files sharing a reference
table are usually sharing it deliberately, and a markdown table flattens into
one enormous pseudo-sentence — the first version of this reported a garbled
table row as duplicated prose. Duplication here is about paragraphs.

## Rejected

**Deciding whether a long file earned its length.** Some have. A file at four
times the median because it is the one place a genuinely intricate constraint
is written down is doing its job. The machine says which files are unlike
their neighbours and in what way; whether that is a fault is a judgement about
content.

**A token budget per file.** The same objection as the size threshold, and
worse: it would make the assessment prescriptive about a repository's
documentation style, which is not this instrument's business.

## Consequences

**Twelve of sixty-one units here are unlike their neighbours**, led by
`README.md` at 3.6 times the median document with 22 prohibitions to 2
requirements. Nine sentences appear in more than one loaded file — three of
them shared between `shared/skills/writing-docs/SKILL.md` and its own
`references/kinds.md`, which is exactly the shape this row exists to find.

**The row is a warning, never bad.** Being unlike your neighbours is a
question, not a verdict.

## Evidence status

| Claim | Grade |
|---|---|
| A repeated table is not a repeated paragraph | **checked** — planted the table exclusion out |
| A file is compared to its own kind | **checked** — planted a single median across kinds |
| A small file is never an outlier for being large | **checked** — planted the floor to zero |
| An untracked file is not loadable context | **checked** — planted the tracking filter out |
| The duplicated paragraphs found here are real | **checked by hand** — three sentences, read in both files |
| Outliers are worth acting on | **argued** — twelve rows on one repository, none yet acted on |
