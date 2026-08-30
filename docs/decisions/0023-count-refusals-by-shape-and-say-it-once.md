# 0023 — Count refusals by shape, in `.git/`, and say it once

Date: 2026-08-30
Status: accepted

## Context

The README has claimed since the beginning that a rule which keeps being hit
stops being prose and becomes a file — "the third time the same rule is hit". No
part of the repository counted to three. The arrow was drawn between two boxes
with nothing under it, which is the same defect as a check nobody has watched
fail.

## What can actually be counted

Not what the sentence implied. It implied counting **violations of a rule that
lives in prose**, and a script cannot detect those — if it could, the rule would
already be a gate rather than a paragraph. Building something that claimed to
count them would be the resemblance trap from `0020` in a new place: a number
that looks like evidence and is a guess.

What is observable is **refusals**. That is narrower, and more useful than it
sounds: a guard refusing the same shape of command over and over is not a guard
doing its job, it is a habit meeting a speed bump, and habits are cheaper to
move than to keep stopping.

So the threshold does not say "write a guard" — one already exists. It asks two
questions, and the answer to either is a file:

- **Same shape every time?** The rule belongs earlier than a guard —
  `permissions.deny`, or branch protection on the server. A guard is the third
  line; `dispatch.py` has said so all along.
- **Did a variant get through in between?** The matcher is too narrow, and that
  is a case in `selftest.py`.

## Decision

**`shared/scripts/guards/_recurrence.py` counts refusals by normalised shape in
`.git/agent-harness/`, and appends one paragraph the first time a shape reaches
three inside a fortnight.**

Four public mechanisms solve this problem, and they agree on the order:
normalise, hash, count, act at a threshold. All four parts are taken from them
rather than invented.

| From | What was taken |
|---|---|
| `git rerere` | hash the **normalised** preimage so incidental differences do not fork the identity, and keep it in `.git/` — per checkout, never committed |
| Sentry | group by fingerprint, and let the event **override** the fingerprint, because automatic normalisation is a guess |
| fail2ban | count per key and act at `maxretry` within `findtime` — the **window** is what separates a habit from a coincidence spread over two years |
| the agent-memory writing | three of the same correction is a rule, and the decision to keep it **stays with a person** |

Concretely: flags and the program's first two words are kept verbatim, because
`git push` and `git push --force` are different habits; operands are abstracted
to `<arg>` with their arity preserved, because the branch is not part of the
habit but the number of them is; values inside flags are normalised, because
`--depth=50` and `--depth=100` are one habit. A guard may export
`fingerprint(tool_input)` and collapse its own spellings.

## Why the count is not under version control

A count in the tree produces a diff on every session, a conflict on every merge,
and records one laptop's habits as a fact about the project. `.git/` is where
rerere puts the same kind of observation, and for the same reason.

What deserves to be committed is the **conclusion** — a deny rule, a selftest
case, a decision record — and a person writes that. This is the human-gated half
of the fourth mechanism above, and it is also hard rule 4 holding: the counter
observes, and the file it argues for is somebody's judgement.

## Rejected

**Speaking on every refusal past the threshold.** It would be furniture by the
second time and scrolled past by the third — attached, as it happens, to the one
message that has to land. Once, like `first_look.py`.

**Counting per guard rather than per shape.** "This guard fired eleven times"
mostly says the guard is working. The signal is in whether it was the *same*
eleven times.

**A threshold that acts on its own.** Nothing here writes a file, edits
settings, or opens anything. `0021` is explicit that a diagnostic which starts
fixing what it finds has stopped being a diagnostic.

## Consequences

Twelve defects were planted in `_recurrence.py`; each turned exactly one case
red — **three only after the cases were rewritten**, and those three are the
interesting part:

- The flag pair `git push origin main` against `git push --force origin main`
  also differs in operand count, so abstracting flags away left it green. The
  case now compares against a command with one fewer operand, so arity cannot
  carry it.
- An object id in an operand position is abstracted by the operand rule anyway,
  so that pair tested nothing about `_SHA`. The rule is load-bearing only inside
  a flag, which is kept verbatim.
- Four malformed `tool_input` values did not raise even with `observe()`'s
  wrapper removed. The path that does raise is the real one: `repo_root()`
  returns `None` outside a repository and hands that straight in.

Each is a case that passed while testing nothing, which is the failure this
repository's second hard rule is about, met three times in one file.

## Evidence status

| Claim | Grade |
|---|---|
| Prose-rule violations cannot be counted by a script | **argued**, and it is the definition of why they are prose |
| Three-in-a-fortnight is the right threshold | **unmeasured**. Taken from fail2ban's shape and the agent-memory writing's number; nobody has yet tuned it against real sessions |
| The normalisation groups habits and separates different ones | **measured**: nine pairs, four of which must *not* group |
| A count in `.git/` is the right home | **argued** from rerere's precedent |
| Saying it once is enough to change behaviour | **unmeasured**, and the same open question as `first_look.py` |
