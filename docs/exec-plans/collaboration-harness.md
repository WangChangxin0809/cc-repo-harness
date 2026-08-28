# Collaboration harness

Goal: two people on one large repository, and each one's agent knows what the
other moved underneath it — before it acts, without being asked — and that
knowing changes the outcome, measured by `claude plugin eval --ablation
with-without` rather than asserted.

Abort if: the with/without delta is indistinguishable on a real
multi-contributor repository. Then push has no measured value at any moment,
what survives is guards, gates and declared relations, and the rest gets a
decision record and a deletion — the same treatment `index/` is getting below
for the same reason.

## Why this order

The falsifying step is second, not last. Steps 4–13 all rest on one unproven
claim: that context delivered when nobody asked for it changes what an agent
does. Three papers measured the opposite arrangement — agent-initiated pull —
and pull won every time it was compared to a precomputed index (see 0004). None
of them measured push, so the claim is open rather than refuted; but building
five phases on an open claim and testing it at the end is how a year gets spent.

So: build the instrument, build the thinnest possible push, measure, and only
then continue.

## Steps

- [x] done    This file. The exec-plan mechanism's first instance is the plan
              for building it — if the format cannot carry its own construction
              it will not carry a migration.

**A · Instrument first — nothing below is judgeable without it**

- [ ] todo    `evals/` skeleton and one case. `claude plugin eval --ablation
              with-without` runs a no-plugin baseline arm and reports the score
              delta; graders marked `with-only` register that the plugin fired
              at all, separately from whether it helped.
- [ ] todo    A real multi-contributor repository as the subject, cloned and
              pinned — `benchmark.py` already clones `requests` and `flask`.
              Not a fixture: this repository has one author and cannot exercise
              "someone else changed it", and a synthetic two-author history
              tests the generator, not the mechanism.
- [ ] todo    Record the no-plugin baseline before writing any new mechanism.
              A baseline measured after the fact is a number chosen to be beaten.

**B · The thinnest push, then the decision**

- [ ] todo    SessionStart delta: what landed since you were last here, filtered
              to paths you have touched. Personalisation comes from your own
              commit history, so there is no index, no rebuild, and nothing to
              go stale. This is moment 2's real content in a shared repository —
              "true right now and no file can hold it".
- [ ] todo    **Decision point.** Measure it with A. If the delta is
              indistinguishable, stop and take the abort branch above. Do not
              proceed to C on the grounds that C is different — it is the same
              claim.

**C · Declared records — only past the decision point**

- [ ] todo    exec-plan lifecycle: active → closed → what happens to the file.
              Unbounded accumulation degrades retrieval (ProactAgent says so of
              its own experience base); `consolidating-notes` is where closed
              plans go.
- [ ] todo    Commit trailers with a schema. The value is not search — that is
              pull, and pull is not ours. It is that a commit is the only record
              every teammate already shares, that cannot be edited after the
              fact, and that `git log` reads without an index. Same shape as
              `Governs:`: one human-written line, one machine-readable edge.
- [ ] todo    PR schema, and route the drift finding to it. "Your change
              falsified a claim someone else wrote down" is a review-time fact,
              and review is where the other person is actually present.
              `drift.py` already detects it and is wired to nothing.
- [ ] todo    Gate: closing an exec-plan whose touched paths have governing
              documents that did not change is red. This is drift in the
              forward direction, and it is checkable, so it is a gate and not
              a reminder.
- [ ] todo    Fast-lane budget: `ci.sh --fast` declares a target (90 s) and
              **reports** overrun. Not a failure — a slow machine would go red
              for a reason that is not the code, and a check that cries wolf is
              unread within a month.

**D · Shrink**

- [ ] todo    Dispose of `index/`. Under this goal it has no consumer: the
              `Governs:` lookup runs inline in `after_edit.py` without a graph,
              and the delta comes from git. Deleting beats demoting — left in
              the tree it reads as though it had been validated.
- [ ] todo    One implementation of `Governs:`. Three exist (`index/build.py`,
              `context/after_edit.py`, `drift.py`), pinned by a selftest, and
              the one defect that escaped was a disagreement between two of them.
- [ ] todo    `probe_repo.py` reports `gates / guards 0 / 0` here because it
              looks under `scripts/` while ours are payload under
              `shared/scripts/`, and reports `~0 tokens/turn` of standing skill
              cost while `claude plugin details` says ~1,312 — it counts
              repository-local skills and is blind to the plugin's, which is the
              cost it exists to report. Then make it recurring: a survey run
              once at install measures a repository that no longer exists.

**E · Upgrade — the reason the plugin persists at all**

- [ ] todo    Version-stamp the payload. `scaffold.py` skips files that exist,
              so N people who installed at N times have N versions and no way to
              say which.
- [ ] todo    `scaffold.py --upgrade` with an acceptance case: scaffold v1,
              upgrade to v2, assert migration happened and local edits survived.
              A plugin that persists but cannot deliver an improvement to an
              already-scaffolded repository has only the trust gate to justify
              itself.

## Not doing, and why

Each of these was proposed and rejected; they are here so the rejection can be
argued with instead of quietly revisited.

| Proposed | Why not |
|---|---|
| Answer questions from docs + code | That is pull. Grep, Glob and Read already are the winning architecture, and three papers say a precomputed index loses to them. We contribute a pointer — "this document governs that path" — and let the agent fetch. |
| Classify each step by type (frontend / backend / database) | Repository-specific, so shipping a fixed taxonomy assumes the shape of repositories we have never seen. Subtree `CLAUDE.md` already routes by path, and paths are observable while labels are arguable. |
| A hard 90 s cap on the fast lane | A budget that fails the build goes red on slow hardware for reasons that are not the code. Declared and reported instead. |
| Semantic index over the repository | Identifiers are exact tokens, so the vocabulary mismatch embeddings solve is weak in code. A-RAG does not build an index for its lexical half either. |
| A second repository for the plugin | `check_docs_runnable.py` and `Governs:`/`drift.py` both compare documents against code in one tree. Splitting deletes two working checks to gain a boundary that directories already provide. |

## Evidence status

The point of this table is that in six months it stays legible which rows were
established and which were judgement.

| Claim | Status |
|---|---|
| Precomputed retrieval loses to agentic pull | **Counter-evidence against us**: three papers, plus our own benchmark losing to a most-churned baseline |
| "When" outweighs "what is stored" | Supporting, indirect: ProactAgent's ablation, on simulated embodied tasks, not code |
| Push changes what an agent does | **Untested.** Nothing here or in the literature has measured it |
| Declared relations cost less than derived ones | Ours, observed: `Governs:` needs no build, no rebuild, no staleness detection; the graph needed all three and a PR to add the third |
