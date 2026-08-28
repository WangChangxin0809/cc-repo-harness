# B1 · SessionStart delta, and the decision point

The thinnest possible push, built only to falsify the claim the rest of the plan
rests on: **that context delivered when nobody asked for it changes what an
agent does.**

## Consulted

- **Existing skills**: none yet.
- **Prior art**: none read. What is wanted is a repository that already pushes
  branch state into a session and has measured whether it helped; not looked for.
- **Research**: three papers (AgenticRAG, A-RAG, ProactAgent). They are the
  reason this step exists and is second rather than last: all three measured
  agent-initiated pull beating a precomputed index, and none measured push. So
  the claim is unrefuted rather than supported. ProactAgent's ablation is the
  closest thing to support — *when* context arrives mattered more than what was
  stored — but that was simulated embodied tasks, not code, and it is
  suggestive at best. **Their implementations have not been read**, and the
  RepoGraph lesson says that is where the papers and the code diverge.

## The mechanism, kept deliberately small

At SessionStart, report what changed on the branch since this working tree last
saw it: paths, governing documents of those paths, nothing else. No graph, no
ranking, no summary of the changes' meaning. Ranking and summarising are where
this would get expensive, and adding them before knowing the plain version works
would mean a null result could always be blamed on the ranking.

Cost is the constraint that makes it thin. SessionStart output is paid on every
session by every person, whether or not it is relevant — the same budget
`CLAUDE.md` is already spending. Whatever this emits has to be short enough that
a session where nothing relevant changed has not been taxed.

## What "changed the outcome" means here

Not "the agent mentioned the change" — an agent handed a list will often
acknowledge it and then work exactly as it would have. The graders have to
require an act: a file read that would not otherwise be read, a convention
followed that the baseline arm violates, a conflict avoided. That is what makes
these `with-only` graders (A1) rather than ordinary ones.

## The decision point

This is the only step in the plan whose result changes the plan.

- **Distinguishable delta** → phases C, D and E proceed as written.
- **Indistinguishable** → the abort branch in the README fires. Push has no
  measured value at any moment, so it is not made bigger in the hope that a
  larger version works — that reasoning has no stopping rule. What survives is
  guards, gates and declared relations. Phase F is untouched, because teaching
  does not depend on this claim.

Recording the negative result is part of the step, not a consolation. A decision
record saying "we measured push and could not distinguish it" is the most
valuable artefact this plan can produce if that is what is true, and it is the
thing that stops the idea being revisited from scratch in six months.

## Done when

- [ ] SessionStart emits the delta, within a stated token budget
- [ ] The eval cases from A1 run against both arms on the A2 subject
- [ ] The result is written down here **before** any phase-C work begins
- [ ] If negative: the decision record exists and the README's steps are cut

## Notes

*(Decisions land here as the step runs.)*
