# Writing one, once nothing fit

Governs: .claude/skills/

A skill is the answer to *"a procedure with a trigger"* and to nothing else. Two
things that look like skills and are not:

- **A rule that can pass or fail.** That is a guard if a script can refuse the
  action before it happens, and a gate if a script can detect the state
  afterwards. A skill asking an agent to remember a rule is a rule that will be
  followed unevenly, and the failures will be silent. See `writing-checks`.
- **A fact.** That is `docs/reference/`, or a comment next to the thing.

## The frontmatter is the whole routing decision

```markdown
---
name: kebab-case-and-stable
description: What it does — then the triggers, in the words somebody would actually type.
---
```

`description` is the *only* thing deciding whether the skill is ever activated,
and it is charged on every turn whether it activates or not. Two consequences
that pull against each other, and the resolution is not "compromise":

**Name the trigger, not the capability.** "Merge an accumulated pile of agent
notes into repository knowledge… use this when notes contradict each other, when
memory has drifted, when a note references something that no longer exists"
routes. "Note management utilities" does not, no matter how accurate it is.

**Stop when the triggers stop being distinct.** Each added clause is one
plausible line and permanent cost. This plugin's own bootstrap description grew
to 179 tokens of symptoms before anyone measured it; at 54 it routes just as
well, because the clauses removed were restatements of the ones kept.

The body is free. It loads only when the skill is invoked, so guidance belongs
there and never in the description.

## Where it lives decides who pays

| | Cost | Use when |
|---|---|---|
| `.claude/skills/` in the repository | that repository only, and it survives after any plugin is uninstalled | almost always |
| a plugin | **every repository on the machine**, whether or not it has anything for the skill to do | only if the skill is how somebody *arrives* at the plugin |

Six skills in a plugin cost about 890 tokens a turn to people who never asked
for it. That is the whole reason payload exists.

## Before you believe it works

```bash
claude plugin validate <path>      # frontmatter, layout, and portable paths
claude plugin details <name>       # what it will cost every turn
```

Then the part no validator does: **give an agent the trigger sentence in a fresh
session and see whether the skill activates.** A skill that never fires is
indistinguishable from a skill that does not exist, except that you are paying
for it. If it does not fire, the description is describing the capability rather
than the moment.

## References inside a skill

A `references/` file loads only when the skill's body points at it and the agent
follows the pointer — so the split is by *when it is needed*, not by length. The
contract, the tables, the thing you check every time: body. The skeletons, the
worked example, the long rationale: a reference, named for the question it
answers.
