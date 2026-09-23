# Implementation and evidence

This page separates the implemented Git-sharing profile from the broader
[target architecture](architecture.md). The [user guide](../../how-to/shared-memory.md)
owns runnable adoption and operation instructions.

## Implemented profile

| Capability | Implementation |
|---|---|
| Record and policy schema | Strict standard-library JSON, duplicate-key rejection, bounded fields, safe paths and recursive publication scanning |
| Authority | Explicit local adoption anchor; accepted Git ancestry; separate draft bootstrap; explicit mapping to a clone's remote-tracking ref |
| Recall | Eligibility before lexical/path/tag ranking, CJK matching, source digests, environment applicability, bounded rendering and view receipts |
| Withdrawal | Minimal tombstones, negative overlay for old branches, explicit version-bound restore and trusted-base merge validation |
| Capture | Private session/worktree candidates, origin receipts, replay identity and quotas |
| Publication | Reviewable preview, unchanged-baseline checks, cooperating writer lock, recoverable multi-record journal and complete-generation pointer |
| Dream | Immutable selected inputs, exact duplicate/conflict/source report, agent-authored output contract, provenance/disposition checks, cumulative byte/attempt budget, cancel and retry |
| Lifecycle | Private purge inventory, retirement proposals, selected export/import and explicit fetch without merge |
| Adoption | Copied Python runtime and repository-local skill, hash-safe owned upgrades, supported command-hook wiring and proposed CI integration |
| Distribution | Scaffold/template copy tables, compatibility-lane selftests and README Archify diagram |

Dream does not launch a model. An agent writes the specifically selected private
output, and the runtime validates it before proposing changes. This supports
agent-assisted consolidation without a hidden executor, API cost or claim that
ordinary file permissions sandbox a model. Format/identifier checks cannot prove
semantic correctness; review is still necessary.

## Capability boundaries

- The delivered deployment uses local Git plus explicit fetch. It does not
  provision a relay, remote private vault or an Anthropic managed Dreams job.
- Native auto-memory capture and strict isolation of host-injected memory are
  unsupported. Existing native and cloud Project memory remain unmanaged.
- Hooks are bounded best-effort delivery; explicit CLI/skill access is the
  fallback for hosts that do not load repository settings. Live host compatibility
  and multi-repository cloud automation are not inferred from JSON wiring.
- The hook worker's delivered hard timeout is five seconds (seven seconds in
  installed host settings), with an explicit bounded timeout option. Two local
  warm worker measurements were 2.875 and 3.797 seconds; individual Windows Git
  calls sometimes took about one second. These are observations, not a latency
  guarantee. The original 100 ms warm lookup / one-second hook target is unmet.
- Normal automatic delivery has a cumulative epoch budget. Supervisor failure
  notices are individually bounded but can repeat outside that counter when the
  worker or its state lock cannot be reached.
- External-source freshness without supported evidence is unjudged. There is no
  model reranker or online verification hidden in recall.
- Initial bootstrap, accepted-ref changes and trusted CI base selection remain
  explicit operations. Remote branch protection is not verified by a config file.
- Git history, remote backups and already delivered context are outside private
  purge's erasure guarantee. Document-backed retirement reports remaining sources.

## Acceptance coverage

The 56 scenarios in [the acceptance specification](integration-and-validation.md)
are requirements, not the number of executable tests. Concrete real-Git cases
are in the three `shared/scripts/memory/test_*.py` modules.

| Scenario family | Concrete coverage / limitation |
|---|---|
| S01, S10, S34, S42 | Installed runtime/new-clone transfer, draft-only initial policy, fake branch policy, unaccepted worktree data |
| S02–S09 | Namespace validation, session isolation, CAS, scoped claims, stale/expired/pinned sources and environment checks; free-text truth stays reviewable |
| S11–S16 | Interrupted apply/recovery, concurrent external bytes, malformed JSON, escaping paths, capture replay and durable receipts |
| S17–S20, S33 | Hook epochs/invalidation contracts, old-branch withdrawal, restore identity and explicit sync; actual host injection is a separate compatibility test |
| S21–S22, S27, S29–S30, S32, S36–S40, S47–S48 | Optional relay/native/cloud adapters are not shipped; diagnostics do not claim support or isolation |
| S23–S26, S31, S35, S41 | Publication scanning, non-executable data, Unicode bytes/line rendering, immutable result-source validation and CLI capture independent of native extraction |
| S28 | Git object IDs remain opaque; schema does not assume fixed SHA-1 width; cross-format CI coverage must be recorded separately |
| S43–S46 | Minimal retirement, source exposure, dependent private snapshot/preview purge and metadata scanning |
| S49–S56 | Dream provenance, scope preservation, same-ID conflicts, no self-acceptance, changed baseline, snapshot integrity, current-session selection, cancellation and cumulative budgets |

## Validation record

Development used Windows with Python 3.12 and real disposable Git repositories.
The suite contains 80 cases: 26 foundation, 30 operation/dream and 24 CLI/integration
cases. A frozen-source run completed all 80 in 583.467 seconds: 78 passed, with
one failure and one error traced to test assumptions. The compaction fixture
incorrectly required a default-budget timeout to stay silent; the restore fixture
tried to retire a record before accepting it. Only those two test methods changed:
functional delivery now uses an explicit 15-second limit, and the restore fixture
accepts its initial record and checks the exact missing-retirement-hash error.
Both corrected cases passed together in 75.956 seconds. SHA-256 comparison
confirmed production modules were unchanged throughout these final runs.
Thus all 80 cases have passing final evidence across the frozen run and targeted
corrections; there was no second single all-green 80-case run.
The existing context suite also passed 20 cases. A separate real Tier B scaffold
smoke check installed the runtime and repository skill, passed doctor, and
confirmed that repeating adoption preserved its original trust anchor.

Independent cross-task and final integration reviews closed their identified
source findings. Regressions cover installation rollback, partial-applicability
exit 2, trusted-base CI, resume withdrawal, capture replay, verified sync freshness,
CRLF source/record identity, test-observation publication, response budgets and
worker-descendant cleanup. The final three cleanup/delivery/fallback cases passed.
Actual subprocess delivery took 7.656 seconds in the targeted run and 8.390 seconds
in the frozen run, with an explicit 15-second worker limit. This does not establish
reliable delivery within the default five seconds.

Full-tree Ruff, Python 3.9 syntax parsing for all 15 memory modules, Archify renderer
syntax, docs layout/plan hygiene, plugin surface, file-size, machine-path and
documented-command checks passed. The proposed downstream CI workflow passed
actionlint and offline zizmor. Syntax parsing is not a Python 3.9 runtime run;
the configured Linux compatibility matrix still needs remote CI execution.

The full local runner initially could not judge because actionlint/zizmor were
missing; the pinned development tools were then installed in an ignored local
virtual environment. The broad run completed 35 runnable steps in 1,932 seconds,
with 11 failures. Its memory step ran while review edits were in progress, so the
separate frozen-source suite is the memory result of record. The other failures
were in gate fixtures, graph/assessment, AgentRoom, plugin-hook/checker fixtures,
wiki extraction, template sync, docs routing and shell-based scaffold acceptance.
Observed failures include Windows path normalization, permissions/locking,
decoding and unavailable shell execution. Docs-index and template-sync failures
were independently reproduced on unchanged `dad6c6c`; the remaining unrelated
failures are recorded, not asserted to have a fully verified common cause.
This change does not claim a green full-repository CI run. Host/API-dependent CI
steps and optional native runtime checks skipped by the local runner remain unrun.

No paid model evaluation or claim of improved agent productivity is included.
The teacher-to-clone test proves that accepted information is transferable through
the runtime; it does not prove that a model will use every recalled constraint.

## Diagram provenance

The README diagram was generated with [Archify v2.16.0](https://github.com/tt-a1i/archify/releases/tag/v2.16.0).
Its editable JSON, native-export SVG and MIT notice are committed together. The
development renderer disables optional network access, uses the official browser
exporter, and verifies receipt/hash identity. Showcase validation passed 9/9 with
zero errors/warnings; four viewport checks and light/dark visual review passed.
Two identical local runs produced identical HTML and SVG hashes. See the
[diagram gallery](../../reference/diagram-gallery.md) for reproduction.
The final label refinement makes acceptance explicit (`Accepted Git records`,
`apply + review`); its SVG SHA-256 is
`39672d567420bea2550e94e5cb5fa59345b2c782e4a9c4835104afd343dc9db7`.
