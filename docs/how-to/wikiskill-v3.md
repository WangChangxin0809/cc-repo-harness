# WikiSkill preview: turn experience into validated skills

- **Covers**: the optional skill-evolution lane, role boundaries, rollback, persistence, and adoption.
- **Does not cover**: a guarantee that a real model will improve outside the supplied validation tasks.

## Run the deterministic wiring demo

```bash
python3 shared/optional/wikiskill/cli.py demo --out /path/to/private/new-run
python3 shared/optional/wikiskill/cli.py status --out /path/to/private/new-run
```

The demo launches real adapter subprocesses and exercises trace reads, grading, candidate acceptance, persistence, and final-test reservation. It uses a deterministic toy adapter and consumes no model budget; it is a control-flow test, not a paper benchmark.

## Keep the roles separate

The inference worker receives the public task and the **full active SKILL.md content**. It does not receive the experience wiki, validation/test labels, or PURPOSE metadata.

The maintainer distills training successes and failures. The proposer must actually read at least four distinct current training trajectories through its scoped file API before it may create or patch a skill. Claimed reads and repeated reads do not satisfy the requirement.

## Accept only strict improvement

```text
candidate validation score > historical best -> accept
candidate validation score = historical best -> reject and roll back the skill
provider/grader unavailable                 -> unjudged, not zero and not pass
```

A rejected skill is rolled back, but the experience wiki, candidate content, diff, verdict, and evidence remain recorded so the same failed idea is not rediscovered without context.

## Preserve the final test

Related tasks are kept in one split group. The final test is reserved for one run after the active skill set is frozen. An interrupted final test is not silently retried as another selection signal.

## Real adapters

The HTTP adapter supports an explicitly configured compatible chat-completions endpoint. A trusted process adapter can be enabled explicitly for coding-agent backends. Temporary directories and minimal environments reduce accidental leakage but are not an OS sandbox; isolate untrusted code outside this runtime.

Exports create a new directory and never overwrite or auto-install a live skill. Review generated skills before adoption.

Reference: [WikiSkill, arXiv:2608.27454](https://arxiv.org/html/2608.27454v1).
