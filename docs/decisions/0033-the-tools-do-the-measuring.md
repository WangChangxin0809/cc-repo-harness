# 0033 — The tools do the measuring

Date: 2026-09-01
Status: accepted
Supersedes the implementation half of 0031. Its argument about *why* coverage
is on the page, and in which direction it may be read, stands unchanged.

## Context

0031 established the claim this dimension rests on: high coverage predicts
little, but a line no test executes **cannot** be caught at the `local-suite`
rung, for any defect, ever. A guarantee, not a correlation.

It then built the instrument to measure it — six hundred lines computing
statement, branch and MC/DC in one AST-rewriting pass. That part was a
mistake, and the shape of the mistake is worth recording because it is easy to
repeat.

**On statement and branch it was strictly worse than `coverage.py`.**
Multi-line statements, generators, `async`, `# pragma: no cover`, exclusion
rules, fifteen years of edge cases against real code — none of them handled,
none of them even known about. Measuring a stranger's repository with an
amateur implementation of a solved problem is not a position a diagnostic can
defend, and this whole project's argument is that it is the instrument that
has to be trustworthy.

**The fourth criterion was the only real justification, and it is narrower
than it looked.** MC/DC exists in the compilers — `clang -fcoverage-mcdc`
(LLVM 18), `gcc -fcondition-coverage` (GCC 14), `cargo llvm-cov --mcdc`,
GNATcoverage — and nowhere else. Not coverage.py, not JaCoCo, not istanbul.
So the hand-rolled instrument was the only source of MC/DC for Python, which
is a real gap and still not enough: one criterion, one language, paid for by
being wrong about three criteria in five languages.

## Decision

**Coverage comes from the ecosystem's own tool. There is no instrument here.**
`cover.py` is deleted. `coverage_tools.py` knows how to ask the tools and how
to read what they say back, and that is all it knows.

**Two ways in, in this order.**

*Run the tool*, where the incantation is known and the tool is already
present: `coverage.py`, `go test -cover`, `c8`. Preferred because it measures
*this* suite now.

*Read a report the repository already produces*, otherwise: lcov, Cobertura,
JaCoCo, coverage.py JSON, Go coverprofile, gcov JSON. A report on disk may
predate the code beside it, but a stale report is still evidence and no report
is none. It is also the only path for C, C++, Rust and Java, whose builds
cannot be driven blind — and therefore the only path by which MC/DC ever
arrives.

**Nothing is installed.** A Python repository whose ecosystem has a coverage
tool and does not have it installed *is a repository with no coverage tool*.
That is a finding about the subject, and reporting it is the point. Installing
one would change what the subject contains, which is hard rule 4 read from an
unusual angle: the instrument may not improve its subject in order to measure
it.

**A criterion the tool does not produce is absent, not zero.** Go's tooling
computes no branch coverage — none, it is not a setting. A Go repository
reading `0 of 0 branches never taken both ways` states a fact about the
language in the grammar of a finding about the code, and the reader cannot
tell which it is. So missing criteria carry no row and are named together in
one row that says why.

**Each conventional report path is paired with its reader**, rather than
trying every reader against every file. The readers are not mutually exclusive
on malformed input: a truncated `gcov.json` is not lcov, but lcov's parser can
only say so by finding no counters, and *found no counters* is one edit away
from *found zero coverage*. Pairing removes the question instead of guarding
against it. This was found by planting: disabling one guard turned three
unrelated cases red, which is what an ordering dependency looks like from the
outside.

## Rejected

**Keeping the instrument for Python's MC/DC only.** Tempting, and it is the
strongest case for keeping any of it. Rejected because the row it produces is
one no other language on the page gets, computed by machinery nobody else has
reviewed, and a criterion that exists for one language only invites comparison
between repositories that cannot be compared.

**Deriving function coverage from coverage.py's line data.** Possible in
fifteen lines — a function is entered if any body line executed — and it would
fill Python's one gap against 2.1's *line and function*. Rejected as the same
mistake in miniature: the moment this file computes a criterion rather than
reading one, the question of whose definition of *covered* is in force comes
back. lcov and JaCoCo carry function counters natively, so Node, Rust, C and
Java answer that row and Python does not. The asymmetry is real and belongs on
the page rather than being smoothed over.

**Walking the tree for coverage reports.** A vendored package ships its own
`lcov.info` more often than not, and a walk reports the dependency's coverage
as the subject's — usually a *high* number, since libraries that publish
coverage reports have good ones. A fixed list of conventional locations misses
some repositories and lies about none.

**Guessing at an unwrappable test command.** Three shapes are recognisable
without reading the repository: a bare `pytest`, a `-m module`, a script path.
A shell pipeline or a `make` target is not one of them, and wrapping it anyway
produces a coverage number for a program that never ran. 0029 settled the
general form of this: the table is a fast path, and something that can read
decides when none of its entries apply.

## Consequences

**This repository now abstains on coverage**, and says why: `coverage` is not
installed on this machine. Previously it produced numbers from its own
instrument. That is a loss of a figure and a gain in honesty — the figure was
computed by the thing being measured.

**Python repositories get no MC/DC row.** Nothing produces it for Python. The
row is absent rather than zero, which is the same rule as everywhere else
here.

**Five assessment cases were deleted and seven added.** The deleted ones tested
instrumentation that no longer exists — short-circuit recording, decision
classification, leaving the tree as it was found. The new ones test the
readers and the abstentions, which is what is left to get wrong.

## Evidence status

| Claim | Grade |
|---|---|
| A criterion the tool does not produce is absent, not zero | **checked** — planted a `0 of 0` branch row on a Go coverprofile |
| lcov's function counter reaches the page | **checked** — planted its removal |
| gcov's conditions are where MC/DC comes from | **checked** — planted the conditions loop out |
| A malformed report abstains rather than reporting zeros | **checked** — planted the guard out |
| A dependency's report is not read as the subject's | **checked** — planted a tree walk |
| An unwrappable command is refused | **checked** — planted a catch-all wrap |
| An uninstalled tool names itself and the fix | **checked** — planted the hint out |
| The mature tools are better than what was here | **argued** — not measured side by side, and the argument does not need measuring: one of them has fifteen years of edge cases and the other had none |
