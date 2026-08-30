# 0022 — One assessment step, which is allowed to end in nothing

Date: 2026-08-30
Status: accepted
Refines `0020` (what the assessment measures) and `0021` (why the plugin stays).

## Context

The bootstrap was documented as nine numbered steps: measure, plan, tier,
classify, scaffold, fill, watch a guard, freeze, write it down. That shape had
three defects, and only the first is cosmetic.

**It leaked implementation detail into the reader's view.** Steps 0 through 3
are all "work out what this repository needs"; splitting them into four is a
statement about how the code is organised, not about what somebody does. The
flow diagram gave five probes their own boxes, which are this plugin's business.

**It was a fixed procedure, so a repository needing one change got eight steps
anyway.** A procedure that cannot scale down is one people abandon at step three
and then describe as heavyweight.

**It had no way to finish without changing anything.** Step 1's plan had a
*Present and fine* column, and the flow around it assumed you were going to
install something regardless. A harness that cannot conclude *this is theirs,
and it is fine* rewrites everything it touches, and the nine steps quietly
guaranteed that outcome.

## Decision

**The assessment is one step, it contains an agent, and its output is a
checklist. What happens next is a decision, and "nothing" is one of the
answers.**

    install → a one-paragraph notice, once per repository
            → assess (one step)
            → the checklist
            → decide
            → an exec-plan, if there is one worth opening
            → re-measure

Three things fall out of that, each of which was the argument for it.

**The agent is inside the assessment, and is handed the numbers.** It reads what
the probes cannot — whether the standing context earns its tokens, which
sentences are waffle, whether each wired hook addresses a mistake *this*
repository makes. It does not count. A model cannot count tokens, will not
produce the same figure twice, and if it produced them then the before/after
comparison that `0020` exists for would be comparing two opinions.

So every checklist row carries a **Basis** of `measured` or `judged`, and a
judged row must quote. The two kinds age differently: a measured row is
re-runnable, a judged one has to be re-argued by someone reading the file again.

**The fixed spine becomes conditional obligations.** Choosing a tier, deleting
the paragraph a rule left, filling `CLAUDE.md` by hand, watching a guard block,
freezing a snapshot before reading it, writing the decision record — all of them
were worth having and none of them belongs to every repository. They now attach
to the plan when the plan goes there. The plan's shape comes from the checklist.

**The plugin speaks once per repository, and only reads.** A `SessionStart` hook
prints the standing cost, which moments are wired and what checks exist, the
first time it sees a repository, records a marker in
`$CLAUDE_CONFIG_DIR/repo-agent-harness/first-look.json`, and never speaks there
again.

## Rejected

**Running the assessment automatically on install.** `blast.py` fires the
repository's own hooks and `catch.py` clones the repo and runs its test suite;
the agent's half costs tokens. Doing any of that because somebody installed a
plugin helps itself to a machine and a bill that were never offered. What runs
unprompted is `probe_repo.py`, which reads files and asks git for a list. This
is hard rule 4 at the level of the instrument: a plugin may report on a
repository and may not start doing things to one.

**A notice on every session.** This plugin's entire argument is that standing
context is paid every turn and mostly not read; a recurring banner is that
mistake one level up, and it would land on the first screen — the one place a
`SessionStart` hook can put something that genuinely could not be known
otherwise. The marker records the numbers as well as the date, so speaking again
when they have moved a long way is a small change later. It is not this change,
because nobody has yet watched the current version be too quiet.

**Keeping "write the plan" as a step separate from "decide".** They read as one
step and are not: the plan is *what* changes, the decision is *whether*. Merging
them is how "no" stops being available.

## Consequences

The uninstall test is unchanged, and so is everything under `shared/scripts/`.
This is a decision about the order somebody does things in, and about what the
plugin does unasked.

`hooks/selftest.py` grew a second suite. Eight defects were planted in
`first_look.py` and each turned exactly one case red — three of them only after
the cases were rewritten, because the first versions asserted an observable that
the fixed and the broken code both produced. A repository that could not be
measured is silent whether or not it was marked; a subdirectory started second
is silent whether or not the hook walks up. That is the ordinary way a case
passes without testing anything.

## Evidence status

| Claim | Grade |
|---|---|
| The nine-step shape read as a fixed procedure | **reported**: the user rejected it in those terms |
| One step is what a reader wants | judgement |
| An agent handed counts beats an agent producing them | **argued** in `0020`, and the token-counting half is a fact |
| The notice costs ~73 ms and is paid once per repository | **measured**, on this repository |
| Once is the right frequency | **unmeasured**. Nobody has yet wanted it to speak again |
