# A2 · A real multi-contributor subject

The goal names "one large repository with several people on it". This repository
is not that, and measuring the collaboration claim here would be measuring it on
a sample of one contributor.

## Consulted

None yet, and this is the step where that costs most: choosing a subject is
exactly where somebody else's published choice would save a mistake we cannot
detect from inside. What is wanted is how SWE-bench-style work picks its
repositories and what it excludes — the selection criteria, not the results.

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
