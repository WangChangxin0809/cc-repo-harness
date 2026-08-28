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

Abort if: the with/without delta is indistinguishable on a real
multi-contributor repository. Then push has no measured value at any moment,
what survives is guards, gates and declared relations, and the rest gets a
decision record and a deletion — the same treatment `index/` is getting below
for the same reason.

## How this folder works

**This file owns state. Step files own substance, and never restate status.**
The rule is not tidiness: nobody reopens a finished step file to change `doing`
to `done`, because by then they are on the next step. State duplicated into the
steps would drift in one predictable direction, and the drift would be silent.

**A step earns a file when it has decisions to record or is worth handing to a
subagent.** Otherwise it is a line here. The failure this shape invites is
trading "one file too long" for "twenty files too many", and the numbering gaps
below are how you see which steps deliberately have none.

**A step file is written when the step is entered, not upfront.** Written in
advance it is fiction, and fiction in a plan is indistinguishable from a
decision that was actually made. A file opened early holds the questions the
step has to answer; the answers land as they are made.

**Every step file carries `## Consulted`, and it may say "none, because".** What
it may not do is be absent. Above, four of the five say some part of the search
has not been run — which is the field working: an empty one is a visible debt,
where no field at all is a step that reads as grounded because nobody asked.

## Why this order

The falsifying step is second, not last. Phases C, D and E all rest on one
unproven claim: that context delivered when nobody asked for it changes what an
agent does. Three papers measured the opposite arrangement — agent-initiated
pull — and pull won every time it was compared to a precomputed index. (That
reading is owed a decision record and does not have one; until it does, the
claim above is only as checkable as this paragraph.) None of them measured push,
so the claim is open rather than refuted; but building four phases on an open
claim and testing it at the end is how a year gets spent.

Phase F is the exception and is listed last only because it is longest. It does
not depend on the claim, so it survives the abort branch intact — which means a
negative result costs four phases rather than everything.

## Steps

- [x] done    This plan, in the shape it describes. If the format cannot carry
              its own construction it will not carry a migration.

**A · Instrument first — nothing below is judgeable without it**

- [ ] todo    [A1 · The eval harness](steps/A1-eval-harness.md)
- [ ] todo    [A2 · A real multi-contributor subject](steps/A2-subject-repository.md)
- [ ] todo    Record the no-plugin baseline before writing any new mechanism.
              A baseline measured after the fact is a number chosen to be beaten.

**B · The thinnest push, then the decision**

- [ ] todo    [B1 · SessionStart delta, and the decision point](steps/B1-session-delta.md)

**C · Declared records — only past the decision point**

- [ ] todo    exec-plan lifecycle: active → closed → what happens to the folder.
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
              documents that did not change is red. Drift in the forward
              direction, and checkable, so a gate and not a reminder.
- [ ] todo    Fast-lane budget: `ci.sh --fast` declares a target (90 s) and
              **reports** overrun. Not a failure — a slow machine would go red
              for a reason that is not the code, and a check that cries wolf is
              unread within a month.

**D · Shrink**

- [ ] todo    [D1 · Dispose of `index/`](steps/D1-dispose-of-index.md)
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

**F · Authoring guidance — the teaching half, which the abort branch does not touch**

The plugin persists for three reasons: it protects a person from a repository
(the trust gate), it teaches a person, and it can upgrade what it installed.
This phase is the second, and it is uneven — four artefact kinds have authoring
guidance and three do not.

- [ ] todo    CI/CD workflow design. Nothing covers it, and this repository's
              own `ci.yml` now carries a pile of hard-won judgement in comments:
              why concurrency cancels pull requests but never `main`, why there
              are no path filters, why actions are pinned to SHAs, why
              acceptance is a separate job, why `release-hygiene` runs only on
              pull requests. That knowledge exists in one file, as comments, and
              is teachable to nobody — the nursery rule running backwards.
- [ ] todo    Script kinds, in one table: guard, gate, selftest, context script,
              our-tools-only. Shape, exit-code contract, where each is installed.
              Currently split across `writing-checks` and `moments.md`, so
              "what kind of script is this" has no single answer to read.
- [ ] todo    Hooks reachable outside bootstrap. `moments.md` holds the contract
              but sits under `bootstrap-repo-harness`, so it fires when someone
              is installing a harness and not when someone is adding a hook to
              one that exists — which is every time after the first.
- [ ] todo    [F4 · The guidance coverage gate](steps/F4-guidance-coverage.md)
- [ ] todo    Every piece of authoring guidance names the check that holds it,
              or states that it has none and why. Teaching alone does not
              standardise: a skill fires when triggered, so the one person who
              does not trigger it diverges, at a leak rate that grows with
              headcount.
- [ ] todo    Say how a convention chooses its scope. Most conventions in a
              large repository are true of one area, and the mechanism is moment
              4 — a subtree `CLAUDE.md`, paid only by whoever opens the
              directory. A project-wide convention that was really an area
              convention is how `CLAUDE.md` reaches its cap and everyone learns
              to skim it.
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
