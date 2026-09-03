---
count: 21
sessions: [2026-08-28, 2026-09-01, 2026-09-02]
route: guard
status: open
ships: shared/scripts/guards/no_foreground_poll_loop.py
---
# a wait for CI, a PR check, or a background job, run as a foreground loop

## What happens
Across 4 sessions the agent waits on something slow — a GitHub Actions run, a
PR's checks, a file a background process will eventually write — by writing
a synchronous shell loop: a bare `sleep N; <check the thing>`, or the wrapped
form, `for`/`until` around a `sleep` and a status check. Both shapes tie up
the turn for as long as the wait takes.

## Why nothing caught it, or what did and how late
The bare form is caught, but not by anything in this repository: the
platform's own auto-mode classifier refuses a leading `sleep` followed by a
poll, 7 times over. Its remedy — the Monitor tool, or `run_in_background` —
does not change the next action: all 7 end in `moved_on`, not a retry with
the suggested tool. The wrapped form is caught by nothing at all until it is
too late: the Bash tool's own 2-minute default kills it mid-loop 11 times
(`retried_changed` 7, `moved_on` 4), and 3 times the person watching stopped
it by hand rather than wait — the one outcome worth weighing above the
others, since it is the person's own label, not an inferred one.

## The cheapest thing that would
Extend the same judgment the platform already makes for a bare `sleep` to
the wrapped shape: a `for`/`while`/`until` body containing `sleep` without
`run_in_background: true` in the same call is exactly as blind as the form
already refused, just spelled differently. Block it pre-emptively and point
at the same remedy the Bash tool's own description already states, so the
model does not have to discover the 2-minute wall by hitting it.
