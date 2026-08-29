# A1 · How many of the twenty are green untouched

Run each corpus repository's own test suite, unmodified, and count how many
pass. That count — not twenty — is the corpus size for every measurement in
phase C, because a repository whose tests already fail cannot tell you anything
about an "after" state.

This is the cheapest step in the plan and the one most likely to end it. It
needs no model, no API budget, and no agent.

## Consulted

- **The corpus itself**, surveyed before this file was written: 16/20 carry test
  files, 10/20 declare a runnable test command, 14/20 have CI. That survey is
  what makes an outside grader look affordable, and it is also why this step
  exists rather than being assumed — *having* a test file and *passing* are
  different facts, and only the first has been measured.
- **`eval/run_corpus.py`**, for the shape. Its per-gate loop and its
  three-state reading (crash / abstain / judged-the-repo) are the pattern here,
  and its own recorded mistake is the one to avoid: its first version read
  `ci.sh`'s combined output and tested a substring, so two different kinds of
  failure landed in one stream and the interesting one was never reported.
  Per-repository exit codes cannot blur like that.
- **SWE-bench**, for why this step is separate at all: its instances are
  validated by running the tests *before* applying anything, precisely to
  discard subjects whose suites do not behave. That validation pass is this
  step.
- **Research**: none. Nothing here is an open question — it is arithmetic that
  nobody has done yet.

## What has to be decided

**What counts as "green".** The obvious answer, *the declared test command
exits 0*, is not obviously right. A repository with three passing tests and no
assertions is green and useless as an instrument. A repository whose suite is
green only after `npm install` pulls 400 packages from a network that may not
be there is green in a way that will not reproduce. The threshold has to be
written down before the number is produced, or it becomes a number chosen after
seeing which repositories would have made the cut.

**How much environment we are willing to build.** Eleven languages. Node, Python,
Rust, Go, and a `Makefile` or two. Installing dependencies for eleven toolchains
is a real cost, and it is paid again on every run. The alternative — only
measure the repositories whose suites run with what is already on the machine —
biases the corpus toward the languages we happen to have. Neither option is
free, and the choice determines whether phase C runs in CI or only here.

**Whether a repository that cannot be made green is dropped or noted.** Dropping
is cleaner and shrinks the corpus. Noting keeps it available for measurements
that do not need a test suite — the "do no harm" step needs a repository, not a
green one. The corpus manifest may need to carry the distinction rather than
this script deciding it per run.

**What a flaky suite does to the count.** A suite that passes four times in
five is not green for a paired before/after comparison, because the difference
being measured is smaller than the noise. This is the same lesson the provider
probe already paid for: one sample is not a measurement. The cost is that
establishing greenness now means running each suite more than once.

## What it produces

A number, and a table behind it: per repository, the command run, the exit code,
the wall time, and which of the four verdicts it earned — green, red, could not
run, or flaky. Written to `eval/results/`, alongside the corpus run, in the same
shape so the two can be read together.

The wall time matters more than it looks. Phase C runs each repository's suite
at least twice per task per arm per model. A suite that takes four minutes is a
different plan from one that takes four seconds, and that multiplier should be
visible before anything is built on top of it.

## What would make this step fail

Not "few repositories are green" — that is a result, and a useful one. This step
fails if it cannot tell *green* from *could not run*, which is the same
distinction `nim_smoke.py` had to learn the hard way: a missing toolchain and a
failing test both produce a non-zero exit, and scoring the first as the second
would discard exactly the repositories whose suites are fine.
