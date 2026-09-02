# 0043 — A mechanism is not a convention

Date: 2026-09-02
Status: accepted
Narrows [0025](0025-dimension-4-asks-whether-an-agent-can-find-its-way.md), which
refused to score a repository on what it keeps.
New: `surface.py`, sub-item 4.0.

## Context

0025 refused to count what a repository keeps, and gave three reasons. Every
one of them is about **conventions**:

1. it grades a repository on whether it adopted somebody else's layout
2. it goes *up* when this plugin is installed — the instrument rewarding its
   own presence
3. it called [0024](0024-skills-are-payload-except-the-one-that-finds-them.md)
   — which cut the standing cost by 81% — a regression, while dimension 5
   called it an improvement

Those reasons hold, and this decision does not touch them. `scripts/gates/` is
our convention. A repository that keeps its checks in `tools/` keeps its
checks, and marking it down for that is marking it down for disagreeing with
us -> [0020](0020-the-assessment-measures-behaviour-not-resemblance.md).

But 0025 then took the reasons further than they reach, and the
overreach cost something real. **A `PreToolUse` hook is not a convention.** It
is the only place a tool call can be refused before it happens. A repository
without one has not chosen a different way of refusing actions — it has no way
of refusing actions, and usually the reason is that nobody knew the moment
existed. The same is true of every other place the product offers: there is no
alternative route to *a fact that opens every session*, or *knowledge that
arrives only when it is needed*.

Treating those as conventions meant the page could not say the most useful
thing it knows about a repository it has just read: **here are the places
nothing is wired, and here is what therefore cannot happen.**
`probe_repo.py` had been computing exactly that, under the heading
`EMPTY MOMENTS`, and it never reached the page.

## Decision

Sub-item **4.0, the surface it uses.** For each mechanism Claude Code offers,
whether this repository has anything at it, and for each empty one, what
therefore cannot happen there.

The admission test for the list: **is there another way to get this effect?**
If yes, it is a convention and does not belong. Twelve entries pass it — the
seven delivery moments, plus scoped rules, subagents, slash commands, MCP
servers, and the end of a turn.

Three rules keep it from becoming the thing 0025 rejected, and each is pinned
by a case that goes red when it is broken:

**Coverage, never a count.** Present or absent per mechanism, nothing else.
Six skills are the same coverage as one. 0024 deleted five skills that all sat
at the same moment, and this row does not move — which is the test 0025 itself
used.

**The repository's own, never the machine's.** A skill a plugin installed is
on somebody's laptop, not in the tree; a teammate who has not installed the
plugin gets nothing from it. Only `origin: repo` counts, so the instrument
cannot reward its own presence. This repository scores 6 of 12 under that
rule, because its skills and agents are the *plugin's* — which is exactly what
[0021](0021-the-repository-keeps-the-harness-the-plugin-keeps-the-instrument.md)
requires of them.

**Every absence says what it costs.** A row that lists what is missing without
saying what is lost is a scold, and a reader cannot act on it. `no
PreToolUse hook` alone is a fact about a file; *"no action can be refused
before it happens, and a destructive one is complete the moment it runs"* is a
finding.

## Consequences

**It narrows, and the agent judges.** An absent mechanism is a candidate, the
same as 4.2's. A repository can be right to have no MCP server, no subagents,
no `UserPromptSubmit` hook. The machine says which places are empty and what
each empty one costs; which of those absences is correct here is a reading.

**It is the one row that improves by being told about a feature.** Every other
measurement here reports something the repository did. This one reports
something it may simply not have known about, which is the cheapest kind of
finding to act on and the one nothing else on the page can produce.

**It does not restore what 0042 removed.** That was the claim *this `CLAUDE.md`
is carrying an agent*, which needs a difference between two runs and cannot be
had cheaply. This says only that a place exists and is empty, which is a fact
about a file and holds still.
