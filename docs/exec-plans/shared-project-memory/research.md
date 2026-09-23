# Shared-memory research and evidence

**Research date:** 2026-09-22. **Repository revision:** `dad6c6c7dca71eb4fcedce83d799e453d2675765`.

This register distinguishes official documented contracts, static observations in a particular release artifact, and proposed design decisions. It does not claim recovered original source, server-side implementation knowledge or behavioral validation from static inspection alone.

## 1. Method and artifact identity

The installed Claude Code command reports **2.1.261** and resolves to the Windows x64 executable distributed by the npm package. Its public release artifact contains readable minified JavaScript alongside native/Bun material. Analysis used byte searches and bounded code windows to follow relevant local control flow. Embedded code was not executed, the installed program was not patched, and user histories, credentials and private services were not accessed.

| Artifact | Identity |
|---|---|
| Installed client | Claude Code `2.1.261`, Windows x64; PE version `2.1.261.0` |
| Executable size | 218,728,608 bytes |
| Executable SHA-256 | `f2f5d1a155167488aeb32cd263e15436253c7b1681ae147c9e73e4d6bbc3c852` |
| Public distribution | [claude-code-win32-x64 2.1.261 package](https://registry.npmjs.org/@anthropic-ai%2Fclaude-code-win32-x64/2.1.261) |
| Repository eval pin | `2.1.273` in `eval/agent/package.json`; not the executable analyzed |
| Narrow comparison | Residual local `2.1.260` executable; same checked constants and control-flow signatures at shifted offsets |

The [evidence manifest](evidence.json) contains the package integrity metadata, executable fingerprints and hashes of locally captured official pages. Downloaded pages and short local analysis notes are ignored research material under `tmp/shared-memory-research/`, not redistributed client source. Snapshot hashes describe the saved text bytes; a subsequently changed official page is not expected to have the same hash.

Offsets below are hexadecimal byte offsets in the exact 2.1.261 executable. Minified function names are only search anchors, not stable interfaces. Another build must be independently located and checked.

## 2. Official source register

| ID | Official source and relevant section | What it establishes |
|---|---|---|
| D01 | [Memory](https://code.claude.com/docs/en/memory#auto-memory), Storage location and How it works | Machine-local auto memory; shared across same-repository worktrees; `MEMORY.md` index plus on-demand topics; documented 200-line/25KB startup budget |
| D02 | [Settings reference](https://code.claude.com/docs/en/settings-reference#automemorydirectory) | `autoMemoryDirectory` requires an absolute or `~/` path; current docs permit settings scopes subject to workspace trust and read policy |
| D03 | [Projects](https://code.claude.com/docs/en/claude-projects#give-a-project-standing-context) | Every project thread reads shared Project `MEMORY.md`; this is separate from local memory and repository `CLAUDE.md` |
| D04 | [Projects limitations](https://code.claude.com/docs/en/claude-projects#limitations) | Current redesigned Projects belong to one user; sharing a Project/its threads with another user is not available in this beta |
| D05 | [Projects redesigned](https://claude.com/blog/projects-redesigned), September 17, 2026 | Coordinator plus cloud threads; shared memory builds over time; rollout statements do not establish a public organization-memory API |
| D06 | [Subagents](https://code.claude.com/docs/en/sub-agents#enable-persistent-memory) | `user`, `project`, `local` memory scopes; project scope can be version-controlled; enabling persistent memory automatically enables Read/Write/Edit |
| D07 | [Hooks](https://code.claude.com/docs/en/hooks#sessionstart) and MCP tool hook fields | SessionStart context delivery; command hook is available on first launch; launch MCP hooks can be skipped before servers are ready; SessionStart is not an HTTP hook |
| D08 | [FileChanged](https://code.claude.com/docs/en/hooks#filechanged) | Filesystem-based notices independent of tools; literal watch filenames, dynamic absolute `watchPaths`; no ability to block a completed file change |
| D09 | [PreCompact/PostCompact](https://code.claude.com/docs/en/hooks#postcompact) and SessionStart | Compaction lifecycle, side-effect-only PostCompact and `SessionStart(source: compact)` for context; no reliance on undocumented relative ordering |
| D10 | [Cloud sessions](https://code.claude.com/docs/en/claude-code-on-the-web) and [Project repository loading](https://code.claude.com/docs/en/claude-projects#what-threads-pick-up-from-your-repositories) | Cloud does not inherit local user settings; multi-repository Project workers do not apply individual repositories' settings hooks/permissions/env |
| D11 | [Cross-session messaging](https://code.claude.com/docs/en/cross-session-messaging) | Messaging among one's own sessions; text transport, not shared files/history or a documented cross-user team bus |

The documented hook event list has no memory-specific write event. General tool events and file watchers are useful, but official documents do not guarantee that every main-session auto-memory write is a visible Write/Edit call. A Project's internal memory storage/API is also not specified by these pages.

Project-memory and local-auto-memory budgets must not be conflated. The documented 200-line/25KB limit in D01 is a local auto-memory contract; D03 does not specify that same server-side limit.

## 3. Static client findings

### S01: worktree sharing is built into default directory resolution

- Configured directory resolver `UF` is visible around `0xAEEC465` (its precedence-list region).
- Default directory computation is at `0xAEEC633`; it uses a canonical repository-root-derived project key.
- Linked-worktree canonicalization follows `.git`, `gitdir` and `commondir` around `0xADD54E3`.
- Workspace trust is checked by the visible resolver before repository-local settings enter its precedence list.

This supports a concrete design requirement: the team's branch-specific candidate queues cannot rely on the native default directory to isolate worktrees.

### S02: native memory has several different budgets

| Control | Location | Observed unit and meaning |
|---|---|---|
| Index constants | `0xAF6371A` | 200 lines; numeric limit 25,000 |
| Index truncation `EJe` | `0xAF72097` | 25,000 JavaScript UTF-16 code units via string length, not a strict UTF-8 byte limit |
| Index injection `Ua` | `0xAF73096` | Reads `MEMORY.md`, applies truncation, contributes it to the prompt |
| Index inspection reader | `0xB4F5B44`, `0xAD1B2AF` | Up to 100,000 actual bytes for inspection; this is not the injected context budget |
| Automatic topic selection | `0xB5D7C7C` | Up to five selected topic files per recall attachment |
| Topic read cap | `0xB5D7F30` | 200 lines / 4,096 UTF-8 bytes; shared reader uses `Buffer.byteLength` around `0xB1A0E88` and `0xB1A14ED` |
| Cumulative relevant-memory cap | `0xB5D1A24`, `0xB5D7EB8` | Constant named `MAX_SESSION_BYTES` is 61,440, but accumulation uses string length/code units |

These numbers are implementation observations, not proposed product defaults. The architecture uses explicit UTF-8 byte budgets, tests Chinese/multibyte content and reports actual token costs separately.

### S03: memory extraction can be a background auxiliary model call

- Main turn-end invokes the extractor around `0xB4EEFFA`, conditional on no `agentId` and a feature gate.
- Extractor setup/control flow starts at `0xB4E82B3`.
- A directly successful memory write since the last pass suppresses redundant extraction.
- Extraction skips turns without sufficient non-meta user prose. The visible default counts whitespace-separated words; a separate flag accommodates CJK text without spaces.
- The auxiliary invocation uses an extraction query source, `skipTranscript: true` and a five-turn bound around `0xB4E8570`.
- Concurrent triggers coalesce into a trailing run around `0xB4E8C6F`.
- A teardown/cleanup path awaits pending extraction around `0xC2435D4`, with an internal finite drain timeout; this is not proof that every termination path drains it.

This is internal control flow, not an official configurable hook event. Feature flags and account/host state can change whether it runs. Static existence does not prove a particular session used it. It does establish why ordinary transcript parsing and a Stop-only collector cannot be assumed complete.

The design adopts the useful principles of deduplication, bounded maintenance and coalescing. It does not copy private prompts, internal feature-flag names or hidden RPCs into a compatibility contract.

### S04: memory categories and agent scopes are distinct

- The local memory type set at `0xAF6416C` contains user, feedback, project and reference categories.
- Persistent-agent scope schema appears at `0xAEA0153`; path mapping is around `0xAF74769`.
- `project` maps into `.claude/agent-memory/<agent>/`; `local` maps into `.claude/agent-memory-local/<agent>/`; `user` maps under the user configuration directory.
- Agent startup paths append persistent-memory context; main-session memory must not be assumed inherited by every subagent.

The runtime's private candidate boundary therefore requires its own storage operation. Simply choosing a native project/local scope would not meet an outside-tracked-tree guarantee. Read-only reviewer agents must not enable a native setting that adds write tools.

### S05: the client contains gated organization-memory discovery and mounts

Three mechanisms must remain distinct: `CLAUDE_CODE_REMOTE_MEMORY_DIR` changes the local storage root in a remote execution environment; `CLAUDE_MEMORY_STORES` configures mounted memory stores; the gated organization-memory discovery flow locates/selects organization/project stores. A remote-looking local directory alone is not evidence of a synchronization service.

The discovery/mount code around `0xAF4CE77` through `0xAF4FB13` includes remote store discovery, response validation, cached selection and read-only/read-write grant handling. Selected stores use a team scope and a `MEMORY.md` prompt index. Access is routed through memory list/read/write operations; local personal memory remains separate. Prompt text around `0xAF6A538` describes organization project memory shared with other people/sessions.

This is stronger evidence than a stray string: there is client control flow for mounted stores and permission-aware access. It supports separating a store interface, capability checks and authorization from prompt rendering in our design.

It does **not** prove general availability, user entitlement, server consistency, conflict resolution, durability or a public integration API. It also does not overturn D04's documented restrictions for the redesigned Projects UI. These may be distinct or gated product surfaces. No discovered private endpoint was called, and the proposed adapter does not depend on it.

## 4. Differences and unresolved evidence

| Question | Evidence | Treatment |
|---|---|---|
| Is the local index limit literally bytes? | Docs say 25KB; this binary uses code units in that path | Record both; use our own explicit byte budget and compatibility tests |
| Is a checked-in custom memory directory ignored? | Schema text at `0xAD9532D` says ignored; resolver at `0xAEEC465` visibly considers trusted project settings; current docs permit them | Do not infer behavior from schema prose alone; test the selected supported settings path on the eval host |
| Is native team memory absent? | Public Projects UI is personal today, but gated remote-memory client machinery exists | Distinguish public support from latent implementation; use public extension surfaces |
| Will extraction always run, including Chinese prompts? | Feature-gated background flow and language-sensitive checks | Explicit remember remains supported; native auto-capture is capability-tested, with rescan and visible degradation |
| Does 2.1.273 behave like 2.1.261? | Not statically inspected here | No extrapolation; include the eval pin in required compatibility runs |
| What consistency does Anthropic's cloud service provide? | Client validation and requests, no server implementation | Unknown; define our own explicit Git/relay consistency model |

## 5. What this repository already implements

- `CLAUDE.md`, scoped rules and `docs/index.md` already make stable project knowledge version-controlled and discoverable.
- `shared/scripts/context/before_write.py` delivers scoped rules and `Governs:` references with explicit limitations. It is not deterministic first-action prevention.
- `.claude/wiki/` is a committed experience catalog deliberately excluded from ordinary inference; `/learn` is an explicit plugin workflow.
- `shared/optional/wikiskill/knowledge.py` implements immutable source versions, exact evidence ranges, stale detection and structured claim lint. Its private SQLite database and reviewer string are not a Git/team authority model.
- `shared/optional/agentroom/` has local transactional/outbox recovery and worktree-aware storage. It does not imply a remotely authenticated, cross-machine or purge-capable memory service.
- Scaffold installation skips existing payload and generated CI files; hook deduplication compares existing command strings. A complete memory feature therefore needs an explicit upgrade and CI-wiring contract.

An independent review of the first architecture draft identified and resolved missing retirement overlays for old branches, a trusted base requirement for reversion detection, complete-generation publication, safe upgrades, and JSON reviewability. Those corrections are in the [architecture](architecture.md) and [acceptance cases](integration-and-validation.md).

## 6. Existing Windows baseline findings

This investigation is a design change, not a repair of existing runtime tests. Repository review exercised selected existing suites with Python 3.12 on Windows:

| Existing suite | Observed outcome |
|---|---|
| Context hooks | 20 cases passed |
| WikiSkill preview | 5 cases passed |
| AgentRoom installer | 6 cases passed |
| AgentRoom coordination | 20 tests, one symlink-privilege skip; returned exit 2 as required |
| AgentRoom MCP protocol | Exit 2 because optional pinned dependencies were absent |
| Wiki replay | Passed |
| Wiki extractor | Path-normalization assertion failed on Windows |
| Scaffold acceptance | 3 of 13 cases errored when trying to execute `./ci.sh` directly |
| Docs routing gate | Windows separator mismatch reports `docs\\index.md` itself as unrouted; independently reproduced by the primary agent |

These observations are not evidence that the new memory feature has passed any runtime test. Windows path/shell portability and the selected optional test dependencies are prerequisites for claiming the complete compatibility profile. The new document routing is separately checked without modifying the existing gate.

## 7. Reproducing and extending the investigation

1. Obtain the exact public package version, verify its package integrity, then compare the extracted executable's SHA-256 and size with the manifest. A mismatched executable invalidates the listed offsets.
2. Read the indicated byte windows; distinguish readable code, schema descriptions, prompts and symbol strings. A string hit alone proves no running behavior.
3. Re-fetch the official pages and record new snapshot hashes/date. Treat documentation updates as new evidence.
4. Run supported black-box compatibility fixtures on the repository's pinned host and model/provider combinations. Observe actual memory files, contexts and tools without calling undocumented endpoints.
5. Feed differences into the capability matrix and tests; do not patch the user's Claude Code installation to make the design work.

## Consulted

Official sources D01–D11, the fingerprinted public release artifacts and the repository paths above. Full target behavior is in [architecture](architecture.md); completion criteria and implementation boundaries are in [integration and validation](integration-and-validation.md).
