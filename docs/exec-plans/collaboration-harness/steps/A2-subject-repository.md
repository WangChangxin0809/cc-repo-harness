# A2 · A real multi-contributor subject

The goal names "one large repository with several people on it". This repository
is not that, and measuring the collaboration claim here would be measuring it on
a sample of one contributor.

## Consulted

- **Prior art**: our own `godot-nakama-workspace` (read in full under A1). It
  rejected the real repository as a subject on purpose — *"Breach already
  contains the fixes for these pitfalls in code comments and would contaminate
  both arms"* — and ran against a clean fixture instead. That is a direct
  argument against this step as originally written, and it is recorded below
  rather than quietly absorbed.
- **Existing skills**: none apply.
- **Research**: still owed. How SWE-bench-style work selects repositories and
  what it excludes — the selection criteria, not the results.

## The contradiction this step now has to resolve

The plan says *use a real multi-contributor repository*. The workspace says *a
real repository contaminates both arms*. Both are right about different things,
and collapsing them into either extreme loses the measurement:

- What the awareness claim needs from *real* is **concurrent history** — two
  people genuinely moving the same tree at overlapping times. That cannot be
  invented convincingly, and a synthetic history is exactly where we would
  accidentally build situations the plugin is good at.
- What contamination is about is **the answer already being in the tree**.
  A repository that solved a problem carries the solution in its comments, its
  tests and its structure, so both arms score high and the delta vanishes into
  the repository's own quality.

So the constraint is narrower than either: real history, at a commit *before*
the knowledge was written down. Replaying to a parent commit — already required
below — is what supplies that, provided the case is built from a change that
actually landed later rather than one invented for the case. If a candidate
subject cannot supply such a commit, it fails this step regardless of how well
it satisfies the other three.

## What has to be decided

**Which repository.** The constraints are not preferences:

- *Several contributors, overlapping in time.* The awareness half is about what
  another person moved underneath you. A repository where one person commits in
  sequence cannot exhibit the effect in either direction, so a null result there
  means nothing.
- *History we can replay.* A case has to put the tree into a state where a
  teammate's change has landed and the agent has not seen it. That is a
  checkout of a real parent commit, not a fixture we invented — invented history
  lets us choose situations the plugin happens to be good at.
- *Installable without permission we do not have.* Scaffolding writes files and
  hooks. On someone else's repository that is a fork, and the fork has to stay
  close enough to upstream that the history keeps arriving.

**Whether one subject is enough.** One repository makes every result a fact
about that repository's conventions. Two is the cheapest defence, and the second
one costs mostly setup rather than design.

## The trap

Choosing the subject after seeing what the plugin does well. The subject is
chosen and written down here *before* phase B is built, and if it later turns
out to be a bad subject, that is recorded as a change with a reason rather than
a quiet substitution.

## Done when

- [ ] The subject repositories are named here, with how each satisfies the three
      constraints — or which one it fails and why that is acceptable
- [ ] The replay mechanism works: a case can put the tree at a parent commit
      with a teammate's change unseen
- [ ] Chosen before any phase-B mechanism exists

## Notes

*(Decisions land here as the step runs.)*
