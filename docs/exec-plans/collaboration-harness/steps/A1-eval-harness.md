# A1 · The eval harness

`evals/` under the plugin root, run by `claude plugin eval --ablation
with-without`. Everything below this phase is a claim about whether the plugin
changes an outcome, and none of those claims is judgeable until this exists.

## Consulted

- **Existing skills**: not yet run. `find-skill` is owed here before any harness
  is written — "does an eval suite for plugins already exist" is exactly its
  question, and writing one first would be the expensive way to find out.
- **Prior art**: not yet read. `claude plugin eval` is first-party, so its own
  shipped example suites are the prior art that matters and they have not been
  opened.
- **Research**: McNemar's test, for paired binary outcomes — the reason the runs
  are paired rather than two independent samples. Nothing else; this step is
  instrumentation, not an open question.

## What has to be decided

**What a case is made of.** A case that only states a task measures the model,
not us. A case has to put the repository into a state where the plugin has
something to say — a teammate's commit landed, a governing document contradicts
the code, a guard's subject is about to be touched — and then ask for work that
does not mention any of it. If the prompt mentions it, the plugin is not what
surfaced it.

**Which graders are `with-only`.** The ablation's value is the no-plugin arm, so
graders split in two. A `with-only` grader asserts something only the plugin
could have caused (a specific path was read, a specific convention was followed)
and is expected to fail in the baseline arm — it is a plugin-fired indicator, and
a `with-only` grader that passes without the plugin is measuring the model's
priors. Ordinary graders score the work itself and run in both arms.

**How many runs, and what makes a delta real.** The environment is
non-deterministic, so one run per arm is noise. The outcomes are paired (same
case, both arms) and binary (grader passed or did not), which is what McNemar's
test is for; the alternative — comparing two mean scores — throws away the
pairing that makes a small sample usable at all.

## The failure this step exists to avoid

A suite that goes green on the day it is written and never fails again. Every
check in this repository is required to have been watched failing, and an eval
case is a check. So each case gets its defect injected once — remove the
teammate's commit, contradict the document differently, disable the hook — and
the case must go red. A case that stays green under injection is measuring
nothing and is worth less than no case, because it reports coverage.

## Done when

- [ ] `evals/` exists with cases that have been watched failing under injection
- [ ] `with-only` graders are marked as such and fail in the baseline arm
- [ ] The run count and the test for significance are written down, not implied

## Notes

*(Decisions land here as the step runs.)*
