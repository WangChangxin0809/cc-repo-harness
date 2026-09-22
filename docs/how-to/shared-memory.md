# Share project knowledge through Git

Repository memory stores reviewable records under `.harness/memory/records/`.
Private discoveries and dream jobs live outside the tracked worktree, under
Git's administrative directory. Existing documents remain authoritative;
records can point to an exact source digest instead of duplicating the text.

## Adopt

From this harness checkout, install into an existing Git repository:

```bash
python3 shared/scripts/memory/cli.py --root /path/to/repository install --accepted-ref refs/heads/main
```

Choose the actual integration ref. This is an explicit local trust decision,
not a claim that a similarly named branch is protected by your Git server.
Review and commit the generated runtime, configuration, repository skill and
hook changes. An initial repository stays draft-only until policy is accepted.
Installation preserves customized runtime files and reports conflicts; a vendor
manifest tracks owned file hashes and hook commands for future upgrades.
The installation receipt returns `ci_proposal`, a private workflow file, and
`ci_target`, its suggested repository destination. Review and copy that workflow
into `.github/workflows/`: it checks out the proposed merge result and a separate
validator from the trusted base, with full history. The first adoption needs
review because the base does not yet contain a validator. Configure the resulting
check as required in your Git host before claiming retirement enforcement.

The scaffold also accepts `--memory --memory-accepted-ref refs/heads/main`
at tier B/C. Those tiers copy the runtime and skill even without activation.

In a fresh clone, explicitly select the team's known integration reference:

```bash
python3 scripts/memory/cli.py init --accepted-ref refs/remotes/origin/main
python3 scripts/memory/cli.py doctor
```

On Windows, replace `python3` with `py -3.12` or your installed Python command.
Hook commands use `python3`; configure a working launcher in Claude Code's shell
if that name is a Windows Store alias. Installing this feature does not alter
global host settings or native auto memory.

Ordinary initialization and upgrades retain the existing local trust anchor.
Changing it deliberately requires `init --accepted-ref REF --readopt`; review the
new authority first. Failed or conflicting upgrades preserve the prior generation
and anchor. An interruption during initial adoption reports an unjudged recovery
state for inspection instead of silently establishing trust.

## Remember, review and recall

```bash
python3 scripts/memory/cli.py --session teacher remember --title "Keep v1" --body "Keep v1 until migration finishes." --reason "Team compatibility decision" --path 'src/api/**'
python3 scripts/memory/cli.py --session teacher propose CANDIDATE_ID
python3 scripts/memory/cli.py --session teacher apply PROPOSAL_ID
```

Use the IDs returned by each operation. `apply` produces a worktree diff.
Review, commit and integrate it using your team's ordinary process. It has no
Git push or merge side effect. Subsequent sessions can retrieve accepted facts:

```bash
python3 scripts/memory/cli.py recall --query "v1 compatibility" --path src/api/server.py
python3 scripts/memory/cli.py verify
```

Recall checks acceptance, current scope, evidence and latest known withdrawals
before ranking. Its result includes sources, exclusions and a version receipt.
Changed source bytes make a summary stale. Unaccepted branch edits and private
candidates do not become team facts by setting `state` to `active`.

For tracked sources, calculate digests from `Repository.source_bytes(path)`:
a clean CRLF checkout is compared using its canonical Git bytes. Dirty source
changes still invalidate the observation. Recall's `budget_bytes` limits the
rendered UTF-8 `text`, including its reference/provenance notice; structured
records and diagnostics have a separate 1 MiB canonical compact JSON limit.
Use `text` for automatic
context delivery, and the structured fields for explicit inspection.

Use `remember --record FILE.json` for a complete structured record, including
source references, environment predicates or explicit claim keys. The CLI's
`--help` and [schema implementation](../../shared/scripts/memory/schema.py)
define the supported fields. JSON files reject duplicate keys and unsupported
schema versions. Private session tokens are returned in operation receipts;
retain them to resume, rather than sharing one token among independent agents.

## Dream

```bash
python3 scripts/memory/cli.py --session teacher dream prepare
python3 scripts/memory/cli.py --session teacher dream inspect JOB_ID
python3 scripts/memory/cli.py --session teacher dream finish JOB_ID --output OUTPUT_PATH
```

Preparation returns an immutable input manifest, deterministic report and a
unique private output path. Ask your agent to synthesize only those selected
inputs into that file. The output contract carries `records`, per-input
`dispositions` and output `provenance`. Review the generated brief/receipt for
the exact keys. Finish checks provenance, evidence preservation, unchanged
baselines and withdrawals before producing a private proposal. Without an
output file, finish performs deterministic analysis and labels semantic synthesis
as unavailable. The runtime makes no model/API call and installs no scheduler.

Two measurements of the same system remain two observations. Contradictions
remain visible until resolved with evidence. An attractive shorter summary
cannot silently drop constraints or authorize a policy change. A proposed rule
or guard still goes through ordinary development and its required tests.

## Withdraw and synchronize

```bash
python3 scripts/memory/cli.py --session teacher forget RECORD_ID --reason "Replaced by the new migration decision"
python3 scripts/memory/cli.py sync --remote origin
```

The first operation creates a retirement proposal; use its returned proposal
through the review workflow. `forget --private` cleans selected private material.
Team retirement retains a minimal tombstone and suppresses old views once the
new accepted state is known. It does not erase Git history, already delivered
model context or a fact still present in its source document. Receipts report
residual source exposure. Explicit fetch never merges/rebases the checkout.
Freshness is renewed only when that remote supplies the adopted authority: use
its remote-tracking ref, or a local integration branch with a matching verified
upstream. An unrelated remote or a local branch behind the fetched tip cannot
refresh the withdrawal observation. Plain `sync` checks the local view only.

## Verification and supported boundary

```bash
python3 scripts/memory/selftest.py
python3 /path/to/trusted-base/scripts/memory/cli.py --root /path/to/candidate check --ci --base TRUSTED_BASE_OID --result PROPOSED_RESULT_OID
```

Pass the base from trusted CI context, not from a candidate's metadata. Tests
use disposable real repositories to exercise acceptance, isolation, stale
sources, publication, transactions and transfer to a new clone. These tests do
not establish model-level productivity gains.

The hook worker has a five-second hard timeout; installed host hooks allow seven
seconds including process startup. `host.py --timeout SECONDS` accepts an explicit
positive limit up to 30 seconds; adjust the outer host timeout accordingly.
Automatic context is capped per epoch, with
at most four path hints and reserved space for withdrawal notices. An invalidated
view pauses automatic delivery until a new context epoch. These limits are
delivery bounds, not a measured latency guarantee; explicit recall remains
available when a hook times out. Worker failures also emit a bounded notice on
supported context events so previously delivered memory is not silently treated
as freshly verified. A supervisor failure can prevent reading the epoch counter;
these short failure notices are bounded individually and may repeat outside the
normal cumulative content budget.

The delivered profile is local Git sharing plus explicit agent-assisted dream
output. Command hooks provide bounded best-effort context; they are not a
security guard. Multi-repository cloud sessions can use the explicit CLI when
repository hooks are not loaded. Remote relays, private cloud vaults, managed
Dreams, native-memory capture and strict host-memory isolation are unsupported
adapters reported by `doctor`. The [complete design](../exec-plans/shared-project-memory/README.md)
records their intended contracts separately from implemented behavior.

The [Archify architecture diagram](../reference/diagram-gallery.md) shows the
flow between private discovery, reviewed Git records and recall.
