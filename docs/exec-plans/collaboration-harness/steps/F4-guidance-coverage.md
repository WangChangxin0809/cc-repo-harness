# F4 · The guidance coverage gate

A gate that fails when the plugin ships an artefact kind it does not teach.

## Consulted

None, and none is needed. Every input this step has is internal: the plugin's own
directory layout is the list of kinds, and the exit-code contract is already
fixed by `writing-checks`. An outside search here would be the ceremony version
of this rule rather than the point of it.

## Why a gate and not a checklist

The uneven coverage this phase fixes — four kinds taught, three not — was not
noticed by anyone. It was found by listing the kinds on purpose, which is
something that happens once. Repair without a gate means the same drift restarts
the day after F1–F3 land, and the next person to notice will be a year out.

This is the nursery rule: a diagnosis that recurred graduates into a check. It
recurred here in the strong sense — the gap existed across every artefact kind
added since the plugin started, silently, for the whole of that time.

## What has to be decided

**What counts as an artefact kind.** Too fine and the gate demands a document
per script; too coarse and "scripts are covered" hides that hooks are not. The
honest unit is *a thing a contributor sits down to author* — a skill, a subagent,
a gate, a guard, a hook, a CI workflow, a document kind, a subtree `CLAUDE.md`.
That list is enumerable and each entry is something a person actually starts
from scratch.

**How the gate knows coverage exists.** The weak version greps for a filename
and passes on a heading that says nothing. The strong version requires the
guidance to name the kind and to state which check holds it — which is the
adjacent step's rule (F5) and gives this gate something falsifiable to look for.

**Where the list of kinds lives.** If the gate carries its own list, adding a
kind means editing the gate, and whoever forgets to gets a pass. Deriving it from
what the plugin actually ships is better and harder: the plugin's own directory
layout is the closest thing to ground truth.

## Exit codes

Three states, as everywhere: 0 covered, 1 a kind ships with no guidance, **2 the
list of kinds could not be determined**. If the gate cannot enumerate what the
plugin ships it has not judged anything, and it says so rather than passing.

## Done when

- [ ] The gate has been watched failing — remove one kind's guidance, see red
- [ ] The failure message names the kind and where its guidance belongs
- [ ] It cannot be satisfied by an empty heading; injection proves that
- [ ] Green only after F1–F3 have actually closed the gaps

## Notes

*(Decisions land here as the step runs.)*
