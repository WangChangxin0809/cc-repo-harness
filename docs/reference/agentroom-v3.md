# AgentRoom preview: from claims to reliable concurrent editing

- **Covers**: coordination, captured editing, CRDT convergence, recovery, and integration boundaries.
- **Does not cover**: an OS-level file lock, arbitrary filesystem-write interception, semantic correctness, or reproduction of the paper's published benchmark.

## Five coordination tools

The paper-facing surface keeps `room_claim`, `room_release`, `room_state`, `room_broadcast`, and `room_read`. The preview adds `room_join`, `room_open`, `room_apply`, `room_delete`, and `room_rename` to make participant identity and version-aware editing explicit.

A shared MCP connection can host multiple subagents only after each one calls `room_join(name)` and uses its own actor token. Tokens separate accidental identity collisions; they are not an OS security boundary.

## Captured editing path

```text
room_open -> text + actor-bound causal snapshot
          -> compute desired text from that snapshot
room_apply -> derive CRDT operations relative to the read
           -> merge concurrent operations
           -> commit state and project to disk
```

A write that never entered this path cannot be recovered later merely because a CRDT is present. Native Write/Edit/Bash operations remain outside capture. The runtime detects observed external drift and stops rather than silently overwriting it.

## Two explicit profiles

`paper` uses the official MCP SDK and `pycrdt`/Yrs. Missing dependencies are a **could not judge** result, never a silent fallback.

`reference` is a standard-library RGA + newline JSON-RPC implementation for offline inspection and deterministic tests. It is not Yjs/Yrs wire-compatible and must not be reported as a reproduction of the paper's native implementation.

## Claims are coordination, not correctness

Claims prevent well-behaved participants from choosing the same work. They do not replace Git worktree coordination, host permissions, or project tests. Two agents can preserve every edit and still produce an invalid combined interface; the final merged state must pass the repository's own validation.

## Recovery

The SQLite transaction records CRDT state, receipts, events, and a filesystem outbox before projecting a file. On restart, pending projections are replayed only when disk content matches the previous or intended digest. A third version is surfaced for review rather than overwritten.

Reference: [AgentRoom, arXiv:2608.23740](https://arxiv.org/html/2608.23740v1).
