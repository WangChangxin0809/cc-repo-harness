---
name: writing-docs
description: Write or restructure documentation that agents and people actually read — choosing the right kind (how-to, reference, troubleshooting, decision record, exec plan, generated), giving each its required shape, and keeping the routing table honest. Use this whenever writing a doc, a runbook, a README, an ADR, a design doc, or a plan; whenever someone says the docs are stale, contradictory, ignored, or too long; whenever moving knowledge out of CLAUDE.md or out of agent memory into the repo; and whenever a document does not obviously belong to exactly one of those six kinds.
---

# Writing docs an agent will actually use

Governs: shared/scripts/context/after_edit.py

A document is read because something happened. That event is its **reading
trigger**, and it decides everything: where the file goes, how long it may be,
and what shape it takes. Documents written without one become reference material
nobody references.

## Partition by trigger, then obey the shape

| Kind | Trigger | Required shape |
|---|---|---|
| `how-to/` | I am about to do a thing | Ordered steps. Each: **action → command → observable criterion** |
| `reference/` | I need to look up a fact | Tables and rules, keyed for lookup, no narrative |
| `troubleshooting/` | I hit a symptom | **Symptom → cause → action**, symptom first, verbatim |
| `decisions/` | Why is it like this? | Numbered, dated, immutable. Context · Decision · Consequences |
| `exec-plans/` | What are we in the middle of? | Goal · steps with state · what would abort it |
| `generated/` | What is it *right now*? | Written from a truth source; regenerating leaves an empty diff |

A file that does not fit exactly one of these is two files.

## The how-to shape is not a suggestion

Three parts per step, all three present:

```markdown
### 3. Rebuild the index

    python3 scripts/index/build.py

Criterion: `scripts/index/query.py --stats` reports a symbol count within 5% of
`git grep -c 'def \|class '`. A wildly lower count means the parser silently
skipped a language.
```

The criterion is what makes the step checkable by someone who does not already
know the answer. Steps without one are read as gestures and executed as
gestures.

**Write the positive path.** The space of wrong ways to do something is
unbounded; the right way is one path. A how-to that spends half its length on
what not to do costs every reader that space and still fails to be exhaustive.

This is not a stylistic preference — it follows from reading triggers. **A
prohibition has no trigger.** Nobody opens a document to find out what they were
about to do wrong; they find out by doing it. So a prohibition worth keeping
belongs where it fires:

| The thing you want to forbid | Where it actually belongs |
|---|---|
| An action that destroys work | A guard, with the reason in the block message |
| A state the repo must not reach | A gate, with the fix in the failure output |
| A pattern that is wrong only here | That subtree's `CLAUDE.md` |
| A road already tried and abandoned | A decision record — that is what they are for |

Failure output is the one place a negative is guaranteed to be read, because the
reader is stuck. Make it carry the remedy and a path: *"blocked: `git restore`
discards uncommitted work in the same file. Back up with `cp` first — see
docs/how-to/reverting-safely.md."*

## Decision records

Immutable. When a decision changes you write a new one with `Supersedes: 0004`,
and edit the old one only to add `Superseded by: 0019`. Editing the original
destroys the only artifact that records what you used to believe and why — which
is the part that stops the same idea being re-litigated every six months.

Record what you rejected. A decision that lists only the winner reads as
inevitable, and the next person re-proposes the alternative you already killed.

Numbering is sequential and never reused. `0001-agent-conventions.md` explains why
the repository is shaped this way.

## Exec plans

Multi-session work needs a file, because context does not survive the session
and the plan is the only thing that does.

- `docs/exec-plans/<name>.md` while active: goal, steps each marked
  `todo | doing | done | dropped`, and the condition that would abort the whole
  plan.
- `docs/exec-plans/tech-debt-tracker.md` is permanent. Anything found in passing
  goes here with the reading that revealed it and the blast radius — never fixed
  inline, because a batch that grows while you work is a batch that never lands.
- On completion the plan is deleted and a decision record replaces it, if
  anything was decided. Finished plans left in place are read as active work.

## Reference and generated

Reference is retrieval infrastructure. A glossary that pins the project's own
vocabulary is worth more than it looks: it is the vocabulary every search
depends on, and when it drifts, searches silently return less.

Generated docs must state their source in the first line and be regenerable in
one command. The gate is: regenerate, and `git diff` must be empty. Without that
gate they are hand-edited within a month, and then they are lying with the
authority of something that looks machine-produced.

## Keep the routing table honest

`docs/index.md` maps *task → read this → then edit this*. It is the only
document allowed to be about other documents, and it holds no knowledge of its
own — detail written back into it is paid by every reader who did not need it.

Two gates keep it from rotting: every file under `docs/` appears in it, and
every path it names exists. Both are ten-line checks and both catch drift the
week it happens rather than the quarter.

## Scope every document

Open with what it covers and what it does not. Two lines. It tells the next
writer where new material goes, which is the difference between a document that
stays focused and one that becomes the place things get appended to.

## Give the document a reading trigger: `Governs:`

Every kind above is defined by *why someone opened it*, and one trigger has no
natural home: **"I am about to change code this document describes."** Nobody
opens a document for that, because knowing to open it requires already knowing
it exists.

One line in the document's first 40 lines fixes it:

```markdown
# How billing works

Governs: src/billing/, src/payments/gateway.py

...
```

Plain text at the start of a line — despite being described elsewhere as
frontmatter, it needs no `---` fence and works anywhere in the head of the file.
Comma- or space-separated. It buys two things:

- **Delivery.** A `PostToolUse` hook (`scripts/context/after_edit.py`) says
  *"docs/billing.md governs this file — read it before assuming how this is
  supposed to work"* the moment the file is edited. Nothing else in the harness
  can deliver a document at that instant, which is the only instant it matters.
- **Reachability.** `scripts/index/build.py` turns the line into weighted
  `governs` edges. Without them documents and code are two disconnected
  components of the graph and no ranking bridges them — a repository with no
  `Governs:` anywhere has documents that rank zero from every code query, which
  looks exactly like having no documents at all.

Three rules that are easy to get wrong:

1. **Directory targets end in `/`.** `Governs: src/bill` also covers
   `src/billing_old/`. An over-broad claim is worse than a missing one: it reads
   as though somebody documented that code.
2. **A target that resolves to nothing is drift, and is reported.** It lands in
   `docs/generated/index-report.md` as a dangling target. This is the one signal
   that catches a document still describing a path that was deleted — invisible
   from the document's side and from the code's side, both.
3. **Do not govern what you do not describe.** The line is a claim that this
   document explains how that code is supposed to work. Pointing it at a whole
   `src/` makes every edit deliver a document that answers nothing, and then the
   hook's output stops being read.

## References

| File | Read when |
|---|---|
| `references/kinds.md` | Full template for each of the six kinds |

Related skills: `writing-checks` (the gates named above),
`consolidating-notes` (merging accumulated notes into these kinds),
`repo-index` (what the `governs` edges are used for).
