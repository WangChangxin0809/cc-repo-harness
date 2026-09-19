# AgentRoom-inspired optional runtime · 0.3.0

- **Covers**: coordination, causal-snapshot text editing, local recovery, installation, protocol verification.
- **Does not cover**: a kernel lock, arbitrary filesystem-write interception, semantic correctness, original-paper benchmark reproduction.

## Two explicit profiles

`paper` is the default: official `mcp==2.2.0` and `pycrdt==0.14.4` (Yrs).
It selects the paper's CRDT family, not an assertion of source-identical reproduction.
Install its dependencies in a dedicated Python 3.10+ environment. No dependency
is installed automatically. Missing dependencies are exit 2 and **never** select
the reference implementation silently.

`reference` uses only the Python 3.9+ standard library: a bounded RGA sequence
CRDT and newline JSON-RPC MCP stdio, supporting 2025-11-25 and three earlier
handshake revisions. It is NOT Yjs/Yrs update compatible, does not advertise
2026-07-28 support, has no HTTP transport, and is not the official SDK.

```bash
python3 shared/optional/agentroom/install.py --root /path/to/repository
python3 shared/optional/agentroom/install.py --root /path/to/repository --apply
```

These commands preview/apply a copy under `scripts/room/` and merge exactly one
`.mcp.json` entry. Existing other servers survive; conflicting local edits abort.
No hook, tool permission, model access, background service, branch or commit is created.
The root must be a Git worktree. A separate worktree is a separate room.

```bash
python3 -m venv /path/to/private/room-env
/path/to/private/room-env/bin/python -m pip install -r /path/to/repository/scripts/room/requirements.txt
/path/to/private/room-env/bin/python /path/to/repository/scripts/room/server.py --root /path/to/repository --profile paper
```

Set `ROOM_PYTHON` for the child-interpreter path in the generated Claude Code MCP
entry, or replace the command with an explicit path in the host's own configuration.
Other MCP hosts may not understand Claude Code environment interpolation: use
absolute paths and an explicit `--root` there. Do not pipe debug text into stdio.

For dependency-free inspection, explicitly install with `--profile reference`.
A later profile switch requires a reviewed configuration change. There is no
silent installer upgrade over customized files.

## Tools and participant identities

Original coordination names: `room_claim`, `room_release`, `room_state`,
`room_broadcast`, `room_read`. Engineering additions: `room_join`, `room_open`,
`room_apply`, `room_delete`, `room_rename`.

One independent stdio server process creates one participant. Subagents sharing
that MCP connection must each call `room_join(name)` and pass its `actor_token`
to all subsequent tools. These tokens separate accidental identities; they do
not protect mutually hostile processes running as the same OS user. Tokens are
not portable between connections. Losing a connection loses its read/identity
session; outstanding leases expire, rather than being taken over by name.

Lease IDs are fresh capabilities. A stale owner cannot release a replacement
lease. Expiry does not terminate OS processes. `room_state(renew=true)` renews
only that participant's still-live leases. Names are labels, never authentication.

## Captured editing protocol

1. Inspect `room_state`; claim every file you intend to change. On refusal, choose
   different work or exchange an interface agreement via `room_broadcast`.
2. Call `room_open(path)` to receive text plus an actor-bound causal snapshot.
3. Compute your desired full text relative to **that** read, then call
   `room_apply(snapshot, text, request_id)`. Exact retries return the same receipt.
4. Inspect the **merged** returned text and run the project's real tests. Broadcast
   contract changes/results; consume `room_read` using the returned cursor.
5. Release current leases. A single coordinator owns Git branch/index mutations.

For new files, `room_open(path, create=true)` prepares a managed empty document.
Delete/rename requires live claims and a current revision; rename requires both
paths and never overwrites an existing destination. It fences old snapshots.

The CRDT computes operations against the read snapshot; concurrent insertions
unseen by a writer are not erased merely because its replacement text lacked them.
The RGA profile retains tombstones. Native profile retains raw Yrs updates,
including out-of-order dependencies; neither does unsafe implicit compaction.
A native journal exceeding 16 MB requires an explicit future checkpoint/migration.

**Native Write/Edit/Bash writes do not enter this capture path.** The room checks
its last projected file digest and stops on observed external drift. That is a
conflict detector, not an OS-level compare-and-swap: a hostile or uncoordinated
writer racing the digest check can still win a filesystem race. Claims are
advisory by default. `--strict-claims` gates only the room's own write tools.
Use OS isolation and controlled mounts when stronger guarantees are required.

## Crash and projection contract

The SQLite transaction records CRDT state, receipt, event and filesystem outbox
before a file is replaced. Projection uses a same-directory temporary file,
fsync and replacement. After an interrupted projection, the next mediated
operation replays the outbox only if the disk matches the previous or intended
hash. An unexpected version is never knowingly overwritten.

This is durable/recoverable, not a multi-file transaction visible atomically to
arbitrary filesystem readers. A rename can transiently expose both paths.
Keep build/test processes coordinated with multi-file changes.

If a human deliberately wrote outside the room, inspect the difference first:

```bash
python3 scripts/room/room_cli.py --root . --backend rga reconcile shared.txt --choose disk  # docs-runnable: ignore
python3 scripts/room/room_cli.py --root . --backend rga reconcile shared.txt --choose disk --expected-sha REVIEWED_SHA --apply  # docs-runnable: ignore
```

Use `--backend pycrdt` for a native room. The second command requires the exact
reviewed digest (`absent` for a missing file). Both versions are backed up in
private Git state. Reconciliation is intentionally NOT an autonomous MCP tool.

## Bounds and local state

Only regular UTF-8 text files up to 128,000 bytes are managed. No NUL, path escape,
`.git`, glob, symlink, hardlink, binary file or directory target. Snapshots expire
after one hour and are bounded per actor. RGA state has an explicit node cap.
Messages and tool input have limits; there is no implicit whole-history injection.

State lives under the worktree Git directory, not under tracked `docs/` or Wiki.
Peer messages and source text are untrusted and can contain private material;
exported events require human review/redaction. Local file mode restrictions
are not a sandbox against the same OS user. SQLite is a local-host coordinator,
not a distributed network lock service and not tested on NFS.

## Verification

```bash
python3 shared/optional/agentroom/selftest.py
python3 shared/optional/agentroom/install_selftest.py
python3 shared/optional/agentroom/protocol_selftest.py
```

The last requires pinned external libraries and uses two official SDK clients;
missing libraries exit 2. The separate delivery-package suite also covers four
simultaneous OS processes, same-connection subagents, causal merge, generation
fences, filesystem drift and a process killed after commit before projection.
Official SDK clients are not a claim that Claude Code/Codex host behavior was tested.

Reference: https://arxiv.org/html/2608.23740v1 . Public tool names and architecture
are reconstructed; original unpublished wire details and benchmarks are not invented.
