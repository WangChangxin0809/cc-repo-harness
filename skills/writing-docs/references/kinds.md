# The six kinds, with templates

Each opens with a two-line scope. That is not ceremony: it tells the next writer
where new material goes, which is the difference between a document that stays
focused and one that becomes the place things get appended to.

---

## `docs/how-to/` — I am about to do a thing

```markdown
# Rotate the signing key

- **Covers**: replacing the active signing key without downtime.
- **Does not cover**: the key format (`docs/reference/keys.md`), or why rotation
  is manual (`docs/decisions/0012-manual-rotation.md`).

Prerequisites: <what must already be true>

### 1. Mint the replacement

    ./scripts/keys.sh mint --label $(date +%Y%m)

Criterion: `./scripts/keys.sh list` shows two keys, exactly one `active`.

### 2. Promote it

    ./scripts/keys.sh promote <id>

Criterion: a fresh token verifies against the new key and fails against the old.
If both verify, the old key was not retired — go to step 3 before assuming
success.

### 3. Retire the old key

    ./scripts/keys.sh retire <old-id>

Criterion: `./scripts/keys.sh list` shows one key.
```

Three parts per step, all three present. The criterion is what makes the step
checkable by someone who does not already know the answer; steps without one are
read as gestures and executed as gestures.

Write the positive path. The set of wrong ways is unbounded and a document that
enumerates them is both longer and still incomplete. A prohibition worth keeping
goes where it fires — a guard's block message, a gate's failure output, a
subtree `CLAUDE.md` — because a prohibition has no reading trigger of its own.

---

## `docs/reference/` — I need to look up a fact

Tables and rules, keyed for lookup. No narrative, no ordering by importance;
order by whatever makes a value findable.

```markdown
# Key formats

- **Covers**: the on-disk and on-wire shape of every key type.
- **Does not cover**: how to rotate one (`docs/how-to/rotate-signing-key.md`).

| Type | Encoding | Length | Where stored |
|---|---|---|---|
| signing | base64url | 32 B | `secrets/signing/` |
```

A glossary belongs here and is worth more than it looks. It pins the project's
own vocabulary, which is what every search depends on — when it drifts, searches
silently return less, and nobody attributes that to the glossary.

---

## `docs/troubleshooting/` — I hit a symptom

Symptom first, in the words the reader actually has: the error text, the wrong
number, the thing that did not happen. Whoever is reading this knows the symptom
and nothing else, so anything else in the heading position is unsearchable.

```markdown
## `verify: signature mismatch` on every request after a deploy

**Cause**: the new key was promoted before the verifier's cache TTL expired, so
half the fleet is still checking against the retired key.

**Action**: `./scripts/keys.sh cache-flush`, then confirm with
`./scripts/keys.sh list --by-node` that every node reports the same active id.

**Not this**: if only *some* requests fail, the cause is a partial rollout, not
the cache — see `docs/troubleshooting/partial-rollout.md`.
```

---

## `docs/decisions/` — why is it like this?

Numbered, dated, immutable. Numbering is sequential and never reused.

```markdown
# 0012 — Signing key rotation stays manual

Date: 2026-03-04
Status: accepted          <!-- or: superseded by 0031 -->

## Context
<The forces. What made this a decision rather than an obvious step.>

## Decision
<What was chosen, stated so it can be checked against the code.>

## Rejected
- **Automatic rotation on a timer.** <Why not — concretely.>
- **<the other real alternative>.** <Why not.>

## Consequences
<What is now true, including the costs. A record listing only benefits is a
pitch, and gets read as one.>

## Revisit when
<What would have to change.>
```

When a decision changes, write a new record with `Supersedes: 0012` and edit the
old one **only** to add `Superseded by: 0031`. Editing the original destroys the
one artifact that records what you used to believe and why — which is the part
that stops the idea being re-litigated every six months.

Record what you rejected. A decision that lists only the winner reads as
inevitable, and the next person re-proposes what was already killed.

---

## `docs/exec-plans/` — what are we in the middle of?

Multi-session work needs a file, because context does not survive the session
and the plan is the only thing that does. Past a few steps it needs a **folder**,
because two demands pull opposite ways: the plan's state has to be readable at a
glance, while one step may carry pages of decisions.

```
docs/exec-plans/migrate-verifier/
    README.md              # state — the whole plan, at a glance
    steps/
        01-shadow-verify.md
        03-cache-flush.md  # 02 has no file, deliberately
```

### `README.md` — state

```markdown
# Migrate to the new verifier

Goal: every node verifying against the v2 verifier, old path deleted.
Abort if: v2 latency exceeds 40 ms p99 on any node — then revert and reopen 0012.

- [x] done    [Shadow-verify on one node](steps/01-shadow-verify.md)
- [>] doing   Roll to 10% — blocked on the cache flush landing
- [ ] todo    [Flush the verifier cache fleet-wide](steps/03-cache-flush.md)
- [~] dropped Dual-write the audit log — unnecessary, v2 writes it already
```

Three rules, each because it is the thing that will be quietly violated:

1. **The README owns state; step files never restate it.** Nobody reopens a
   finished step file to change `doing` to `done` — by then they are on the next
   step. So duplicated state drifts in one predictable direction, and silently.
2. **A step earns a file when it has decisions to record or is worth handing to
   a subagent.** Otherwise it is a line in the README. The failure this shape
   invites is trading "one file too long" for "twenty files too many".
3. **Numbering gaps are deliberate.** `01, 03` says step 02 has no file on
   purpose. Renumbering to close the gap turns "no file needed" into "file
   missing", and the two need to stay distinguishable.

### `steps/NN-name.md` — substance

Written **when the step is entered, not upfront.** Written in advance it is
fiction, and fiction in a plan is indistinguishable from a decision that was
actually made. Opened early, it holds the questions the step has to answer.

```markdown
# 03 · Flush the verifier cache fleet-wide

## Consulted

- **Existing skills**: `find-skill` — nothing for cache invalidation; closest is
  a Redis skill that assumes a single node.
- **Prior art**: envoy's `--drain-strategy`; it drains connections rather than
  invalidating, which is the opposite problem. Read the code, not the docs —
  their README describes a flag that was removed two releases ago.
- **Research**: none. This is a deployment sequencing question, not an open one.

## What has to be decided

<The questions, before the answers exist. This is the useful half of a step
file opened early.>

## Done when

- [ ] <observable, in the same sense a how-to criterion is observable>
```

**`## Consulted` may be empty, but never absent.** "None, because this step only
executes what 01 decided" is a complete and legitimate answer; a missing heading
is not. This is the same shape as `<!-- unrouted: reason -->` — an exemption that
has to state its reason, because an exemption without one becomes blanket.

The three lines are three granularities of the same outward question, and they
have different hit rates. `find-skill` searches the ecosystem for a capability
that already exists. Prior art is other people's **code**, which is more honest
than other people's documentation. Research is for when the direction itself
might already be refuted — and any decision a paper drives is checked against
that paper's implementation, because a paper describes a system at its best and
the code is what shipped.

The field is not a reading log. It records what changed, or that nothing did:
"read X, it does not apply because Y" is worth more than a citation, and a bare
list of links is the failure mode this heading invites.

### Lifecycle

`tech-debt-tracker.md` is permanent and lives beside the plans. Anything found
in passing goes there with the reading that revealed it, the commit it was
measured on, and the blast radius — never fixed inline, because a batch that
grows while you work is a batch that never lands.

On completion, delete the folder and write a decision record if anything was
decided. A finished plan left in place is read as active work. Deleting the
folder deletes the step files with it, which is why anything worth keeping is
promoted into a decision record rather than left in `steps/`.

### Routing

One row in `docs/index.md` points at `README.md`, and `check_docs_index.py`
reaches the step files through the links the README already has. A step file the
README does not link stays unrouted and is reported — the same defect as an
orphan document, one level down, and the one this shape makes easy to create.

---

## `docs/generated/` — what is it right now?

First line names the source and the command. The gate is: regenerate, and
`git diff` must be empty.

```markdown
<!-- Generated by scripts/index/build.py --report. Do not edit.
     Regenerating this file must leave an empty git diff. -->
```

Without that gate these are hand-edited within a month, and then they are lying
with the authority of something that looks machine-produced.
