# 0032 — A rung cannot be read without the layer behind it

Date: 2026-09-01
Status: accepted
The ladder printed the same character for "nothing is wired here" and "three
things are wired here and none of them worked".

## Context

Dimension 2's ladder reports *moments* — `before-write`, `same-turn`,
`local-suite`, `ci`, `never`. It does not report *mechanisms*, and without the
mechanisms a zero cannot be read:

| what the page printed | what it could mean |
|---|---|
| `before-write: 0` | no PreToolUse hook exists — the layer is absent |
| `before-write: 0` | two hooks are wired and neither caught anything |

The second is much the worse finding and it was indistinguishable from the
first. To say *where* a defect was caught you first have to know what there
was to catch it with.

## Decision

**An inventory row, printed immediately above the ladder**, so the ladder is
read against it. Each layer reports one of four states, and the four are the
point:

| state | meaning |
|---|---|
| `none wired` | the layer does not exist |
| `N caught` | it exists and it worked |
| `0 of N caught` | it exists, N defects reached it, it caught none |
| `nothing reached it` | it exists, and the rungs above caught everything first |

**The fourth state is not a footnote — it is a correctness fix.** The walk
stops at the first red, so when the top rungs catch everything the rungs below
show zero because nothing ever got that far. Flagging that would report a
repository that catches defects *before they are written* — the best possible
result — as one whose test suite does not work. The first version of this row
did exactly that, and a selftest case written against it caught it before it
ever ran on a real repository.

Only `0 of N caught` is flagged, and it outranks `none wired`: a repository
with nothing wired has a gap, a repository whose wiring is silent has a gap
*and* a false belief about itself.

**`rule` is in the inventory and has no rung.** A sentence in `CLAUDE.md`
saying *never do X* is an interception layer — it is trying to stop the same
defect as the hook. It cannot be measured by injection, because firing an Edit
payload at a document does nothing. So it is counted, from dimension 5's own
figures — prohibitions on the floor minus the ones a guard was *measured*
enforcing — and marked `unenforced, no rung`.

Prohibitions a guard already enforces are excluded from that count. They are
not a second layer; they are the guard, described twice.

## Rejected

**Giving `rule` a rung.** It would credit a repository for a layer nobody can
show working, which is the failure mode this whole dimension exists to avoid.

**Measuring rules by spending an agent.** It is the honest way to do it: hand
an agent the rule and the task, see whether it writes the defect anyway. It is
also stochastic, expensive and not repeatable across runs, so a before/after
comparison — the thing this page is for — would be comparing two samples of
the same coin. Priced and declined, not overlooked.

**Inferring the layers from settings alone.** The inventory takes its hook
counts from what was actually fired during the walk where that is available,
and falls back to the probe's reading of the settings. A settings file that
declares a hook which does not run is a claim, not a layer.

## Consequences

**The first thing it found is about us.** On this repository, guards suite as
the command: `before-write: 2 hook(s), 0 of 17 caught`. Two PreToolUse hooks
are wired, seventeen injected defects reached them — two from this
repository's history, fifteen mutated — and neither hook caught one. Before
this row that read as `before-write: 0`, which looked exactly the same as
having no hooks at all.

**`same-turn: none wired` and `ci: none wired` are now visible as absences**
rather than as zeros. The CI one is a limitation of `catch.ci_command`, which
looks for a `ci.sh` or a `make ci` and does not recognise a GitHub Actions
workflow — the inventory makes that gap legible instead of reporting it as a
result about the repository.

## Evidence status

| Claim | Grade |
|---|---|
| A wired-but-silent layer is distinguished from an absent one | **checked** — planted the absent branch away |
| A rung nothing reached is neither | **checked** — planted the state away; the case was written before the bug was known and found it |
| Only the silent layer is flagged | **checked** — planted the flag |
| A rule is counted and given no rung | **checked** — planted the rung |
| Prohibitions a guard enforces are not a second layer | **checked** — planted the subtraction away |
| The inventory changes what anybody does about a zero | **argued** — the distinction is new and nobody has yet acted on one |

## Amendment, same day: a hook that could not have run is not a layer

The row's first run against this repository read:

    before-write: 2 hook(s), 0 of 16 caught

flagged `bad`. It was wrong, and wrong in the way that gets a page dismissed:
of the two PreToolUse hooks here, one is wired `matcher: "Bash"` — the
destructive-command guards. The ladder introduces defects by editing files, so
it fires `Edit` payloads, and Claude Code would never send one to a Bash-only
hook. The row was accusing a guard of failing at a job it was never given.

Two things were broken by the same omission. `wired()` recorded each hook's
matcher and `fire_ex()` ignored it, so every hook was fired at every payload.
Besides inflating the inventory, a Bash-only hook that *did* block on an Edit
payload would have been recorded as a `before-write` catch that cannot happen
in reality — a false catch at the best rung on the ladder.

So the hooks are filtered by matcher against the payload's tool before
anything is fired, in `catch` and in `run_mutants` alike. An empty matcher or
`*` still means every tool; anything else is matched as the regular expression
it is, falling back to splitting an alternation when it does not compile.

| Claim | Grade |
|---|---|
| A Bash-only hook is not asked about an edit | **checked** — planted the filter out and watched the case go red |
| A catch-all matcher still means every tool | **checked** — planted `*` out of the catch-all set |
