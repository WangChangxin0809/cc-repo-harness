# 0051 — The run is the record, and the header says what is still open

Date: 2026-09-02
Status: accepted

## Context

An assessment is two passes over one run. The first measures and writes
`run.json`; the second reads it back with `--from`, applies the readers'
answers, and writes the page. Run by hand, the second pass was given `--html`
and not `--json`, so the page carried five rows in dimension 1 and the JSON
beside it carried three, and the two were read as the instrument
disagreeing with itself. They were one measurement at two moments.

The same page, taken with no readers at all, was honest row by row -- an
unanswered brief is an absent row, never a zero (0047) -- and dishonest as
a page, because nothing at the top said the readers never came. The
instrument's half could be handed over as the whole assessment, and the
question *should the assessment require an agent* was really the question
*can a partial page pass for a full one*.

## Decision

**A pass that changes what the page says writes the run back.** `--from RUN`
without `--json` updates `RUN` in place, and the run carries an `applied`
list naming the answer flags it holds. `--json` still names another file
when one is wanted. The run is the record; the page is a view of it.

**The header names what is still open.** Both the text and the HTML page
open with one line, present only when it is true: *instrument only -- N
question(s) unanswered: observe, permitted · not judged: dimension 2*. The
briefs are the five the instrument can leave (observe, permitted, mutants,
truth, conflict); a dimension is named when it abstained. A page carrying
that line is not the assessment, and says so where a reader looks first.

The assessment does not *require* an agent. The instrument alone is worth
running, and 0022 says an assessment step may end in nothing. What it
requires is that a page without its readers cannot be mistaken for one with
them.

## Consequences

`run.json` after the second pass is the file to keep; there is no second
JSON to reconcile. Anyone who diffed the first pass's JSON against the page
diffs the same file now.

The header line is the only thing on the page that can turn a full
assessment into a partial one by its absence; it is checked by a selftest
that leaves a brief unanswered and reads the header, so a rendering change
that drops it turns red.
