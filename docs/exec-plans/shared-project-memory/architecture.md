# Shared project memory architecture

This document specifies proposed behavior. The [plan index](README.md) owns implementation status; [research](research.md) separates observations from design choices. The [Chinese operation guide](operations-and-experience.zh-CN.md) specifies `remember`, `recall`, `dream`, verification and withdrawal with architecture diagrams and a worked example.

## 1. Scope and alternatives

The product is reusable repository machinery for teams using Claude Code, including compatible model providers. It must work in a new clone and after the scaffolding plugin has been removed. Knowledge is ordinary inspectable data; the core does not require a model API, vector service or online coordinator.

| Approach | Strength | Limitation | Decision |
|---|---|---|---|
| Point native auto memory at a Git directory | Closest to native UX | Couples private notes and team authority; native shared-worktree behavior does not provide branch review, semantic merging or a portable relative directory setting | Not the canonical store |
| Use an online shared database as authority | Fast cross-machine updates | Adds availability, identity, hosting and offline dependencies; a clone alone is insufficient | Optional transport/cache only |
| Version individual records in Git and build host-specific views | Reviewable, branch-aware, offline and compatible with repository ownership | Needs capture, validation and host adapters | Selected architecture |

Complete design does not mean all installations require all services. Git-only and connected collaboration are deployment profiles of the same data and consistency model, not different maturity levels.

## 2. Non-negotiable contracts

- An accepted fact is traceable to an exact record version and an acceptance policy.
- A record never grants tool permissions, shell execution, network access or authority to change that policy.
- Personal information is private by default. Sharing an item is a distinct publication action under the team's policy.
- A fresh clone can discover accepted memory without the author machine, an external database or the installation plugin.
- Framework recall never silently promotes a different branch/worktree/repository's provisional facts. Unmanaged host memory is outside this guarantee and is reported explicitly.
- No last-writer-wins rule resolves contradictory claims. Timestamps help readers judge age, not truth.
- An unavailable source, host capability or validator is `unjudged`, not green.
- The system can withdraw a fact from future retrieval; it cannot erase a model's existing context or all copies of Git history.

## 3. Four storage domains

| Domain | Content | Owner and lifetime |
|---|---|---|
| Repository | Policy and accepted/proposed-on-branch record files; existing docs/rules | Git history and repository review |
| Private workspace state | Candidate outbox, origins, native capture staging, processing checkpoints | Local user; partitioned by worktree/session |
| Derived views | Search index, selected indexes, host projections, freshness results | Rebuildable; exact snapshot and policy version in each cache key |
| Collaboration exchange | Update notices and explicitly shared proposals | Optional authenticated service; never the sole durable record |

Proposed tracked layout:

```text
.harness/memory/
  config.json
  records/
    <stable-id>.json
docs/                         existing authoritative knowledge
.claude/                      host wiring and repository-local skills
scripts/memory/               runtime copied into target repositories
```

Each record is one UTF-8 JSON file. Its optional `body` is an array of Markdown lines, rendered by joining with a newline; canonical formatting keeps each source line separately diffable. Inline content is limited to 4 KiB UTF-8 after rendering. Longer material belongs in an authoritative document referenced by `target`, which is the preferred form for existing knowledge. JSON is chosen for unambiguous standard-library parsing, one-file atomic replacement, stable validation and no new YAML dependency. A generated Markdown view supplies a short index and topic files through framework recall; it is never put in a native auto-memory write directory. Those views are disposable and never a second editable source of truth. Proposal tooling also produces a semantic diff and readable Markdown preview.

Private worktree state is rooted under the absolute administrative Git directory returned by `git rev-parse --absolute-git-dir`, then partitioned by a random local session token. Linked worktrees therefore have separate state. Git's common directory holds only repository-level identity/coordination metadata. Never use a shared `nosession` fallback: a missing host session ID gets a new local token, and attachment/resume requires its stored receipt. Before worktree removal, pending candidates can be exported explicitly to a private user outbox; removal without that step cannot promise their retention. Cloud containers may use a host-provided private state directory with its own declared durability. Private state is outside the tracked tree, not merely protected by an ignore pattern. Credentials and absolute machine paths never enter tracked configuration.

A random repository namespace is created on adoption. Forks inherit records but do not automatically inherit authorization to an upstream collaboration room. Remote authorization binds namespace plus the authenticated repository/tenant; namespace alone is not proof of membership.

Private candidate durability is explicit: `filesystem` survives process restarts while that Git directory exists; `user-vault` additionally persists to an authenticated, user-private remote outbox when configured; `ephemeral` can be lost with a cloud sandbox. The vault is not the team relay and does not publish candidates to teammates. A deployment requiring durable cloud capture must provision persistent storage or the private vault; doctor reports exit 2 if only ephemeral storage is available. Accepted Git records have their own durability regardless of this choice.

## 4. Record model

The schema is versioned. Unknown major versions are rejected explicitly, not partly interpreted.

Core schema limits are explicit: a record file is at most 64 KiB UTF-8, its title 160 bytes, summary 512 bytes, rendered inline body 4 KiB, evidence list 16 entries and dependency list 64 entries. Limits are validated before indexing; oversized material is a referenced source rather than silently truncated canonical knowledge. Candidate/storage quotas stop accepting additional content with a visible reason; unresolved candidates are never silently discarded merely to make a quota green.

| Field | Contract |
|---|---|
| `schema_version`, `id` | Schema version and immutable, path-safe identity |
| `kind` | `decision`, `constraint`, `procedure`, `pitfall`, `context` or `reference` |
| `title`, `summary` | Human label and bounded retrieval summary |
| `body` or `target` | Exactly one: bounded Markdown line array, or `{path, content_digest, section?}` for an authoritative source |
| `scope` | Repository namespace, relevant relative paths, task tags and optional environment predicates |
| `claim` | Optional explicit key plus JSON value; only these structured claims have deterministic semantic-conflict checking |
| `evidence` | Source type, stable locator/version, content digest or Git object identity, and optional exact excerpt range |
| `freshness` | Dependency checks, optional expiry, and last human verification date |
| `supersedes` | Explicit predecessor IDs; acyclic, with a stated replacement reason |
| `restores` | Optional exact prior retirement identity plus reason; required for deliberate reactivation |
| `state` | `active` or `retired`; acceptance is derived separately from Git and policy |

Validation is state-dependent. The content fields above apply to active records. A retired record instead contains only `schema_version`, `id`, `state: retired`, and a `retirement` object with the previous record digest, a bounded non-sensitive reason code/text and optional replacement ID. It forbids `body`, `target`, evidence excerpts, title and summary. Its own digest is the retirement identity used by a later `restores` field. Thus a minimal tombstone can remove sensitive current-tip metadata as well as the body; the separate Git-history limitation still applies.

Git object IDs are treated as opaque algorithm-qualified identities; the schema does not assume every repository uses SHA-1. Independent SHA-256 digests identify imported bytes. Canonical record hashes use a specified deterministic JSON serialization, while concurrency checks also compare the exact existing file bytes.

`evidence` admits different truth claims:

- A repository source uses a commit/object identity and a relative path. A line range without a source version is insufficient.
- A test observation records the tested code revision, command identity and result artifact digest. Passing once does not imply timeless correctness.
- An explicit team decision is a normative declaration accepted through review. It does not need fictitious test evidence.
- An external reference records the URL, captured version/digest and observation time. An unreachable URL cannot be declared fresh.
- A user's instruction is summarized into a shareable decision with attribution allowed by the user/team policy; the private transcript is not copied into Git.

When a source and its referencing record change in the same proposal, evidence pins the intended source blob/content digest. It does not try to embed the not-yet-known commit ID of that same record, which would create a circular hash dependency. The finalized view receipt supplies the enclosing commit identity after integration.

An existing document remains its own authority. A memory record pointing to it stores routing metadata and a source-bound summary, not a competing copy of the document. On source change, the old summary stops being served as verified knowledge until refreshed.

The core scope grammar allows exact repository-relative paths, a directory prefix ending in `/**`, or `**` for the whole repository. It excludes arbitrary regex, negation and brace expansion. Environment predicates are conjunctions of named keys with finite allowed string/boolean values. Pairwise path-prefix and value-set intersection are deterministic; missing environment facts produce `unjudged` applicability. Task tags guide retrieval, not proof that contradictory claims have disjoint scopes. Paths preserve Git's identity and use `/`; case/Unicode aliases that cannot be resolved safely on the current filesystem are reported rather than normalized into another file.

## 5. Authority is separate from content

A record's own `state`, author name, timestamp or claimed reviewer cannot make it accepted. The reader derives an authority tier:

| Tier | When applicable | Treatment |
|---|---|---|
| Accepted team knowledge | Record bytes are present in the configured accepted history applicable to the checkout | Eligible for ordinary recall after freshness checks |
| Branch proposal | Record added/changed in the current branch outside accepted history | Visible as a proposal, never silently relabeled as a team decision |
| Session observation | Explicit local candidate with this session's provenance | Available to its owner; not broadcast by default |
| Incoming proposal | Another participant deliberately shared it through an authorized channel | Attributed, provisional and outside ordinary accepted recall |

Repository policy declares the accepted ref and review expectations. Real enforcement comes from branch protection or an explicitly configured trusted integration process, not a JSON declaration. Setup reports whether that enforcement has been checked; offline mode can use a previously known accepted ref but must show its synchronization age.

An initialized deployment loads acceptance policy from its already accepted policy snapshot. A branch that edits its own policy cannot use that edit to approve its own records. Initial trust and a deliberate session-local policy override are explicit adoption actions; a repository UUID or an arbitrary remote name is not sufficient authentication.

An unborn repository or first adoption has no inherited accepted history. It operates in draft-only mode until an explicit bootstrap policy and initial integration establish that authority. Setup does not guess that an arbitrary current branch or similarly named remote is trusted.

For an ordinary feature branch, resolve a unique accepted ancestor with Git merge-base against the locally known accepted ref. The accepted view is read at that ancestor; branch and dirty-worktree changes form labeled overlays. Multiple merge bases, missing history or an unresolved accepted ref produce an explicit `unjudged` state. They never fall back to calling arbitrary HEAD content approved.

An accepted-ref update ahead of the checkout produces a delta notice. Knowledge that depends on newer code is not activated in an older checkout. After the checkout is reconciled, rebuild the applicable view. Explicit branch-independent organization decisions may be delivered as attributed updates, but cannot override a code-dependent fact without resolving applicability.

Withdrawals have stricter semantics than positive updates: retirement/revocation events from the latest authenticated known accepted tip form a negative overlay over every older branch view. They suppress that record even when the checkout still uses an ancestor containing its active version. A reviewed restore lifts suppression only for the explicitly restored record version when it is applicable; it does not resurrect arbitrary ancestral bytes. Every receipt includes the last-known revocation watermark. Offline use cannot know about later withdrawals, so it reports that limit; policy can require recent revocation knowledge for selected sensitive record classes and return `unjudged` when unavailable.

A recall pins its positive snapshot but rechecks the latest locally known revocation overlay before emitting content, so an older generation handle cannot bypass a newly observed withdrawal. Notices and subsequent cleanup invalidate affected derived views; already delivered model context remains subject to the stated forgetting limit.

Each view has a receipt containing repository namespace, checkout HEAD, accepted ancestor/ref tip, record-set digest, policy digest, dirty-overlay digest, adapter version and freshness-check time. Identical inputs yield identical eligible records.

Dirty canonical files are excluded from accepted automatic recall. They can be inspected through an explicitly labeled proposal preview, as can session candidates. A committed branch overlay is read from an immutable Git tree. The accepted snapshot, rather than the worktree's current filesystem contents, supplies source bytes for an accepted `target`; changed source bytes mark the current applicability stale rather than being silently substituted under an old accepted digest.

## 6. Reading and context delivery

Retrieval first filters by authority, lifecycle, repository, branch/environment applicability and freshness. Ranking cannot bring an ineligible record back into results.

Core ranking is deterministic: explicit record/path match, task tags, then Unicode-aware lexical matching. Stable IDs break ties. Embeddings or a model reranker are optional adapters and operate only on the already eligible set; they neither create approval nor repair missing evidence. Indexes are local and rebuildable.

| Moment | Delivery |
|---|---|
| Session start | Small orientation, view receipt, unresolved material conflicts and memory entry point |
| User prompt | Bounded task-relevant summaries when a supported hook can supply context |
| Before a relevant path is touched | Source links and applicable record IDs, coordinated with existing `Governs:` routing |
| Explicit recall | Full selected records with provenance and exclusion reasons |
| Resume/compaction | New context epoch; rebuild orientation and reset appropriate deduplication state |
| Accepted update or withdrawal | At the next observable host boundary, state what changed and invalidate affected cached results |

The Claude Code adapter uses command hooks at SessionStart. Official startup behavior can skip an MCP-tool SessionStart hook before servers connect, and SessionStart does not accept an HTTP hook. `UserPromptSubmit` can use supported command/HTTP/MCP mechanisms, but the default path remains local. `PostCompact` records invalidation state; `SessionStart` with source `compact` performs context delivery. Their handlers are idempotent and do not assume an undocumented relative ordering.

Suggested default hard byte budgets, to be measured rather than presented as token estimates: 4 KiB at startup, 8 KiB per explicit recall response and 16 KiB total automatic supplemental delivery per context epoch. Automatic path hints select at most four records. A generated native index stays below both 100 lines and 8 KiB, comfortably below the host's documented limits. Overflow is reported with a recall route, not silently treated as complete coverage.

Budgets are product defaults, not proven optimums. Telemetry records actual tokenizer usage when the host exposes it. A hard behavioral constraint belongs in a guard/gate or host permission, not in an item that may be omitted to fit a retrieval budget.

A `PreToolUse` hint can arrive after the action has already been planned. It is not a guarantee the first action follows that hint. Required prevention uses the existing guards; memory supplies explanation and relevant knowledge.

Rendered knowledge has a fixed provenance wrapper stating that it is reference material, cannot override user/repository instructions and cannot grant permissions. This is an aid to instruction hierarchy, not proof against prompt injection. Runtime never executes memory text or writes it into settings, rules or guards. Promoting a fact into an enforced rule is a separate visible change, with the repository's required checks for new guards/gates.

## 7. Capturing discoveries

All framework-managed capture paths end in a private candidate before publication:

1. Explicit `remember`/`forget` requests interpreted by a repository-local skill and written through the repository CLI.
2. An agent notices a reusable decision or correction during work and proposes a structured candidate, with the same origin and scope requirements.
3. An optional native-memory adapter observes changes in an explicitly selected private memory location and stages the diff for classification.
4. A user explicitly imports a selected external/native/cloud memory export. There is no implicit import of all historical sessions.

The classifier separates personal preference, durable project knowledge, transient task state, unresolved hypothesis and already-represented knowledge. A model may propose the classification; deterministic checks enforce schema, allowed paths, maximum size, known credential patterns and source existence. Publication scanning recursively covers every textual field, including title, summary, Markdown lines, source URLs/excerpts/labels, target sections, lifecycle reasons and tombstones. It also scans generated semantic diffs/previews, export bundles and any explicitly transmitted proposal body. Pattern scanning does not prove absence of sensitive material; all publication paths still use the selected review policy.

Every candidate carries a private origin receipt: session/worktree identity, observed HEAD, target-record baseline hash, source channel and processing ID. Idempotency is based on the processing ID and semantic content hash, not wall-clock order. Local originals can be retained under an explicit retention policy; they are not an automatic evidence attachment to a PR.

The publication pipeline is:

```text
observe -> private candidate -> classify and deduplicate -> validate
        -> explicit proposal diff -> team acceptance -> versioned recall
```

The agent can perform classification and prepare the full diff automatically. Default acceptance is the repository's normal review/merge process. A team can configure automatic acceptance for specified, mechanically verifiable classes, with scope, provenance and required checks stated in policy. Neither a generated candidate nor a retrieved page can enable that mode.

Hooks collect receipts or schedule bounded local work. They do not launch an unbounded recursive agent, silently spend a model API budget or push/merge Git changes. A Stop hook is not the only persistence point: process termination can occur without it. Candidate creation and processing checkpoints are durable as they occur.

### Dream maintenance

`dream` is a bounded producer of candidates and proposals, not another memory store. It reads an immutable manifest of accepted records, explicitly selected private candidates and allowed sources. Its optional semantic executor writes to a unique private job output directory. Core orchestration remains standard-library code and shares candidate validation, evidence checks, CAS and proposal generation with `remember`. An unavailable semantic executor is reported rather than silently counted as completed synthesis.

The job proposes deduplication, source-bound summaries, contradictions, stale-record maintenance and routing into authoritative docs/rules or a separate guard/gate change. Every input has an explicit output disposition; every proposed conclusion retains its evidence, scope, exceptions and source-version associations. Verbatim-loss checks are aids, not proof of semantic preservation. Frequency, timestamps and model confidence do not resolve truth or grant acceptance. Job completion never accepts a record or executes proposed code.

Jobs retain input/output digests, provenance mappings, checkpoints, budget usage and findings. Defaults are manual; configured automation must bound input, time, model cost, concurrency and retry. Retries/resumes share the logical job's cumulative budget; an uncertain external call is reconciled through executor receipts/idempotency support or left unjudged, never blindly resubmitted. An executor without required isolation is not launched. Hooks enqueue work rather than run unbounded synthesis. Resume and publication recheck source/record/policy baselines and known withdrawals. Changed baselines require reconciliation; retired content invalidates dependent output and enters the purge inventory. The detailed job/result states and user-facing operation contracts are in the [operation guide](operations-and-experience.zh-CN.md).

The existing consolidation workflow supplies the snapshot/synthesis/loss-review pattern. Its mutable default output directory and informal text diff do not satisfy these job, privacy or authority contracts; reuse requires independently tested extraction, not renaming the existing CLI. Its earlier preference for later notes in a contradiction must not carry into shared-memory decisions.

## 8. Native Claude Code and cloud adapters

The universal repository path uses checked-in instructions, repo-local skills, the memory CLI and supported hooks. Personal native auto memory continues to work independently; installing shared memory does not rewrite the user's global settings.

The optional native capture adapter can launch a session with an isolated absolute `autoMemoryDirectory` using supported host settings, once that host/version has passed compatibility checks. The directory is private and worktree/session aware. Accepted knowledge is exposed as a generated view through the repository read path; native notes are proposals, not automatic edits of canonical records.

The directory boundary is strict: native auto memory contains provisional native notes only. Accepted rendered views live in a separate immutable generation directory and are delivered by repository recall/hooks, not by native `MEMORY.md` startup injection. The native host may still read its own provisional notes; doctor labels that as provisional host context, not framework-approved recall. A strict branch-isolation profile must isolate or explicitly disable native memory for that session before launch. It is unsupported on a host that injects uncontrollable memory; a cloud Project's separate memory cannot be assumed configurable through the local setting. No global setting is changed to manufacture this guarantee.

Do not point native auto memory directly at the canonical record tree or symlink a global shared-worktree memory directory into it. Do not assume changing a setting from a SessionStart hook affects memory the host has already loaded. Adapter setup must happen before launch; attach-to-running-session mode uses normal repository recall.

Native capture watches only its declared directory, records an initial manifest, and processes newly created/modified files against that baseline. A rescan recovers changes missed by file events. A deletion becomes a withdrawal candidate, not a remote delete. Hook visibility of native writes is a capability to test, not a requirement for correctness.

`FileChanged` is an acceleration signal, not an exactly-once capture protocol. Its matchers seed literal filenames and its dynamic `watchPaths` replace an explicit absolute-path list; no recursive-directory subscription is assumed. Session start, subsequent prompt boundaries and explicit maintenance rescan the bounded capture directory, so a new topic file omitted from the watch list is still discovered. FileChanged only marks local work pending; later supported context hooks deliver notices. Background native extraction can finish after a turn's visible response, so checkpoints must not equate Stop with extraction completion.

Local terminal/IDE sessions use the same repository runtime. Cloud sessions clone the canonical store with the repository. For a multi-repository cloud Project, official host behavior may not load each repository's settings hooks; the guaranteed fallback is the checked-in instruction/skill entry point plus an explicit per-repository bootstrap. Setup must report whether automatic delivery is active rather than pretend a copied settings file was loaded.

Anthropic's cloud Project memory is a separate store. No documented universal export/import or synchronization API is assumed. This design supports an explicit user-provided export through the importer, not undocumented client endpoints. Server-side consistency and conflict rules remain outside the inspected client evidence.

Subagents receive explicit memory scope and a view receipt. Native `memory: project` directories are writable agent notes, not evidence that a note has completed team review. A parent session's memory must not be assumed to appear in every subagent; the adapter passes the required context or asks it to recall from the repository.

Framework-provided read-only reviewers do not enable native subagent `memory`, because the host automatically enables Read/Write/Edit when it is set. Their memory access is through read-only recall. Framework-managed workers also use the private candidate operation instead of native `memory: project`, whose fixed `.claude/agent-memory/<agent>/` path is inside the tracked tree; `memory: local` is merely gitignored and does not satisfy the outside-tree isolation contract either. Existing user-defined native-memory agents are reported as separate, unmanaged storage. Adoption preserves them and offers an explicit import/migration; it does not claim all host-written memory now obeys the framework's privacy boundary.

## 9. Concurrent writers and transactions

Different worktrees have separate candidate queues and views. Different records normally merge as different Git files. A generated aggregate index is never a frequently edited tracked hotspot.

Updating an existing record requires the expected baseline hash. If it changed, the operation returns a conflict with both versions. No silent overwrite or last-write-wins merge is permitted. Textually disjoint changes to the same record still require schema and claim validation.

Within one worktree the runtime serializes its own writers, stages changes in a private transaction journal, validates the intended record set, then atomically replaces individual files. Multi-record changes are not claimed to be a single filesystem atomic operation. Readers retain the prior valid snapshot until a complete, internally consistent generation is available. Recovery checks old/new digests; an unrelated external edit becomes a recovery conflict rather than an overwrite.

The visibility protocol is explicit: journal each intended path with old/new exact-byte hashes and a generation ID; stage and validate the complete record set; write an immutable private generation manifest with a completion marker; atomically replace the current-view pointer only after validation succeeds. Readers pin that manifest for an operation. Recovery accepts only old or intended-new file bytes and leaves the old pointer active on failure. Git-committed views use immutable Git trees directly. Arbitrary editors' multi-file writes are not transactions the runtime can infer; they stay drafts until an explicit validated proposal snapshot exists.

Git/editor changes bypassing the runtime remain possible, as with any repository file. They trigger a rescan and validation before the next snapshot. Runtime locks protect cooperating processes, not arbitrary programs or malicious writers.

Conflict handling has three levels:

1. Same identity and baseline mismatch: deterministic edit conflict.
2. Same explicit claim key, overlapping scope and incompatible values: deterministic claim conflict, including separate files from independent PRs.
3. Contradictory free text or unknown scope overlap: a review finding/model-assisted suspect, not a mechanically proven contradiction.

Scope comparison uses a bounded documented pattern grammar. When overlap cannot be proven or disproven, the result is `unjudged`; it does not choose a winner. Resolution creates an explicit replacement/reconciliation with evidence and retains the supersession history. CI examines the proposed merge result, so two individually valid branches cannot evade the structured-claim check simply by changing different files.

## 10. Freshness, contradiction and forgetting

Freshness checks are content-based where possible. Changing a depended-on file invalidates its captured digest; that means the claim needs reassessment, not that it is logically false. Renames can retain a source identity only after an explicit verified mapping. Merely reaching an external URL does not verify the old statement.

Ephemeral status such as a branch name, test result or current plan progress stays in existing live reports/exec-plans, with pointers from memory if useful. It does not become a timeless memory fact. Mutable external facts carry an expiry or explicit revalidation policy.

Retirement keeps a minimal tombstone containing identity, reason and replacement pointer as appropriate. Active indexes and caches exclude retired content. The merge-result gate receives a trusted accepted-target/base OID and proposed-result OID, not just the final worktree. Deleting a tombstone or changing it back to active requires `restores: {retirement_record_hash, reason}` naming that retirement. Missing base/history is exit 2. A restore is a new reviewed revision; reverting an unrelated commit cannot satisfy that condition accidentally. Bypassing the required gate or rewriting protected history remains a server-side branch-protection concern.

`forget` distinguishes local draft removal, retirement from future team recall, and a request to remove sensitive data from history. Only the first two are ordinary memory operations. Historical removal requires the repository's separate history-rewrite and secret-response process; Git clones, backups and already-delivered context cannot be guaranteed erased by this runtime.

Retiring a target-backed routing record removes that route and its derived summary, not the fact from the authoritative document. The forget receipt reports that source as residual exposure. With appropriate authorization, the proposal can include a coordinated edit of the source document; ordinary document readers and old Git versions otherwise remain able to see it. The system never equates forgetting an index entry with erasing its source.

Private removal has an explicit inventory: candidate body/origin material, processing checkpoints, generated previews and indexes, native staging, local database/WAL/journal copies, pending exports and queued relay proposals. The local operation cancels retransmission and invalidates affected generations before best-effort deletion/compaction. It requests deletion from a configured user vault or content-carrying relay and collects acknowledgments. The receipt distinguishes logically removed/unreachable copies, acknowledged remote deletion, unavailable remotes and retention/backups beyond its control. Filesystem/SSD forensic erasure is not promised. A body-carrying transport must declare its deletion/retention contract before it can be selected for that profile; the default relay remains ID/digest-only.

An active session that already read withdrawn material receives an invalidation notice at the next supported boundary. For a material withdrawal, the runtime recommends a fresh context and marks the old view unusable for new recalls. It cannot guarantee a model has forgotten text already in context.

## 11. Optional live collaboration

The live profile adds an authenticated relay or a host-supported session channel. The existing local AgentRoom may supply transport mechanics for cooperating local participants; cross-machine authentication and durable remote operation are separate work, not capabilities its current SQLite store implies.

Messages carry repository/tenant binding, producer identity, sequence, event ID, base revision, record digests and one of `accepted-tip`, `proposal-available`, `withdrawal` or `conflict`. Default notices contain IDs/digests, not transcript text. Sharing proposal bodies is explicit and subject to the same publication policy.

Withdrawal notices never repeat the withdrawn body. Existing AgentRoom event logs do not provide a general purge contract, so that bridge transports IDs/digests and a recall locator, not private or retractable memory bodies.

Recipients verify membership and authorized repository binding, deduplicate IDs, reject replayed sequence ranges and validate payload bounds. An `accepted-tip` message is only a hint to obtain the corresponding Git objects through an authorized remote and verify applicability. It cannot turn an arbitrary transmitted paragraph into accepted knowledge.

Offline clients continue using a labeled local snapshot and queue explicit outgoing proposals. Reconnect resynchronizes from durable Git history and a bounded relay cursor. Missed or reordered notices do not change the final accepted state. Expired relay events are recoverable; the relay is not the only place a team decision exists.

Transport failure does not block ordinary coding or fabricate a fresh view. Revocation stops future authorized retrieval; previously copied data cannot be remotely erased. No background automatic pull/rebase, forced push or merge is part of a memory hook.

## 12. Components and failure behavior

| Component | Owns | Does not own |
|---|---|---|
| Repository resolver | Git identity, worktree, accepted view and overlays | Inferring team permission from a record |
| Record store and validator | Schema, CAS edits, lifecycle, transactional recovery | Deciding free-text truth |
| Candidate processor | Capture receipts, classification, dedup and proposal preparation | Automatically granting team acceptance |
| Dream coordinator | Immutable jobs, bounded synthesis, provenance/loss reports and candidate output | Accepting its own output, silently deleting knowledge or running generated code |
| Evidence checker | Digests, applicability, source freshness and explicit claims | General semantic entailment |
| Retrieval/view renderer | Eligibility, ranking, budgets and receipts | Canonical editing or permission changes |
| Host adapters | Supported event wiring, epoch handling, native capture | Private cloud protocols |
| Collaboration adapter | Authentication, notices, retry and reconciliation | Replacing Git authority |
| CLI and diagnostics | Inspect, remember, recall, dream, verify, propose, forget/retire, sync, doctor and export operations | Hidden network/model spending |

Core copied runtime remains Python 3.9+ standard library. SQLite may cache local indexes and transactions but no SQLite database is committed as shared truth. Optional dependencies stay in opt-in adapters with explicit installation and failure reporting.

Machine-readable results distinguish `ok`, `empty`, `conflict`, `stale`, `unsupported` and `unjudged`. Gate exit codes preserve repository convention: 0 judged clean, 1 detected violation, 2 could not judge. An absent optional adapter is an explicit deployment state, not a failing core feature; a selected required adapter that cannot run is `unjudged`.

## Consulted

See [research and evidence](research.md) for the source register and [integration and acceptance](integration-and-validation.md) for module mapping, compatibility tests and adversarial cases.
