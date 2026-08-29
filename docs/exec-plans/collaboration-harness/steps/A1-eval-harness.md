# A1 · The eval harness

`evals/` under the plugin root, run by `claude plugin eval --ablation
with-without`. Everything below this phase is a claim about whether the plugin
changes an outcome, and none of those claims is judgeable until this exists.

## Consulted

- **Existing skills**: the local skill store, where `godot-nakama-workspace`
  turned out to be a hand-built paired-arm eval harness rather than a skill —
  `evals.json`, `assertions.json`, `run_eval.sh`, `grade.py`, iteration
  directories, an HTML review. It is the closest prior art there is, and it is
  ours. Reading it changed this step from *build a harness* to *port its case
  design onto the first-party runner*, which is a much smaller step.
- **Prior art**: that workspace, in detail. Four decisions in it are load-bearing
  and are adopted below. One is a gap: its arms are `with_skill | old_skill`,
  so it never measured *no skill at all*. That is precisely the arm
  `--ablation with-without` adds, and the reason the plan's next step records a
  no-plugin baseline first.
- **Research**: McNemar's test, for paired binary outcomes — the reason runs are
  paired rather than two independent samples. Nothing further; this step is
  instrumentation, not an open question.

### What the workspace already settled

- **The prompt never names the pitfall.** Its cases read like a teammate's
  message — *"the save button isn't even wired up"* — while the assertions test
  for six specific things the agent had to know unprompted. This is the same
  rule stated below, arrived at independently, which is the strongest form of
  agreement available here.
- **Assertions are needles, not quality judgements.** Its grader prompt is
  explicit: *"You are NOT judging whether the code is good"*, no credit because
  the agent "probably knew", no credit for generic hedging. And it separates
  *does X* from *states X* — code that implements a behaviour satisfies the
  first and not the second. That distinction is worth keeping verbatim.
- **The subject was chosen to avoid contamination**, and this is the finding
  that reaches beyond this step. Its note: runs go against a clean fixture and
  *not* the real repository, because the real one "already contains the fixes
  for these pitfalls in code comments and would contaminate both arms." See A2
  — that constraint pulls against how A2 is currently written.
- **Both arms produce comparable artefacts**: final message, a design note the
  agent is asked to write, and a `git diff` with generated paths excluded. Three
  artefacts, so a grader can distinguish what was done from what was understood.

`claude plugin eval` supplies natively what that workspace built by hand: cases
as `case.yaml` or `prompt.md` + `graders/*.md`, `--ablation with-without` on by
default whenever a plugin resolves, `with-only` graders (including
`tool_used: Skill`) treated as plugin-fired indicators outside the score, a
judge model, `--max-cost-usd`, and the HTML report. So the work here is case
design and grader wording, not runner plumbing.

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
