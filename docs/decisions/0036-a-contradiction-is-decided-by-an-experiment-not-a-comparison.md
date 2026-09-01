# 0036 — A contradiction is decided by an experiment, not a comparison

Date: 2026-09-01
Status: accepted
Dimension 4.3: where a document promises something the code does not do.
Follows CASCADE (arXiv:2604.19400), with three divergences recorded below.

## Context

The obvious design is to hand a model the document and the code and ask where
they disagree. The paper measures that baseline at **0.53 precision** —
roughly 27 false positives per 71 real inconsistencies — and the reason is
structural rather than fixable by prompting: a model reads the ordinary gap
between high-level prose and detailed implementation as a contradiction, so
most of what comes back is a paragraph that is *less specific* than the code
rather than wrong about it.

## Decision

**Replace the comparison with an experiment.**

An agent writes several tests from the document alone, never having read the
implementation. They run against the real code; all passing ends it. Any
failing, and the agent writes an implementation from the same sentence, still
blind to the real one, and the same tests run against that. The two runs are
crossed into `p2p`, `f2f`, `f2p`, `p2f`.

**A contradiction is reported only when `f2p > 0` and `p2f == 0`.**

`f2p > 0` is the evidence. `p2f == 0` is the guard, and it is the condition
easiest to drop and most expensive to lose: a test the real code passed and
the document's code fails means that implementation is *incomplete*, so its
successes on the `f2p` tests prove nothing. Without the guard this is the 0.53
baseline with extra steps.

`f2f` matters as much. A test both versions fail is a wrong test, and there
are more wrong tests than there are inconsistencies — which is the entire
reason a second round exists.

**Several tests per claim, not one.** The paper generates 8.4 per method, 5 to
20 per function. The count is not thoroughness for its own sake: the decision
is arithmetic over a set, and a single test cannot produce `p2f` at all. A
design with one test per claim silently has no guard.

**Two numbers travel with the row.** CASCADE reports **precision 0.88, recall
0.21**. It is right about seven of eight findings and finds a fifth of what is
there. That trade is correct for this page — a finding must be real or nobody
reads the next one — but it means **an empty result says almost nothing**, and
the row says so rather than reading as a clean bill.

## Divergences from the paper, and what they cost

| | CASCADE | here |
|---|---|---|
| input | method-level Javadoc | prose documents across a repository |
| generated code | the method body, inside the real class, signature and doc retained | the whole file named by the claim |
| subject | one Java method | whatever the sentence names |

The first is the significant one. A Javadoc comment sits against exactly one
method and its scope is unambiguous; a sentence in a README may be about a
function, a command, a directory or a policy. So the machine half here does
something the paper needs no equivalent of: **it narrows prose to the
sentences that name something executable and assert something checkable**, and
everything else is dropped before an agent is spent. Fenced blocks go too — a
fence is an example, and it is where a document is most often literally
correct.

The second divergence makes `p2f` more likely to fire than in the paper, since
replacing a whole file can break things the method-body swap could not. That
is a bias toward silence, which is the right direction for this page.

Because of all three, **0.88 is an upper bound we have no claim on.**

## Rejected

**Reporting the claim count as a finding.** "21 testable claims, not checked"
is a fact about the session, not the repository. The row prints only once the
rounds have run, per 0033's rule that an unjudgeable row is not printed.

**Spawning the agent from the module.** Hard rule 4. `promises.py` writes two
briefs and grades two sets of answers; something else decides to spend an
agent, exactly as `judge.py` does for mutants.

**Running the agent's code anywhere but a throwaway clone.** The test and the
implementation are both code this repository did not write. One clone per run,
never per phase.

## Consequences

**This is the dearest thing on the page.** Two agent rounds and up to two suite
runs per claim, against mutation's one run per mutant. Opt-in, for the same
reason `--mutate N` is: only the caller can bound it.

**21 testable claims here**, one of them an exit-code promise and one a
documented default; the rest behaviour. None has been run.

## Evidence status

| Claim | Grade |
|---|---|
| A pass-to-fail discards the whole claim | **checked** — planted the guard out |
| A test both versions fail is not a finding | **checked** — planted `f2f` as a finding |
| A test missing from the second run counts in neither | **checked** — planted positional pairing |
| A fenced example is not a promise | **checked** — planted fence tracking out |
| A claim has to name something executable | **checked** — planted the subject requirement out |
| The guard is what separates this from the 0.53 baseline | **cited** — the paper's number, not ours |
| The narrowing finds the claims worth testing | **argued** — 21 sentences from this tree, none yet tested, so precision here is unmeasured |
