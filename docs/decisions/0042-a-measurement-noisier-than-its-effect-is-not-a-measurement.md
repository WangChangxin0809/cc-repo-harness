# 0042 — A measurement noisier than its effect is not a measurement

Date: 2026-09-02
Status: accepted
Supersedes the navigation half of [0025](0025-dimension-4-asks-whether-an-agent-can-find-its-way.md).
Removed: `memory.py`, the `repo-probe` agent, `--memory`, and sub-item 4.0.

## Context

0025 argued that a repository's memory cannot be measured by counting what it
keeps. That argument still holds and nothing here touches it: a count grades a
repository on whether it adopted somebody else's conventions, goes *up* when
you install this plugin, and calls
[0024](0024-skills-are-payload-except-the-one-that-finds-them.md) — which cut
the standing cost by 81% — a regression while dimension 5 called it an
improvement.

The answer 0025 gave was a **difference**. Two `repo-probe` agents, each
reading a tree it had never seen and answering the same nine questions: six
about the repository as a whole, three that were the subject lines of real
commits with those commits' own diffs as the answer key. One read the tree; one
read a copy with `CLAUDE.md`, `.claude/` and every nested `CLAUDE.md` removed.
The gap between them was the memory.

It is the right question. It is not a measurement, and the reason is
arithmetic rather than design.

**The noise is larger than the effect.** Each run is one sample of a
non-deterministic process, and each side is three graded questions. The
quantity reported is the difference of two such samples, so it carries both
variances and none of the averaging — the one thing that would shrink it is
repetition, and repetition is the one thing the budget forbids. The effect it
looks for is a file or two.

**The failure mode is the worst available.** A measurement that moves when
nothing has changed does not read as noise on the page. It reads as a finding.
Rerun the pair after an afternoon of no work and dimension 4 can improve; do
the same after real work and it can collapse. Somebody acts on that, and the
page has spent its credibility on a coin.

**It could not be made cheaper without making it worse.** More samples is more
agents, and dimension 4 was already the only part of the assessment with an
agent budget. Fewer questions is less signal against the same variance.

`truth.py`'s own opening said this in the sentence that introduced it — *"the
right measurement and an expensive, noisy one"* — and the honest reading of
that sentence was that it should not ship, not that it should ship with a
caveat.

## Decision

**Removed, not disabled.** `memory.py`, `agents/repo-probe.md`, the `--memory`
flag, and sub-item 4.0 are gone from the tree.

A flag nobody should pass is worse than no flag: it is code that has to keep
working, documentation that has to stay true, and a row on the page reading
*not probed* — which invites somebody to go and probe it. An abstention is an
honest answer to a question worth asking. This question is not one this
instrument can ask.

Dimension 4 keeps the half that a single deterministic read can answer:

| | |
|---|---|
| 4.1 | what is written down, and whether its references resolve |
| 4.2 | candidates for a second reading, judged and recorded |
| 4.4 | documents that contradict each other |
| 4.5 | whether the instructions are shaped so a model can follow them |

Its question changes with it. It was *can an agent find its way here, and is
that because of something the repository keeps?* It is now **is what this
repository writes down still true, and is it worth what it costs to keep?** —
which is what the surviving rows actually answer, and what the old headline
claimed to answer while abstaining on the half that would have.

## Consequences

**The thing 0025 was protecting against is now handled elsewhere.** Thickness
stays a denominator and never a score, so adding files still cannot raise
anything, and installing this plugin still does not improve the repository it
is measuring. What is lost is the positive claim — *this `CLAUDE.md` is
carrying an agent* — and nothing here replaces it. Dimension 5 asks what the
standing context costs; nothing now asks what it earns.

That gap is real and it is stated rather than papered over. A row that cannot
tell a good `CLAUDE.md` from a thick one is a row nobody should trust, and one
that says nothing at least does not mislead.

**Scored sub-items go from fourteen to thirteen**, none of which abstain on a
repository with documentation. The average is computed over what was measured,
which it always was.
