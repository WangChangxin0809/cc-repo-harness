# A2 · The concurrency fixture

A small repository, scaffolded with this harness, plus a way to run N agents
against one base concurrently and collect what they produced. That is the
subject. It is built, not found.

## Consulted

- **Prior art**: our own `godot-nakama-workspace` (read in full under A1). It
  rejected the real repository as a subject on purpose — *"Breach already
  contains the fixes for these pitfalls in code comments and would contaminate
  both arms"* — and ran against a clean fixture instead. That decision, made for
  a single-agent skill eval, turns out to be the right one here for a second
  reason as well.
- **Prior art**: OpenAI's Symphony spec, §8–§9. Its model is one issue → one
  agent → one isolated workspace cut from a base → one pull request, with
  concurrency bounded by slots and no coordination between running agents. That
  is the arrangement this fixture has to reproduce, and reproducing it is a
  script rather than a study.
- **Existing skills**: `bootstrap-repo-harness` scaffolds the subject.
- **Research**: how SWE-bench-style work selects repositories — no longer owed.
  It answers *which real repository to pick*, and this step no longer picks one.

## What changed, and why the old version was wrong

This step used to say *find a real multi-contributor repository*, and it carried
a contradiction it could not resolve: the awareness claim needs real concurrent
history, while a real repository contaminates both arms by already containing
the answers. The resolution offered was "real history at a commit before the
knowledge was written down", which is true but nearly unfindable.

Both horns come from assuming the collaborators are people. Human concurrency
has to be excavated, because it already happened; **agent concurrency can be
generated, because it has not happened yet.** N issues against one base is a
loop, it is reproducible, it is cheap to rerun when the mechanism changes, and
nothing in the tree contains the answer because nobody has written it yet.

That also removes the corpus prerequisite. The failure modes do not need
collecting — they are the four rows in the README's table, and each one is a
situation the fixture can be built to produce on demand.

## What has to be decided

**What the subject repository is.** Small enough to scaffold green — the
positioning says the intervention point is a small project, so the subject
should be one, and `ci.sh --fast` going green is part of what is being tested.
Real enough that two agents can plausibly contradict each other in meaning
rather than only in text.

**How to produce row four on demand.** Three of the four failure modes are easy
to stage. The fourth — two agents touching no common file and contradicting each
other in meaning — is the one nothing catches today and the one this whole
fixture exists to exhibit. If the fixture cannot reliably produce it, the
strongest claim the harness has stays untested and this step has not succeeded.

**Whether the arms differ by plugin or by repository.** Rung 0 established that
most of what we ship is payload, so `--ablation with-without` removes the skills
and leaves the scaffold in both arms. For the convergence half that is the right
cut. For the awareness half it is not: the SessionStart delta is repo-side and
would be present in both. Those arms are two repository states, and the fixture
has to be able to produce both.

**Cost, before building it.** N agents × M tasks × both arms × enough runs for
the pairing to mean anything. The godot workspace used a 1500 s timeout per run.
This number should be estimated in this file before the fixture is built, not
discovered afterwards.

## Done when

- [ ] A scaffolded small repository exists as the fixture, green from a clean
      worktree
- [ ] N agents run concurrently against one base and their outputs are collected
      comparably — final message, design note, diff, as the godot workspace did
- [ ] The fixture can produce all four failure modes on demand, row four
      included, and that has been demonstrated rather than assumed
- [ ] Both arm-cuts are producible: with/without plugin, and with/without the
      repo-side mechanism
- [ ] The estimated cost of one full run is written here

## Notes

*(Decisions land here as the step runs.)*
