# 0030 — Mutation is the second injection, and a survivor is never a finding

Date: 2026-09-01
Status: accepted
0028 established which of the mutation paper's numbers we reproduce. This is
about putting the result on the page without turning it into a score.

## Context

Dimension 2 asks *when a defect is introduced, how late is it caught?* and
until now it had exactly one way of introducing one: take a fix from the
repository's own history and put the defect back. That injection is the
strongest evidence on the page — the defect really happened here, and the fix
is the answer key — and it has one blind spot it cannot see past.

**It only asks how late, never whether.** A repository whose replayed defects
are all caught by the local suite gets a good reading on dimension 2. That
reading is silent about every line the suite *executes without asserting
anything about*, because no defect in the repository's history happened to land
on one. Mutation asks precisely that question, and the two can disagree.

The machinery for it was built and measured in 0028. It sat in four standalone
CLIs that `factsheet.py` did not call, so the page still said `how the defect
got in: 1 way`, which was true and was also a description of a tool we had
already written.

## Decision

**`--mutate N`, off by default, while the replay is on by default.** The
asymmetry is the point, and it is about who can bound the cost. The replay runs
the suite three times, and the page chooses the three. Mutation runs the suite
once per mutant, and the caller chooses the count — it is the only thing on
this page whose cost the page cannot bound on its own, so it is the only thing
the caller has to ask for. The pre-flight line from 0026 states the arithmetic
before any of it runs: *up to N+3 more runs of that command*.

**Either injection producing a reading means the dimension was measured.** When
the replay abstained — no test command, a shallow clone — and mutation ran, the
dimension is `measured` and mutation supplies the headline. When both ran, the
replay keeps the headline, because *how late* is this dimension's question and
mutation answers a narrower one.

**A surviving mutant is a candidate. The page never calls it a finding.** This
is the row that would be wrong three times in ten if it claimed defects: the
paper reports 70.6% of survivors shown to Python developers as worth acting on,
which is the same sentence as *three in ten were not*. Nothing on this page can
tell which three — only something that reads the enclosing code can. So the row
says `N candidate(s) for an agent`, says what the judging pass is, and the
brief for it is written into the JSON under `mutant_brief` with the enclosing
function included.

**The caveats are printed above the figure they disqualify, not below it.** A
survivability percentage taken over a flaky suite, or over lines no test
executes, looks exactly like the paper's number and is not comparable to it.
Both caveats are flagged `warn` and both sort above the count, because a
caveat under a number is a footnote and a footnote loses.

## Rejected

**Turning survivability into a score.** It is a denominator-shaped quantity
wearing a percentage, and 0027 already settled the general form of this
mistake: a repository with a high survivor rate may have a thin suite, or it
may have a lot of lines nothing should assert about. The page reports the
figure next to the paper's, and stops.

**Letting mutation change the ladder.** Mutants have no rung. They are not
caught *late*; they are caught or they are not, by one suite, at one moment.
Placing them on `local-suite` would put synthetic defects into a count whose
whole value is that its defects are real.

**Scoring the survivors here by pattern.** Tempting — most survivors in one
repository do look alike — and it is how the `SHORTCIRCUIT` rule in `arid.py`
came to exist. That rule is marked as the one thing in the file not
transcribed from the paper's Appendix A precisely because deriving rules from
the repository you are measuring is how a measurement becomes a mirror.

**Running mutation inside the replay's clone.** The replay clones to a work
directory; mutation writes each mutant into the tree in place and restores it.
Sharing one tree between them would have the replay's checkouts and the
mutant restores stepping on each other, and the failure would look like a
flaky suite rather than like a bug in the instrument.

## Consequences

**Dimension 2 can now say two different things about one repository**, and the
interesting case is when they disagree: the repository's own history is caught
early, and lines the tests execute go unnoticed when changed. That is a
statement about test *depth* that nothing else on the page produces.

**The page can now cost hours.** `--mutate 200` on a repository with a
two-minute suite is most of a working day. The pre-flight says so; nothing
else stops it, and nothing should — the caller asked.

**`judge.py` stays out of the loop.** `factsheet.py` builds the brief and
writes it into the JSON. It does not spawn anything, which keeps the page a
measurement and not an agent, per hard rule 4.

## Evidence status

| Claim | Grade |
|---|---|
| Mutation is off unless asked, end to end through the CLI | **checked** — planted a non-zero default and watched the case go red |
| The result reaches dimension 2 when it runs | **checked** — planted the wiring out |
| A run with no replay still counts as measured | **checked** — planted the state upgrade out |
| A survivor is never presented as a finding | **checked** — planted the word |
| The brief carries the enclosing code, not just a diff line | **checked** — planted it empty |
| Caveats sort above the figure | **checked** — planted them below |
| Two injections disagreeing is informative | **argued** — the mechanism is there and the disagreement has been produced once, on this repository |
