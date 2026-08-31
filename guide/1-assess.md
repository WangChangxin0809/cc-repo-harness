# Assess a repository

An agent reads the repository against the five dimensions below and writes a
checklist. It has one instrument, which it runs first and then holds while it
reads:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/factsheet.py \
        --root . --html assessment.html --json assessment.json
```

`--html` writes a self-contained page — no network, no fonts, no scripts — which
is the thing a person actually reads. Add `--full` to also replay defects, which
is slower and runs the repo's own tests.

The [`repo-assessor`](../agents/repo-assessor.md) agent does all of this,
including the reading. It never changes the repository.

## Five dimensions

| | Dimension | The question | A low score means |
|---|---|---|---|
| 1 | **Controlled Execution** | can an agent working here in good faith destroy something? | your uncommitted work can be destroyed and nothing refuses |
| 2 | **Change Validation** | when a defect is introduced, how late is it caught? | defects this repo has actually produced would reach `main` |
| 3 | **Reliable Delivery** | when a change is called done, what is the evidence? | the green light is real, but it has nothing to do with what you changed |
| 4 | **Repository Memory** | can an agent that has never seen this repo find its way, and is that because of something the repo keeps? | a newcomer edits the wrong file, and nothing here shortens the search |
| 5 | **Context Economy** | what does the harness cost per turn, and at worst? | tokens are spent every turn on text that restates the code |

A dimension earns its place only if a low score names a **specific observable
failure** — the right-hand column. That filter is also why none of the five
scores whether a repository has adopted this project's conventions: a repo that
stops destruction with a hand-written `bash` hook scores full marks on 1.

## 1 — Controlled Execution

Six destructive actions are aimed at the repository's own hooks and **never
run** — the payload is offered, the answer is read. What is graded is what it
would cost to undo:

| | Class | Undo | Examples |
|---|---|---|---|
| **A** | fully recoverable | one git command, by anyone | edit, create, delete a tracked file |
| **B** | git recovers, state is lost | reflog, and knowing it exists | commit, merge, rebase |
| **C** | it left the machine | social — others already have it | pushing, forced pushes, remote, CI config, lockfile |
| **D** | no clean recovery | nothing local holds the old state | untracked files deleted, uncommitted work overwritten, refs destroyed, a secret committed |

Class alone decides nothing — a commit is B and happens fifty times a day. The
second axis is how often the action is legitimate, and the two together say what
the harness owes: **nothing** for A and B, **leave a trace** for most of C, and
a **hard block** only for D actions that are rarely right. The asymmetry flips
at the D line: below it a false block costs more than a miss, at D it does not.

Two more things this dimension covers: whether a rule in `.claude/rules/` is
actually delivered at the moment it matters, and whether the harness blocks work
the agent legitimately needed to do. A harness that blocks everything fails here
as completely as one that blocks nothing.

## 2 — Change Validation

Real defects from this repository's own history — reverts, and fixes that
touched a test — are put back one at a time, and what is recorded is **where
each was first caught**:

```
before-write   a guard refused it            costs nothing
same-turn      a post-write hook caught it   costs one turn
local-suite    the local check script        costs minutes
--- the cliff: the session ends, the context is gone ---
ci             the server                    costs a round trip
never          nothing                       it is in main
```

The headline is one sentence — *N of M survive past the end of a session*. Not a
count: one caught at `ci` is not comparable to one caught before it was written.

The defects are the repository's own on purpose. A synthetic bug measures
whether *our* idea of a defect resembles what this repo checks for. And if the
toolchain is not installed this abstains rather than scoring zero — a repo whose
tests cannot run here is not a repo with bad tests.

## 3 — Reliable Delivery

Dimension 2 asks whether a wrong change gets through. This one asks the other
half: when a change is called done, **what makes that believable**. A repository
can have a green light that covers none of what was touched, and then whether
work is accepted depends on who happened to be looking.

So what is read is coverage rather than existence — the entry point that
returns pass/fail is already observed by dimension 2's `local-suite` rung, and
counting it twice would just say the same thing louder. The signals here:

- of the recent changes, how many touched code and touched nothing that
  verifies it
- **where those tests are**, named directory by directory. Every repository
  puts them somewhere different, so a percentage nobody can trace back is a
  number that looks the same whether coverage is poor or the suite is simply
  somewhere the instrument did not look. Naming the directories makes a miss
  correctable, and the reading is expected to open the repository and correct it
- whether CI **runs** the suite, or only exists. A pipeline that installs,
  lints, builds and deploys goes green on every push, and from the tick on the
  pull request it is indistinguishable from one that ran everything
- whether the verdict is a command someone can run, or a description someone
  wrote
- **how often a place was repaired again after being called done** — counted
  from committed history, and only from commits focused enough to be
  attributable, so it is rework rather than a busy file. It lived in dimension
  4 until that one stopped reading history and started watching an agent
  -> [0025](../docs/decisions/0025-dimension-4-asks-whether-an-agent-can-find-its-way.md)

These are deliberately loose, and reaching a conclusion from them is the
reading's job, not a threshold's. This dimension also still speaks when the
toolchain is missing and dimension 2 has abstained, which is the argument for
its keeping its own place.

## 4 — Repository Memory

This one is not read off the repository. **An agent that has never seen it is
sent in, and what happens is the measurement.**

It answers nine questions on a copy of the tree: six about the whole place — the
components, the flows, what is generated, where the tests are, what is unusual
here — and three micro ones, each of which is the **subject line of a real
commit** and nothing else, asking *which files would you change to do that?*
The commit's own diff is the answer key, so the repository wrote its own exam.

**Then the same nine questions are asked again**, of the same tree with
`CLAUDE.md`, `.claude/` and every nested `CLAUDE.md` removed.

> The difference between the two runs is the memory.

That is the whole design, and it is why nothing here counts skills, hooks or
rules. A count would grade a repository on whether it adopted somebody else's
conventions, and it would go *up* when you install this plugin — the instrument
rewarding its own presence. A difference cannot be raised by adding files: a
thin `CLAUDE.md` that halves the search beats six skills that change nothing
-> [0025](../docs/decisions/0025-dimension-4-asks-whether-an-agent-can-find-its-way.md).

Three things make it trustworthy:

- **The probe cannot cheat.** Both copies are made without `.git`, and the
  probe agent is given no Bash. One `git log --grep` would answer every micro
  question perfectly, and a rule against it could be broken silently — so the
  history is not forbidden, it is absent.
- **It costs two agents.** One session answers all ten questions; the second
  run is the same session on the stripped copy. It is opt-in for that reason,
  and without it this dimension **abstains** — a repository nobody probed is
  not a repository an agent cannot navigate.
- **No rates.** Three questions do not make a percentage. The rows say what
  happened, including how many files each answer named, because recall alone is
  answered by listing the tree.

Alongside it, offline and free: whether there is anywhere mistakes are written
down, and **whether anything reads it**. A write-only record is the failure mode
that looks healthiest from outside — the file exists, it is long, and it has
never changed anyone's behaviour.

## 5 — Context Economy

The unit is settled — characters over four, offline, no network — and the three
numbers are named: **floor** (what every turn pays before anyone types),
**ceiling** (the worst a single turn can reach), **parked** (what is installed
but only arrives when something asks for it). The page still prints two of them
in units it does not add up, which is why this section is short.

## What comes out

One artefact: the [assessment checklist](2-checklist.md). Five sections in the
order that ignoring them costs you, and every row points at something specific
in the repository.

The hardest questions are the ones with no number behind them — is the standing
cost earning its tokens, which sentences are waffle, does each hook address a
mistake *this* repository actually makes. Answering them is the reading, and it
is the reason the checklist is worth more than the fact sheet.

Keep the fact sheet's `--json`. [Re-measuring](5-re-measure.md) later needs the
earlier file, and it is the only way anything here can claim to have helped.
