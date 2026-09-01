# Re-measure

- **Covers**: stage 4 — the last one, where a claim about the repository either
  survives or does not.
- **Does not cover**: the work itself ([4](4-do-the-work.md)), or how the first
  numbers were obtained ([1](1-assess.md)).

The point of measuring before was to be able to measure after. Skip this and the
whole sequence collapses into *we did some work and it felt better*, which is
the state most repositories were already in.

## Same command, same units

```bash
python3 shared/scripts/assess/factsheet.py --root . --json after.json
```

The same command that produced the first page. Not a shorter version, not a
different flag set — a re-measurement that changes the instrument measures the
instrument.

Two things follow, and both are easy to get wrong:

- **`--no-full` before must mean `--no-full` after.** The replay is on by
  default; dimension 2 abstains when it is skipped, and an abstention
  compared against a measurement is not a comparison.
- **`--memory` before must mean `--memory` after.** Dimension 4 costs two agents
  and is the only non-deterministic dimension; comparing a probed run to an
  unprobed one reads as a collapse that never happened.

## Only the measured rows may be compared

The checklist marked every row *measured* or *judged*. Those two do not
re-measure the same way, and pretending otherwise is how improvement gets
claimed without being demonstrated:

| basis | what a second run gives you |
|---|---|
| **measured** | a number that moved, or did not |
| **judged** | a second opinion, from an agent that has now read your change |

A judged row can only be *re-read*, and it should be re-read by saying what
changed and why the judgement should differ — not by asking the same question
again and accepting a nicer answer.

## Say it in the repository's units, not ours

The only claims worth making are claims about the repository:

> ✗ "We added three gates and a guard."
>
> ✓ "Two of six irreversible actions were refused; now five are. No legitimate
> action became blocked. Defects that previously reached CI are now refused
> before the write."

The first is a claim about us and is true whether or not anything improved. The
second can be wrong, which is what makes it worth saying.

## A row that did not move is a result

Sometimes the change was right and the number did not move. Sometimes the change
was wrong. Sometimes the row was never going to move because it was measuring
something adjacent to what you fixed.

All three are worth writing down, and the third is the most valuable, because it
says the dimension is not asking quite the right question — which is a finding
about **the instrument**, not about the repository, and it is the only way the
instrument ever improves.

A regression is also a result. If dimension 5's floor went up because you added
a `CLAUDE.md`, that is the bill for whatever dimension 4 gained, and the two
should be read together rather than one at a time.

## Close the loop

Update the exec-plan's `README.md` with what moved, what did not, and what you
now believe that you did not believe before. Then it is finished — including
when the honest ending is *this did not work*.

**Criterion**: somebody reading only the plan's README can say which rows moved,
by how much, in the repository's own units, and what is still open.
