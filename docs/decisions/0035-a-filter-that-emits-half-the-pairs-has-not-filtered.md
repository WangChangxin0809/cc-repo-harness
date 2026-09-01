# 0035 — A filter that emits half the pairs has not filtered

Date: 2026-09-01
Status: accepted
Dimension 4.4: where two documents in this repository disagree with each
other. After ConflictRAG (arXiv:2605.17301), and mostly a record of what did
not survive contact with a real tree.

## Context

Dimension 4 asks whether what the repository writes down is true. `truth.py`
answers half of it — references that point at nothing. The other half is
documents contradicting *each other*, and it has an arithmetic problem before
it has a detection problem: 59 documents is 1711 pairs, and handing all of
them to an agent is a bill nobody pays twice.

ConflictRAG's contribution here is not its classifier but its shape: a cheap
filter first, a model only on what survives, 62% fewer calls at 90.8%
accuracy. Their cheap stage is an embedding classifier, which is unavailable
under `shared/`'s constraints — standard library only, offline. So ours had to
be lexical.

## Decision

**One rule, not three.** Two documents are a candidate when they name the same
code-shaped token and **attach different numbers to it**. That is all.

The two rules that were cut are the record worth keeping, because both sounded
better than the one that survived:

| rule | intended catch | what it produced here |
|---|---|---|
| different path for the same subject | a directory that moved, updated in one document only | **772 pairs** comparing paths that happened to sit near the same flag, values truncated by the window |
| one negates what the other asserts | a document forbidding what another requires | **552 pairs**, because "X does not do Y" beside "X does Z" is two predicates and nothing lexical separates that from a contradiction |

Both signals are real. Neither is expressible with this machinery. The
surviving rule fires **once** on this repository, on `--budget 3000` in
`agents/repo-explorer.md` against `--budget 2000` in the skill it invokes,
where `query.py`'s actual default is 2000.

The general form: **a filter whose own author's repository produces 553 hits
has not narrowed anything, it has moved the reading problem somewhere else.**
Precision here is not a nicety. The output is a bill for an agent's attention,
and an imprecise filter spends it on nothing.

**Four narrowings, each earned by a measured failure.**

*The value must be attached, not nearby.* Sentence scope gave 1051 candidates
from 1891 pairs; a 60-character window gave 1050. A `--json` flag with the
words "Stage 5" eleven characters away is not a flag with the value 5. The
number must follow the name across nothing but separators.

*Disjoint, not merely unequal.* `{600}` against `{077, 600}` is one document
giving more context than the other. Requiring inequality reported every such
pair as a contradiction.

*A token most documents name is not evidence.* `CLAUDE.md` produced 27 of the
first 40 candidates on its own. The oldest rule in retrieval, applying
unchanged: a term with no discriminating power is not evidence, however
code-shaped it looks.

*Only what the repository keeps.* Tracked files, and no dot-directories. This
repository holds a corpus of **other people's cloned repositories** under
`eval/.work/`, and the first run compared 355 of their documents against each
other and presented the result as a finding about this tree. `tmp/` holds
throwaway pages nobody committed on purpose.

**Supersession is not conflict.** A decision record that replaces an earlier
one contradicts it on purpose, and a repository that keeps its history has
many. Before this rule existed the loudest candidates were 0031 against 0033 —
the system working, reported as the system broken. Documents declaring
`Supersedes`, `Replaced by` or `Status: superseded` are not paired.

**Three signals travel with each pair and none decides.** Which was written
last; which is on the floor — not a claim about correctness but about which
one is currently doing damage, since a claim on the floor reaches the agent
whether or not anybody opened the file; and which of the disputed values the
code contains, the strongest and still not proof.

**Their Entropy-TOPSIS ranks those three, and does not pick between them.**
III-C of the paper is the one part of it that needs no model: entropy
weighting and TOPSIS are both closed form, so the arithmetic is copied whole
rather than approximated. Their five criteria are pulled out of prose by an
LLM; ours are the three signals above, already numeric.

The entropy step is what earns its passage, and `on_floor` is the reason.
That criterion is false on every candidate in most repositories, and a reader
skipping past the same "neither is on the floor" on every pair is doing by
hand what a weight of zero says once. `E_j = -1/ln(m) · Σ p_ij ln p_ij`, then
`w_j = (1-E_j)/Σ(1-E_k)`: a criterion that does not vary has maximum entropy
and drops out. On this repository the run now reports `on_floor 0.00,
recency 0.50, code_agrees 0.50` — two signals did the work and the third said
so itself.

**The matrix is min-maxed before the entropy, and that is not cosmetic.**
Commit timestamps inside one repository agree to four significant figures.
Raw, every `p_ij` is uniform to a rounding error, recency comes out with the
entropy of a constant, and the signal is dropped with nothing saying it was.
It survives the bug when it is the only criterion that varies — a lone
non-degenerate column normalises to the whole weight however little it
discriminates — which is why the selftest has to make it compete.

## The divergence: it ranks, it does not decide

ConflictRAG **selects a source** with `C*` and generates the answer from it.
Here the number is handed over with the pair as `leans`, and the agent still
answers `believe`.

Not timidity. Theirs answers a query whose asker cannot check it; ours is read
by somebody who can open both files in a second, and the pair usually is not a
conflict at all — two documents giving one number two values are as often an
example beside a default. A score that picked winners would also be this
plugin's rule 4 broken from the inside: a diagnostic that starts fixing what
it finds has stopped being a diagnostic -> 0021.

`case_the_score_ranks_and_does_not_decide` is the guard, and it fails if
`rank` ever writes `believe`, `real`, `verdict` or `winner` into a candidate.

**What the numbers are worth here.** The paper's 62% cost reduction and 90.8%
accuracy are measured at `K=5` retrieved documents — ten pairs per query. This
runs over a whole repository: 64 documents, 2016 pairs. The shape transfers;
those two numbers do not, and are not claimed.

## Rejected

**Embeddings.** The paper's cheap stage, and unavailable: `shared/` installs
nothing and runs offline. Ours misses conflicts phrased without a shared
token, which is a real loss and the price of the constraint. The same
constraint rules out every released implementation in this area — MiniCheck,
SeCon-RAG and RAMDocs all want `torch`, `transformers` and weights, and
ConflictRAG has released nothing at all: its code and prompts are promised
"upon acceptance", and it is still only submitted to IEEE SMC 2026.

**Their conflict taxonomy.** The 4-class head sorts conflicts into factual,
temporal, opinion and none. Opinion does not exist between a repository's own
documents, and temporal is what supersession already handles by construction.
Two live categories is not a taxonomy worth the output field.

**Their type-adaptive resolution, and conflict-aware generation.** Stages 3
and 4 of the pipeline end in a written answer. This module reports and stops.

**Reporting the candidate count as a finding.** A candidate is not a conflict.
The row says "not yet judged" until an agent has read them, exactly as
surviving mutants stay `pending` under 0030.

## Consequences

**One candidate on this repository, and it is real.** An agent definition and
the skill it invokes give different values for the same flag.

**The path signal moves to 4.3.** Deciding where something lives means looking
at the tree, which is CASCADE's territory, not a lexical comparison of two
documents.

## Evidence status

| Claim | Grade |
|---|---|
| Supersession is excluded | **checked** — planted the exclusion out |
| A value must be attached, not nearby | **checked** — planted an unanchored number match |
| Overlapping values are agreement | **checked** — planted `!=` for `isdisjoint` |
| A ubiquitous token is not evidence | **checked** — planted the frequency ceiling out |
| Only tracked files are compared | **checked** — planted the tracking filter out |
| A cloned repository's documents are not ours | **checked** — planted dot-directory walking |
| The two cut rules were not salvageable | **measured** — 772 and 552 candidates on this tree, against 1 for the rule kept |
| One candidate is the right number | **argued** — one repository, and the filter's recall is untested because nobody has planted a conflict in a real tree and watched it be found |
| A criterion that never varies is weighted to zero | **checked** — planted equal weighting in |
| Raw timestamps collapse the recency weight | **checked** — planted the min-max out, against a competing criterion |
| A truncated grep is not the strength of the signal | **checked** — planted the display cap back into the ranking |
| The score ranks and does not decide | **checked** — planted `believe` into `rank` |
| A tie is a tie, not a column order | **checked** — planted an index-dependent tiebreak |
| Entropy-TOPSIS ranks better than the three signals raw | **untested** — the paper measures 82.7% against 78.3% for LLM direct selection; this repository has one candidate, which is no sample at all |
