# Integration and acceptance

The [architecture](architecture.md) defines the target behavior. This document maps that complete design into this repository and defines the evidence required before claiming it works. It is not a claim that the proposed modules or evaluations already exist.

## 1. Existing components and changes

| Existing surface | Retain/reuse | Required change |
|---|---|---|
| `CLAUDE.md` and nested instructions | Small standing rules, repository ownership | Add a concise memory entry point in adopted repositories, with host-independent source locations |
| `docs/index.md`, docs/decisions and exec-plans | Existing authoritative facts, decisions and current work | Index them by reference; do not duplicate their full contents into memory records |
| `shared/scripts/scaffold.py` | Copy tables, tier adoption, skip-existing behavior and hook merging | Add explicit memory adoption/profile selection, runtime copy entries, configuration and idempotent upgrades |
| `scripts/context/session_brief.py` and its scaffold template | Branch/worktree/plan orientation | Add an independent memory SessionStart hook, preserving the repository-specific existing brief |
| `shared/scripts/context/before_write.py` | Scoped-rule and `Governs:` delivery | Share lookup results/dedup identity with memory routing and handle context epochs; do not add competing duplicate injections |
| `shared/scripts/context/on_stop.py` | Existing validation aggregation | Surface pending proposals and memory check failures without being the only persistence mechanism |
| `shared/scripts/consolidate.py` and `shared/skills/consolidating-notes/` | Frozen-input/separate-output pattern, evidence-loss review and routing | Extract suitable checks for dream; replace mutable output reuse with private immutable jobs and record-aware provenance; do not inherit timestamp-based conflict resolution |
| `.claude/wiki/` and `shared/scripts/wiki/` | Experience records, recurring failures and proposal history | Explicitly promote selected conclusions to ordinary memory/docs/rules; do not make the failure catalog a universal prompt |
| `shared/optional/wikiskill/knowledge.py` | Source hashes, evidence ranges, stale detection and explicit claim concepts | Extract independently tested reusable concepts; do not make its private SQLite store the shared canonical database |
| `shared/optional/agentroom/` | Local cooperation and crash-recovery ideas | Optional notices bridge only; retain dependency boundaries and add remote identity separately if selected |
| `shared/scripts/gates/` | Red/green planted-defect tests and exit-code contract | Memory schema, references, scoped-claim conflicts, lifecycle and policy checks |
| `evals/` and host eval tooling | Deterministic behavioral graders and disposable repositories | Add memory-persistence and team-transfer experiments with correct enabled/disabled attribution |
| `scripts/sync_template.py` and template repository | Source-controlled scaffold distribution | Include new payload and upgrade fixtures through the same source tables |

Before changing shared modules, their `CLAUDE.md` constraints apply: copied runtime depends only on the destination tree and Python standard library. Diagnostic/model-driven evaluators remain outside mandatory payload.

## 2. Proposed module boundaries

The names below identify implementation responsibilities, not runnable commands currently present.

| Proposed module under `shared/scripts/memory/` | Public responsibility |
|---|---|
| `schema.py` | Strict versioned record/policy/candidate validation and canonical digest |
| `repository.py` | Repository/worktree identities, accepted ancestor, shallow-history diagnostics |
| `store.py` | Record enumeration, CAS edits, transaction journal and recoverable generations |
| `evidence.py` | Source digest checks, expiry, path applicability and structured claim intersections |
| `candidates.py` | Private outbox, idempotent processing and publication-ready diffs |
| `dream.py` | Private immutable job manifests, bounded executor orchestration, checkpoints and provenance/loss reports; sends outputs through candidates/propose |
| `retrieve.py` | Eligibility-first deterministic ranking and explainable exclusions |
| `render.py` | Byte-bounded Markdown views/indexes for framework recall, kept outside native writable memory |
| `session.py` | Context epochs, view receipts, invalidations and dedup checkpoints |
| `cli.py` | Inspect/recall/remember/dream/verify/propose/forget/retire/sync/doctor interfaces |
| `selftest.py` | Deterministic system/contract acceptance using disposable Git repositories |

Host-specific hooks remain thin adapters under the context wiring; model-assisted maintenance is invoked through repository-local skills/agents, not hidden inside core retrieval. A repository-local memory skill should be installed as payload, subject to existing context-budget limits. It must not become a second always-on plugin skill.

The optional live adapter is packaged outside the zero-dependency core. Existing AgentRoom/WikiSkill code is not imported wholesale merely because some concepts are reusable. Shared utilities are extracted only where ownership, dependency floors and tests remain clear.

## 3. Policy and operation contracts

Tracked policy specifies schema version, namespace, accepted-ref convention, allowed record classes, publication mode, scope grammar, budgets, freshness defaults and enabled adapter names. Authentication material and machine directories are supplied locally or by the cloud environment.

Operation contracts are the same across a CLI, an agent tool wrapper and future UI:

| Operation | Required inputs | Observable result |
|---|---|---|
| Inspect | Repository/worktree | Active policy, authority view, sync age, pending count and compatibility state |
| Recall | Query and/or paths, view identity, budget | Eligible records, source/version receipts, omissions and exclusion reasons |
| Remember | Structured content, intended scope, source receipt | Private durable candidate ID; never an implicit push |
| Dream | Pinned view, explicit private selection, source/policy digests, executor and budgets | Private job receipt, synthesis/provenance/loss findings and candidate proposal; completion is not acceptance |
| Verify | Selected records and view/source identities | Freshness, scope and evidence report; missing semantic evidence stays unjudged |
| Propose | Candidate IDs and expected baselines | Reviewable canonical-file diff with validation findings |
| Apply resolved proposal | Expected old hashes and approved intended record set | Transaction receipt, or a conflict without overwriting external changes |
| Retire | Record ID, baseline hash, reason/replacement | Reviewed retirement change; private removal is a separate operation |
| Forget | Explicit private-cleanup or team-retirement scope and selected IDs | Private purge inventory/receipt, or a retirement proposal with residual exposure reported; no implicit history rewrite |
| Sync | Authorized remote/profile and last cursor | New known ref/cursor plus applicability delta; no implicit rebase/merge |
| Doctor | Host version and configured profile | Verified capabilities, absent/unsupported capabilities and remediation |
| Export/import | Explicit selection, format/version and destination/source | Source-preserving transfer report; import remains provisional until accepted |

Network and model work are visible operations with configured time/cost bounds. Ordinary recall uses local data. Dream batches deduplication and semantic conflict suggestions; it cannot silently delete records on a model's confidence score. Its precise triggers, job/result states, reuse boundary and example interactions are specified in the [Chinese operation guide](operations-and-experience.zh-CN.md).

## 4. Migration and adoption

Adoption is idempotent and preserves existing `CLAUDE.md`, settings hooks, docs and personal memory. It produces a concrete diff and profile report. It does not install remote services or change global Claude Code settings as a side effect.

Current scaffold behavior skips files that already exist and deduplicates hooks by their full command. That is not an upgrade mechanism. The proposed installer needs a versioned vendor manifest of shipped file hashes and owned hook identities. It replaces an installed runtime file only when the bytes match a known shipped version; locally modified files yield a conflict and proposed patch. It removes only an exactly identified old owned hook, preserves custom hooks and never overwrites user records/configuration. A separate memory startup hook avoids rewriting a custom generated session brief. Path-hook cooperation uses a checked compatible adapter version; until wiring is resolved, doctor reports automatic delivery as incomplete instead of adding duplicate injections.

Copying a gate does not activate it in an existing `ci.sh`. Adoption supplies an explicit CI wiring patch and verifies the selected CI runner actually includes it. If it cannot determine that, the required integration check returns exit 2. Policy changes are reviewed using the prior accepted policy, including changes that would introduce automatic acceptance.

Existing material is handled according to its current authority:

1. Existing docs/rules/decisions become referenced sources; their text remains where it is.
2. `.claude/wiki/` remains an experience catalog. A maintainer selects an actual conclusion and source, then promotes it through the candidate pipeline. A rejected idea stays rejected unless new evidence is attached.
3. Native local memories are imported only from a selected directory/selection. `user` notes default to private; a `project` or `feedback` type is not sufficient proof that the content is team-shareable.
4. Reviewed WikiSkill knowledge exports keep their source digests and prior review metadata as provenance. The destination's acceptance policy still applies; an imported reviewer string is not an authorization token.
5. Cloud Project memory uses an explicit available export or user-selected content. Do not fabricate an API or promise transparent bidirectional synchronization.

Schema upgrades run as deterministic Git-visible migrations with a before/after report and the original revision available for rollback. Readers reject unsupported major schemas with exit 2. Derived caches are rebuilt; migrations never require committing a database binary.

Uninstalling the plugin leaves copied runtime, records and repo-local instructions operational. Removing the memory feature itself disables its hooks and entry points while leaving knowledge files readable. Removing a live relay returns the deployment to Git sharing without losing accepted records.

Existing architectural prose that says per-machine memory is not a repository's knowledge authority should be clarified, not inverted. ADR 0059's experience-wiki boundary remains; any broader claim that all memory harms inference must not be inferred from that one evaluation setting.

## 5. Compatibility matrix

Compatibility is a tested capability set for an exact host version, not a broad version-range guess.

| Environment | Required path | Feature-specific checks |
|---|---|---|
| Windows terminal Claude Code | Repo instructions, Python runtime, supported hooks | Drive/path normalization, atomic replacement, process locking, native directory settings |
| Linux/macOS terminal | Same core | Permissions, symlinks, case sensitivity, filesystem notifications |
| Linked worktrees | Git-derived identities | Private queue separation, accepted ancestry, parallel capture |
| Detached/shallow checkout | Explicit immutable view | Missing merge-base is diagnosed; no fabricated team approval |
| Single-repository cloud session | Cloned records plus active hook/skill adapter | Ephemeral disk, reconnect, no dependency on local user paths |
| Multi-repository cloud Project | Per-repository entry point and explicit bootstrap | Settings hook limitations, namespace separation, no accidental cross-repo recall |
| Subagents | Explicit view/scope handoff | Parent memory not assumed inherited; project-memory directory is not approval |
| Alternative model through Claude Code | Same host tool/hook contract | Instruction adherence, candidate quality and tool reliability measured separately |
| No native auto-memory support | Repository memory path | Native capture visibly disabled; canonical recall remains usable |
| Offline | Last known accepted snapshot | Sync age shown; no hidden model/network dependency |

The research client and repository evaluation pin differ; both belong in the initial test matrix. Native capture is disabled for an unknown capability profile until checked. Published host changes trigger a compatibility probe and evidence refresh, not an automatic rewrite of the user's installation.

## 6. Deterministic acceptance suite

Every new gate must have both a planted defect it rejects and a legitimate neighbor it accepts. The following are release contracts, not test results from this design exercise.

| ID | Scenario | Required observable result |
|---|---|---|
| S01 | Fresh clone, plugin removed | Accepted knowledge is discoverable through repo-owned entry points |
| S02 | Two repositories with identical filenames | No cross-repository memory result |
| S03 | Two worktrees write native/private notes | Candidates stay partitioned; no implicit branch promotion |
| S04 | Same record concurrently updated from one baseline | One CAS conflict; neither update silently lost |
| S05 | Different records assert conflicting scoped claim values | Merge-result validator identifies both IDs and overlap |
| S06 | Different records have demonstrably disjoint scopes | No false conflict merely because claim keys match |
| S07 | Free-text contradiction without structured keys | No claim of deterministic truth detection; suspect is reviewable |
| S08 | Source file changes, moves or is deleted | Dependent content is stale/unjudged as appropriate; never silently fresh |
| S09 | New accepted memory requires code ahead of checkout | Advisory delta only; incompatible knowledge excluded |
| S10 | Branch proposal uses `state: active` or a fake reviewer | It does not become accepted team knowledge |
| S11 | Crash during multi-record replacement | Prior valid view or recovered complete view; mixed generation is not served |
| S12 | Editor modifies a staged record during recovery | Recovery stops with a conflict and preserves external bytes |
| S13 | Truncated/malformed/oversized record or unknown schema | Bounded diagnostic, no arbitrary parse fallback |
| S14 | Path traversal, symlink escape or case alias | No outside-root read/write; supported valid paths still work |
| S15 | Duplicate or reordered capture event | One candidate outcome per idempotency key |
| S16 | Session ends without Stop hook | Existing candidate receipts remain recoverable |
| S17 | Memory recall after compaction/resume | Appropriate context epoch changes; essential orientation can be re-delivered |
| S18 | Retired record still present in cache/native staging | Future accepted recall excludes its body; invalidation is reported |
| S19 | Git revert would resurrect a retirement | Lifecycle validator requests explicit restore resolution |
| S20 | Interrupted fetch or unavailable relay | Local valid view remains usable with visible sync age |
| S21 | Replayed/forged relay notice or wrong repository tenant | Rejected; no record or accepted-ref authority change |
| S22 | Lost relay history followed by reconnect | Git reconciliation reconstructs durable accepted state |
| S23 | Secret-shaped value or personal transcript in a proposal | Known-pattern checks and publication review catch the planted case; no promise of universal PII detection |
| S24 | Memory text asks for tools, credential access or policy changes | Data is not interpreted by runtime as executable configuration |
| S25 | Sensitive fact requested forgotten | Future recall retirement distinguished from historical deletion |
| S26 | Budget overflow, including multibyte Chinese text | UTF-8/line limits respected; omission is visible; no partial JSON/UTF-8 output |
| S27 | Missing optional versus selected required adapter | Absent optional is a reported profile; required unavailable is exit 2 |
| S28 | SHA-1 and SHA-256 Git repositories | Identity and source-version checks work without a fixed 40-character assumption |
| S29 | Native adapter setup after host memory loading | Doctor refuses to claim the already-running session was reconfigured |
| S30 | Cloud multi-repository session without repository hooks | Explicit fallback reported and usable; no false automatic-delivery claim |
| S31 | Both source doc and referencing summary change in a PR | Evidence is evaluated against the proposed merge result |
| S32 | Fork inherits namespace but no upstream membership | Relay refuses unauthorized upstream participation |
| S33 | Old feature branch references a record retired on the accepted tip | The revocation overlay suppresses it without waiting for a code rebase |
| S34 | Branch loosens its own auto-accept configuration | Old accepted policy still governs the policy change and associated records |
| S35 | Chinese/multiline/backtick inline record | Human-readable semantic diff and line-preserving canonical serialization |
| S36 | Native project-memory agent or missing session identity detected | Unmanaged storage is reported; no private candidate enters a shared fallback bucket |
| S37 | Native background writer creates an unwatched topic file after Stop | Next bounded rescan recovers it; capture completeness is not claimed before that boundary |
| S38 | Upgrade encounters customized runtime/hooks and an old CI script | Custom bytes preserved; explicit conflicts and CI patch, no duplicate old/new owned hooks |
| S39 | Read-only reviewer enables native persistent memory by mistake | Adapter detects the host's added write tools and rejects that read-only profile |
| S40 | Cloud sandbox loss with only ephemeral private storage | No false durable-capture claim; required durable profile fails doctor until persistent storage/private vault exists |
| S41 | Explicit Chinese remember request with no whitespace | Repository capture works independently of native language/feature-gated extraction |
| S42 | New repository has no accepted branch/history yet | Draft-only bootstrap, never self-approval by guessing current HEAD |
| S43 | Sensitive active record is retired | Current-tip tombstone omits body/target/title/summary/excerpts; history limitations remain explicit |
| S44 | Target-backed record is forgotten while its document remains | Receipt reports residual source exposure; coordinated source removal is a separate authorized change |
| S45 | Draft exists in cache/journal/native staging/vault/export queue | Logical invalidation and purge inventory cover each copy, with unavailable remotes/backups reported |
| S46 | Credential-shaped value is in metadata, preview or tombstone | Recursive publication checks reject the planted value outside the main body too |
| S47 | Native writer rewrites its own MEMORY.md | Accepted rendered generation is separate and unchanged; provisional native context is not represented as approved |
| S48 | Strict profile runs on a host with uncontrollable native memory | Doctor reports unsupported isolation, rather than claiming total prompt separation |
| S49 | Dream merges records with distinct measurements, exceptions and source revisions | Per-input disposition and source-to-output mappings preserve associations; planted identifier loss is reported, semantic preservation still requires review |
| S50 | Dream completes with active records, fake reviewer metadata or a policy patch | Output remains provisional; job completion does not affect accepted recall or grant publication authority |
| S51 | Record, source or accepted policy changes while dream is running | Pre-application baseline checks require reconciliation; external edits and prior valid view survive |
| S52 | Two worktrees run dream, then one job crashes and retries | Immutable job manifests and private directories stay separate; checkpoints recover without stale candidate/session mixing or duplicate publication |
| S53 | Dream reaches budget, is canceled, has empty input, an uncertain paid-call result or lacks a capable selected executor | Explicit terminal/result state and cumulative retry budget receipt; no blind resubmission, launch without required isolation or false semantic completion |
| S54 | Dream proposes an escaping route, private transcript publication or executable instructions | Route/schema/publication checks expose the planted violation; synthesis output never becomes tool/config authority |
| S55 | Repeated observations conflict with one explicit normative decision | Frequency/timestamps do not decide authority; both evidence and conflict remain reviewable, one-off decisions can be proposed |
| S56 | Record is retired while dream runs or before a checkpoint resumes | Known retirement invalidates dependent output/preview and triggers cleanup; publication cannot resurrect it without the explicit restore contract |

Filesystem tests use temporary repositories on real supported filesystems. Windows path and concurrency tests are not replaced by mocks that only reproduce the implementation. Gate selftests run at the oldest and newest supported Python versions, with intermediate versions/OS combinations in the broad compatibility lane.

## 7. Behavioral evidence

The question is whether shared memory changes useful outcomes for a fresh worker, at an acceptable cost. Seeing a hook fire or a `MEMORY.md` exist is not enough.

Use matched disposable repository snapshots and holdout tasks. An initial teacher session receives information that cannot be reconstructed from the worker's code alone, such as a compatibility commitment or a chosen external procedure. An independent worker starts without the teacher transcript. Its expected action is graded deterministically from produced artifacts and tool traces.

Compare at least these conditions:

- Existing harness without the new shared-memory feature.
- Native personal auto memory only, where host capabilities permit the comparison.
- A manually written equivalent project instruction/document, to distinguish knowledge availability from retrieval quality.
- Proposed shared memory with the same accepted facts.
- Proposed shared memory with stale, contradictory and irrelevant records added.

Do not use plugin-installed versus plugin-absent alone to measure a feature designed to survive plugin removal. The native plugin evaluator remains useful for assessing adoption behavior; runtime benefit needs memory-enabled versus memory-disabled paired fixtures after equivalent scaffold installation.

Required tasks include cross-person/fresh-machine transfer, relevant recall, irrelevant abstention, explicit correction, outdated-source abstention, supersession, multiple worker convergence and a restarted/compacted session. At least one negative control corrupts delivered memory in a detectable way to prove the delivery channel can affect the worker; that is a channel test, not desirable production behavior.

For dream, compare independent-worker behavior using the same corpus before and after accepted consolidation. Preserve teacher/worker separation and include distinct measurements, scope exceptions and misleading repetition. Evaluate omitted constraints, wrong generalization, stale/withdrawn reuse and transfer success alongside cost. A shorter store or higher retrieval-hit count alone is not a benefit.

Report sample sizes, exact agent/host/model versions, seed/fixture revisions, task outcome deltas, confidence intervals, wrong-memory usage, cost and elapsed time. Repeat across the intended model backends. The WikiSkill training/validation/final-test split discipline can be reused; do not optimize on the final transfer set.

Release claims require zero failures on deterministic isolation/publication/recovery contracts, plus a demonstrated beneficial transfer effect without a material regression on unrelated tasks. A numeric effect threshold and non-inferiority margin must be registered before paid runs using the task owners' tolerated risk/cost; this document does not invent measured performance or statistical power.

## 8. Performance and observability

Benchmark 100, 1,000 and 10,000 records on declared hardware and storage. Measure cold rebuild, warm lookup, hook latency, startup bytes/tokens, candidate backlog and recovery time separately. A full rebuild is background/explicit work; a hook exceeding its configured budget reports degraded recall rather than blocking indefinitely.

Initial engineering targets are a 100 ms warm local lookup and a one-second hook wall-time cap on the documented benchmark machine. They are targets to validate, not claims about the current implementation. Cold-start behavior must remain useful through a bounded entry point even when an index is absent.

Local diagnostics explain why a record was delivered, excluded, stale or conflicted, including view and record digests. Metrics default to counts, timings and IDs; query text, memory bodies and transcript fragments are not sent to an external analytics service. Any team telemetry exporter has its own explicit data policy.

## 9. Complete delivery checklist

These are completion criteria for one integrated feature, not a succession of deliberately incomplete releases:

- Record/policy schemas, versioned migrations and a stable operation contract.
- Git authority/view resolution with worktree, branch, dirty-state and offline semantics.
- Durable capture, deduplication, CAS/transaction recovery, proposal preparation and review integration.
- Bounded dream jobs, immutable inputs, traceable synthesis, loss/conflict reports, cancellation and recovery through the same proposal pipeline.
- Eligibility-first recall, bounded projections, context epochs and invalidation.
- Tested native/cloud/subagent adapters with capability diagnostics and documented fallbacks.
- Live-profile identity, notice validation, replay handling and offline reconciliation, if shipped as supported.
- Scaffold/template wiring, upgrade/uninstall behavior and compatibility documentation.
- Deterministic failure cases, independent worker-transfer evaluations and reproducible cost measurements.

Implementation can be divided among owners according to the dependency graph: schema/identity precede store and evidence; those precede capture and recall; adapters use the stable operations; distribution and acceptance exercise the assembled system. That division organizes engineering work without shrinking the target product.

## Consulted

See the exact source register in [research](research.md). Existing integration anchors include `shared/scripts/scaffold.py`, `shared/scripts/context/before_write.py`, `shared/optional/wikiskill/knowledge.py`, `shared/optional/agentroom/store.py`, `.github/workflows/ci.yml` and `evals/README.md` at the revision recorded by the [plan index](README.md).
