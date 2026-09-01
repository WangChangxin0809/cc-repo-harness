# 0031 — Coverage is the denominator, and its inference runs one way

Date: 2026-09-01
Status: accepted
Dimension 2 could say when a defect was caught. It could not say which parts
of the repository it had not looked at, and silence that is not stated reads
as a pass.

## Context

Both of dimension 2's injections are blind in the same place, for different
reasons:

- **The replay** only reaches lines this repository's own history put a bug
  in. Code that has never had a recorded fix is never exercised by it.
- **Mutation** only touches lines the suite already executes. That restriction
  is deliberate — a mutant on an uncovered line survives by construction and
  measures nothing — but it means the mutation figures are silent about
  exactly the code that is least tested.

So a repository could read well on both and have half its tree untouched by
either. The page said nothing about that half.

**The objection to adding coverage, and why it fails.** Coverage is a famously
weak predictor: Zhao, Zhou & Cohen (2026), replicating Inozemtseva & Holmes
and Papadakis on LLM-generated suites over Defects4J, put its correlation with
real-bug detection at r ≤ 0.481 in the pooled view — and every strong figure
they report is *between* generators, n=13, not between individual suites. One
repository's one suite is the weak regime.

That objection is about the **positive** direction: high coverage does not
show a suite is good. The inference in the other direction is not a
correlation at all:

> A line no test executes cannot be caught at the `local-suite` rung. Ever.
> For any defect.

That is a guarantee about the ladder, derived from what the ladder is. It is
the reason coverage belongs here, and it decides everything about how it is
reported.

## Decision

**Coverage is reported as what the measurement cannot see, and printed
*before* the ladder rather than after it.** It is the ladder's denominator. A
reader who sees `local-suite: 14` should already know how much of the tree
that rung is able to speak about.

**Three criteria, and each one's absence is a different finding with a
different fix.**

| | absence proves | what fixes it |
|---|---|---|
| statement | no test executes this line | a test that gets there at all |
| branch | this decision only ever went one way | a test that gets there with the other answer |
| MC/DC | this condition never decided the outcome on its own | a test that varies *this* condition while holding the others |

**Never reached and reached-but-one-way are reported separately.** They are
two findings with two different fixes, and a single branch percentage hides
both.

**MC/DC is measured by rewriting the AST, because nothing else can.**
`sys.settrace` gives line events and says nothing about the value of an
individual condition. Every decision's boolean tree is walked to its atomic
leaves, each leaf wrapped in a recorder that returns its argument untouched.
Short-circuiting is preserved exactly — a wrapped operand is still only
evaluated when Python reaches it.

**A condition that short-circuited away is recorded as absent, never as
false.** This is the single detail the whole measurement rests on. Write
`False` for the operand that never ran and two observations differ in two
places instead of one, no independence pair is found, and a condition that was
tested perfectly well is reported as untested. The failure is silent and it is
worst exactly where short-circuiting is most common.

**Masking MC/DC, not unique-cause, and the page says which.** Unique-cause
MC/DC is usually unreachable in a language with `and`/`or`; conditions
short-circuited away in one of a pair are treated as masked rather than as
disagreements. Reporting the number without the variant would be claiming a
stricter result than was measured.

**`assert` is not a decision.** An assertion that has gone both ways is a test
run that failed, so in any repository whose suite is green every assertion is
one-way by construction. Counting them would report every correct assertion as
an uncovered branch — a denominator made entirely of noise, and one that gets
worse the more carefully a repository asserts.

**The instrument puts the tree back, including its bytecode.** Sources are
restored, the recorder module is deleted, and the `.pyc` files compiled from
the instrumented sources are removed along with any `__pycache__` directory we
created. A `__pycache__` that was already there is the subject's and stays.

## Rejected

**Path coverage.** Exponential in the number of decisions, so the denominator
is meaningless. No standard asks for it either.

**Reporting coverage as a score, or comparing it between repositories.** That
is the direction the replicability study measured and found weak. The rows
give counts and name files; the percentage is there to be read against the
command that produced it, not against another repository.

**Instrumenting for statement coverage too.** The existing path — the
subject's own `coverage` if it has one, `tracer.py` otherwise — measures the
*untouched* tree. The instrumented copy has different line numbers, and a
statement figure taken off it would be about a program that does not exist.

**Silently proceeding when instrumentation changes the result.** If the suite
was green before and is not green after, the branch and MC/DC figures are
about a different program. That is a flagged row above the figures, not a
footnote under them.

## Consequences

**MC/DC finds mutation's holes without running the suite once per mutant.**
Observed on this repository, guards suite as the command: `dispatch.py:91` and
`no_protected_branch_push.py:86` appear both in the one-way decision list and
in the surviving-mutant list. That is expected — a condition that never varies
is exactly a condition you could delete without a test noticing — and it means
the cheap criterion predicts where the expensive one will find something.

**One suite against a whole tree reads as a very low number.** The same run
reports 1.2% statement coverage, because the command given runs one of this
repository's seven suites and the denominator is every source file. The number
is correct and the row names the command, but a caller who wants a figure
about the repository has to give a command that runs all of it.

**Dimension 2's default run costs one more suite execution.** Coverage runs
with the replay, not behind its own flag: it is two runs of the suite against
the replay's three, and it is what makes the replay's result readable.

## Evidence status

| Claim | Grade |
|---|---|
| A short-circuited condition is recorded absent, not false | **checked** — planted the false-fill and watched `a` stop being independent |
| MC/DC finds a condition branch coverage calls covered | **checked** — planted MC/DC as branch coverage |
| Never-reached is not reported as one-way | **checked** — planted the merge |
| An assertion is not a decision | **checked** — planted `ast.Assert` back into the decision walk |
| The instrument leaves the tree as it found it | **checked** — planted the sweep out, and separately the restore out |
| Absence of coverage proves a ladder rung cannot fire | **argued from construction** — it is what the rung is, not a measurement |
| Coverage predicts effectiveness | **not claimed** — the study says it does not, in the direction people read it |
