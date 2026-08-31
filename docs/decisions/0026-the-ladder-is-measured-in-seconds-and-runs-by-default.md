# 0026 — The ladder is measured in seconds, and it runs by default

Date: 2026-09-01
Status: accepted
Changes dimension 2 in three ways: the defect replay is on unless refused, each
rung carries the time it costs, and the page states that there is exactly one
way a defect is put in.

## Context

Dimension 2 is the assessment's headline: *when a defect is introduced, how late
is it caught?* It was also the dimension that almost never produced a number,
and the one whose number was hardest to argue with when it did.

Three problems, and they compound.

**It was opt-in.** `--full` guarded the replay. A flag that must be remembered
in order for the page's most important row to exist is a row that does not
exist: every run that forgot it printed `not replayed — rerun with --full`, and
the page's headline dimension abstained. Nobody was deciding not to measure;
they were failing to type six characters.

**A rung name has no size.** The ladder printed
`before-write:0 same-turn:0 local-suite:1 ci:1 never:1`. The docstring claims
there is a *cliff* between `local-suite` and `ci` — the session ends, the
context is gone, everything after is paid for twice — but a list of names shows
five evenly spaced things. The claim was in the prose and never in the numbers.

**The page did not say what it had not done.** Every instance is a real defect
from the repository's own history, put back by taking the files the fix touched
to their state at its parent. That is the design's strength: the defect actually
happened here, and the fix is the answer key. It is also a narrow window. A
repository can score `before-write:3` and still be wide open to every failure
mode that never became a commit — and a reader is entitled to know that before
concluding "this repository catches defects".

## Decision

### The replay runs unless it is refused

`--full` becomes `--no-full`. The cost — minutes, and running a stranger's test
suite on this machine — is real, so it is **announced before it is spent**
rather than explained afterwards:

```
  assessing /home/you/their-repo
  replaying up to 3 of this repository's own defects, in a clone under /tmp/…
  it will run: python3 -m pytest -q
  and its CI entry point: bash ci.sh
  --no-full skips all of it
```

Printed to stderr, before anything runs, with the actual command named. The
objection to defaulting this on was that it executes code from a repository
nobody has read. The answer is not to hide it behind a flag people forget — it
is to say what is about to happen, in the specific, while it can still be
stopped.

### Each rung carries its seconds, and they are measured differently

| rung | the number is | measured where |
|---|---|---|
| L0 before-write | wall clock of the hooks that ran | this machine |
| L1 same-turn | wall clock of the hooks that ran | this machine |
| L2 local-suite | wall clock of the scoped suite | this machine |
| L3 ci | median of the repository's **own completed runs** | `gh run list` |
| L4 never | there is no number | — |

The rungs are not measured the same way because they are not the same kind of
wait, and pretending otherwise is the whole trap. On this repository the row
reads `local-suite:3s  ci:31s` — the 31 seconds is what CI actually takes here,
read from twenty of its own runs, not what its CI command takes on a laptop with
a warm cache and no queue.

**When `gh` cannot answer, there is no number.** No local substitute, no zero.
The row shows `?` and says why. This is the same rule as everywhere else: an
abstention is a result, and a number measuring the wrong thing is worse than no
number, because it is *smaller* and it flattens the cliff the row exists to
show.

### The page says there is one way in

A row, always present, on every run:

> **how the defect got in** — 1 way: the repository's own fix, reverted

with the note saying what is *not* done: nothing is mutated, no payload is
written, and a repository can be caught early by this and still have failure
modes nothing on this page looks for. The count is `1` so that it can later
become `2` or `3` and the reader can see the instrument widen.

## Rejected

**Timing CI locally.** It is one line — the CI command is already run in the
replay, so the wall clock is free. It is also a different measurement wearing
the right measurement's units. What rung 3 costs a person is *time until they
are told*, which is queue plus runner plus their own attention returning; none
of those exist on the machine running the assessment. A local figure would have
made the cliff look like a step, which is precisely backwards.

**Keeping `--full` and warning about it.** A warning printed when the flag is
absent is read by the same people who already forgot the flag. The default is
where the behaviour lives.

**Reporting mean rather than median CI seconds.** One timed-out run at 6 hours
moves a mean and does not move a median, and this number is describing a typical
wait.

**Grading the seconds.** The row is `info` and has no threshold. What counts as
slow depends on the repository, and a threshold invented here would be scoring a
stranger's CI against our habits — which is the resemblance trap this project
already refuses in dimension 4.

## Consequences

**Assessments become slower by default and less often silent.** Previously the
common path was fast and abstained. Now the common path costs minutes and
produces the row the page exists for. The pre-flight line is what makes that an
acceptable trade rather than a surprise.

**Dimension 2 now abstains for a better reason than before.** On *this*
repository it still abstains — `no runnable test command`, because our suites
are `selftest.py` scripts and `ecosystems.py` looks for a `tests/` directory
plus a packaging marker. That is a genuine limitation of the instrument on
itself, now visible on every run instead of hidden behind an unused flag.

**`gh` becomes an optional dependency of one row.** Not of the assessment.
Absent, everything else still measures, and the ci seconds read `?`.

## Evidence status

| Claim | Grade |
|---|---|
| The seconds are populated by a real replay | **measured** — an end-to-end replay on a two-commit fixture returned `rung='local-suite' seconds=0.35` |
| The ci figure comes from the repository's own history | **measured** — `ci_seconds('.')` returned 31.0s across this repository's own completed runs |
| An unreadable CI history abstains rather than reading as fast | **checked** — planted `return 0.0` on the `gh` failure path and watched the case go red |
| A dropped seconds row is caught | **checked** — planted `if False:` in place of `if timed:` and watched the case go red |
| A dropped injection disclosure is caught | **checked** — planted a renamed label and watched the case go red |
| The replay cannot silently go back to opt-in | **checked** — planted `--full` as `store_true` and watched the case go red |
| Defaulting the replay on measures more repositories | **argued** — it follows from the flag being forgotten, but no before/after count of abstentions across a corpus has been taken |
