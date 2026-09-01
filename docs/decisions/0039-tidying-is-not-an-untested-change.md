# 0039 — Tidying is not an untested change

Date: 2026-09-01
Status: accepted
Dimension 3.1: which changes owe a test, and which are counted anyway.

## Context

The row read *N of the last M code changes touched nothing that verifies
them*, and M was every commit that touched a source file. That denominator
counts a rename across forty files, a reformat, a dependency bump and a
directory move as changes that arrived without a test.

None of them would be made safer by a new test. Counting them puts a
repository's tidiest weeks against it and quietly rewards leaving the mess
alone, which is the opposite of what the row is for.

## Decision

The denominator narrows to changes that **add behaviour or repair it**, read
off the conventional-commit type: `feat`, `fix`, `perf` and their spellings
owe a test; `docs`, `chore`, `style`, `refactor`, `test`, `build`, `ci`,
`revert`, `deps` and `release` do not.

**An untyped subject is counted, not guessed at.** This is the load-bearing
half and the reason the classifier returns three values rather than two. A
repository that does not type its subjects cannot be narrowed, and inferring
intent from free-form English would shrink the denominator on every repository
at once: every score improves, no repository has changed, and the page is now
lying in the flattering direction. So an untyped subject stays in, and the row
says which denominator it used. Adopting conventional commits sharpens your own
measurement; not adopting them costs the benefit of the doubt and never buys a
hidden pass.

**The machinery row does not narrow.** `ci:` and `build:` owe no unit test and
leave the percentage for exactly that reason — and a change to the thing that
does the verifying owes evidence whatever its commit type. Narrowing both
together hid precisely the commits that row exists to find, which is how the
interaction was noticed: the existing case for it turned red.

## Consequence

On this repository, 5 of 42 became 2 of 36. The six excluded changes are
genuine tidying, and the two that remain are the ones worth looking at.
