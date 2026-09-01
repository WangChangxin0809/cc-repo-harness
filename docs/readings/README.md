# Readings

Two of the assessment's sub-items hand over a list a machine narrowed and
cannot judge: **4.2**, candidates for a second reading, and **4.4**, documents
that might contradict each other. An agent reads them and says which are real.

Without somewhere to put that answer, the reading does not survive the session.
The same twenty-four candidates come back on the next run and on every run
after it, and each reader pays again to rediscover that `scripts/guards/` is
what a *scaffolded* repository gets and is correctly absent from the repository
that scaffolds it. These files are that answer, kept.

```bash
python3 shared/scripts/assess/factsheet.py --root . \
  --truth-answers docs/readings/truth-answers.json \
  --conflict-answers docs/readings/conflict-answers.json
```

## They are keyed by what they are about, not by position

An answer names the `file` it concerns. The candidate lists are rebuilt from
the tree on every run, so an `id` is a position in one run and nothing more:
act on a candidate and everything after it renumbers. A file of ids alone would
then attach yesterday's verdicts to today's candidates, silently, in whichever
direction the shift went.

So `id` is the fast path, used when it agrees with `file` and ignored when it
does not, and an answer that cannot be matched to exactly one candidate is
reported as stale rather than applied to a near miss.

Tier 3 needs one more thing, because its claim is not a property of the
document at all. *"5 commit(s) to what it points at"* changes whenever anything
that document points at is touched — by anyone, for any reason — so an answer
keyed to the claim would expire on somebody else's commit, and an answer keyed
to nothing would apply last week's reading to this week's document. Each tier-3
candidate therefore carries `moved`, the moment the document itself last
changed, and the answer copies it. The reading stands while the document does
and expires when it does not, which is exactly as long as it was true for.

## Answering, and re-answering

```bash
python3 shared/scripts/assess/truth.py    --brief run.json   # the questions
python3 shared/scripts/assess/conflict.py --brief run.json
```

A candidate you leave out stays pending, and pending is printed. That is the
honest state: an unread candidate and a considered one are different things,
and only one of them is a decision.

**A dismissal is worth writing down.** Twenty-three of the twenty-four here are
dismissals, and they are the reason nobody has to read those twenty-three
again. The two that were real are in the file with what was wrong and the
change that fixed it.
