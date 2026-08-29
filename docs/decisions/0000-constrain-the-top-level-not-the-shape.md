# 0000 — Constrain the top level, not the shape

Date: 2026-08-29
Status: accepted

## Context

The docs half of this plugin was designed from first principles: six kinds, each
partitioned by reading trigger, each with a required internal shape, plus a
routing table and a `Governs:` declaration. None of it had been checked against
what anyone else does or against anything measured.

Four surveys were run: published research, agent-facing files in 70 major
repositories, documentation architecture in large long-lived repositories, and
the public guidance of the companies building coding agents. Three finished
independently and converged. The conclusions below are theirs, graded, and the
grades matter more than the conclusions — in six months it must stay legible
which rows were measured and which were judgement.

### What is measured

| Finding | Evidence |
|---|---|
| Documentation **shape** does not predict outcome | Two controlled studies, independently: Ernst & Robillard 2023 (*EMSE* 28(5), 65 participants, narrative vs structured, Bayesian ordered regression) found no association between format and architecture-understanding performance; what predicted it was prior exposure to the source. McMillan 2026 (n=1650 Claude Code sessions, factorial) found none of four file-structure variables nor three interactions detectable after correction |
| Repository **overviews** are inert; **instructions** are obeyed | Gloaguen et al., arXiv:2602.11988 (138 CTXbench + 300 SWE-bench Lite, three agents, with/without): no success-rate gain, inference cost +20%; but a repo-specific tool named in the file was used 1.6×/instance versus <0.01× unnamed |
| Reproduction instructions dominate every other context signal | ORACLE-SWE, arXiv:2604.07789: +56.3%, against edit location +17.4% |
| More context measurably hurts | Jia et al., arXiv:2603.28119: ~6× compression of supporting context *improved* resolve rate 5.0–9.2%. Chroma's context-rot study: degradation from length alone, worsened by topically-similar distractors |
| Reference documentation lives on its examples | arXiv:2503.15231: removing code examples drops accuracy from 0.66–0.82 to 0.22–0.39 |
| Stale prose actively degrades reasoning | CodeCrash, arXiv:2504.14119: misleading natural language in code degrades reasoning 23.2% |
| Drift is universal, not exceptional | Tan, Wagner & Treude, arXiv:2212.01479: of 3,000+ GitHub projects, most contain an outdated code-element reference at some point in their history |
| Curated procedural knowledge helps; self-generated does not | SkillsBench, arXiv:2602.12670: +16.2pp curated, ~0 self-generated — though software engineering was the *weakest* domain at +4.5pp |

### What is observed

| Finding | Source |
|---|---|
| A fixed shallow top level with a free interior survives at scale | OpenStack mandates `admin cli configuration contributor install reference user` for every project repo and explicitly leaves the interior free. Sampled across seven independent repositories: six conform, each with project-specific additions alongside. One deviation (swift: `config` for `configuration`) in roughly a decade |
| Audience above type is what large repositories converged on | Linux (books named for readers), NumPy (NEP 44, users/developers/meta with types nested), Django (`intro topics ref howto` + `internals`), Postgres (manual + in-tree READMEs). Pure type layouts survive only in single-audience projects |
| Agents read instruction files and working notes; classical genres barely at all | Observational mining of 557 sessions / 3,033 documentation opens: agent instructions 35.4%, agent working notes 25.1%, architecture/ADR 4.0%, API reference 1.3%, troubleshooting 0.4%. Failure-driven consultation was 7.5% |
| Restructuring is the cheap half | Corbet, having run the largest documentation reorganisation in open source: *"Converting documents to RST? easy! Evaluating for relevance and correctness? Updating them to match reality? …less so"* |
| Gates are what separate current documentation from stale | Postgres fails the build on a dangling cross-reference, CPython on a new Sphinx warning, Rust on a broken anchor. Every project that moved documentation out of the code repository also lost its blocking checks — verified for Kubernetes, Terraform, React and VS Code, none of which has a `docs/` at root |
| The ADR genre usually dies | Buchgeher et al., *IEEE Access* 2023, mining 900+ repositories: about half of all repositories with ADRs have between one and five. It survives past ~40 records only where a governance process pulls it |
| Sequential numbering collides under concurrent contribution | Open edX's `docs/decisions/` carries four collided numbers. Every numbering scheme that survived takes its number from an existing identifier: Rust from the PR, Go and Kubernetes from the issue |

## Decision

**Fix the top level. Leave the interior free. Put the enforcement on freshness.**

1. `docs/` has a fixed, shallow top level: `index.md`, `decisions/`, `how-to/`,
   `reference/`, `exec-plans/`. Additions are permitted once the index routes
   them. A directory that forks a required name is an error whether routed or
   not, because that is the failure that actually occurred at OpenStack.
   `check_docs_layout.py` holds this.
2. **Internal shape rules are demoted from requirements to advice.** Two
   controlled studies, one on people and one on agent sessions, found no effect.
   The constraint moves to where evidence exists.
3. One shape rule survives as a requirement: **a how-to step carries an
   observable criterion.** That is content rather than form, and it is the
   highest-measured-value thing a document can contain.
4. `troubleshooting/` stops being a directory. Its content moves into the
   failure output of the guard or gate that detects the condition — agents open
   troubleshooting documents 0.4% of the time and self-consult on failure 7.5%
   of the time, but respond well to structured guidance delivered at the error.
5. `generated/` stops being a directory. Being generated is a property a file
   declares in its own header, and the regenerate-and-diff gate keys on that
   declaration rather than on location.
6. **Decision records take their number from the pull request that introduces
   them.** Numbers are not continuous and are not meant to be. A record is
   written as `0000-<slug>.md` and renamed when its pull request opens.
7. `Governs:` is retained and its justification changes: it is a **freshness
   mechanism**, not navigation. Navigation is unsupported — agents infer paths
   rather than consult indexes — while drift is universal and stale prose is
   measurably harmful.
8. The plugin stops claiming improved task success. What is measured is fewer
   wasted exploration turns, lower runtime, and enforced conventions.

## Rejected

- **A pure Diátaxis four-way split at the root.** CPython adopted the vocabulary
  and never restructured; NumPy restructured but put audience above type;
  Django's version predates the framework; Canonical, its largest adopter,
  reports no metric and notes it initially makes documentation *look worse*. No
  adoption with measured outcomes was found anywhere.
- **Audience as our top-level axis**, despite it being what survived at Linux,
  NumPy, Django and Postgres. Those projects ship a product to operators and
  users; a repository the size we intervene in has one audience — someone
  changing this code. Splitting on `agent/` versus `human/` was considered and
  rejected: nothing in 70 surveyed repositories does it, and every document
  would be argued over twice.
- **Deleting the hand-written routing table** in favour of a generator. Large
  repositories all generate their index and get reachability free from a site
  generator's strict mode (Sphinx `-W` turns "not in any toctree" into a build
  failure, with `:orphan:` as the opt-out — the exact shape of our own unrouted
  exemption). We have no site generator and will not add one to a stranger's
  repository, so the hand-rolled checker stays. This is recorded because the
  survey's own words were *"nobody hand-rolls a reachability checker — that is
  itself the finding"*, and the next person should know we read it and
  disagreed for a stated reason.
- **Keeping the required internal shapes** on the argument that they cost
  nothing. They cost the credibility of every other rule beside them: a
  requirement with a null result standing against it teaches that requirements
  here are decorative.

## Consequences

The plugin now constrains less and checks more. Four required directories
instead of six kinds with mandated internals; one new gate; two directories
retired.

`writing-docs` loses most of its prescriptive content, and what remains has to
be honest that it is advice. That skill was among the larger ones, so the
standing token cost falls — but the guidance that survives is weaker-sounding,
and weaker-sounding guidance is easier to ignore. This is accepted deliberately:
the alternative is guidance that sounds strong and is known not to work.

Existing records 0001–0003 keep their sequential numbers. The scheme changes
going forward rather than retroactively, so for a while the directory carries
both, which is ugly and is the honest representation of a convention that
changed.

The claim about `Governs:` is now a hypothesis with a named test rather than a
feature with a rationale. No measured work exists on declared doc-to-code
relationships at all — 8 of 70 repositories declare anything similar and none
verifies it in CI — so this is genuinely untested ground rather than a
best-practice we adopted.

## Revisit when

- The doc-only versus guard-enforced experiment runs. Nobody has compared a rule
  stated in a document against the same rule enforced before the action, and it
  is the central bet of this plugin. Three arms, one rule, violation rate
  against session length.
- Anyone measures whether a repository overview's value scales with repository
  size. The measured null came from small Python repositories, while the largest
  agent files in the wild belong to the largest monorepos. If value scales, the
  right artefact is an empty budgeted template rather than a filled map — which
  is what Ray ships, in nine lines.
- The ADR directory passes roughly forty records, or visibly stops growing.
  Half of all repositories with ADRs never exceed five.
