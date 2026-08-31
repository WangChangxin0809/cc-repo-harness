---
name: bootstrap-repo-harness
description: Lay the foundation that makes a repository teach coding agents how to work in it — CLAUDE.md and its subtree files, .claude/ hook wiring, a layered docs/ truth source, scripts/ gates and guards, and a decision record explaining the shape. Use this whenever someone says the agent keeps repeating a mistake, that rules in CLAUDE.md are ignored, that context feels full before they've typed anything, that a new agent or teammate takes too long to get productive, or asks to set up CLAUDE.md / AGENTS.md / hooks / project conventions / onboarding for AI. Also use it when starting a fresh repo that agents will work in, or when auditing an existing one that has grown conventions nobody enforces.
---

# Bootstrap a repository harness

Governs: shared/scripts/scaffold.py, shared/scripts/probe_repo.py, shared/scripts/assess

A harness is the machinery that puts the right knowledge in front of an agent at
the moment it acts, and stops the actions that are cheaper to prevent than to
review. Most repositories have none: they have a `CLAUDE.md` full of rules that
are read once, paid every turn, and followed unevenly.

**Everything this skill installs must work without it.** The test is literal:
install, uninstall the plugin, hand a fresh agent a real task, and the
repository must still teach it how to work. Anything that only works while the
plugin is present was built in the wrong place.

That is independence, not disposal. A harness decays — the standing cost creeps
up, a guard stops matching, a document falls behind the code it claims — and a
repository cannot notice that about itself. Step 1 is worth re-running months
later for exactly that, which is why the assessment is never copied into the
tree: it reports on the repository rather than being part of it.

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

`${CLAUDE_PLUGIN_ROOT}/…` means a file inside this plugin. It is a real
environment variable set by Claude Code, not a placeholder to substitute by
hand — a plugin's install location differs by install method and platform, so
anything that hardcodes a path or asks the reader to guess one is broken on
somebody's machine. `<skill>/…` means a file beside the SKILL.md being read.

Bare paths like `scripts/guards/` mean the **target repository** — that is where
things end up, and where they must keep working after the plugin is gone.

## Steps

Five. The first two happen before anything in the repository changes, and the
second one is allowed to end the whole thing. Each has one observable
criterion; if the criterion cannot be checked, the step is not done.

### 1. Assess — one step, ending in a checklist

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/factsheet.py --root <repo>
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/factsheet.py --root <repo> --no-full
```

One page, every line measured: the standing per-turn cost and where it comes
from, which of the seven moments are wired, which irreversible actions are
refused *before they happen* — and whether any legitimate action is refused
along with them — how many defects the repository's own history can supply, and,
how late those defects are actually caught. `--no-full` is the second line
above: it skips the replay, which is the only slow part. A repository whose
tests will not run here **abstains**; it does not score zero.

Then you read, **holding those numbers rather than producing them**. A model
cannot count tokens, will not give the same figure twice, and if it produces the
numbers then the comparison at step 5 compares two opinions. The page ends by
naming the three questions it could not answer, and they are the whole of your
brief:

1. Is the standing cost earning its tokens, or restating the code next to it?
2. Which sentences in the docs are waffle? **Quote them.**
3. Does each wired hook address a mistake *this* repository actually makes?

The step ends in one artefact — **the assessment checklist**. Its shape is
fixed, so that two assessments of the same repository months apart can be laid
side by side; everything else about it is yours.

**Five sections, in this order** — the order in which ignoring something costs
you:

| | Section | Means |
|---|---|---|
| 1 | **Irreversible** | work can be destroyed. Nothing below matters until this is empty |
| 2 | **Silent** | wrong, and produces no symptom |
| 3 | **Late** | caught at CI, or never |
| 4 | **Expensive** | paid every turn and not earning it |
| 5 | **Fine** | present, correct, deliberately left alone |

**One row per finding**, four columns:

| Finding | Evidence | Proposed change | Basis |
|---|---|---|---|
| Deleting tracked work is not refused | the `rm -rf` probe walked through | a guard | measured |
| 612 tokens/turn restate the directory layout | `CLAUDE.md:14-31`, against `docs/index.md` | cut to the routing table | judged |
| Commit messages follow a house convention | 40 of the last 50 | none — leave it | measured |

**Four rules, and then use your judgement:**

- **Basis is `measured` or `judged`, never blank.** They age differently: a
  measured row can be re-run, a judged one has to be re-argued.
- **A `judged` row quotes.** A claim you cannot quote is one nobody can check,
  and "the docs are verbose" has never once caused a deletion.
- **A section with nothing in it says *none*.** That is a result. An empty
  **Irreversible** section is the best news in the document, and going looking
  for something to put there is how an assessment starts inventing findings.
- **Things that are present and fine get rows too**, with *none* as the proposed
  change. In this plugin's corpus, seventeen of twenty repositories have no
  `Requirements` section in their README — a fact about README conventions, not
  seventeen defects. A harness that cannot say *this is theirs, and it is fine*
  rewrites everything it touches.

The sections are where a finding belongs, not a quota. A repository whose whole
checklist is two rows in **Expensive** and eleven in **Fine** has been assessed
properly.

**Criterion**: five sections in order, at least one row proposing *none*, and
every `judged` row quoting something.

### 2. Decide whether any of it is worth changing

One question, asked of the checklist as a whole. **"No" is a real answer**, and
it is written down in `docs/decisions/` rather than treated as a run that failed
to find work — the next person needs to know this was looked at and left.

If the answer is yes, it is yes to *specific rows*. A decision to "improve the
repo" is how a bounded piece of work becomes a rewrite.

**Criterion**: you can name the rows you are acting on, and the rows you are
leaving, and say why for both.

### 3. Open the exec-plan

`docs/exec-plans/<name>/README.md` owns the state — what is done, what is next,
what is blocked. The steps beside it own the substance. Keep it short enough
that somebody finishes it; a plan nobody finishes is a plan nobody follows.

Then a `## Not doing, and why` section, listing the checklist rows you decided
against. Without it, the next person re-proposes them.

The plan is built from the checklist, so its shape is this repository's, not a
fixed procedure. But some steps drag obligations behind them, and these are the
ones that get skipped:

| If the plan | it must also contain |
|---|---|
| installs anything | choosing a tier below, and naming what you deliberately did *not* install |
| takes a rule out of prose | routing it to one of the seven moments, **and deleting the paragraph** |
| runs `scaffold.py` | filling `CLAUDE.md` and `ARCHITECTURE.md` by hand — nothing generates them |
| adds a guard or a gate | watching it block something you typed, and watching its selftest go red |
| touches accumulated notes | freezing the snapshot read-only *before* anything reads it |
| any of the above | a decision record naming one alternative that was rejected, and why |

| Tier | Repo | Install |
|---|---|---|
| **A** | < 50 source files | `CLAUDE.md` · `.claude/settings.json` · `docs/index.md` · `scripts/guards/` |
| **B** | < 800 | + subtree `CLAUDE.md` · the six `docs/` kinds · `gates/` · `selftests/` · `ci.sh` |
| **C** | larger, or several agents in parallel | + `scripts/index/` · consolidation · a gold set for the harness itself |

Installing above tier leaves machinery nobody needs. It rots, and its rot
teaches everyone that the machinery is decorative.

**Criterion**: the plan has a non-empty `## Not doing, and why`, and every
obligation its steps triggered is in it as a step.

### 4. Work it

Three things about the machinery, in the order they surprise people.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/scaffold.py --root <repo> --tier <A|B|C> --dry-run
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/scaffold.py --root <repo> --tier <A|B|C>
```

**The red list is the to-do list.** `./ci.sh --fast` is red immediately after
scaffolding and is supposed to be: `check_templates_filled.py` names every
placeholder still sitting in a scaffolded file. That red list is the only form
of to-do list that cannot be forgotten, so do not go looking for a way to make
it green early — green here would mean the gate cannot see the thing it exists
to see. The scaffolder is additive and idempotent; nothing existing is
overwritten, and `settings.json` is merged after a `.bak`.

**Empty directories are deliberate.** `docs/how-to/`, `docs/decisions/`,
`scripts/selftests/`, `scripts/baselines/` are created empty because **a
directory is itself a trigger**: an agent that sees `docs/exec-plans/` writes a
plan there, and an agent that sees nothing invents a location.

**Read the guards before trusting them.** Wiring `scripts/guards/dispatch.py`
as a `PreToolUse` hook means every `.py` in that directory executes before every
Bash call in this repository — including files a teammate adds later, and files
that were already there when you cloned. That is a code path worth one careful
look, and it is why this plugin's own hook will not run a repository's guards
until you have said so:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/run_repo_guards.py --status
```

Then **break one on purpose** and confirm the selftest goes red. See
`writing-checks`, including why a broken guard is deliberately made to fail
*open*.

**A guard that keeps refusing the same thing is not a guard working**, it is a
habit meeting a speed bump — and habits are cheaper to move than to keep
stopping, to `permissions.deny` or to the server. Nothing counts that for you;
notice it, or find it in the next assessment. See `0023` for why a counter was
built for this and then removed.

**Criterion**: `./ci.sh --fast` is green because the files were written rather
than because a gate was exempted, and you have watched a guard block a command
you typed, watched a near-miss go through, and watched its selftest turn red
under injection.

### 5. Re-measure, and close the rows

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/factsheet.py --root <repo>
```

Same command, same units. Every `measured` row on the checklist now closes or
does not, and the only claims allowed are in those units: *two of six
irreversible actions were refused, now five are, and nothing legitimate became
blocked.* Never *we added five guards* — that is a claim about us.

`judged` rows do not close by re-running anything. They close by someone reading
the file again, which is why they had to quote in the first place.

**Criterion**: at least one measured number moved, no false block appeared, and
every row on the checklist is closed, open with a reason, or in `## Not doing`.

## Acceptance

The first three hold however small the plan was. The rest apply only if the plan
went there — a repository that needed two rows changed does not owe you a tier.

1. **Every row of the checklist is closed, open with a reason, or in `## Not
   doing`.** A row that quietly disappeared is the failure mode this whole shape
   exists to prevent.
2. **The fact sheet was taken again, and the claims are in its units.** Not "we
   added three gates" — that is a claim about us. `blast.py` refuses more than it
   did, no legitimate action became blocked, and defects that used to reach CI
   are caught before the write.
3. **Uninstall the plugin.** The repository still teaches — same guards, same
   gates, same `ci.sh`, nothing missing but the trust prompt and the ability to
   measure itself. Then reinstall it: the instrument is worth keeping.

If the plan installed anything:

4. Every hook in `settings.json` is one line invoking a script, and nothing
   under `.claude/` explains why anything is true.
5. No scaffolded template still carries a placeholder — `check_templates_filled`
   is green because the files were written, not because it was exempted.
6. `ci.sh` runs green from a clean worktree, and disconnecting a hook on purpose
   turns it red. A suite that survives that is measuring nothing.

If the plan moved a rule, or added a check:

7. At least one rule left `CLAUDE.md`, and its paragraph is gone rather than
   duplicated.
8. A guard has been seen blocking, and its selftest has been seen red.
9. A fresh session's first screen states something no file could have contained.

## References

| File | Read when |
|---|---|
| `references/target-architecture.md` | You want the finished tree before starting |
| `references/moments.md` | Wiring a hook and needing the exact contract |

Related skills: `writing-docs` (what goes in `docs/`), `writing-checks` (gates
and guards), `writing-github-docs` (README and the community health files),
`repo-index` (retrieval at tier C), `consolidating-notes`.

These five are **not installed with this plugin** — you copy them into the
repository as part of the scaffold, at the tier that earns each one, so they
reach teammates who never installed anything. Until that copy happens they are
files on disk under the plugin's `shared/skills/`, readable but not loaded, so
a reference to one of them here may not resolve to an invokable skill yet.
