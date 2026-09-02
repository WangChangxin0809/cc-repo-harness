# 0046 — A reading says what would move it, and is read twice

Date: 2026-09-02
Status: accepted
Amends 0041. The ten stays; what is added is the line under it and the
second reader.

## Context

0041 put every sub-item on a ten so the page could say **which row first**.
It did that. Then the person holding the page asked the next question, which
is *and do what there*, and the page had nothing: a 4 with a line saying why
it was a 4 is a diagnosis, and the row stayed open until somebody re-read
the measurements underneath it and worked out the change themselves.

Two other things showed up in use. A number from one reader is one reader's
number; there was no way to tell a 4 that any reader would give from a 4
that another would call a 7. And the page listed sub-items by id, so the
row to act on first was somewhere in the middle, under the ones that were
fine.

## Decision

**Each score carries `moves_if`**: the one change to this repository that
would raise it most, in the repository's own terms — a file, a hook, a rule,
a test. A direction is refused by the brief; *improve coverage* moves
nothing. `nothing`, with a clause, is a legitimate answer and it **closes the
row**: it stays on the item and comes off the list.

**The page opens with that list, lowest score first.** The radar and the
per-item body follow. The list is the artefact; what is under it is the
evidence.

**Every dimension is read twice, by two readers who did not see each
other's numbers.** Both numbers are kept on the item with the mean. Two
readings more than two points apart are **marked as disagreeing**, not
averaged quietly: at that distance the two read different repositories, and
which one is right is a finding the assessor is asked to settle with a file
and a line. Two points is the width a single reader's own re-reading moves
by; it was chosen by watching, not derived.

**One reader per dimension**, given only that dimension's brief. A reader
with all five in view scores the repository; a reader with one scores the
dimension, which is what the number is supposed to be.

## Consequences

`review.py --answers` repeats, and every file is pooled. Five per-dimension
files and two whole-page files are the same shape to it, so whoever spawns
the readers does not merge anything.

A page that says `nothing` on every row is the result 0022 said could
exist, and it now has a shape: an empty list at the top.

The second reading doubles the cost of the cheapest step. The readers do
not run the suite, and the step they double is the one that decides what
the page says, so this is the right place to spend twice.
