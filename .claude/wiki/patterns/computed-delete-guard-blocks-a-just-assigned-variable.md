---
count: 4
sessions: [2026-09-02]
route: guard
status: shipped
ships: shared/scripts/guards/no_computed_delete.py
---
# `rm -rf "$VAR"` blocked though $VAR was set to a literal one line up

## What happens
Four times in one session, `no_computed_delete.py` refused an `rm -rf "$VAR"`
whose value was fixed a line or two earlier in the same command — a scratch
directory the command had just assigned to a variable, or a loop variable
walking a short, literal, written-out list. The guard's computed-path check
treats any `$VAR` as unreviewable, which is correct for `$(git ls-files |
head -20)` and wrong for a variable whose only possible values are sitting
in plain sight one line up.

## Why nothing caught it, or what did and how late
This is today's behavior, not a historical one: replaying all four commands
against the current guard still blocks every one of them. The outcome splits
1 `retried_changed` to 3 `moved_on` — the reason's suggested remedies
(`--dry-run`, name the paths) do not fit a directory the command just
created for itself, so most of the time the person worked around the block
a different way rather than following it.

## The cheapest thing that would
Exempt a `$VAR` from the computed-path check when the same statement assigns
it a literal, unexpanded string earlier (`VAR=<no $, no backtick>`), and
likewise a `for x in a b c; do ... $x ...; done` whose list is itself
written out in full. Anything still built from a subshell, a file, or an
unset variable keeps being blocked — the guard's own near-miss cases already
cover why that half must stay.
