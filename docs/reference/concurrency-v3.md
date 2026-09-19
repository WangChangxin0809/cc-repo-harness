# Concurrency assessment preview

- **Covers**: coordination readiness and paired task-effect reporting.
- **Does not cover**: a sixth overall score or points for merely installing a room server.

Configuration, implementation tests, host loading, captured writes, semantic conflict detection, and real task benefit are different evidence layers. Passing one layer does not imply the next.

`shared/scripts/assess/concurrency.py` is a read-only experimental attachment. It does not start target-repository code and does not modify the existing five-dimension score.

For effect measurement, compare the same task, repository commit, model, seed, environment, and grader across reasonable baselines such as isolated worktrees and the room treatment:

```bash
python3 shared/scripts/assess/concurrency_effects.py runs.json \
  --baseline isolated-worktree --treatment room
```

The report keeps success rate, paired wins/losses, successful-run speedup, model-token cost, and human intervention separate. Missing toolchains are unmeasured rather than scored as failures; unknown prices remain unknown rather than becoming zero cost.

Synthetic fixtures validate the measurement code. Product benefit requires real paired agent tasks.
