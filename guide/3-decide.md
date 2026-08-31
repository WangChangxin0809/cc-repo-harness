# Decide what to change

- **Covers**: stage 2 — the gate between knowing and doing, and the plan that
  comes out of it if anything does.
- **Does not cover**: how the checklist was written
  ([2](2-checklist.md)), or doing the work ([4](4-do-the-work.md)).

One question, asked of the checklist as a whole: **is any of this worth
changing?**

It is a real gate, and it is the step most likely to be skipped, because by the
time somebody has produced a checklist they have already decided they are here
to fix things. That is exactly when a harness starts rewriting a repository that
did not need it.

## "No" is an answer

Write it down and stop. In the exec-plan's `README.md`:

```markdown
State: closed — assessed 2026-08-30, nothing worth changing.

Three of six irreversible actions are already refused, no legitimate action is
blocked, and every replayable defect is caught before the session ends. The
standing cost is 76 lines of CLAUDE.md, of which none restates a file next to
it. Section 5 of the checklist has four rows.
```

That is a **result**, not a run that failed to find work. It is also the thing
that stops the same repository being assessed again in three months by somebody
who has no way of knowing it was already looked at.

## "Yes" is yes to specific rows

Not to the checklist. A decision to *improve the repo* is how a bounded piece of
work becomes a rewrite that touches forty files and finishes none of them.

Go row by row. For each one, the answer is **do it**, **not now**, or **no** —
and `not now` and `no` are different: the first is a queue, the second is a
judgement that survives being asked again.

The rows you decline go into the plan's `## Not doing, and why`. Without that
section they get re-proposed by the next person, or by the next assessment,
which will find them again because they are still there.

**Section order is the default priority.** Irreversible before silent before
late before expensive. Deviating from it is allowed and worth one sentence
saying why — *"the token cost is being fixed first because the person paying it
is here this week"* is a fine reason; not noticing the order is not.

## Opening the plan

The folder already exists — [stage 1](2-checklist.md) opened it to hold the
checklist. Deciding fills in the rest:

```
docs/exec-plans/<name>/
├── README.md          state, what is next, what is blocked, and Not doing
├── assessment.md      the fact sheet and the checklist  (already there)
├── baseline.json      factsheet --json                  (already there)
└── steps/             one file per step, owning the substance
```

The README owns **state**; the step files own **substance**. That split is the
whole convention, and the reason for it is that state changes every day and
substance does not — a plan that mixes them is one where nobody can tell what is
left by reading the top.

Keep it short enough that somebody finishes it. A plan nobody finishes is a plan
nobody follows.

## The obligations

The plan's shape comes from the checklist, so it is this repository's shape and
not a fixed procedure. But some steps drag obligations behind them, and these
are the ones that get skipped:

| If the plan | it must also contain |
|---|---|
| installs anything | choosing a tier, and naming what you deliberately did **not** install |
| takes a rule out of prose | routing it to one of the seven moments, **and deleting the paragraph** |
| runs `scaffold.py` | filling `CLAUDE.md` and `ARCHITECTURE.md` by hand — nothing generates them |
| adds a guard or a gate | watching it block something you typed, and watching its selftest go red |
| touches accumulated notes | freezing the snapshot read-only **before** anything reads it |
| any of the above | a decision record naming one alternative that was rejected, and why |

Each of these was once a numbered step in a fixed nine-step procedure. They
became conditional because a repository that needs one change should not be
walked through eight steps to get it — see
[0022](../docs/decisions/0022-one-assessment-step-that-may-end-in-nothing.md).

### Tier, if anything is being installed

| Tier | Repo | Install |
|---|---|---|
| **A** | < 50 source files | `CLAUDE.md` · `.claude/settings.json` · `docs/index.md` · `scripts/guards/` |
| **B** | < 800 | + subtree `CLAUDE.md` · the `docs/` kinds · `gates/` · `selftests/` · `ci.sh` |
| **C** | larger, or several agents in parallel | + `scripts/index/` · consolidation · a gold set for the harness itself |

The fact sheet already printed the tier. Installing above it leaves machinery
nobody needs, and machinery that rots teaches everyone that the machinery is
decorative — which costs more than the thing it was supposed to prevent.

**Criterion**: you can name the rows you are acting on and the rows you are
leaving, and say why for both; `## Not doing, and why` is not empty; and every
obligation the plan's steps triggered is in it as a step.
