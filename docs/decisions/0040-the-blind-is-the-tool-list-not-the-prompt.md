# 0040 — The blind is the tool list, not the prompt

Date: 2026-09-01
Status: accepted
Extends [0036](0036-a-contradiction-is-decided-by-an-experiment-not-a-comparison.md),
which decided the method and left it with nothing to run it.

## Context

0036 built `promises.py`: it narrows a repository's prose to the sentences that
name something executable, writes two briefs, and grades two sets of answers.
It deliberately spawns nothing — hard rule 4 — and so nothing ever ran it. The
factsheet computed `promises_brief` every time and had no flag to hand an
answer back, which meant the row could not print by any route a person could
take. The method was implemented and unreachable.

The missing half is an agent, and the question is what stops that agent from
reading the implementation. Everything CASCADE measures depends on the tests
having been written by something that had not seen the code: a test written
afterwards agrees with the code by construction, and the crossing then reports
`p2p` on everything and finds nothing, forever, silently.

## Decision

**`repo-promise-tester` is given `Write` and nothing else.**

No `Read`, no `Grep`, no `Glob`, no `Bash`. It receives a brief in its prompt
and writes JSON to a path. It cannot look at the subject because there is no
call it could make that would show it to the subject — the same construction as
`repo-probe`, which has no shell because a single `git log --grep` would answer
every question it is being graded on.

An instruction not to look is one an agent can talk itself out of, and the
failure is invisible: the page still prints, the numbers still look like
numbers, and the row reports a clean bill on the repository it was run to
catch. A blind that only holds when the agent cooperates is not a blind.

**The assessor may not answer for it.** Having read the repository is
disqualifying, in exactly the way it is for dimension 4's navigation half.

**Two flags, not one.** `--promise-tests` runs round one; `--promise-impls`
runs round two, and only claims the real code *failed* reach it. They are
separate because the second brief cannot be written until the first has run.

**A claim still waiting on round two is not a pass.** The row's `bad`/`ok`
split had no third state, so a `pending` claim — one whose test the real code
failed — printed under `ok` beside the words *the code passed it*. Undecided is
now its own flag.

## Also taken from the paper, on a second reading of its code

**Round one is two stages.** `MultiStepJavaTestGenerator` asks first for a
prose description of the behaviour under test, then for a JSON list of *"if
this then that"* statements, and only then fills the stubs. That decomposition
is where 8.4 tests per method come from; asked straight for tests, a model
writes the one that occurred to it, and a claim tested once cannot produce the
`p2f` guard at all. The brief now asks for the behaviours first and keeps them
with the result.

**The document is the ground truth in round two**, in the paper's words *"even
if the function name contradicts it"*. The question is whether the sentence was
buildable as written, not what its author probably meant.

**A test that does not parse is dropped before it runs.** CASCADE gets this
from the Java compiler: uncompilable tests are repaired up to three times and
then the claim returns negative. Python has no compile step, so a syntax error
would instead exit non-zero on both runs, cross as `f2f`, and reach the same
verdict — after the second agent round had been spent on it. Worse, a claim
whose only failing tests were typos goes `pending`, which is what schedules
that round.

The drop is **syntax only**. A test that fails to import, or calls something
the document promised and the code does not have, still runs: that failure is
frequently the finding, and round two is what decides whether the document or
the test was wrong. Widening the filter to anything that fails at import would
delete the most common inconsistency there is.

## Rejected

**A repair round.** The paper's three compile-repair attempts need a compiler
error to work from; ours would be a third agent round to fix a bracket. The
claim is dropped instead, and the page says so.

**One agent kept across both rounds.** Nothing needs the continuity — round
two's brief carries the failures — and an agent that has seen its own tests run
has been given a signal about the code it was not supposed to have.

**Letting the agent report what it found.** It never sees either run. An agent
that states an expected verdict has started arguing for its own tests.

## Consequences

`--promise-tests` costs one agent, one clone and one run per claim; the second
flag adds the same again for the claims that failed. It is the dearest thing on
the page and it is off unless asked for.

**The plugin's standing cost grows by one agent description.** That is the bill
for the row existing at all.

## Evidence status

| Claim | Grade |
|---|---|
| A test that does not parse never becomes evidence | **checked** — planted the parse check out, two cases went red |
| A test that fails to import is never dropped | **checked** — planted the filter widened |
| A claim with no parseable test is untested, not pending | **checked** — planted the parse check out |
| The blind agent cannot reach the code | **checked** — planted `Read` into its tool list |
| A pending claim is not reported as a pass | **checked** — planted the flattering note back |
| Two stages produce more tests than one | **cited** — the paper's 8.4 per method, not measured here |
| The blind is what makes the crossing mean anything | **argued** — no run of this on a repository yet |
