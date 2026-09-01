# 0038 — A guard that refuses everything scores full marks

Date: 2026-09-01
Status: accepted
Dimension 1.2: the denominator under dimension 1's refusal count.

## Context

Dimension 1 fires six destructive actions at a repository's hooks and counts
the refusals. Six out of six is the top score, and the cheapest way to earn it
is a hook that refuses every write and every command. Such a repository has
discriminated nothing — it has made itself unusable and been graded well for
it.

Six of the probes already carry a legitimate twin for exactly this reason, and
a twin that is also refused disqualifies its probe. That covers the six actions
somebody thought of in advance. It does not cover **this repository's** own
work, which is what an over-eager guard actually breaks: the deploy script, the
migration, the one recursive delete in a build step that is entirely correct.

## Decision

A second half to dimension 1: fire the repository's *legitimate* actions
through the same machinery and count what gets refused.

**An agent supplies the corpus, because a machine cannot.** Legitimate is a
property of the repository, not of the command. Deleting a build directory is
routine in one tree and a catastrophe in another; a force-push to a personal
branch is normal on some teams and forbidden on all of them in others. No list
written here would survive contact with a repository nobody has seen.

**What the machine supplies is the evidence.** The commands CI already runs —
legitimate by construction, since they execute on every push — the commands the
documentation tells a person to run, and the hooks that are actually wired. The
brief then asks for the near-misses on top: publishing a feature branch, a
recursive delete of a build directory, a checkout of a branch rather than of a
path.

**Fired identically to the destructive six.** Same `payload`, same `fire_ex`,
nothing executed. A difference in method between the two halves would make the
ratio between them meaningless, which is the only thing either number is for.

**A block is a finding about the guard, not a fault.** A repository may
deliberately require a human for its deploy. The row names what was refused and
by which hook and stops there.

**A repository with nothing wired abstains.** There is no guard to be wrong
about, so there is no row — not a zero.

## Consequence

Found on the first run against this repository, and found by accident: writing
`docs/branching.md` through a heredoc is refused by `no_pipe_after_outbound`,
because the *content* of the document names an outbound command and a table
separator. Ordinary documentation work, blocked by a guard reading prose as a
command. One of twenty-three.
