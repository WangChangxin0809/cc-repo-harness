# docs/ routing table

- **Covers**: mapping "what I am about to do" to "what to read, then where to edit".
- **Does not cover**: the knowledge itself — that lives in the document being
  pointed at.

| I want to | Read first |
|---|---|
| Know why `docs/` is shaped this way, and what the evidence was | [0019](decisions/0019-constrain-the-top-level-not-the-shape.md) |
| Know whether the retrieval layer is worth its cost | [0001](decisions/0001-retrieval-is-measured-not-argued.md) |
| Know what this plugin is and is not, and why it is named that | [0002](decisions/0002-the-name-states-the-scope.md) |
| Know how the index extracts symbols, and what it used to claim | [0003](decisions/0003-the-extractor-is-regexes-and-says-so.md) |
| See what is in flight | [collaboration harness](exec-plans/collaboration-harness/README.md) |
| See whether the harness helps a repository we did not write | [field trial](exec-plans/field-trial/README.md) |
| Know what was found in passing and deliberately not fixed | [tech debt](exec-plans/tech-debt-tracker.md) |
| Know why the plugin stays installed instead of leaving | [0021](decisions/0021-the-repository-keeps-the-harness-the-plugin-keeps-the-instrument.md) |
| Know why the assessment measures behaviour rather than resemblance | [0020](decisions/0020-the-assessment-measures-behaviour-not-resemblance.md) |
| Know why assessing is one step, and why the plugin speaks once | [0022](decisions/0022-one-assessment-step-that-may-end-in-nothing.md) |
| Know why nothing counts how often a rule is hit | [0023](decisions/0023-nothing-counts-how-often-a-rule-is-hit.md) |
| Know why only one skill is installed and the rest are copied | [0024](decisions/0024-skills-are-payload-except-the-one-that-finds-them.md) |
| Know why dimension 4 watches an agent instead of counting what is kept | [0025](decisions/0025-dimension-4-asks-whether-an-agent-can-find-its-way.md) |
| Know why the defect replay runs by default and the ladder is in seconds | [0026](decisions/0026-the-ladder-is-measured-in-seconds-and-runs-by-default.md) |
| Know why dimension 4 checks whether what is written down is still true | [0027](decisions/0027-thickness-is-the-denominator-and-falsity-is-the-score.md) |
| Know which of the mutation paper's numbers we reproduced, and which we did not | [0028](decisions/0028-mutation-testing-copied-from-a-paper-and-checked-against-its-numbers.md) |
| Know why dimension 5 itemises the floor, and why the replay can be told how to run | [0029](decisions/0029-the-floor-is-itemised-and-the-replay-can-be-told-how-to-run.md) |
| Know why mutation is opt-in, and why a surviving mutant is never a finding | [0030](decisions/0030-mutation-is-the-second-injection-and-a-survivor-is-never-a-finding.md) |
| Know why coverage is reported as a denominator and never as a score | [0031](decisions/0031-coverage-is-the-denominator-and-its-inference-runs-one-way.md) |
| Know why the ladder is read against an inventory of what could have caught it | [0032](decisions/0032-a-rung-cannot-be-read-without-the-layer-behind-it.md) |
| Know why coverage is read from the ecosystem's tool and never measured here | [0033](decisions/0033-the-tools-do-the-measuring.md) |
| Know why a check that runs is not a check that is required | [0034](decisions/0034-running-and-being-required-are-different-settings.md) |
| Know why the document-conflict filter has one rule and not three | [0035](decisions/0035-a-filter-that-emits-half-the-pairs-has-not-filtered.md) |
| Know why a documented promise is tested twice before it is a finding | [0036](decisions/0036-a-contradiction-is-decided-by-an-experiment-not-a-comparison.md) |
| Know why the floor is measured per file and not only as a total | [0037](decisions/0037-a-total-hides-the-one-file-worth-finding.md) |
| Know why the refusal count is read against the repository's own work | [0038](decisions/0038-a-guard-that-refuses-everything-scores-full-marks.md) |
| Know which changes owe a test, and which are counted anyway | [0039](decisions/0039-tidying-is-not-an-untested-change.md) |
| Know why the last pass is an agent's number and not a threshold | [0041](decisions/0041-two-states-cannot-say-which-one-to-fix-first.md) |
| Know why the agent that tests a promise cannot read the repository | [0040](decisions/0040-the-blind-is-the-tool-list-not-the-prompt.md) |
| Know why dimension 4 stopped measuring whether an agent can navigate | [0042](decisions/0042-a-measurement-noisier-than-its-effect-is-not-a-measurement.md) |
| Know why counting mechanisms is allowed where counting files is not | [0043](decisions/0043-a-mechanism-is-not-a-convention.md) |
| Read a number this repository measured rather than argued | [docs/generated/](generated/) — written by scripts, never by hand |
| See which assessment candidates were read, and what was decided | [readings](readings/README.md) — 4.2 and 4.4, answered and kept |

The top level — `decisions/`, `how-to/`, `reference/`, `exec-plans/` — is fixed
and checked by `check_docs_layout.py`. **Inside each one, organise however suits
the material.** Additions at the top level are allowed once a row here routes
into them; a directory that forks a required name is an error either way.

An exec-plan is a folder: its `README.md` owns the plan's state, and the steps it
links own the substance. One row here covers the whole folder — the README is
what routes the rest, so a step file it does not link is reported unrouted.
