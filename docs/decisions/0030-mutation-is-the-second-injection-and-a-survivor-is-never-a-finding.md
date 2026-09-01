# 0030 — Mutation is the second injection, and a survivor is never a finding

Date: 2026-09-01
Status: accepted
0028 established which of the mutation paper's numbers we reproduce. This is
about where the result goes: into the ladder, not beside it.

## Context

Dimension 2 asks *when a defect is introduced, how late is it caught?* and the
answer it gives is a ladder — `before-write`, `same-turn`, `local-suite`,
`ci`, `never` — with a cliff in the middle. Until now it had one way of
introducing a defect: take a fix from the repository's own history and put the
defect back. That injection is the strongest evidence on the page, and it has
one blind spot.

**It only asks how late, never whether.** A repository whose replayed defects
are all caught by the local suite reads well on dimension 2, and that reading
is silent about every line the suite *executes without asserting anything
about* — because no defect in the repository's history happened to land on one.

The first attempt at fixing this put mutation **beside** the ladder instead of
in it: a mutant was `killed` or `survived`, meaning the test suite noticed or
did not. That is a different question from this dimension's, and a narrower
one. It measures one rung out of five and reports it as if it were about the
repository. A mutant is a change to a file, so every moment that can see a
change can see it — a PreToolUse hook that refuses the write is a defect that
*never reached the disk*, which is the top of the ladder, not a defect the
suite missed.

## Decision

**A mutant walks the same five rungs a real defect walks, and both are counted
in one ladder.** Hooks are fired at it with an Edit payload, then the suite
runs, then CI. First red wins, and the walk stops there, exactly as
`catch.rung` already did for history defects. A hook that also refuses putting
the original line back is a `false-block` and gets no rung at all — otherwise
the top of the ladder goes to the least discriminating check in the
repository, and a repository could top the measurement by refusing every edit.

**An uncaught change is `pending`, not `never`.** This is the row the whole
design turns on. `never` is only a failure if the thing never caught was worth
catching, and the paper's own figure says roughly three survivors in ten are
not: an initial capacity, a log line, a default nobody promised. So a mutant
nothing caught is not yet a defect. It is reported pending, and parking it at
`never` before anybody has said it is a defect would make a repository look
worse for having bought a measurement nobody has finished reading.

**The agent's verdict is what makes it a defect.** `--mutant-answers` feeds
back what the agent said after reading `mutant_brief`:

| verdict | what happens |
|---|---|
| productive | it lands at `never` — a real defect nothing in this repository catches |
| unproductive | it leaves the count **entirely** — it was not a defect |
| unanswered | it stays pending, counted neither way |

So the flow is: **generate the defect → walk the ladder → for the ones nothing
caught, an agent decides whether they were defects → those that were are the
`never` count.** Anything caught at a rung needs no second opinion: something
asserted about that line, so the change is a real defect by construction.

**`--mutate N`, off by default, while the replay is on by default.** The
asymmetry is about who can bound the cost. The replay runs the suite three
times and the page picks the three; mutation runs it once per mutant and the
caller picks the count. It is the one thing here whose cost the page cannot
bound on its own, so it is the one thing the caller has to ask for. The
pre-flight line from 0026 states the arithmetic before any of it runs.

**Both caveats sort above the rows they disqualify.** A ladder taken over a
flaky suite, or over lines no test executes, looks exactly like a real one. A
caveat printed under the number it disqualifies is a footnote, and a footnote
loses.

## Rejected

**Keeping killed/survived as the reported outcome.** It is a fine internal
verdict and it is still what the suite rung returns. As the page's answer it
was wrong: it renamed this dimension's question to fit the tool that had just
been built.

**Turning survivability into a score.** It is a denominator-shaped quantity
wearing a percentage, and 0027 settled the general form of this mistake. The
figure is printed next to the paper's, and stops there.

**Counting unjudged survivors at `never` and correcting later.** It would make
every mutation run look bad until somebody spent an agent, which is a strong
incentive to not run it — the opposite of what the measurement is for.

**Scoring the survivors here by pattern.** Tempting, and it is how the
`SHORTCIRCUIT` rule in `arid.py` came to exist. That rule is marked as the one
thing in the file not transcribed from the paper's Appendix A precisely
because deriving rules from the repository you are measuring is how a
measurement becomes a mirror.

**Running mutation inside the replay's clone.** Both write to a tree; sharing
one would have the replay's checkouts and the mutant restores stepping on each
other, and the failure would look like a flaky suite rather than a bug in the
instrument. Mutation gets its own bench under the same work directory.

## Consequences

**Dimension 2 has one ladder with two sources**, and the row says which count
came from where. A repository with no replayable history — a shallow clone, a
young repository — can now still be measured on this dimension, because
mutation supplies defects where history does not.

**The page can now cost hours.** `--mutate 200` against a two-minute suite is
most of a working day. The pre-flight says so; nothing else stops it, and
nothing should.

**`judge.py` stays out of the loop.** `factsheet.py` builds the brief and
writes it into the JSON; it does not spawn anything, which keeps the page a
measurement rather than an agent, per hard rule 4.

## Evidence status

| Claim | Grade |
|---|---|
| A mutant is caught at the rung that catches it, not always at the suite | **checked** — the same fixture reaches `local-suite` with no hooks and `before-write` once a blocking hook exists |
| A hook that refuses everything gets no rung | **checked** — recorded as a false block instead |
| An unjudged uncaught change is pending, not `never` | **checked** — planted the parking and watched the case go red |
| A verdict of unproductive removes it from the count | **checked** — same case, all three verdict states |
| Mutation is off unless asked, end to end through the CLI | **checked** — planted a non-zero default |
| The brief asks about the whole ladder | **checked** — planted the old suite-only wording |
| Caveats sort above the rows they qualify | **checked** — planted them below |
| The `never` count after judging is the true one | **argued** — it is as true as the agent judging it, which the page says on the row |
