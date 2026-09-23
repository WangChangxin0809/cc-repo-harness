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

## Offline checks and reviewed policy

These commands do not run Claude or contact a provider:

```sh
python3 .github/scripts/validate_plugin_eval.py --suite evals
python3 .github/scripts/test_plugin_eval.py
```

[`policy.json`](policy.json) fixes the expected cases, graders, weights, scoring
flags and hard safety requirements independently of the result being judged.
It also records SHA256 hashes of the reviewed case, prompt, fixture and grader
files, after normalizing CRLF to LF. Changes to these files require reviewing and
updating the corresponding policy hashes; adding a case also requires explicit
grader expectations. The free inventory check rejects an empty suite, missing or
extra cases/graders, changed rubric files and a changed native host pin. It is a
reviewed-file integrity check, not a general YAML parser or a model benchmark.

## Manual model-backed workflow

`plugin-behavior-eval` remains `workflow_dispatch` only, with a 120-minute timeout
and `--no-publish`. Before configuring a provider, starting the proxy or making a
smoke request, it validates inputs and the suite:

| Input | Accepted values | Default |
|---|---|---|
| `runs` | integer 1..10 per arm per case | 3 |
| `concurrency` | integer 1..4 | 1 |
| `max_cost_usd` | finite number >0 and <=20 | 20 |
| `threshold` | finite number 0..1 | 0.67 |
| `model` | 1..256 characters, no control characters or surrounding whitespace | `nvidia/nemotron-3-super-120b-a12b` |

`max_cost_usd` is Claude's **list-price estimate and stop mechanism**, not a
guarantee about the actual upstream vendor bill. In-flight requests and estimation
differences can exceed that value. The smoke request is separate from the native
suite estimate. No paid/model calls are made by the offline selftests or PR lane.

The preflight saves `plugin-eval-inputs.json` with independently requested run
counts, threshold, model, concurrency and the policy fingerprint. The summarizer
consumes that metadata rather than trusting expectations claimed by the result:

```sh
python3 .github/scripts/summarize_plugin_eval.py plugin-eval.json \
  --inputs plugin-eval-inputs.json
```

Without `--inputs`, this command uses the documented defaults for offline
inspection. To prepare independent metadata locally, use
`validate_plugin_eval.py --inputs --output plugin-eval-inputs.json` and the
corresponding input flags. Failed runs still upload any JSON, validated inputs,
preflight log, policy and local report that were produced. A native run that ends
without JSON is explicitly unjudgeable instead of silently skipping the summary.

## Judgment contract

- **0: judged pass.** Both arms contain the requested number of distinct traces,
  all expected graders are present, execution completed, all WITH cases meet the
  threshold and every WITH hard safety grader passes on every run.
- **1: judged quality or safety failure.** Complete evidence demonstrates a case
  below threshold or a hard safety violation. Preservation and the negative
  request's no-tool/no-write rules cannot be averaged away by other successes.
- **2: cannot judge.** Missing, malformed, duplicate, inconsistent or nonfinite
  evidence; unsupported host/schema; plugin loading failure; partial, aborted,
  errored or skipped-grader runs; or a native `grader threw:` exception.

The summary recomputes run weighted scores, case means/perfect-run pass rates,
WITH-minus-WITHOUT deltas, suite aggregates and total estimated cost. Boolean
values do not count as numbers. Unknown extension fields are tolerated, while
required evidence is never substituted with zero. WITHOUT quality and safety are
reported separately: baseline defects do not fail the plugin's WITH safety gate.
Delta is descriptive; negative/control cases do not have to show positive delta.
A pass establishes this suite's adoption behavior, not a statistically proven
model advantage or the benefit of persistent runtime hooks in an existing repo.

## Native schema provenance

The reviewed host is the repository pin **Claude Code 2.1.273**, JSON
`schemaVersion: 1`. The contract was checked against the
[official plugin-eval documentation](https://code.claude.com/docs/en/plugin-evals)
and the exact pinned npm platform package's embedded serializer, scorer and
runner, with the archive integrity verified against `eval/agent/package-lock.json`.
No host binary or model was run for that inspection. Offline fixtures are
synthetic native-shaped records, not claims of an actual provider evaluation.

In this version, positive `tool_used: Skill` graders are WITH-only indicators:
they are unscored in WITH and omitted entirely from WITHOUT. Explicit `arm: both`
on the negative Skill grader keeps it scored in both arms. Native run `passed`
means a perfect weighted score, whereas case thresholding uses the dispatch
threshold. `runsPerCase` reflects the case declaration and may differ from the
CLI `--runs` override, so actual arm lengths are checked against saved dispatch
inputs. Each run gets a unique temporary sandbox and `tracePath`; timestamps are
not treated as unique sample identifiers. A host upgrade requires rechecking
these contracts and updating policy/tests together.
