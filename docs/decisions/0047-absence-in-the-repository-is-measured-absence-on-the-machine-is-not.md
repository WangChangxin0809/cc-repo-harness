# 0047 — Absence in the repository is measured; absence on the machine is not

Date: 2026-09-02
Status: accepted

## Context

Rule 3 says exit 2 means COULD NOT JUDGE and is never a pass. The
assessment took that rule seriously and, in three places, took it too far:
it abstained where it should have measured, and the repositories it went
quiet on were the ones with the least.

- A repository with **no test file anywhere** got `no runnable test
  command`, the same words as a repository whose toolchain this machine
  lacks. Dimension 2 abstained on both.
- A repository with **no pipeline of any host** got nothing under 3.3 to
  3.6, because `pipeline.py` reads GitHub Actions and abstains on the
  others; it abstained on nothing as well.
- A repository with **nothing written down** produced an empty value for
  *what it writes down*, and the reading drops an empty value as an
  abstention.

Each of these was the loudest thing about that repository, and each was
the one row the page did not print. 1.1 had already been fixed the same
way: a tree with no `.claude/` scores `0/6 — nothing is wired`, not blank.

## Decision

**Absence in the repository is a measurement.** No test file, no pipeline
file, no document, no `.claude/`: each is a red row under its sub-item, in
the words *absent in the repository, not unread*, so the reader knows
which kind of nothing it is looking at.

**Absence on the machine is not.** A toolchain that is not installed, a
remote nobody could ask, a host `pipeline.py` does not read: these abstain,
as before, and the abstention is never a number.

The test that separates the two: **would a clone of this repository on a
fully equipped machine change the row?** If no, the row is about the
repository and it is measured. If yes, it is about this machine and it
abstains.

## Consequences

The history is read once and costs nothing, so the missing-suite row prints
even under `--no-full`. A Jenkinsfile still leaves 3.3 unprinted: that is
unread, not absent, and reading it is a table to extend rather than a rule
to change.

0041's guard stands: nothing here puts a number on an abstention. It puts a
row on an absence, and the reader puts the number on the row.
