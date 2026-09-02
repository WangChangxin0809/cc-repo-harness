# 0056 — Answers that outlive a run

Date: 2026-09-02
Status: accepted

## Context

Dimension 4.2 (truth) scored 5.5/10 against a page that carried its own
explanation: of its 24 candidates, roughly two thirds were never findings and
never will be. `guide/` and `skills/bootstrap-repo-harness/` describe the
repository a person is scaffolding, not this one — `scripts/guards/`,
`src/billing/`, "five guards", "three gates" are correct exactly because they
are absent or mismatched here. Every run rediscovers them, a reader spends its
turn dismissing them again, and the row is graded on how many times a human
had to re-answer a question this repository already answered once.

`truth.py` was built to make a dismissal durable: an answer is matched by the
`file` it names, not by the `id` a run happened to number it, because the
candidate list is rebuilt from the tree and renumbers on every run. A tier-3
answer additionally carries `moved`, the commit at which the document it is
about last changed, and it stops applying the moment that document is edited
again — `_locate`'s `unexpired()` check. The mechanism to keep an answer was
already there. Nothing in this repository was using it: `commands/assess.md`
and `agents/assess/reader.md` both had the reader answer every brief from
nothing, every time, and the file the reader wrote (`W/d4/truth.answers.json`)
lived in a throwaway directory outside the repository and vanished with it.

`docs/readings/` already existed, holding `truth-answers.json` from an earlier
round of this same reading and a `README.md` explaining the file-not-id
convention. What it did not have was anything telling a reader to *use* it —
the wiring stopped one step short of the payoff.

Reading the 24 candidates by hand (this run) found 23 of them are the same
shape as before: a heading miscounted against a directory of the same name
("Three rules" against `rules/`), a target-repository path correctly absent
here (`scripts/guards/`, `scripts/index/`), an anti-pattern quoted to be
avoided ("Never *we added five guards*"), or a document whose subject churned
without the document's own claims going wrong. One was real:
`shared/skills/repo-index/SKILL.md` said "five guards define `check`" and, at
the commit that sentence was last touched, five did (`dispatch.py`,
`_template.py`, and three real guards). Three guards have shipped since
(`no_committed_credential.py`, `no_computed_delete.py`,
`no_silenced_check.py`), all defining `check`, and the same paragraph's other
count — "sixteen unrelated `def main()`" — had drifted further still, to 69
per `shared/scripts/index/build.py`'s own graph. The honest fix was to correct
the sentence, not to store a dismissal for a claim that was actually wrong;
done in this change, with numberless phrasing ("every guard module defines
`check`") where a hardcoded count would only go stale again at the next guard.

## Decision

**Answer the brief once, keep the answer in `docs/readings/`, and teach the
pipeline to start from it.** `docs/readings/truth-answers.json` gets this
run's 23 dismissals appended (it already accumulates across runs — several
ids there carry more than one entry, one claim per point in the tree's
history). The one real finding is not stored as an answer: the document is
fixed, so there is nothing left to dismiss, and recording a stale claim as
"true" would either never match again or — proven while testing this change
— coincidentally reattach to whatever unrelated candidate a later run happens
to place in the same slot of the same file. `docs/readings/README.md` already
states why a stored answer is safe (the file-over-id match, the tier-3 expiry)
and did not need rewriting.

`commands/assess.md` step 2 and `agents/assess/reader.md`'s answer phase now
say, in one sentence each, that a repository carrying `docs/readings/`
answers is judged only on what is new or expired — never re-dismissed.

## Consequences

- Verified with `--truth-answers`: the original run (24 candidates) grades to
  24 dismissed / 0 pending against the updated answers file. A fresh run
  taken after the `repo-index/SKILL.md` fix still has 24 candidates — a new,
  unrelated "Two readings" heading-count took the fixed sentence's place in
  the round-robin — and still grades to 0 pending, because an older tier-3
  entry for that same file, whose own claim and tier do not match, reattaches
  to it through `_locate`'s last, unqualified narrowing step (any single
  remaining candidate for a named file is accepted once the exact claim and
  tier both fail to narrow it). That is a real edge in the matching design,
  worth knowing before trusting a stored answer blindly on a heavily-edited
  file — not something this change alters, since `truth.py` is shared
  payload and its matching contract is out of scope here.
- Synthetically moving a stored tier-3 answer's document (bumping the
  candidate's `moved` past the answer's) does make that entry `stale` and
  the candidate `pending` again, confirming the expiry half of the mechanism
  independently of the reattachment case above.
- The next assessment of this repository pays for 23 fewer re-reads on this
  row, and whoever reads the one new candidate this run left pending starts
  from a page that already explains why the rest are not findings.
