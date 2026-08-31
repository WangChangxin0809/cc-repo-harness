# Write the assessment checklist

- **Covers**: the one artefact stage 1 produces — its five sections, its four
  columns, where the file goes, and the two rules that make it reviewable.
- **Does not cover**: how the numbers in it were obtained
  ([assessing](1-assess.md)), or what to do with the rows
  ([deciding](3-decide.md)).

The fact sheet is free to run and writes nothing. **Writing a checklist is what
makes it an assessment**, and an assessment gets a folder:

```
docs/exec-plans/<name>/
├── README.md          state: assessed → decided → in progress → closed
└── assessment.md      the checklist, and the fact sheet it was read from
```

The folder opens **here**, before the decision to change anything — not after.
An assessment that concludes *nothing is worth changing* needs a written home as
much as one that leads to work, and a closed exec-plan folder is exactly that
home: the next person can see the repository was looked at, by whom, when, and
what was found. Without it, "we checked and it was fine" survives as folklore
and gets re-litigated in a quarter.

## Five sections, in this order

The order is not thematic. **It is the order in which ignoring something costs
you**, so that a checklist read from the top is read in the right order even by
someone who stops halfway.

| | Section | Means | Empty means |
|---|---|---|---|
| 1 | **Irreversible** | work can be destroyed | nothing here can lose work |
| 2 | **Silent** | wrong, and produces no symptom | failures here announce themselves |
| 3 | **Late** | caught at CI, or never | defects are caught before the session ends |
| 4 | **Expensive** | paid every turn and not earning it | the standing cost is carrying its weight |
| 5 | **Fine** | present, correct, deliberately left alone | — |

**Nothing below section 1 matters until section 1 is empty.** A repository where
tracked work can be deleted without a prompt does not have a documentation
problem, whatever else the page said.

A section with no rows says `none`. That is a **result** — a finding that this
class of problem was looked for and not found — not a gap to go and fill. A
checklist with five populated sections on a small repository usually means
somebody went looking for work.

Section 5 is the one that gets skipped and the one that keeps the whole thing
honest. In this plugin's corpus, seventeen of twenty repositories have no
`Requirements` section in their README; that is a fact about README conventions,
not seventeen defects. **A harness that cannot say *this is theirs, and it is
fine* will rewrite everything it touches.**

## Four columns, one row per finding

| Finding | Evidence | Proposed change | Basis |
|---|---|---|---|
| Deleting tracked work is not refused | the `rm -rf` probe walked through | a guard on `rm -rf` over tracked paths | measured |
| 612 tokens/turn restate the directory layout | `CLAUDE.md:14-31`, against `docs/index.md` | cut to the routing table, keep the two rules | judged |
| A fix that changed no test happened twice | `a1b2c3d`, `9f8e7d6` | none — two in a year is not a pattern | measured |
| Commit messages follow a house convention | 40 of the last 50 | none — leave it | measured |

### Rule 1 — `Basis` is `measured` or `judged`, and never blank

The two kinds of claim age differently, and mixing them is how a checklist stops
being usable six months later:

- a **measured** row can be re-run. It closes when the number moves.
- a **judged** row cannot. It closes when somebody reads the file again and
  agrees.

[Re-measuring](5-re-measure.md) can only speak to the measured rows. Labelling
them is what lets it.

### Rule 2 — a `judged` row must quote

Not a formality. *"The docs are verbose"* has never once caused a deletion,
because there is nothing in it to agree or disagree with. `CLAUDE.md:14-31`
with a proposed replacement can be argued about — and **losing that argument is
also a result**, one that belongs in section 5.

A judged row you cannot quote is a row you have not finished thinking about.

## What the file holds besides the rows

Paste the fact sheet output above the table, verbatim, and keep the `--json`
beside it. Two reasons, both about the future: the numbers are what
[re-measuring](5-re-measure.md) diffs against, and a checklist without the page it
was read from cannot be audited by anyone who was not there.

```
docs/exec-plans/<name>/
├── README.md
├── assessment.md      the fact sheet, then the checklist
└── baseline.json      factsheet.py --json, kept
```

**Criterion**: five sections present and in order, every section either
populated or saying `none`, at least one row proposing *none*, and every
`judged` row quoting something.

## Why the shape is fixed at all

Because two assessments of the same repository months apart have to be
comparable, and free-form prose is not. The sections and the columns are the
only thing making a later reading say *this row closed* rather than *this feels
better now*.

Nothing enforces the shape today — no gate reads `assessment.md`. That is
[tech debt](../docs/exec-plans/tech-debt-tracker.md) and it is the ordinary kind: a
convention held by prose is followed unevenly, which is the argument this whole
repository is built on, turned on itself.
