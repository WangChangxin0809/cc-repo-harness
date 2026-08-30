# Target architecture — what "finished" looks like

Read this **before step 1**, so the assessment has something to compare
against. The steps describe motion; this describes the destination.

Legend: `◆` written by `scaffold.py` · `◇` authored by hand, shape prescribed here.

```
repo/
├── CLAUDE.md                  ◆ cap 100 lines, gate-enforced · moment 1
├── ARCHITECTURE.md            ◇ bird's eye · codemap · invariants · hidden constraints
├── SECURITY.md                ◆ how to report; the rules themselves live in checks
├── ci.sh                      ◆ the one acceptance entry · roster · three lanes
│
├── .claude/                     wiring only — never knowledge
│   ├── settings.json          ◆ each hook is one line calling scripts/
│   └── guards.json            ◆ protected branches · layer stack · exceptions
│
├── src/
│   ├── api/CLAUDE.md          ◇ loads automatically when this subtree is read · moment 4
│   └── billing/CLAUDE.md      ◇
│
├── docs/                        the truth source
│   ├── index.md               ◆ routing table: task → read → edit
│   ├── how-to/                ◇ action → command → criterion, per step
│   ├── reference/             ◇ tables keyed for lookup; the glossary lives here
│   ├── troubleshooting/       ◇ symptom → cause → action
│   ├── decisions/               numbered · immutable · superseded, never edited
│   │   ├── 0001-agent-conventions.md  ◆ why this repo is shaped this way
│   │   └── 00NN-….md          ◇ Supersedes: 0001
│   ├── exec-plans/
│   │   ├── tech-debt-tracker.md   ◆ permanent · found-in-passing goes here
│   │   └── <name>.md          ◇ deleted on completion
│   └── generated/             ◇ regenerate, then git diff must be empty
│
└── scripts/                     judgment — every pass/fail decision
    ├── guards/                  reads one proposed action, before it runs
    │   ├── dispatch.py        ◆ add a rule = add a file; broken guards fail open
    │   ├── _recurrence.py     ◆ counts refusals by shape in .git/ · says it once
    │   ├── selftest.py        ◆ must be seen failing before you trust it
    │   └── no_*.py            ◆ three universal starters
    ├── gates/                   reads the worktree, at CI time
    │   ├── check_context_budget.py  ◆ CLAUDE.md cap + always-on skill cost
    │   ├── check_docs_index.py      ◆ routing table both directions
    │   ├── check_layering.py        ◆ imports point down the stack
    │   └── selftest.py              ◆ every gate turns red on its own defect
    ├── context/               ◆ what the hooks call · moments 2 and 6
    ├── index/                   tier C — one graph, one entry point
    │   ├── build.py           ◆ full rebuild from source, no incremental state
    │   └── query.py           ◆ callers differ only in the seed
    ├── selftests/             ◇ one per gate you add, proving it can turn red
    └── baselines/             ◇ every reading records the commit it was measured on
```

## By tier

| Tier | Adds |
|---|---|
| **A** | `CLAUDE.md` · `.claude/` · `docs/index.md` · `how-to/` · `reference/` · `guards/` |
| **B** | + `ARCHITECTURE.md` · `SECURITY.md` · `ci.sh` · `0001` · the rest of `docs/` · `gates/` · `context/before_write.py` |
| **C** | + `scripts/index/` · consolidation · a gold set for the harness itself |

Installing above tier leaves machinery nobody needs. It rots, and its rot
teaches everyone that the machinery is decorative.

## The files people get wrong

**`ARCHITECTURE.md` is written, never generated.** It answers "how does this
thing work" for someone who does not yet know what to ask — the one reading
trigger the six `docs/` kinds have no home for. A generated rollup describes the
current accident; a written one describes the intent, including the constraints
that are not visible in the code. `CLAUDE.md` answers "what must never happen"
and is paid every turn, so it stays short; `ARCHITECTURE.md` is read on demand,
so it can be long.

**`SECURITY.md` holds almost nothing.** It says how to report a vulnerability.
The rules split three ways — what must not leave the machine is a guard, what
must not enter the tree is a gate, and why the boundary sits where it does is a
decision record. Security prose that is only prose is the clearest case of a
rule with no reading trigger.

**`docs/decisions/0001-agent-conventions.md` is the closing act.** It records why
the repository has this shape. Without it the conventions survive as folklore,
and folklore gets routed around within a quarter. With it, the next person can
argue with the design instead of quietly abandoning it.

**Empty directories are load-bearing.** `docs/exec-plans/` existing is what
makes an agent write its plan there instead of inventing a location. They ship
with a `.gitkeep` so the trigger survives a clone.

## Acceptance

The plugin is a bootstrapper, not a dependency — install it, delete it, and the
repository must still teach a fresh agent how to work in it. Test it that way:
install, remove, hand an agent a real task, watch whether it follows the
conventions.

1. Every hook in `settings.json` is one line invoking a script, and nothing
   under `.claude/` explains why anything is true.
2. At least one rule has moved out of `CLAUDE.md` into a subtree file or a
   check. If nothing moved, the classification was never done.
3. `scripts/guards/selftest.py` and `scripts/gates/selftest.py` both pass,
   **and** you have watched one block a command you typed on purpose — and
   watched a near miss go through.
4. A fresh session's first screen states something no file could have contained.
5. `./ci.sh --fast` is silent and green from a clean worktree.
6. The index rebuilds from source in seconds, and its negative control records
   which edges it cannot see.
7. Disconnect a hook deliberately and the harness's own suite turns red. A suite
   that survives that is measuring nothing.
