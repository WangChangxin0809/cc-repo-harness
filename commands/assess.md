---
description: Measure this repository as a place for an agent to work — five dimensions, one page, nothing changed
argument-hint: "[path] [--no-full] [--test-command CMD] [--coverage-command CMD] [--mutate N] [--promises] [--once]"
allowed-tools: Bash, Read, Grep, Glob, Task
---

Assess the repository at `$1` (default: the current directory) and produce one
page a person can act on.

**Nothing in the repository may be changed.** Deciding what to do about the
findings is a separate step, done by a person holding what you wrote. An
assessment that ends in *nothing here is worth changing* is a result.

Work in a directory outside the repository — `mktemp -d` — and call it `W`
below. Everything the run writes goes there; the repository gets nothing.

## 1. Run the instrument, and hold its numbers

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/factsheet.py \
        --root "${1:-.}" --json W/run.json --html W/facts.html
```

The replay runs by default: real defects from the repository's own history,
put back, and how late each one is caught. It costs minutes, runs that
repository's tests, and prints the command before it runs. `--no-full` only
if the caller asked.

**Two things about the test command, and the second one bites.**

If it says *no test command was found*, that is a fact about a table, not
about the repository: read the CI file, the `Makefile`, the contributing
guide, and pass what you find as `--test-command`. *No tests exist* is a
finding and stays one; a table that missed a convention is not.

If it names a command and dimension 2 comes back COULD NOT JUDGE with *no
such file*, the command exists today and did not exist at the commits the
replay parks at. The replay checks out this repository's own history, so a
runner added last month is absent in March. Pass an entry point old enough
to be there — often the suites the runner calls, chained — and say in the
hand-back that you substituted one, because the rung it measures is then the
suite and not the documented command. This repository hit exactly that.

The command runs through a shell, so `cd app && flutter test` works, and
everything it names must be tracked by git. A shell line no coverage tool
can wrap — a loop, a `cd`, an `&&` chain — makes 2.1 abstain while 2.3 still
measures; pass a single plain invocation as `--coverage-command` as well and
both rows fill in.

`--mutate N` is opt-in and runs the suite once per mutant. Pass it only when
asked or when the suite is fast.

Exit 2 means COULD NOT JUDGE. Say so and stop.

**Do not recompute what it gave you.** You cannot count tokens, you will not
give the same figure twice, and if the numbers come from you then
re-measuring later compares two opinions instead of two measurements.

## 2. Answer what it could not — one reader per dimension, in parallel

The run leaves questions only a reader of the repository can answer: whether
an agent can watch its own change run, which of the repository's own actions
are legitimate, which uncaught mutants matter, which document candidates are
real. Each is a brief with a flag on `factsheet.py` for feeding the answer
back.

Spawn an `assess-reader` for dimensions **1**, **2** and **4** at once, each
with `RUN=W/run.json`, its `N`, `DIR=W/dN`, `PHASE=answer`. Dimensions 3 and
5 leave nothing to answer. Each reader replies with the answer paths and the
flags they feed; a reader that says it had nothing is a normal result.

If `--promises` was asked for, also spawn **one** `assess-promise-tester`
with the round-one brief — `promises_brief` in the JSON — and a path to
write `W/tests.json`. It has `Write` and nothing else; you have read this
repository and are the one agent who cannot write those tests.

## 3. Put the answers on the page without running the suite again

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/factsheet.py \
        --from W/run.json \
        --observe-answers W/d1/observe.answers.json \
        --legitimate-actions W/d1/permitted.answers.json \
        --mutant-answers W/d2/mutants.answers.json \
        --truth-answers W/d4/truth.answers.json \
        --conflict-answers W/d4/conflict.answers.json \
        --promise-tests W/tests.json \
        --json W/run.json --html W/facts.html
```

Pass only the flags whose file exists. `--from` reads the run back and
applies the answers; nothing is re-measured, so this takes a second. `--json`
may be left out: the run is written back in place, with an `applied` list
saying which answers it carries. A header line reading *instrument only* means
briefs are still unanswered or a dimension was not judged; do not hand that
page over as the assessment. If
promise claims are left `pending`, a **new** promise tester gets
`promises_brief2` and its `impls.json` goes back through `--promise-impls`.

## 4. The reading — every dimension, twice unless `--once`

Spawn an `assess-reader` for each of the five dimensions with `PHASE=read`,
`DIR=W/rN`. Each writes `W/rN/reading.json`: a score out of ten per sub-item,
why in this repository's terms, and the one change that would move it.

Then, unless `--once` was passed, spawn five more with `DIR=W/sN`. The second
reading is what makes a number worth anything: two readers more than two
points apart on one row saw different repositories, and the page says which
rows those were instead of averaging them quietly.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/review.py \
        --grade W/run.json \
        --answers W/r1/reading.json --answers W/r2/reading.json ... \
        --answers W/s1/reading.json --answers W/s2/reading.json ... \
        --html W/reading.html --json W/reading.json
```

Every file is pooled. A sub-item scored twice carries both numbers.

## 5. Hand back

Point at `W/reading.html`. It opens with *what would move the number, lowest
first* — that list is the artefact, and it is for the person. `W/facts.html`
is the measurement behind it. Then, briefly:

- the worst thing on the page, in one sentence, in the repository's terms
- the rows where the two readings disagreed, and which reading you believe
- anything the page could not see: the most dangerous action in this
  repository is usually a command in its own README, and the six generic
  probes never fire it. Read the quick-start, the seed and migration
  scripts, and ask what each would do to a branch somebody cares about
- what you are deliberately **not** proposing, and why

## What a low score means, when you write the summary

| | | A low score means |
|---|---|---|
| 1 | Controlled Execution | uncommitted work can be destroyed and nothing refuses |
| 2 | Change Validation | defects this repository has produced would reach `main` |
| 3 | Reliable Delivery | the green light is real but unrelated to what changed |
| 4 | Repository Memory | a newcomer edits the wrong file, and nothing shortens the search |
| 5 | Context Economy | tokens are spent every turn on text that restates the code |

Absence in the repository is measured: no `.claude/`, no test file, no
pipeline, nothing written down each put a red row on the page. Absence on
this machine is not: a toolchain nobody installed abstains, and an abstained
sub-item is in no brief. The page never confuses the two, and neither may you.
