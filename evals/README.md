# Plugin behavior evals

This suite measures the **installed plugin's behavioral contribution**, not an
internal component in isolation.

Run it with Claude Code's native plugin evaluator so every case is repeated with
and without the plugin. The useful number for positive cases is therefore
`delta = WITH - W/OUT`, not the absolute WITH score alone.

The first suite deliberately uses deterministic graders only:

- outcome: files or final text that a user can observe;
- process: whether the bootstrap skill fired when it should;
- specificity: whether that skill stayed out of an unrelated request.

Fixtures create small disposable Git repositories. They never copy this
repository's expected output into the agent workspace. `evals/results/` is
generated and ignored.

The existing Git co-change benchmark remains valuable, but it is a component
benchmark for `scripts/index/`, not a plugin benchmark.
