# 0020 — The assessment measures behaviour, not resemblance

Date: 2026-08-30
Status: accepted

## Context

The plugin needed a way to say where a repository stands before it changes
anything. The obvious dimensions were written down first, and they were all
wrong in the same way:

> standing context · `CLAUDE.md` length · guard/test/lint/ci completeness ·
> docs readability · whether hooks are used well

Every one of those asks *does this repository look like ours*. Scored that way,
full marks means "copied us", and a repository that achieves the same ends by
strict review and a good CI pipeline fails. This is the trap the field trial
already named for gates — our own checks cannot be the grader — arriving one
level up, in the instrument that decides what work to do.

The corpus had already shown what that costs. Seventeen of twenty repositories
have no `Requirements` section in their README, and the first response to that
number was to soften the check. That was backwards: prevalence is not
correctness. But the inverse is equally true, and an assessment that only knows
how to say *not like us* cannot ever say *this is theirs, and it is fine*.

## Decision

**A dimension earns its place only if a low score names a specific, observable
failure.** Applied, that filter produces different dimensions and merges two:

| | Question | What a low score costs | Needs a model? |
|---|---|---|---|
| 1 | Which irreversible actions are refused before they happen? | work that cannot come back | no |
| 2 | When is a defect first caught? | see the ladder below | no |
| 3 | Is what the docs claim still true? | confidently wrong work | half |
| 4 | Can an agent find what already exists? | duplicates and contradictions | yes |
| 5 | What does all of the above cost every turn? | the useful part gets crowded out | no |

Three of the five original dimensions dissolve into these, and dissolving them
made them measurable rather than losing them:

- **"Waffle" is not a dimension**, it is a symptom of 3 and 5. That makes it
  testable: if deleting a sentence changes nothing an agent can find out, it was
  waffle. Better than a judgement about tone.
- **`CLAUDE.md` length is not a dimension.** Four hundred lines that stop five
  recurring mistakes are cheap; eighty that restate the directory listing are
  not. The quantity is cost per fact.
- **"Are hooks used well" should never be asked.** A hook is a mechanism.
  `permissions.deny` reaches the same end, so does a pre-commit script, so does
  branch protection. Asking about the mechanism is what makes an assessment
  reward resemblance.

### Time-to-catch, and the cliff

Dimension 2 is not a boolean. The same defect caught at different moments costs
different amounts, and for an agent the curve is not smooth:

    L0 before-write   a hook refuses the edit; the mistake never exists
    L1 same-turn      the agent still holds the context that produced it
    L2 local-suite    a few turns, session still warm
    ---- the session ends, and that context is gone with it ----
    L3 ci             a person is recruited and re-derives what happened
    L4 never          nothing went red

The discontinuity between L2 and L3 is specific to agent-written code: an
agent's context is not persisted, so "caught after the session" means caught
without the only thing that knew why the change was made. This is the reason the
seven-moments framing exists at all, and it had never been used as a scale.

**Blast radius is not a separate dimension**; it is the region of this axis
where every rung after L0 is worthless. A deleted file is not caught by a test
suite, and a secret in the history is not caught in review.

### Early is only better if it is right

A hook that refuses everything scores L0 on every defect and is the worst thing
in a repository: it blocks real work and people switch it off. So every
destructive probe is paired with a legitimate counterpart that must be allowed,
and a rung firing on both is reported as a false block rather than a catch.

This is not hypothetical. Writing `blast.py` was itself blocked by one of the
guards it measures — the probe's command strings sat in a shell heredoc, and a
guard that reads command text cannot tell a command being run from a string
being written. The false-block column caught its own author before it had been
run once.

### The defects come from the repository, not from us

Replaying a defect needs a defect, and inventing them makes the measurement a
mirror: we would invent the ones our guards already stop. Each repository's own
history supplies better ones — a commit that fixed something is a bug that
really happened, chosen by somebody with no stake in this plugin.

Counting them is not enough, so `catch.py` runs the validation pass SWE-bench
runs over every candidate instance: remove the source half of the commit, keep
the test half, and require the tests to go red.

## Consequences

**Four of the five dimensions need no model.** That was not the goal; it fell
out of probing behaviour instead of asking an agent's opinion. Only dimension 4
genuinely requires running one, and there the agent is the *subject*, not the
judge — how many files it reads before its first edit is behavioural data, and
it can be repeated and compared across models. An agent's score out of ten
cannot.

**The agent is handed the counts rather than asked to produce them.** A model
counting is expensive, unrepeatable, and cannot count tokens. `factsheet.py`
ends by naming the three questions it could not answer, and that list is the
entire brief for the step that costs money.

**Improvement may only be claimed in these units.** "We added three gates" is a
claim about us. "Two of six irreversible actions were refused, now five are, no
legitimate action became blocked, and defects that reached CI are now refused
before the write" is a claim about the repository.

**This does not settle who chooses the defects at scale.** For a single
repository its own history is the answer. For a corpus comparison the set still
has to come from somewhere that is not us, and repositories with no test file at
all — three of the twenty — can supply none.

**The assessment is a diagnostic and is not copied into anybody's tree.** It is
run from the plugin, like `probe_repo.py` and `drift.py`. Uninstalling the
plugin must not change what a repository does.

## Evidence status

| Claim | Grade |
|---|---|
| A defect's cost depends on when it is caught | judgement, long-standing in the literature; the L2/L3 cliff for agents is ours and unmeasured |
| Removing the source half of a fix makes its tests go red | **measured**: 26 of 31 candidates across three corpus repositories |
| Scoping to the tests a commit touched recovers instances whole-suite greenness discards | **measured**: 12 → 26 on the same candidates |
| A repository with tests and no hooks catches its defects at L2 | **measured**, and a selftest case |
| Blanket refusal registers as a false block, targeted refusal does not | **measured**, two selftest cases |
| Four of five dimensions need no model | true of what is built; dimension 4 is not built |
| Repositories differ enough that resemblance-scoring would misjudge them | judgement, supported by the corpus survey |
