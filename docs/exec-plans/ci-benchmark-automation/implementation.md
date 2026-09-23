# CI and benchmark implementation plan

> Execute in the isolated `codex/ci-benchmark-automation` worktree. Independent
> file ownership permits parallel implementation; each component receives
> independent review and defect-based validation before integration.

**Goal:** trustworthy automated evidence from pull request through release.
**Architecture:** retain current lanes; add repository-only benchmark/evidence
tools and consume their contracts in GitHub Actions.
**Tech stack:** Python standard library, Python 3.9+, GitHub Actions, pinned
Claude Code native evaluator, Archify 2.16.0 for the architecture visual.
**Spec:** [architecture](architecture.zh-CN.md).

## Global constraints

- Do not change copied `shared/` runtime behavior for a tooling-only task.
- Exit 0 means judged pass; 1 means judged defect; 2 means could not judge.
- Every new rejecting rule needs a witnessed defective input and passing twin.
- No API/model requests during PRs or local verification; no new external messages.
- Preserve the five existing required status contexts and `CI required`.
- No file over 2000 lines; repository docs routing and Python 3.9 remain valid.

## Task 1: offline memory benchmark

**Own:** `eval/benchmarks/` (runner, fixed fixture, comparator, selftests).
**Interface:** runner accepts `--implementation-root`, `--output`, `--repeats`;
comparator accepts base/head result paths and produces Markdown to stdout or
`--summary`. Root integration will use the final documented command names.

- [x] Write fixed, manually expected cases for positive English/Chinese recall,
  path scope, no match, bounded bytes, unaccepted, stale and retired knowledge.
- [x] Exercise real Git and production recall; isolate baseline imports in a
  separate process. Do not derive expected IDs from production output.
- [x] Add scorer/comparator regression tests: unexpected record, omitted case,
  duplicate ID, NaN/boolean score, missing sample and incompatible fingerprint
  must not pass. Witness red before implementing the rejecting behavior.
- [x] Emit structured provenance, per-case evidence, raw timing and median.
  Deterministic quality failure returns 1; invalid/missing evidence returns 2.
- [x] Run actual candidate and baseline measurements and compare them; timing
  changes do not fail a quality-passing run.

## Task 2: native plugin evaluation evidence

**Own:** `.github/scripts/summarize_plugin_eval.py`, dedicated selftest/input
validation scripts, `.github/workflows/plugin-eval.yml`, `evals/README.md` and
any explicit grader-policy data under `evals/`.

- [x] Reproduce existing false passes with realistic pinned-host result data.
- [x] Validate schema and finite numeric ranges, expected cases/runs, complete
  arms, abnormal execution, grader completeness and consistency with aggregates.
- [x] Independently require preservation/no-unrequested-write safety graders;
  show WITHOUT separately and do not demand positive delta for negative tasks.
- [x] Bound inputs before proxy or provider access; keep manual triggering,
  timeouts, no publishing, no model calls in tests, and honest cost language.
- [x] Summarize complete evidence, expose quality failures as 1 and incomplete
  evidence as 2; preserve artifacts on failures.

## Task 3: release and CI terminal evidence

**Own:** `.github/scripts/release_evidence.py`, corresponding selftests,
`.github/workflows/release.yml`, `.github/scripts/check_ci_results.py`.

- [x] Reproduce release-before-CI and absent/invalid selector false-green paths.
- [x] Implement bounded exact-SHA polling of main push runs for `ci.yml` and
  `postmerge-ci.yml`; only success permits release, retry pending/missing until
  deadline, reject wrong repo/branch/event/SHA and latest failed reruns.
- [x] Separate read-only verification from contents-write tagging, preserve
  idempotent version tag behavior, and reject non-main manual dispatch.
- [x] Make terminal fan-in reject malformed selectors and nonselected failures.
- [x] Exercise success, pending, failure, canceled, stale and malformed evidence
  locally without network mocks substituting for policy behavior.

## Task 4: integration, automation, documentation and review

**Own:** `ci.yml`, new offline benchmark workflow, `dependabot.yml`, README and
docs, Archify JSON/SVG/renderer, integration edits only after owners finish.

- [x] Wire new tooling tests into the existing surface job; add offline quality
  execution to the appropriate existing lane; keep local workflow runner usable.
- [x] Add scheduled/manual same-runner baseline comparison with artifacts,
  explicit failure behavior and exact base/head references; configure portable
  memory benchmark on Linux, Windows and macOS without claiming full OS support.
- [x] Extend dependency maintenance for optional AgentRoom runtime; retain
  review-based upgrades and stable branch protection contexts.
- [x] Document pinned upstream evidence, architecture, commands, actual results
  and unsupported claims; generate and inspect the Archify architecture visual.
- [x] Run targeted tests, linters and relevant CI lanes; independent review;
  push PR and require hosted CI. [PR #104](https://github.com/WangChangxin0809/cc-repo-harness/pull/104)
  records the protected merge and subsequent main verification.
