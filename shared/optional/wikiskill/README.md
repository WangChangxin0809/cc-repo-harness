# Persistent WikiSkill and reviewed knowledge runtime

- **Covers**: persistent skill evolution, external model/process adapters, immutable evidence, ingest/query/lint and reviewed publication.
- **Does not cover**: a model, OS sandbox, automatic deployment, or reproduction of published benchmark scores.

## Run the complete synthetic wiring demo

```bash
python3 shared/optional/wikiskill/cli.py demo --out /path/to/private/new-demo-run
python3 shared/optional/wikiskill/cli.py status --out /path/to/private/new-demo-run
```

The demo actually launches separate adapter subprocesses, serves scoped trace
read requests, computes independent grades, accepts a candidate and reserves the
final test. It uses a deterministic toy adapter, NOT an LLM. Its success is a
protocol/control-flow result, not a skill-learning benchmark.

## Real provider or trusted agent process

```bash
python3 shared/optional/wikiskill/cli.py run --dataset tasks.json --out /path/to/private/run --iterations 8 --http https://YOUR-PROVIDER/v1/chat/completions --model YOUR-MODEL --export /path/to/private/new-export
```

This is an explicit paid-call entry point. Set `WIKISKILL_API_KEY` in the local
environment; never put keys in command arguments, datasets, Wiki, or Git. The
HTTP adapter is OpenAI-compatible JSON chat completions with scoped `read_file`
tool calls for the proposer. It has no shell tool. No credential-bearing redirect
is followed and HTTPS is required except loopback test servers. It does not hide
network/model errors behind fabricated grades. Full skill content is never
silently truncated to meet a context limit.

A coding-agent backend can be provided as a **trusted** process:

```bash
python3 shared/optional/wikiskill/cli.py run --dataset tasks.json --out /path/to/private/run --allow-exec --command-json '["/absolute/python", "/absolute/agent_adapter.py"]'
```

The adapter receives one JSON start line and can request allowed virtual tools
before returning its final output. See `examples/demo_adapter.py`. Temporary cwd,
minimal inherited environment, a deadline and a process group limit accidental
leaks/hangs. They are NOT a sandbox: a malicious adapter can read the OS owner's
files. Run untrusted agents in separately configured containers/mounts, and grant
only the workspace/tools needed by the task. Child program hashes are bound into
the run's resume identity. Do not modify the adapter during an experiment.

## Dataset and grader contract

`schema: 1`, `tasks` list: `id`, `group`, `split` (`train`, `val`, `test`),
`prompt`, `input`, `expected`. IDs are unique; related groups cannot cross splits;
every split is nonempty and training has at least four tasks. Example provided.

The bundled CLI grader is deliberately **exact string match**. This fits the
example, not arbitrary code/spreadsheet/search benchmarks. Integrators can use
`Runner(..., grader=..., grader_id='pinned-task-grader')` with a deterministic
repository-owned test grader. Model predictions never supply their own score.
Frozen dataset, backend, grader identity, iteration count and seed must match
on resume. A new task family requires its own independently validated grader.

The environment and task similarity still matter: group labels cannot detect
semantic train/test leakage that a dataset author failed to label. Review splits.

## Evolution contract

1. Validate empty active skills to establish a baseline.
2. Run training with the full active `SKILL.md` contents, no experience Wiki,
   validation/test labels or `PURPOSE.md` in the inference payload.
3. Maintain the persistent experience Wiki from at most five failures and three
   successes. Selected trace bodies have the paper-profile 15,000-character limit.
4. The proposer receives a training summary and must actually read at least four
   distinct current training traces through its virtual file API before a create
   or patch. Claimed reads, repeated reads and held-out reads do not qualify.
5. Stage one candidate; accept only when its validation score is **strictly
   greater** than the historical best. A tie rolls back skills, not Wiki.
6. Retain candidate instructions, PURPOSE, diffs, verdict and evidence even when
   rejected. `no_action` is valid. An unavailable grader/provider is unjudged.
7. Freeze final active skills and reserve the final test exactly once. A run
   interrupted during final testing refuses to silently try the test again.

State and audit events are transactional SQLite, immutable per-task results are
reused on resume, and OS writer locks prevent two controllers mutating one run.
No promise of exactly-once external side effects: an adapter may act before a
process crashes without the controller receiving a receipt. Task backends must
provide their own idempotency and disposable workspaces.

## Export and adoption

Exports create a NEW directory. The default includes accepted SKILL/PURPOSE and
a result report, not raw traces or experience Wiki. `--include-experience` is a
private review option, not publication approval. Files may still contain sensitive
model-generated text: inspect and redact before committing. Nothing opens or
merges a PR, installs generated rules, or updates the live skill set automatically.

The existing repository `/learn` and ADR0059 are left unchanged. This is an
optional full skill-evolution lane, not a replacement of guard generation with a
renamed skill system. `model.py` retains the executable specification; `runner.py`
is the persistent controller, sharing the same validated operations.

## Reviewed LLM Wiki

`cli.py knowledge` supports immutable source versions, exact hash/line references,
draft pages, human approval, stale detection, explicit supersession, lexical
query and whitelist publication. `Knowledge.answer(question, adapter)` checks
that model citations refer to supplied evidence. It cannot prove that a cited
sentence logically entails a model claim. Contradiction lint checks explicit
structured keys, not general natural-language truth. Known credential shapes
are refused, not all possible credentials/PII. Human review remains required.

The experience Wiki is private by default. Only reviewed knowledge enters the
public documentation lane; the two stores and purposes must not be confused.

References:
https://arxiv.org/html/2608.27454v1
https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
