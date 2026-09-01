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

The consequence of installing above tier is in `SKILL.md`, beside the tier
table there.

## The files people get wrong

**`ARCHITECTURE.md` is written, never generated.** It answers "how does this
thing work" for someone who does not yet know what to ask — the one reading
trigger the six `docs/` kinds have no home for. A generated rollup describes the
current accident; a written one describes the intent, including the constraints
that are not visible in the code. `CLAUDE.md` answers "what must never happen"
and is paid every turn, so it stays short; `ARCHITECTURE.md` is read on demand,
so it can be long.

**`SECURITY.md` holds almost nothing.** It says how to report a vulnerability.
The rules split three ways, and each half goes where it runs:

- what must not leave the machine is a guard
- what must not enter the tree is a gate
- why the boundary sits where it does is a decision record

Security prose that is only prose is the clearest case of a rule with no
reading trigger.

**`docs/decisions/0001-agent-conventions.md` is the closing act.** It records why
the repository has this shape. Without it the conventions survive as folklore,
and folklore gets routed around within a quarter. With it, the next person can
argue with the design instead of quietly abandoning it.

**Empty directories are load-bearing.** `docs/exec-plans/` existing is what
makes an agent write its plan there instead of inventing a location. They ship
with a `.gitkeep` so the trigger survives a clone.

## Acceptance

The acceptance list is in `SKILL.md`, under **Acceptance**, and it is not
repeated here. Two copies of it existed until they were compared: one asked for
`ci.sh` and the other for `./ci.sh --fast`, each carried an item the other did
not, and nothing would have caught either drifting further -- which is what a
skill in this same repository is about.

What belongs here, because it is about the shape of the tree rather than about
finishing a plan:

- The index rebuilds from source in seconds, and its negative control records
  which edges it cannot see. (Tier C only; there is no index below it.)
