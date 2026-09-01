---
description: Measure this repository as a place for an agent to work — five dimensions, one page, nothing changed
argument-hint: "[path] [--no-full] [--test-command CMD] [--mutate N] [--promises]"
allowed-tools: Bash, Read, Grep, Glob, Task
---

Assess the repository at `$1` (default: the current directory) and produce one
page a person can act on.

**Nothing in the repository may be changed.** Deciding what to do about the
findings is a separate step, done by a person holding what you wrote. An
assessment that ends in *nothing here is worth changing* is a result.

## Run the instrument, then hold its numbers

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/factsheet.py \
        --root "${1:-.}" --html assessment.html --json assessment.json
```

If the caller asked for `--memory`, dimension 4 is measured too. It costs
**exactly two agents** — that budget is the design, not a suggestion:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/memory.py \
        --root "${1:-.}" --work "$WORK" --prepare
```

Spawn two `repo-probe` agents on `$WORK/with` and `$WORK/without`, give both
**the same questions** from `$WORK/brief.json`, save their JSON replies, and
score with `--score --with-answers … --without-answers …`. The difference
between the runs is the measurement; the `with` run alone is not a score.
Without this, dimension 4 abstains, which is a result and not a zero.

The replay runs by default: it takes real defects from the repository's own
history and finds how late each one is caught. It costs minutes and it runs
that repository's tests, so the command is printed before it runs. Pass
`--no-full` only if the caller asked to skip it.

Dimension 2 opens with coverage — statements, branches and conditions the
suite never exercises. It is the ladder's denominator, not a score: absence is
the finding, and a high percentage means very little. If the figures look
catastrophic, check that the command you supplied runs all of the repository's
suites and not one of them.

`--mutate N` is off by default and adds a second source of defects: one line
the tests already execute, changed, walking the same ladder. It runs the suite
once per mutant, so pass it only when the caller asked or when the suite is
fast. The changes nothing caught come back as `pending` — read
`mutant_brief` in the JSON, judge each one, and feed the verdicts back with
`--mutant-answers`. Unjudged, they are counted neither way.

If the page says no test command was found, that is a fact about the ecosystem
table, not about the repository. Read the CI file yourself and pass what you
find as `--test-command`. *No tests exist* is a real finding and must still be
reported as one; *a table did not recognise this convention* is not.

Exit 2 means COULD NOT JUDGE. Say so and stop.

**Do not recompute what the page gave you.** You cannot count tokens, you will
not give the same figure twice, and if the numbers come from you then
re-measuring later compares two opinions instead of two measurements.

`--promise-tests` is the other opt-in, and the dearest one. Dimension 4.3
decides whether the documents are still true by experiment: an agent writes
tests from a document alone, they run against the real code, and anything
failing gets a second round where the same agent writes the implementation the
document describes. A contradiction is reported only when a test goes
fail-to-pass and none goes pass-to-fail.

Spawn a `repo-promise-tester` for it — it has `Write` and nothing else, and
that is the point: you have read this repository, so you cannot write these
tests. Feed it `promises_brief` from the JSON, pass its answer back as
`--promise-tests`, then `promises_brief2` and `--promise-impls` if anything is
left pending. Without the first flag the row does not print, which is correct:
an unrun experiment is not a clean bill, and neither is an empty one — the
method finds about a fifth of what is there.

## Then answer what it could not

The page ends by naming its own blind spots. Those are the reason a person is
running this rather than a cron job:

1. Where do the tests actually live? The page names the directories it read
   the verdict from — go and look, including under `frontend/` and `backend/`.
   A suite missing from that row makes the percentage under it wrong, not low.
2. Is the standing cost earning its tokens, or restating the code?
3. Which sentences in the docs are waffle? **Quote them.**
4. Does each wired hook address a mistake THIS repository makes?
5. Is anything you would normally need refused? Name the tool call and the rule.

The most valuable findings usually are not on the page at all. The probes fire
six *generic* destructive actions; a repository's most dangerous action is
often a command in its own README. Read the quick-start, the seed and migration
scripts, and the CI config, and ask what each would do to a database or a branch
that somebody cares about.

Score the repository on what it achieves, not on which conventions it reached
for. A repository that stops destruction with a hand-written `bash` hook is
fully protected.

## Hand back

Point at `assessment.html` — that is the artefact, and it is for the person.
Then, briefly: the worst thing you found in one sentence, the rows worth acting
on with evidence and a proposed change each, and what you are deliberately
**not** proposing and why.

For a longer or unattended run, delegate the whole thing to the
`repo-assessor` agent instead.
