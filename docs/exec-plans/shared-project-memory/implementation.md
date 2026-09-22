# Shared project memory implementation plan

> For agentic workers: use subagent-driven-development with isolated file ownership, behavioral selftests, task review and a final integration review.

**Goal:** Deliver repository-owned memory capture, recall, consolidation, proposals, retirement, validation and adoption, with reproducible Archify diagrams in the README.

**Architecture:** Git stores reviewed records; Git administrative storage holds private sessions, jobs and disposable views. All mutations use one validator and proposal/CAS pipeline. The default deployment is Git-only; optional remote/native capabilities are reported explicitly and never simulated as available.

**Tech stack:** Python 3.9+ standard library, Git, repository-local skill and Claude Code command hooks; Node only for development-time Archify rendering.

**Spec:** [Architecture](architecture.md), [operations](operations-and-experience.zh-CN.md), [acceptance](integration-and-validation.md).

## Global constraints

- Copied runtime must work after plugin removal; no mandatory external Python dependencies.
- Private material lives outside the tracked worktree, partitioned by session/worktree. Missing session IDs generate random tokens.
- Exit 0 means judged success, 1 means detected violation/conflict, 2 means could not judge. CLI JSON also exposes status.
- Acceptance is derived from trusted Git history and prior policy, never from record metadata or dream completion.
- Recall pins immutable source versions and overlays latest known retirements; scope and freshness are checked before ranking.
- Python tests use disposable real Git repositories and filesystems. Plant failing fixtures before implementing their behavior.
- Never silently overwrite local edits, enable external model spending, transmit private material or push/merge changes.
- No source file exceeds 2,000 lines; use small modules and clear public contracts.

## Shared interfaces

All modules live under `shared/scripts/memory/` and are copied to `scripts/memory/`. Package imports are relative; CLI entry points add their parent directory for direct execution.

```python
class MemoryFailure(Exception):
    # status in conflict, invalid, stale, unsupported, unjudged
    status: str
    details: dict
    code: int

def canonical_bytes(value: object) -> bytes: ...
def digest(value: object) -> str: ...  # sha256 of canonical JSON
def validate_record(record: dict) -> dict: ...
def validate_policy(policy: dict) -> dict: ...

class Repository:
    root: Path
    git_dir: Path
    private: Path
    def __init__(self, root): ...
    def git(self, *args: str) -> bytes: ...
    def resolve(self, ref: str) -> str: ...
    def policy(self) -> dict: ...
    def initialize(self, accepted_ref: str) -> dict: ...
    def view(self, environment=None) -> dict: ...

def recall(repo, query='', paths=None, environment=None, budget=None) -> dict: ...
def verify(repo) -> dict: ...
def validate_tree(repo, base=None, result=None) -> dict: ...

class MemoryStore:
    def __init__(self, repo, session=None): ...
    def remember(self, record, processing_id=None, origin=None) -> dict: ...
    def candidates(self) -> list: ...
    def propose(self, ids) -> dict: ...
    def apply(self, proposal_id) -> dict: ...
    def forget(self, record_id, reason, private=False, replacement=None) -> dict: ...

class Dream:
    def __init__(self, store): ...
    def prepare(self, ids=None, max_bytes=1048576) -> dict: ...
    def finish(self, job_id, output=None) -> dict: ...
    def inspect(self, job_id) -> dict: ...
    def cancel(self, job_id) -> dict: ...
```

`Repository.view()` returns `status`, `policy`, `records` (list of eligible active records), `excluded` (ID/reason entries), and `receipt`. It does not read provisional records as accepted. `recall()` adds ranked bounded `records` and a rendered `text`; verification and validation return findings and exit semantics. Local adoption fixes a trusted accepted-ref/policy anchor outside tracked files; first bootstrap without history stays draft-only. CLI reports first-clone adoption requirements explicitly.

`MemoryStore` owns the session token and exposes `repo`, `session`, `directory`. Candidate receipts return `id`; proposed changes return `id`, `changes`, `status` and private preview path. Applying writes only a reviewable working-tree change, never creates Git acceptance. Dream returns `id`, job `state`, result status and private output location. It may produce a deterministic consolidation report without a model, while external semantic output is validated as provisional input, with complete source mapping and baseline checks.

## Task 1: Validated records and versioned recall

**Owner files:** `memory/{__init__,errors,schema,repository,evidence,retrieve}.py`, `memory/test_foundation.py`.

- [x] Write real-Git failing cases for unaccepted branch data, fake policy edits, old-branch withdrawal, stale sources, malformed/duplicate-key JSON, Unicode budgets and conflicting claims.
- [x] Implement strict schemas and size/path limits, prior-policy Git authority, immutable view receipts, scope/freshness checks and deterministic relevance ranking.
- [x] Implement merge-result validation including tombstone deletion/restore checks against explicit trusted base.
- [x] Run `py -3.12 -m unittest discover -s shared/scripts/memory -p test_foundation.py -v`, record red/green evidence, review this task.

## Task 2: Capture, proposals, transactions and dream

**Owner files:** `memory/{store,dream}.py`, `memory/test_operations.py`; consumes Task 1 interfaces.

- [x] Write failing cases for private session isolation, duplicate events, CAS conflicts, interrupted multi-record apply, purge, immutable job replay and non-self-acceptance.
- [x] Implement private candidates, source-preserving exportable proposals, baseline-checked atomic per-file writes with journal/recovery and whole-generation validation.
- [x] Implement immutable bounded dream preparation, deterministic evidence/dedup report, separate synthesis output, input/output disposition validation, cancellation, recovery, cumulative budgets and withdrawal checks.
- [x] Run `py -3.12 -m unittest discover -s shared/scripts/memory -p test_operations.py -v`, record red/green evidence, review this task.

## Task 3: CLI, adoption, hooks and release validation

**Owner files:** `memory/{cli,install,host,selftest}.py`, `memory/test_integration.py`, scaffold/CI tables, repository-local memory skill, user guide and plan state.

- [x] Write failing fresh-clone/plugin-removal CLI and installation fixtures. CLI dispatches only the shared interfaces above; no duplicate authority logic.
- [x] Add init/inspect/remember/recall/verify/propose/apply/forget/sync/dream/doctor/export/import/check operations with JSON receipts and explicit nonzero diagnostics.
- [x] Add hash-safe versioned runtime installation, exact owned-hook upgrades, custom-file preservation and CI wiring proposal. Wire opt-in adoption into scaffold/template distribution.
- [x] Add bounded startup/prompt/compaction delivery and native/cloud capability diagnostics. Unknown host profiles use explicit recall; no undocumented hooks or native memory guarantees.
- [x] Run the memory suite, related scaffold/context/template checks, repository surface checks and full local CI runner. Distinguish baseline Windows issues from regressions.
- [x] Exercise the complete teacher-to-new-clone CLI lifecycle. Do not claim model-level transfer benefit from a CLI fixture.

## Task 4: Archify documentation and independent review

**Owner files:** `.github/assets/diagrams/07-shared-memory*`, development renderer/source and README/diagram-gallery entries.

- [x] Verify the selected public Archify repository and pin its source revision; render locally without sending repository contents to a service.
- [x] Preserve editable diagram source, reproducible rendering instructions, attribution and readable light/dark output.
- [x] Put the architecture diagram and accurate feature entry into README, link the operational guide.
- [x] Independently review runtime and integration diffs, fix important findings and update the acceptance coverage ledger before delivery.

## Execution record

The task ledger and detailed red/green/review reports live in ignored `tmp/shared-memory-implementation/`. The plan index records shipped versus unsupported capabilities and remaining external evaluation work. Optional adapters are never presented as tested implementations merely because their contracts exist.
