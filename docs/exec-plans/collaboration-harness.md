# Collaboration harness

Goal, two halves. Both on one large repository with several people on it, and
both measured by `claude plugin eval --ablation with-without` rather than
asserted.

**Awareness** — each person's agent knows what the others moved underneath it,
before it acts, without being asked, and that knowing changes the outcome.

**Convergence** — two people adding the same kind of thing independently produce
the same shape, and where they do not, a check says so before merge. The metric
here is *variance between runs*, not score: guidance that standardises makes
independent runs resemble each other, and that is visible in a way "was the
answer good" is not.

The second half is what makes this normative for a large project rather than
merely helpful to one person. It is also the half that decays with headcount:
guidance fires when it is triggered, so one person who does not trigger it
diverges, and the leak rate grows with the number of people. Which is why every
row of phase F has to name the check that holds it, or say that it has none.

Abort if: the with/without delta is indistinguishable on a real
multi-contributor repository. Then push has no measured value at any moment,
what survives is guards, gates and declared relations, and the rest gets a
decision record and a deletion — the same treatment `index/` is getting below
for the same reason.

## Why this order

The falsifying step is second, not last. Phases C, D and E all rest on one
unproven claim: that context delivered when nobody asked for it changes what an
agent does. Three papers measured the opposite arrangement — agent-initiated
pull — and pull won every time it was compared to a precomputed index (see
0004). None of them measured push, so the claim is open rather than refuted; but
building four phases on an open claim and testing it at the end is how a year
gets spent.

So: build the instrument, build the thinnest possible push, measure, and only
then continue.

Phase F is the exception and is listed last only because it is longest. It does
not depend on the claim, so it survives the abort branch intact — which is worth
knowing before the measurement comes back, because it means a negative result
costs us four phases rather than everything.

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

**F · Authoring guidance — the teaching half, and the only phase the abort
branch does not touch**

The plugin persists for three reasons: it protects a person from a repository
(the trust gate), it teaches a person, and it can upgrade what it installed.
This phase is the second one, and it is uneven — four artefact kinds have
authoring guidance and three do not. It is deliberately *not* gated behind step
B's decision point, because guidance is worth the same whether or not push turns
out to change anything.

- [ ] todo    CI/CD workflow design. Nothing covers it, and this repository's
              own `ci.yml` now carries a pile of hard-won judgement in comments:
              why concurrency cancels pull requests but never `main`, why there
              are no path filters, why actions are pinned to SHAs, why
              acceptance is a separate job from checks, why `release-hygiene`
              runs only on pull requests. That knowledge exists in one file, as
              comments, and is teachable to nobody. Knowledge stuck in an
              artefact is the nursery rule running backwards.
- [ ] todo    Script kinds, in one table: guard, gate, selftest, context script,
              our-tools-only. Shape, exit-code contract, and where each is
              installed. It is currently split across `writing-checks` and
              `moments.md`, so the question "what kind of script is this" has no
              single answer to read.
- [ ] todo    Hooks reachable outside bootstrap. `moments.md` holds the contract
              but sits under `bootstrap-repo-harness`, so it fires when someone
              is installing a harness and not when someone is adding a hook to
              one that exists — which is every time after the first.
- [ ] todo    Gate: every artefact kind the scaffolder creates has guidance that
              names it, and every kind the guidance names is still something the
              scaffolder creates. Both directions, because guidance for a kind
              that no longer exists reads as authoritative, and a kind with no
              guidance is where everyone invents their own convention. This is
              the nursery discipline applied to the teaching half: the third
              time we notice the two have drifted, it stops being noticing and
              becomes a check.
- [ ] todo    Every piece of authoring guidance names the check that holds it,
              or states that it has none and why. Teaching alone does not
              standardise: a skill fires when triggered, so the one person who
              does not trigger it diverges, and on a large project that leak
              rate scales with headcount. The pairing is the repository's own
              rule — what cannot tolerate a miss does not go through retrieval —
              applied to conventions rather than to rules.
- [ ] todo    Say how a convention chooses its scope. Most conventions in a
              large repository are true of one area, not of everything, and the
              mechanism for that is moment 4 — a subtree `CLAUDE.md`, paid only
              by whoever opens the directory. A project-wide convention that was
              really an area convention is how `CLAUDE.md` reaches its cap and
              how everyone learns to skim it.
- [ ] todo    Retire `repo-index` with the code it documents (phase D). A skill
              teaching a component that was deleted is worse than no skill.

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
| Guidance reduces variance between independent runs | **Untested**, and it is the convergence half of the goal — worth measuring separately from score, because a plugin can raise quality without standardising anything |
| Declared relations cost less than derived ones | Ours, observed: `Governs:` needs no build, no rebuild, no staleness detection; the graph needed all three and a PR to add the third |
