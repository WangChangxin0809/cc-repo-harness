# 0049 — The instrument asks a hook only what Claude Code would ask it, and the matcher names every tool a guard judges

Date: 2026-09-02
Status: accepted

## Context

The second reading of this repository at 1.4.1 scored dimension 1 lowest,
and the reader for 1.1 said why: the fact sheet read `refused before they
happen: 6/6`, but the dispatcher was wired `matcher: "Bash"`, and two of
the six probes are not Bash calls. `blast.py` and `permitted.py` fired every
probe at every PreToolUse hook. `catch.py` had honoured the matcher since
0032, for exactly the reason written there: a Bash-only hook asked about an
Edit answers a question Claude Code never puts to it. Its two siblings had
not been given the same rule, so the headline of dimension 1 was the
instrument talking to itself. The honest number was 4 of 6.

The 4 was not the instrument's fault. Three guards here judge Write and
Edit -- `no_committed_credential`, `no_silenced_check`, `no_computed_delete`
-- and `dispatch.py`'s own docstring said to widen the matcher the first
time a guard judged a non-Bash call. Nobody had. Because the dispatcher
fails open, an unasked guard and a quiet one look identical at runtime, and
nothing said so.

That silence hid a third thing. `no_silenced_check` judged the *edited
text* alone for a failure path, so a reworded docstring in a gate would have
been refused as "replaces it with something that cannot fail". It had never
fired in a live session, so nobody had seen it. And it did not know that a
guard fails by returning a reason: it refused a whole-file replacement of a
guard that could still refuse. Meanwhile `no_piped_outbound`, which does
run, split every command on every `|` regardless of statement boundaries
or quotes, and refused the capture-then-filter form its own reason text
recommends. A guard refusing its own remedy is a guard somebody turns off.

## Decision

**The instrument fires a probe only at the hooks Claude Code would run for
that tool.** `blast.py` and `permitted.py` select with `catch.applicable`,
as `catch.py` does. Both halves of dimension 1 are the same firing on
purpose, so they get the same rule.

**The matcher names every tool a guard judges**: `Bash|Write|Edit|MultiEdit|
NotebookEdit`, here, in the scaffold, and in the plugin's own hook. Not
`*`, because an interpreter start on every Read buys nothing.

**The guards' selftest checks the wiring.** For every tool some guard's
CASES say it refuses, the nearest `.claude/settings*.json` that wires
`dispatch.py` must have a matcher that names it; otherwise the selftest is
red and says which guard is a file that never runs. It is silent when
nothing above the guards wires the dispatcher: then the wiring is somebody
else's, or absent, and neither is its subject. Its own red was watched in
the scaffold's acceptance suite, on a tier A repository whose matcher is
narrowed back to `Bash`.

**`no_silenced_check` judges the file after the edit**, not the edit. It
reads the file, applies the replacement, and refuses only when the file
could fail before and cannot after. An empty `old_string` is a whole-file
replacement, which is the shape the instrument sends. A file it cannot read
is judged as before when the whole of it is being replaced, and left alone
otherwise. Under `guards/`, returning anything but `None`, `0`, `False` or
an empty string is a failure path.

**`no_piped_outbound` reads statements and quotes.** A command is split into
statements at `;`, `&&`, `||` and newlines outside quotes; only an outbound
command upstream of a pipe *in the same statement* counts; quoted text is
data. `$(git push)` inside double quotes is still missed, and the docstring
says so -- the guard is a speed bump, as 0021 and its own dispatcher say.

**`no_protected_branch_push` strips heredoc bodies first.** It refused the
command writing a selftest case that named `git push origin main`, twice,
while the guard beside it was being fixed for the same mistake.

**The silence probe is aimed at a check that can fail.** Once the guard
judges the file after the edit, a probe aimed at an empty `__init__.py`,
taken because it sorted first, is a probe the guard correctly allows, and
the page would read `nothing stops it` about a repository that stops
exactly this. `factsheet.py` now skips helpers, `__init__.py` and
`conftest.py`, and takes the first file with a failure path in it. The
agent that rewrote the guard found this before it shipped.

## Consequences

The headline of dimension 1 is a number about the repository. On this one
it reads 6 of 6 again, now because the guards are asked.

Every Write and Edit in a scaffolded repository now pays the dispatcher's
interpreter start, about 45 ms. That is the price of the two guards that
were bought and never installed.

Two guards that had never fired on an edit now do, and the reading is the
thing that will say whether they refuse ordinary work. Their first live
session is the next assessment's 1.2.
