---
name: bootstrap-repo-harness
description: Lay the foundation that makes a repository teach coding agents how to work in it — CLAUDE.md and its subtree files, .claude/ hook wiring, a layered docs/ truth source, scripts/ gates and guards, and a decision record explaining the shape. Use this whenever someone says the agent keeps repeating a mistake, that rules in CLAUDE.md are ignored, that context feels full before they've typed anything, that a new agent or teammate takes too long to get productive, or asks to set up CLAUDE.md / AGENTS.md / hooks / project conventions / onboarding for AI. Also use it when starting a fresh repo that agents will work in, or when auditing an existing one that has grown conventions nobody enforces.
---

# Bootstrap a repository harness

Governs: shared/scripts/scaffold.py, shared/scripts/probe_repo.py

A harness is the machinery that puts the right knowledge in front of an agent at
the moment it acts, and stops the actions that are cheaper to prevent than to
review. Most repositories have none: they have a `CLAUDE.md` full of rules that
are read once, paid every turn, and followed unevenly.

**This skill installs a foundation and then becomes unnecessary.** The test is
literal: install, uninstall the plugin, hand a fresh agent a real task, and the
repository must still teach it how to work. Anything that only works while the
plugin is present was built in the wrong place.

## Two rules everything else follows from

**Knowledge lives in the repository, not in agent memory.** Memory is
per-machine, invisible to review, and cannot be corrected by a teammate. A fact
worth keeping is worth a file with a path someone can cite in a pull request.

**What cannot tolerate a miss never goes through retrieval.** Retrieval is
best-effort by construction. Rules whose violation is irreversible or silent go
into a guard that blocks the action, or into a gate that fails the build — never
into a paragraph hoping to be read.

With one honest correction, because the rule above is where harnesses oversell
themselves: a guard is also best-effort. It matches command text and it fails
open by design, so `B=push; git $B origin main` walks past it. For a rule that
genuinely cannot tolerate a miss, the guard is the third line — after
`permissions.deny` in `.claude/settings.json`, and after server-side branch
protection. What the guard adds is the paragraph explaining why, delivered at
the moment of the attempt. See `writing-checks`.

## The seven delivery moments

Every piece of knowledge you place is answering: *at which moment does this
arrive?* Wiring is cheap; picking the wrong moment is what makes harnesses fail.

| # | Moment | Mechanism | Cost | Use for |
|---|---|---|---|---|
| 1 | Every turn | `CLAUDE.md` | Paid always | The few rules with no local trigger |
| 2 | Session start | `SessionStart` hook | Once | What is true *right now* and no file can hold |
| 3 | Each prompt | `UserPromptSubmit` hook | Per turn | Retrieval seeded by what was just asked |
| 4 | Reading a subtree | nested `CLAUDE.md` | Only when relevant | Rules true inside one directory |
| 5 | Before an action | `PreToolUse` guard | Only on match | Blocking what review cannot undo |
| 6 | After an action | `PostToolUse` hook | Only on match | Reacting to what just changed |
| 7 | On demand | skills, subagents | Only when triggered | Procedures with a clear trigger phrase |

Moment 4 is the most under-used and the highest leverage. A rule that is only
true inside `src/billing/` costs every session nothing until someone opens
`src/billing/`, at which point it is delivered without being asked for.

## Path convention

`<skill>/…` and `<plugin>/…` mean files inside this plugin. Bare paths like
`scripts/guards/` mean the **target repository** — that is where things end up,
and where they must keep working after the plugin is gone.

## Steps

Each step has one observable criterion. If the criterion cannot be checked, the
step is not done — move on only when it reads true.

### 0. Survey before touching anything

```bash
python3 <plugin>/shared/scripts/probe_repo.py --root <repo>
```

It reports which of the seven moments are wired, what discipline already exists,
the standing per-turn cost of installed skill descriptions, and a suggested
tier. **Criterion**: you can state the tier and name at least one convention the
repository already has. Bolting a second convention onto a repo that has one is
how you get two that are both half-followed.

### 1. Choose a tier and stay in it

| Tier | Repo | Install |
|---|---|---|
| **A** | < 50 source files | `CLAUDE.md` · `.claude/settings.json` · `docs/index.md` · `scripts/guards/` |
| **B** | < 800 | + subtree `CLAUDE.md` · the six `docs/` kinds · `gates/` · `selftests/` · `ci.sh` |
| **C** | larger, or several agents in parallel | + `scripts/index/` · consolidation · a gold set for the harness itself |

Installing above tier leaves machinery nobody needs. It rots, and its rot
teaches everyone that the machinery is decorative. **Criterion**: you can say
what you deliberately did *not* install and why.

### 2. Classify every existing rule by moment

Take the rules already written down — in `CLAUDE.md`, in a wiki, in someone's
head — and route each one:

- Can a script detect the violating action before it runs? → guard (moment 5)
- Can a script detect it in the worktree? → gate, and delete the prose
- Is it true only inside one directory? → that directory's `CLAUDE.md` (moment 4)
- Is it a procedure with a trigger phrase? → a skill (moment 7)
- None of the above, and a miss is expensive? → keep it in `CLAUDE.md`

**Criterion**: at least one rule left `CLAUDE.md`. If nothing moved, the
classification was performed as a formality.

### 3. Scaffold

```bash
python3 <plugin>/shared/scripts/scaffold.py --root <repo> --tier <A|B|C> --dry-run
python3 <plugin>/shared/scripts/scaffold.py --root <repo> --tier <A|B|C>
```

Additive and idempotent; nothing existing is overwritten; `settings.json` is
merged after a `.bak`. It also creates empty directories — `docs/how-to/`,
`docs/decisions/`, `scripts/selftests/`, `scripts/baselines/`. That is
deliberate: **a directory is itself a trigger.** An agent that sees
`docs/exec-plans/` writes a plan there; an agent that sees nothing invents a
location.

`./ci.sh --fast` is **red** immediately after this, and it is supposed to be:
`check_templates_filled.py` names every placeholder still sitting in a scaffolded
file. That red list *is* the fill-in list, and it is the only form of to-do list
that cannot be forgotten. Do not go looking for a way to make it green early —
green here would mean the gate cannot see the thing it exists to see.

**Criterion**: `git status` shows the tree, and `./ci.sh --fast` is red naming
placeholders rather than red for any other reason.

### 4. Fill the two files that cannot be generated

`CLAUDE.md` — **hard cap 100 lines**, enforced by a gate. Scope it: say what it
covers and what it does not, so the next person knows where new material goes
instead of appending here. Every line is paid on every turn of every session.

`ARCHITECTURE.md` — bird's-eye view, codemap, and the invariants that are not
visible in the code. It answers *"how does this work"* for someone who does not
yet know what to ask, which is the one reading trigger `docs/` has no home for.
Written by hand: a generated rollup describes the current accident, a written
one describes the intent. It is read on demand, so it may be long.

**Criterion**: neither file contains a sentence that was true of a generic
repository.

### 5. Read the guards, then watch one block

```bash
python3 scripts/guards/selftest.py
```

Three starters ship: destructive restore, piped outbound commands, protected
branch pushes. Adding a rule means adding a file — the dispatcher discovers it.

**Read them first.** Step 3 wired `scripts/guards/dispatch.py` as a `PreToolUse`
hook, which means every `.py` in that directory now executes before every Bash
call in this repository — including files a teammate adds in a later pull
request, and files that were already there when you cloned. That is a code path
worth one careful look, and a diff worth reviewing like any other. It is also
why this plugin's own hook will not run a repository's guards until you have
explicitly trusted them:

```bash
python3 <plugin>/hooks/run_repo_guards.py --status
```

Then **break one on purpose** and confirm the selftest goes red. A guard you
have never seen fail is a file, not a check. See `writing-checks` for the
discipline, including why a broken guard is deliberately made to fail *open*.

**Criterion**: you have watched a guard block a command you typed, watched a
near-miss go through, and watched the selftest turn red under injection.

### 6. Make the snapshot immutable before any consolidation

If the repository has an accumulated pile of agent notes, they are input to
consolidation and must be frozen before anything reads them. See
`consolidating-notes`. **Criterion**: the snapshot directory is read-only on
disk, and the synthesis wrote to a *different* path that you diffed.

### 7. Close by writing down why

`docs/decisions/0001-agent-conventions.md` — what was chosen, what was rejected,
what would have to become true to revisit it. Without it the conventions survive
as folklore, and folklore gets routed around within a quarter. With it, the next
person argues with the design instead of quietly abandoning it.

**Criterion**: the record names at least one alternative that was considered and
rejected, with the reason.

## Acceptance

1. Every hook in `settings.json` is one line invoking a script, and nothing
   under `.claude/` explains why anything is true.
2. At least one rule moved out of `CLAUDE.md`.
3. A guard has been seen blocking, and its selftest has been seen red.
4. A fresh session's first screen states something no file could have contained.
5. No scaffolded template still carries a placeholder — `check_templates_filled`
   is green because the files were written, not because it was exempted.
6. `ci.sh` runs green from a clean worktree, and disconnecting a hook on purpose
   turns it red. A suite that survives that is measuring nothing.
7. Uninstall the plugin. The repository still teaches — same guards, same gates,
   same `ci.sh`, nothing missing but the trust prompt.

## References

| File | Read when |
|---|---|
| `references/target-architecture.md` | You want the finished tree before starting |
| `references/moments.md` | Wiring a hook and needing the exact contract |

Related skills: `writing-docs` (what goes in `docs/`), `writing-checks` (gates
and guards), `repo-index` (retrieval at tier C), `consolidating-notes`.
