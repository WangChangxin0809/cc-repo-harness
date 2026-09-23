# Research register

Research date: 2026-09-23. Repository baseline: `eb19d49`.

The existing fast PR and broad postmerge lanes, pinned native plugin evaluator,
WITH/WITHOUT cases, weekly graph benchmark and self-assessment were inspected
before choosing additions. They remain the foundation of this design.

## Observed local gaps

- Release run `35756286123` finished at 16:46:17Z before the same commit's CI
  (`35756286004`, 16:47:39Z) and postmerge (`35756286093`, 16:47:15Z).
- The native-eval summarizer accepted missing arms, empty runs and score 9;
  an absent mean delta rendered as +0.000. Missing evidence could look positive.
- No repeatable memory-specific quality/performance dataset accompanied the
  memory runtime, although its behavioral selftests already cover correctness.

## OpenAI Codex: pinned source, not a borrowed infrastructure stack

Inspected commit
[`286d4ecf44b4e9daba0a9fdd229a4047b770a71a`](https://github.com/openai/codex/commit/286d4ecf44b4e9daba0a9fdd229a4047b770a71a).

- [Workflow policy](https://github.com/openai/codex/blob/286d4ecf44b4e9daba0a9fdd229a4047b770a71a/.github/workflows/README.md)
  tests synthetic merge candidates and aggregates a stable required result.
  Our existing PR selector/terminal gate already does this; we strengthen its
  malformed-input handling instead of replacing it.
- [Postmerge workflow](https://github.com/openai/codex/blob/286d4ecf44b4e9daba0a9fdd229a4047b770a71a/.github/workflows/postmerge-ci.yml)
  separates wide compatibility from the fast PR path. Our Python matrix keeps
  that division; Rust/Bazel build archives and sharding are not justified here.
- [bench-smoke command](https://github.com/openai/codex/blob/286d4ecf44b4e9daba0a9fdd229a4047b770a71a/justfile)
  uses benchmark test mode. [CLI E2E benchmark](https://github.com/openai/codex/blob/286d4ecf44b4e9daba0a9fdd229a4047b770a71a/codex-rs/cli/e2e_benches/codex_help.rs)
  measures real processes and asserts success before interpreting timing. We
  similarly separate correctness/instrument checks from repeated measurements.

## Ruff: compare both implementations using one instrument

Inspected commit
[`d1e47fbf5b8e831795e2b71d2353ae551764cd84`](https://github.com/astral-sh/ruff/commit/d1e47fbf5b8e831795e2b71d2353ae551764cd84).

- [Ecosystem and benchmark jobs](https://github.com/astral-sh/ruff/blob/d1e47fbf5b8e831795e2b71d2353ae551764cd84/.github/workflows/ci.yaml)
  build baseline and candidate for one comparison harness, retain raw results,
  fail on project errors and reject missing artifacts. We adopt same-harness
  base/head measurement and explicit evidence compatibility checks.
- [Memory report](https://github.com/astral-sh/ruff/blob/d1e47fbf5b8e831795e2b71d2353ae551764cd84/.github/workflows/memory_report.yaml)
  compares both binaries on one runner and reduces parallelism. Ruff's memory
  here means process memory consumption, not shared project knowledge.
- Ruff separates simulation, memory and wall-time benchmarking; wall time uses
  dedicated `codspeed-macro` runners. We do not infer stable timing from ordinary
  hosted runners, introduce a paid service, or hide failures behind retries.
- [Daily fuzzing](https://github.com/astral-sh/ruff/blob/d1e47fbf5b8e831795e2b71d2353ae551764cd84/.github/workflows/daily_fuzz.yaml)
  complements fixed PR cases with wider bounded sampling. This supports separate
  recurring evidence, but does not justify copying its automatic issue creation.

## Claude Code native evals

The [official plugin-eval documentation](https://code.claude.com/docs/en/plugin-evals)
was read on 2026-09-23. The repository lockfile pins **2.1.273**; documentation
requires at least 2.1.269. Case schema `1.1` and result schema `1` are distinct.

- WITH/WITHOUT gives a baseline for plugin adoption behavior. Positive Skill
  invocation graders are instrumentation by default, not task-outcome score.
- Partial output, aborted runs, skipped paid graders and per-run errors need
  explicit handling; a rate-limited run need not set the suite's partial flag.
- Native scores are weighted averages and repeated-run means. With the current
  weights and threshold 0.67, losing the preserved project instructions can
  still score 5/7; an unsolicited Write can still score 7/8. Mandatory safety
  graders therefore need an independent rule for each WITH run.
- The no-matching-case CLI probe alone also passes for an empty suite. It is
  host compatibility smoke; a separate explicit inventory verifies real cases.

No paid result was collected during this implementation. Locally constructed
schema regression fixtures must not be described as successful model runs.

## Boundaries and follow-on evidence

- `self-assess` run `35606983156` could not read branch protection with its
  integration token. Its green workflow means a report was generated, not
  that unreadable protection was verified. This work does not grant broad PATs.
- `corpus-improve` has a different exploratory scoring/exit contract. This work
  does not promote it to a release gate or claim corpus task success.
- The graph benchmark still measures two fixed co-change corpora under its
  existing filtering. Sensitivity analysis and a long-lived graph baseline are
  separate from the newly implemented memory benchmark.
- Real memory benefit requires an enabled/disabled **repository runtime**
  comparison with equivalent knowledge available, not simply plugin presence.
  Current native cases measure adoption, routing and unrelated-task specificity.
- Upstream workflow source shows implementation, not that a remote ruleset is
  configured correctly. Actual local repository protection remains enforced by
  the existing required status contexts and the ordinary PR merge path.
