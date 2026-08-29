# Collaboration harness

**Give a small project the capacity to survive becoming a large one, worked
purely by agents.**

The intervention point is when the repository is small. What it buys is the
ability to absorb many concurrent agents later without the codebase losing
coherence — which is a property the repository has to already possess by the
time it needs it, because nobody adds it under load.

## Why this is the gap

Orchestration is solved and open: OpenAI's [Symphony](https://github.com/openai/symphony)
spec runs an issue tracker as the control plane, gives every issue its own agent
and its own isolated workspace, and polls continuously so no human assigns work.
Its §5 is called *Repository Contract*, and what it asks of the repository is a
root `WORKFLOW.md` holding tracker config and a prompt template. That is all.

So **Symphony scales the number of agents, and nothing scales the repository's
ability to absorb them.** At one agent a messy repository is survivable, because
a person reviews. At twenty concurrent agents opening pull requests, the
repository's own conventions are the only thing still holding coherence — human
attention is precisely what the orchestrator removed. Symphony reports a 500%
increase in landed pull requests; landed pull requests is also the metric that
rises when review is removed, so read that as 500% more entropy arriving at one
tree.

Symphony is cited here as evidence of the shape of the problem, not as an
integration target. **This plugin is for Claude Code**: the agents in every
claim below are Claude Code agents, the entry file is `CLAUDE.md`, and the
delivery moments are Claude Code's hooks. What Symphony demonstrates is that the
orchestration half is solved and open while the repository half is specified as
a prompt template — and that emptiness is the same whichever agent fills the
slots.

## The two halves, restated against concurrent agents

**Awareness** — an agent knows what landed underneath it since its workspace was
cut, before it acts, without being asked, and that knowing changes the outcome.
Under Symphony this is structural rather than occasional: workspaces are cut
from a base and merged later, so *every* agent past the first is working against
a tree that has moved.

**Convergence** — two agents given the same kind of task independently produce
the same shape, and where they do not, a check says so before merge. The metric
is *variance between runs*, not score. This matters more here than under human
collaboration, because the people who would have noticed two divergent solutions
are the ones the orchestrator took out of the loop.

## What concurrency actually breaks

The failure modes are enumerable rather than collected, which is why this plan
no longer waits on a corpus:

| Two agents, one base | Caught by | Where |
|---|---|---|
| Solve the same problem two different ways | guidance, and variance measurement | phase F |
| B's workspace predates A's merge | the SessionStart delta | B1 |
| Both edit one file | git, for free | already solved |
| **Touch no common file, contradict each other in meaning** | `Governs:` pairs, `drift.py` | **nothing catches this today** |
| Each invents its own convention | gates | already built |

Row four is the one CI cannot see and the one that only exists under
concurrency — a single agent never contradicts itself across two workspaces. It
is the strongest argument the declared-relation half of this harness has, and it
has never been tested, because we have never run two agents at once.

Abort if: with the delta delivered, concurrent agents on a scaffolded repository
are no more coherent than concurrent agents without it. Then push has no
measured value at any moment; what survives is guards, gates and declared
relations, and the rest gets a decision record and a deletion — the same
treatment `index/` is getting below, for the same reason.

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

**Phase A was blocked and is not any more, and the reason is worth keeping.**
While the collaborators were assumed to be people, the subject had to be a real
multi-contributor repository with concurrent history, and the cases had to come
from a corpus of real collaboration failures nobody had collected. Both were
genuine blockers and neither dissolves by thinking harder. Agents remove both:
concurrency can be *generated* — N issues, N agents, one base — so the history
is reproducible instead of excavated, and the failure modes are enumerable (the
table above) instead of gathered. The measurement problem was never hard; the
wrong collaborator was assumed.

## The eval ladder

Four rungs, cheapest first, each able to end it. Rungs 0 and 1 are done
(`scripts/measure_cost.py`, `scripts/probe_moments.py`) and needed no model, no
network and no budget.

| Rung | Asks | Status |
|---|---|---|
| 0 | What does it cost? | **Done.** ~2359 tok standing; 55% is the plugin and is paid in every repository, including ones the harness never touched |
| 1 | Does anything fire at all? | **Done.** Five moments, both directions, all as declared |
| 2 | Is the channel inert? | Corrupt the delivered brief in a detectable way; if output is unchanged the channel is dead and B1 fails without paying for rung 3 |
| 3 | Does it converge? | N agents, one task, measure variance — and **our own gates are the grader**, so no judge model and no rubric |
| 4 | Do outcomes improve? | Only if 0–3 survive |

Rung 3 deserves its own note: convergence does not need an LLM judge. Run N
agents on *"add a gate that checks X"*, then run our existing gates and
selftests over what they produced. Conformance rate is the metric — free,
deterministic, and built on judgement we already trust. It measures the gates at
the same time: if both arms score alike, either the guidance does nothing or the
gates are too loose, and both are worth knowing.

## Steps

- [x] done    This plan, in the shape it describes. If the format cannot carry
              its own construction it will not carry a migration.

**Now · What the positioning exposed. Does not wait on the decision point, which
is why it carries no phase letter — the letters mean "in this order".**

- [x] done    Dropped `AGENTS.md` from the plugin's keywords. It was advertised
              and never produced, and the fix runs the other way: this plugin is
              for Claude Code, Claude Code reads `CLAUDE.md`, and a second entry
              file for other vendors is not ours to write. Reading one a target
              repository already has stays in scope — `probe_repo.py` looks for
              it and `moments.md` says what to do when both exist. Handling what
              we find is not the same as promising to produce it.
- [ ] todo    [The ratchet: no single agent may make it worse](steps/N2-ratchet.md)

**A · Instrument first — nothing below is judgeable without it**

- [x] done    Rung 0 and rung 1: `scripts/measure_cost.py` and
              `scripts/probe_moments.py`. Cost before benefit, and firing
              before effect. Neither needs a model or a budget.
- [ ] todo    [A1 · The eval harness](steps/A1-eval-harness.md)
- [ ] todo    [A2 · The concurrency fixture](steps/A2-subject-repository.md)
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
              `context/before_write.py`, `drift.py`), pinned by a selftest, and
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
| Support Symphony's `WORKFLOW.md` | Betting on one orchestrator's adoption before anyone has asked. The spec is Apache-2.0 and stable enough to read, so the cost of waiting is a day's work later; the cost of guessing wrong is a file we ship to strangers forever. Revisit when someone actually runs it against a scaffolded repo. |
| Build the orchestrator | Symphony is the orchestrator, it is open, and it is a solved problem with a reference implementation. Our half is the one it leaves empty — §5 asks the repository for a prompt template and tracker config, and nothing about being able to absorb what comes back. |

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
