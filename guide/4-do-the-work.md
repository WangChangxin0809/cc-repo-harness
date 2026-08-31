# Do the work

- **Covers**: stage 3 — turning an accepted plan into changes, and the two
  obligations that apply to every one of them.
- **Does not cover**: deciding whether to act ([3](3-decide.md)), or proving it
  worked afterwards ([5](5-re-measure.md)).

Nothing here is specific to assessment. It is ordinary work, done in a
repository whose harness you are about to change, and the whole of this stage
is two rules that are easy to skip precisely when they matter.

## A check nobody has watched fail is a file, not a check

This is the one rule that has no exception. A gate or guard is not finished when
it is written and passing — passing is what an empty function does. It is
finished when:

1. you broke something on purpose,
2. you watched **that** check go red and name the thing you broke,
3. you put the broken input into its selftest, so it is watched again forever.

Step 2 is where the surprises are. A regex that matches nothing, a hook wired to
the wrong event, a `sys.exit()` that returns 1 where Claude Code needs 2 —
each of these passes every test that was never designed to fail.

Two failure shapes worth planting deliberately, because both look like success:

| plant | what it catches |
|---|---|
| a defect the check *should* stop | the check works at all |
| a check that **crashes** — a bad import, a syntax error | that a crash is not read as a pass |

The second one has bitten this project. Claude Code treats a hook exiting 2 as
*block* and **any other non-zero as a non-blocking error — the action
proceeds**. A guard with a missing import therefore allows everything while
looking, from outside, exactly like a guard that is protecting you.

## Exit 2 means COULD NOT JUDGE, and is never a pass

A check that cannot see its subject must say so and return 2. It must not return
0, and it must not be wrapped in `|| true`.

The temptation is always the same: the check is noisy in some environment, so it
gets a fallback that makes the noise stop. What that actually ships is a check
which is green when it works and green when it is broken — and nobody finds out
which, because the two are indistinguishable from the outside.

If a check genuinely cannot run somewhere, that is an **abstention**, and an
abstention is a result. Report it as one.

## While you are in there

Three things that are cheap now and expensive later:

- **Write the decision record as you go.** Not afterwards. The alternative you
  rejected is vivid while you are rejecting it and gone a week later, and the
  rejected alternative is the half of a decision record that has value.
- **Grade your own claims.** *measured* / *checked* / *argued* — and say which.
  An argued claim is fine; an argued claim wearing a measured claim's clothes
  is how a repository ends up believing things nobody ever tested.
- **Leave the fact sheet's `--json` where you found it.** Stage 5 diffs against
  it, and regenerating it after the change measures the wrong thing.

## What "done" means

Not *the change is written*. Done is:

- every check you added has been watched failing, and its selftest holds that
- nothing you changed made an existing check pass for a new reason
- the plan's `## Not doing, and why` still says what you are still not doing
- the rows you claimed you would move are the rows you are about to re-measure

**Criterion**: somebody who was not here can run one command, see it go red on
the defect you planted, and see it go green without it.

Then [re-measure](5-re-measure.md) — in the same units, with the same command.
