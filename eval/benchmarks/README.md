# Offline memory benchmark

This repository-only instrument exercises production memory recall against a
fixed, manually specified Git history. It uses Python 3.9+ and Git, makes no
network/model calls, and is not copied into scaffolded repositories.

```bash
python3 eval/benchmarks/selftest.py
python3 eval/benchmarks/memory.py --implementation-root . --output tmp/memory.json --repeats 1
```

The default selftests validate scoring, evidence completeness, comparison and
CLI errors without running the full benchmark. `selftest.py --integration` also
runs all twelve cases against the current repository. Use `--repeats 1` for a
PR quality check; measurement defaults to three repetitions (allowed: 1–30).

The fixed cases cover English and Chinese recall, matching and nonmatching
paths, no query match, UTF-8 byte limits, unaccepted branch records, private
candidates, changed sources, accepted retirement over an older checkout, dirty
record overlays and unknown environment predicates. Expected IDs and delivered
text fragments live in `fixture.json`; they are never learned from the runtime.

Each run constructs one real temporary repository. Main accepts the original
records, then accepts a retirement. A topic checkout from the earlier accepted
commit adds an unaccepted record; source and record edits remain dirty, and a
private candidate is captured through the production store. Recall must apply
the latest accepted retirement despite the older checkout.

Quality fails for missing or unexpected IDs, dangerous marker leaks in text or
structured records, missing rendered `[id]` attribution or required text,
changed gold title/summary/body, text without any selected records, missing
required exclusions, wrong runtime exit codes and exceeded byte budgets.
Empty-result cases do not inflate the recall denominator. Missing cases,
samples, receipts, malformed values or inconsistent summaries are unjudged.
The comparator recomputes quality from raw samples; it does not trust a claimed
passing score. This measures these engineered cases, not arbitrary secrets or
real user task success.

Exit codes distinguish the benchmark's judgment:

- **0:** complete evidence, all deterministic quality constraints pass.
- **1:** complete evidence demonstrates a quality defect.
- **2:** evidence is missing, malformed, incompatible or could not be collected.

A case explicitly expecting runtime code 2 can pass when it correctly proves
that behavior. This does not turn an incomplete benchmark run into a pass.

To compare implementations, invoke the **same current harness** for both roots,
sequentially on the same runner/interpreter:

```bash
python3 eval/benchmarks/memory.py --implementation-root ../baseline --output tmp/base.json --repeats 3
python3 eval/benchmarks/memory.py --implementation-root . --output tmp/head.json --repeats 3
python3 eval/benchmarks/compare.py tmp/base.json tmp/head.json --summary tmp/comparison.md
```

Each implementation is imported in a fresh worker process. Results identify
the implementation commit, memory subtree dirty state, runtime-byte digest,
fixture digest, harness digest, Python, Git, OS, architecture and machine name.
The harness rejects changes to those measured inputs during a run. Different
fixture/harness/protocol/case sets, environments or repetition counts cannot be
compared as equivalent measurements. Baselines without the memory runtime are
unjudged. Raw records, delivered text, receipts, timing samples and per-case
medians remain in JSON even when complete evidence shows a quality failure.

Timing covers a new `Repository` plus `recall` for each sample, excluding fixture
setup and the worker interpreter's startup. Only the first fixture recall is
`cold`; subsequent samples can reuse the disposable Git-history cache and are
`warm`. The comparison reports separate phase medians and ratios, without a
wall-clock pass threshold. One repetition provides no warm English sample and
no distribution estimate. Shared-runner contention remains noise even when
the fingerprints match; same-runner comparison does not establish statistical
significance. These twelve synthetic cases are not the 100/1,000/10,000-record
scaling benchmark or a measurement of dream synthesis quality.
