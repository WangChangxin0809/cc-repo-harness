# 0021 — The repository keeps the harness, the plugin keeps the instrument

Date: 2026-08-30
Status: accepted
Supersedes the positioning in 0002, not its scope argument.

## Context

The plugin described itself as something that "lays a repository's foundation
and then leaves", and the README said it "becomes unnecessary". That was an
honest description of what it could do, and it collapsed two different claims
into one:

1. **The repository must not depend on the plugin.** Everything the bootstrap
   installs lives in the target tree, under version control, working for
   teammates who never installed anything.
2. **The plugin has nothing left to offer afterwards.**

The first is the architecture and is not negotiable. The second was only true
because there was nothing to come back for.

`0020` changed that. The assessment measures a repository's standing per-turn
cost, which irreversible actions it refuses before they happen, and how late a
real defect from its own history is first caught. Those are not properties of a
morning's work. They are properties that **decay**:

- a `CLAUDE.md` grows back, one reasonable-looking paragraph at a time
- a guard stops matching a command that changed shape
- a document falls behind the code it claims authority over
- a check that used to refuse an edit gets a narrower matcher during a bad week
- an installed plugin's skill descriptions quietly add to every turn's bill

A repository cannot notice any of that about itself, because every one of them
is invisible in a diff. The whole argument for a gate rather than a paragraph
applies here one level up.

## Decision

**The repository keeps the harness. The plugin keeps the instrument.**

Which half a file belongs to has one test: *does the repository need this in
order to work, or does this only report on the repository?* Guards, gates,
`ci.sh`, hooks, `CLAUDE.md`, `docs/` — copied in, because the repository needs
them. `probe_repo.py`, `drift.py`, `assess/` — never copied, because they report.

The uninstall test stays exactly as it was, and its meaning changes: it
establishes **independence, not completion**. Uninstalling costs you the
measurement, never the machinery.

## Consequences

**Step 0 is worth re-running.** It was written as the front of the bootstrap;
it is equally the thing to run in three months against a repository that was
bootstrapped in one. Same units, so the numbers are comparable — which is the
property the fact sheet was built for and the reason improvement may only be
claimed in its terms.

**Hard rule 4 gets harder, not softer.** A plugin that leaves cannot smuggle
repository behaviour in for long. A plugin that stays can, and the instrument is
the most comfortable place to do it: a diagnostic that starts fixing what it
finds has stopped being a diagnostic, and the repository has quietly acquired a
dependency nobody reviewed.

**Nothing in the tree changes.** This is a decision about what the plugin is
for, not about what it installs. `assess/` was already excluded from
`scaffold.py`'s `COPY` table on the reasoning in `0020`; this records why that
exclusion is the positioning rather than an implementation detail.

**A second, unbuilt use becomes obvious.** If the fact sheet is worth re-running
by hand, it is worth running on a schedule — a monthly job that reports the
standing cost and the catch ladder, the way a repository already watches its
test suite. That is not built, and the argument against building it now is that
nobody has yet re-run the assessment on a repository months after bootstrapping
it. Deciding on a cadence before anyone has seen a second data point would be
inventing the shape of a curve from one observation.

## Evidence status

| Claim | Grade |
|---|---|
| Harnesses decay in the ways listed | **partly measured**: this repository's own `probe_repo.py` had gone blind to its own gates and to ~791 tokens/turn of standing cost, and neither was visible in any diff |
| A repository cannot detect its own decay | judgement, and the same argument as gate-versus-paragraph |
| The fact sheet's numbers are comparable across time | **measured** for before/after within one session; never yet across months |
| Re-running months later is useful | **unmeasured**. This is the claim the positioning rests on, and nobody has done it yet |
