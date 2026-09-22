# CI and benchmark operations

- **Covers:** local checks, memory measurements, model-eval evidence and release
  automation for this repository.
- **Does not cover:** adopting these workflows in a scaffolded repository, or
  claims that synthetic benchmark scores measure real agent productivity.

## Run the checks

```bash
python3 scripts/check.py --list
python3 scripts/check.py --job surface
python3 scripts/check.py --job python-compat
python3 scripts/check.py
```

The local runner reads the same steps as `ci.yml`. It prints skipped CI-only
steps. Missing tools or unclassifiable steps return 2, not success. Development
linters are pinned in `.github/requirements-dev.txt`.

PRs use Python 3.9 and 3.14 plus selected scaffold, optional-runtime and host
lanes. Every push to main runs all blocking lanes; postmerge adds every Python
minor from 3.9 through 3.14. The stable `CI required` result rejects missing or
invalid selector evidence and selected jobs that did not succeed. The five
legacy contexts remain for the repository's current branch protection.

## Run a memory benchmark

```bash
python3 eval/benchmarks/memory.py --implementation-root . --output tmp/benchmarks/head.json --repeats 3
```

The dataset is independent of production recall code. Its expected records
are fixed, and its temporary repositories have real Git histories. Per-case
results expose false inclusion, missed expected knowledge, output bytes and
raw elapsed times. Timings include the measured recall path, not fixture setup.
An expected refusal is a contract case, not evidence of a successful retrieval.

To compare two revisions, check out the older implementation separately and
invoke **the same current benchmark script** with each implementation root:

```bash
git worktree add --detach tmp/benchmarks/base HEAD^
python3 eval/benchmarks/memory.py --implementation-root tmp/benchmarks/base --output tmp/benchmarks/base.json --repeats 3
python3 eval/benchmarks/memory.py --implementation-root . --output tmp/benchmarks/head.json --repeats 3
python3 eval/benchmarks/compare.py tmp/benchmarks/base.json tmp/benchmarks/head.json
```

Both results must share the fixture, harness, environment and sample contract.
The implementation revision may differ. Missing or incompatible evidence is
unjudged. A quality violation fails; an elapsed-time ratio does not fail the
build. Small sample counts and hosted-runner contention limit timing inference.

`memory-benchmark.yml` does this for relevant PRs and main pushes, on a weekly
schedule, or by manual dispatch. PRs use their base SHA; pushes use the event's
previous SHA; scheduled/manual runs use the checked-out commit's first parent.
It measures base first, then candidate, so time-of-run effects remain a possible
confounder. Linux, Windows and macOS get separate artifacts, retained 30 days;
cross-OS timing is not compared. This proves benchmark portability, not that
every existing harness selftest runs on every operating system.

## Interpret native plugin evals

Use the existing `plugin-behavior-eval` workflow manually, with provider
credentials configured separately. Inputs are validated before provider access.
The suite uses locked Claude Code, repeated WITH/WITHOUT runs, deterministic
graders and an explicit threshold. See [the eval contract](../../evals/README.md)
for exact cases and safety criteria.

Interpret absolute quality, plugin delta, safety violations and execution
completeness separately. Incomplete arms, aborted runs, skipped graders and
invalid scores cannot be reported as success. A negative task can correctly
have zero plugin delta; preserving project instructions cannot be offset by
success on less consequential graders.

The native cost ceiling uses the client's estimated list price and may stop
after a charge has begun. It is not a guaranteed third-party invoice ceiling.
These jobs remain manual. Offline checks do not establish a measured model
benefit; no paid evaluation was needed to implement this pipeline.

## Release and recurring maintenance

The release workflow's read-only job requires successful **main push** runs of
`ci.yml` and `postmerge-ci.yml` for the exact SHA to publish. Pending/missing
runs have a finite wait; failure, cancellation, invalid identity or unreadable
evidence blocks the write-capable job. Dispatching from another branch is
rejected. Existing version/tag idempotency is preserved.

Dependabot proposes updates to Actions, development linters, Claude Code and
the optional AgentRoom runtime. It does not auto-approve or auto-merge them.
Weekly co-change retrieval and self-assessment reports retain their own scope;
a green reporting workflow alone does not establish that every finding passed.

[Design and source research](../exec-plans/ci-benchmark-automation/README.md)
explain the tradeoffs and record the validation evidence.
