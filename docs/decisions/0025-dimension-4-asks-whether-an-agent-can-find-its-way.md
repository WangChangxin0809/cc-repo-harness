# 0025 — Dimension 4 asks whether an agent can find its way

Date: 2026-08-31
Status: accepted
Replaces Learning Capture with **Repository Memory**, and changes how it is
measured: from reading what the repository keeps, to watching an agent that has
never seen it try to work in it.

## Context

Dimension 4 asked *has a mistake made here ever turned into something that acts
next time?* and answered it by reading git history for repairs, checks that
arrived after repairs, and files where mistakes are written down.

It found real things. On a subject repository it surfaced a script written after
a live outage — with the outage described in its own header — that was in no
test suite, no CI, and no README. That is a genuine finding and the dimension
earned its place producing it.

But two problems had built up.

**The chain it was really following is not about learning.** *A check exists,
and nothing runs it* is a delivery failure, and dimension 3 already reports two
of its shapes (`checks only one machine can run`, `CI runs the suite`). Keeping
a third shape in dimension 4 split one question across two places.

**What remained was going to be measured by thickness.** The natural next step —
count the skills, hooks and rules a repository keeps — fails three ways:

1. It is resemblance scoring, which this project has a rule against: it grades a
   repository on whether it adopted our conventions, and a repository with a
   good README and no `.claude/` would score zero while losing nothing.
2. It scores *installing this plugin* as an improvement to the repository being
   measured. The instrument would reward its own presence.
3. It contradicts dimension 5 on the same change. Moving five skills out of the
   plugin cut the standing cost from ~888 to ~173 tokens a turn (0024).
   Dimension 5 calls that an improvement; a thickness count calls it a
   regression. Two dimensions giving opposite verdicts on one change is not a
   trade-off, it is a broken scale.

0001 already refused this move once, for the retrieval layer. It could have
scored the index on existing. Instead it measured recall against two controls —
a random floor and a churn baseline that ignores the seed entirely — and
concluded the index **does not beat churn** and does not earn its cost. A number
without a control cannot reach that conclusion, and a thickness count has no
control available to it.

## This is what 0020 already said dimension 4 would be

0020 settled that the assessment measures behaviour rather than resemblance, and
in its consequences it wrote:

> Only dimension 4 genuinely requires running one, and there the agent is the
> **subject**, not the judge — how many files it reads before its first edit is
> behavioural data, and it can be repeated and compared across models. An
> agent's score out of ten cannot.

Its evidence table then graded that row *"true of what is built; dimension 4 is
not built"*. What shipped instead was a history reading, because it was cheap
and available. This decision builds the thing 0020 described, and the tool-call
count per question is exactly the "how many files it reads" it was pointing at.

## Decision

Dimension 4 becomes **Repository Memory**, and its question is:

> Can an agent that has never seen this repository find its way, and is that
> because of something the repository keeps?

Two halves, and the second is what makes it *memory* rather than *legibility*.

### The probe

One agent, one session, nine questions, on a copy of the repository with no
history. Six are macro — components, flows, source of truth, what is generated,
where the tests are, what constraints are specific to this place. Three are
micro: given **only the subject line** of a real commit, name the files you
would change.

**The copy is the tree as it is, not the tree at each commit's parent.** Three
commits have three different parents, and one session cannot be asked nine
questions about three different trees. Checking out one parent would also mean
grading an answer against files that do not exist in the tree the probe is
reading. So the task is *localisation, not reproduction*: the bug is already
fixed, and the question is whether you can find the code it lives in. Only
commits whose files still exist become questions — a question whose answer was
deleted has no right answer.

### The measurement is the difference between two runs

The same nine questions are asked twice:

| run | the copy contains |
|---|---|
| **with** | the repository as it is |
| **without** | the same tree, minus `CLAUDE.md` (including every nested one), `.claude/`, `AGENTS.md`, `.cursorrules`, and `.github/copilot-instructions.md` |

**The difference is the memory.** This is the whole point of the design. A thin
`CLAUDE.md` that halves the search is worth more than six skills that change
nothing, and adding files can no longer raise the score — it raises dimension
5's bill while leaving this difference untouched.

## Why the probe cannot cheat, by construction

The probe runs on a temporary copy checked out at the parent commit **with the
`.git` directory deleted**, and the probe agent is given `Read, Grep, Glob` and
**no Bash**.

A rule saying *do not look at the history* is a rule an agent can break, and
nobody would know: `git log --grep` finds the answer to every micro question in
one call, and the run would look like a brilliant result. So the history is not
forbidden, it is **absent**. Removing Bash removes the second route in as well,
and the probe has no legitimate use for it — it is reading, not running.

## The budget: two agents

Cost is a design constraint, not an afterthought. The obvious shape — one agent
per question class, doubled for the with/without comparison — is ten agents per
assessment, which puts the dimension out of reach for the thing it is for
(measuring the same repository again after a change).

One agent answers all nine questions in one session. Later questions benefit from
what earlier ones taught it about the repository; that is not contamination,
it is what a real session looks like, and it makes "how many tool calls did this
take" a cumulative figure worth comparing.

| | agents |
|---|---|
| with the repository's own context, 9 questions | 1 |
| without it, the same 9 questions | 1 |
| judging the answers that need judging | 0 — see below |
| **per assessment** | **2** |

The default tier spawns **none**. This dimension abstains unless asked for,
exactly as the `--full` replay does, and the page still renders in seconds.

## Three of the questions grade themselves, and the rest are judged for free

| question | answer key |
|---|---|
| where are the tests, and what runs them | `_test_homes` and `_ci_verdict`, already computed for dimension 3 |
| what is generated rather than written | `.gitignore` plus generated-file markers |
| which files would you change for *this* commit | the commit's own diff |
| components, flows, source of truth, constraints | judged by the assessing agent |

The last row costs nothing extra: an agent is already running the assessment and
already reading the page. It judges what a regex cannot, which is the division
of labour this whole assessment is built on.

The micro questions are chosen from commits touching at most `FOCUSED` source
files. Above that, *did you find the right files* has no meaning — the same
attribution rule dimensions 2 and 3 already use, and the one dimension 4 was
missing when it counted busy files as reworked ones.

## No rates

Three micro questions do not support a percentage. Reporting `66%` from a sample
of three is a number invented to look like a measurement.

The rows say what happened:

```
fix: 岗位树渲染为空
    with context      2 of 2 files, 11 tool calls
    without context   0 of 2 files, 23 tool calls
```

That can be argued with. `66%` cannot.

## What the first live run found, and what it changed

Run against this repository, two probes, nine questions each:

| | files found | tool calls |
|---|---|---|
| with `CLAUDE.md` and `.claude/` | 3 of 5 | 15 |
| without them | 3 of 5 | 13 |

**A difference of zero, on a repository an agent navigated easily.** Both probes
said the same thing in their notes: what carried them was `docs/decisions/` —
read, not loaded. One of them added that `0023` names the exact file the revert
removed, how it was wired, and how it was tested.

The first implementation called that **bad**, and it was wrong. It conflated two
questions that have to stay apart:

1. *Can an agent find its way here at all?* — from the `with` run, absolute.
2. *Is that because of what is loaded on every turn?* — the difference.

A repository that answers **yes** to the first and **no** to the second is not
failing. It is keeping its memory somewhere an agent has to open, which works,
and the finding is for dimension 5: *the loaded part is being paid for and is
not what is doing the work*. The failure is when both answers are no.

So the dimension reports two rows, and only *both low* is bad. The design
survived its first contact with reality; the scoring did not, and the run is the
only reason we know.

## Consequences

**Dimension 4 becomes the only non-deterministic dimension.** Two runs on one
repository give different numbers, and the project's main use is before-and-after
comparison. Mitigations: the commits are chosen by a fixed rule (the most recent
focused ones), the question set is fixed, and results are reported as rows with
their tool-call counts rather than as a score to be tracked over time.

**It becomes the most expensive dimension**, from a dimension that cost nothing
but reading `git log`. It is opt-in for that reason.

**The failure→control→active chain does not disappear.** Its findings move to
dimension 3, where *a check nobody runs* already lives. Nothing that was found
before stops being found.

**A repository with no standing context scores zero difference, correctly.** Not
because it lacks a `CLAUDE.md`, but because there is nothing to remove in the
second run — the two runs are the same run. The page should say that plainly
rather than reporting a difference of zero as a failure.

## Rejected

**Counting skills, hooks and rules.** The three reasons above. The shortest form
of the objection: it is a number that cannot come out low for a repository that
has adopted our conventions and cannot come out high for one that has not,
whatever either repository is actually like to work in.

**A learning rate `R / M`.** The denominator is whatever the miner happened to
find, so a repository with a tidy history yields a larger `M` and scores worse
for being better documented. And a rate does not name a specific observable
failure, which is this project's admission test for a dimension.

**Asking the agent to rate its own understanding.** Models are badly calibrated
about their own comprehension and will nearly always say yes. If it is kept at
all it should be a *prediction made before* the micro questions, with the gap
between predicted and actual reported — an over-confident reading is itself a
finding, because it means an agent will not ask for help before it is lost.

**Giving the probe the commit diff.** It leaks the answer: the diff names the
files the question is asking it to find. Only the subject line goes in.

**SZZ-style bug-inducing-commit mining.** A serious technique, and the right one
if the question were still *what did this repository learn*. Its false positives
have the same root as the bug dimension 4 just had — a repair touching thirty
files blames thirty lines of history, twenty-nine of them noise — and its agentic
variants cost an agent call per candidate, which is the budget this decision
exists to protect.

## Evidence status

| Claim | Grade |
|---|---|
| The old dimension found a real control that nothing ran | **checked** — reported against a subject repository, verified in its `pytest.ini`, its CI (absent) and its README |
| Thickness contradicts dimension 5 | **checked** — 0024 measured ~888 → ~173 tokens/turn for a change a thickness count scores as a loss |
| A number needs a control to reach a negative conclusion | **checked** — 0001 reached exactly that conclusion, and only because it had two |
| Deleting `.git` removes the cheat | **checked** by a selftest case, and confirmed live — see the row below |
| Two agents is enough to separate memory from legibility | **measured once**: two probes on this repository, 3/5 both ways, 15 vs 13 tool calls. That is a real reading and it is a sample of one; whether a difference of zero is a finding or noise needs a second repository |
| The probe cannot reach the history | **measured**: both live probes had Bash and both reported *"no git history at all... I did NOT read any commit log that gave away the micro answers"* |
