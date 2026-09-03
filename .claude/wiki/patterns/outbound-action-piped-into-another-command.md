---
count: 42
sessions: [2026-08-29, 2026-08-30, 2026-09-02]
route: guard
status: shipped
ships: shared/scripts/guards/no_piped_outbound.py
---
# git push, a mutating `gh`, or curl/wget-with-body piped into another command

## What happens
Across 4 sessions the agent shortens a transcript by piping an outbound
action into something else — a push into `tail`, a `gh pr create` into a
follow-on command, a `curl -X POST` into `jq`. A pipeline reports the exit
status of only its last stage, so a rejected push or a failed create reads as
success, and every step after it proceeds on a change that was never made.

## Why nothing caught it, or what did and how late
`no_piped_outbound.py` blocks this before it runs, 42 times over. That is not
a stale count: replaying all 42 captured commands against today's guard, 20
still trigger, so the habit is current, not historical (the other 22 no
longer match — the guard's own statement-splitting and quote-blindness were
themselves fixed mid-run, once on this repository's own test fixtures, per
its docstring). Once blocked, the outcome splits 28 `retried_changed` to 14
`moved_on`: the reason's replacement — capture output, then filter — is
concrete enough that the model adopts it in the same turn most of the time.

## The cheapest thing that would
Already shipped, and doing its job. The finding here is not a gap: it is
that this is the single most frequently triggered check in the repository,
and worth knowing that before anyone reads it as unused.
