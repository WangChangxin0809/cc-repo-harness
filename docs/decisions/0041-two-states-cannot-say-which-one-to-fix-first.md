# 0041 — Two states cannot say which one to fix first

Date: 2026-09-01
Status: accepted
The reading: an agent puts every sub-item on a ten, and the shape is drawn
from those numbers.

## Context

Every row on this page was a measurement with a `good` or `bad` beside it. Two
states are enough to say something is wrong and never enough to say **which
thing to do next**, which is the only use anybody has for the page. A six and a
two are both `bad`, and they are not the same week's work.

Thresholds cannot supply the missing order. `3 of 6 destructive actions
refused` is serious in a repository where an agent commits all day and
irrelevant in one it cannot write to. `31% of statements never executed` is
alarming in a payments library and ordinary in a tree of one-shot scripts.
`nothing is required on main` is the week's finding in a team of twelve and
noise in a repository with one author. A number written into the instrument is
a number chosen for a repository nobody has seen.

## Decision

The last pass is a reading. An agent that has the measurements **and** has
opened the repository puts each sub-item on a **ten**, with one line saying
what about *this* repository moved the number.

**Ten, and not precision.** Nothing here pretends there is a rubric behind a 6
against a 7. What ten carries that two cannot is **order**, and order is what
the page is for. It is also comparable against itself: two runs of the same
repository, before and after a change, is the comparison this supports.

**An abstention never becomes a number.** This is the last place `could not
judge` could get back onto the page, and the worst, because a number on a chart
is indistinguishable from a measurement. A sub-item nothing measured is not in
the brief, and a score for one is refused rather than dropped, so the run says
which id it threw away.

**One function decides what exists.** The brief and the grader both call
`collect`, because a sub-item the brief did not ask about can only be refused
if both agree about what was measured.

**The shape is drawn from the numbers, and only the shape.** Five axes, one
polygon, no second polygon and no baseline. The area means nothing; which axis
is short means something.

## Consequence

The mapping from printed rows to sub-items is matched on row labels rather than
set where each row is built. Nine modules produce rows, and threading an id
through all of them would make the numbering theirs; a row nobody has mapped
shows up as unmapped instead of being silently scored.
