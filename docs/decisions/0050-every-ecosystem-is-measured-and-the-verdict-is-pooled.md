# 0050 — Every ecosystem is measured, and the verdict is pooled

Date: 2026-09-02
Status: accepted

## Context

`ecosystems.find` returned one (ecosystem, command): the first that
detected at the root, else the first found one or two directories down. A
repository with Python at the root and Go under `cli/`, or Node under
`web/` and Go under `cli/`, was measured as if it had one suite.

Three rows read wrong because of it, and all three read wrong in the same
direction. The replay ran the one suite, so a defect whose regression test
lived in the other read as `never` -- a sentence about the instrument,
printed as a sentence about the repository. Coverage reported one tool's
figure as the repository's. And nothing on the page said a second suite
existed, so a reader had no way to know which of the two it was looking at.

The selftest that pinned it builds two rooted Python suites, puts the fix
and its test under `b/`, and watched the ladder put the defect on `never`
while `a/` stayed green.

## Decision

**Every suite is found.** `find_all` returns each language ecosystem that
detects at the root, then the first found in each directory one and two
levels down, a directory inside one already taken skipped, a documented
command read at the root only. `find` is its first entry, so callers that
can run one command keep working -> 0029.

**An aggregate at the root claims the tree, when there is something to
aggregate.** A root `Makefile` with a `test:` target, or a command the
repository documents for itself, is the recipe that drives everything. With
more than one language suite, or none, it is returned alone. With exactly
one, the language runner stays the answer, as it always was: `pytest` can
name a single test and `make` cannot, and there is nothing to aggregate.

**The verdict is pooled: red if any suite is red; could not run only if no
suite ran; green otherwise.** Every runnable suite runs at each rung.
Scoping stays per suite -- a suite whose subtree holds one of the tests the
fix touched is narrowed to them -- and a suite whose subtree holds none of
them runs whole rather than being skipped, because the source the fix
reverted may break an existing test in the other suite, and seeing that is
the reason to run more than one. A suite that is not green at the fix is
left out of that instance and says so; the instance is unusable only when
none is left.

**A suite whose tool is not on this machine is found and not run.** Its
command stays None, the page carries it as `suites found but not run`, and
the row is an abstention: an absence on the machine, not in the repository
-> 0047. It never turns the pool red.

**Coverage is each suite's own tool, summed per criterion.** Each runner is
handed its suite's directory and its suite's command, and the totals are
added over the suites whose tool produces the criterion -- Go has no branch
coverage, so a pooled branch row beside a Go suite is Python's alone and
the note says so -> 0031, 0033. `how` names every tool that ran and what
share of the suites the figure holds. `--test-command` and
`--coverage-command` are one suite each, as before.

## Consequences

Dimension 2 gains a row naming how many suites the ladder pooled and which,
and one more when a suite was found and could not run. The replay costs one
extra suite run per rung per additional suite, bounded by the number of
suites and not by the size of the history.

Mutation still runs one suite, the first `find` returns. A mutant in the
second suite's source is judged by the first suite, which is the limit
this decision leaves standing; the row already says which command it ran
against -> 0030.

Two Python suites at the root and under `pkg/` are two suites. If the root
one already drives the other, the page counts one suite twice, and a root
`Makefile` is the way a repository says so.
