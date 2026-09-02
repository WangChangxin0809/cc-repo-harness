---
name: writing-docs
description: Write or restructure documentation that agents and people actually read — choosing which of the four directories it belongs in (how-to, reference, decisions, exec-plans), knowing what belongs in a failure message instead of a file, and keeping the routing table honest. Use this whenever writing a doc, a runbook, a README, an ADR, a design doc, or a plan; whenever someone says the docs are stale, contradictory, ignored, or too long; whenever deciding where a convention or a prohibition should live; whenever moving knowledge out of CLAUDE.md or out of agent memory into the repo; and whenever a document does not obviously belong in exactly one of those four directories.
---

# Writing docs an agent will actually use

Governs: shared/scripts/context/before_write.py

A document is read because something happened. That event is its **reading
trigger**, and it decides everything: where the file goes, how long it may be,
and what shape it takes. Documents written without one become reference material
nobody references.

## Fix the top level; leave the interior free

| Directory | Trigger | What it holds |
|---|---|---|
| `how-to/` | I am about to do a thing | Ordered steps, each ending in an observable criterion |
| `reference/` | I need to look up a fact | Facts keyed for lookup, carried by working examples |
| `decisions/` | Why is it like this? | Numbered from the PR, dated, superseded rather than edited |
| `exec-plans/` | What are we in the middle of? | Goal · steps with state · what would abort it |

Four directories, fixed. **Inside each one, organise however suits the
material.** Both halves are evidence, not taste: a mandated shallow top level
with a free interior is the arrangement that survived a decade across hundreds
of OpenStack repositories, while two controlled studies — one on 65 people, one
on 1,650 agent sessions — each found *no* effect from documentation shape. So
the constraint sits where something was measured and stays off where nothing
was. Templates in `references/kinds.md` are advice.

Additions to the top level are fine once `docs/index.md` routes them. A
directory that forks a required name (`adr/`, `howto/`, `plans/`) is an error
either way — that fork is how one bucket silently becomes two.

A file that does not fit any of the four is usually two files.

## The one shape rule that is a requirement

Three parts per step, all three present:

```markdown
### 3. Rebuild the index

    python3 scripts/index/build.py

Criterion: `scripts/index/query.py --stats` reports a symbol count within 5% of
`git grep -c 'def \|class '`. A wildly lower count means the parser silently
skipped a language.
```

This one is required while the rest of the shape guidance is advice, because it
is **content rather than form**. Of five context signals measured against
SWE-bench Verified, reproduction instructions were worth +56.3% — three times
edit location and more than everything else combined. Steps without a criterion
are read as gestures and executed as gestures.

**Write the positive path.** The space of wrong ways is unbounded; the right way
is one path. And a prohibition has no reading trigger — nobody opens a document
to find out what they were about to do wrong. They find out by doing it.

So a prohibition worth keeping belongs where it fires. **This is also where
troubleshooting content goes**, and it is why there is no `troubleshooting/`
directory: agents open such documents 0.4% of the time and consult documentation
after a failure 7.5% of the time, but structured guidance delivered *at* the
error produced over 85% recovery against 17%.

| The thing you want to forbid, or the symptom you want to explain | Where it belongs |
|---|---|
| An action that destroys work | A guard, with the reason in the block message |
| A state the repo must not reach | A gate, with the fix in the failure output |
| A symptom with a known cause | The failure output of whatever detects it |
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

**The number comes from the pull request, not a counter, and numbers are not
continuous.** Write the file as `0000-<slug>.md` and rename it when the PR
opens. A counter looks tidier and breaks under concurrent contribution: two
people both take the next number, both are right when they write it, and both
land — Open edX's decision directory carries four collided numbers from exactly
that. Every scheme that survived at scale numbers from an identifier that
already exists (Rust from the PR; Go and Kubernetes from the issue).

Two honest notes. These are for people, not agents — in observed sessions agents
opened decision and architecture documents 4.0% of the time, and no measured
evidence says they help an agent at all. And the genre usually does not survive:
about half of all repositories with decision records have five or fewer.

## Exec plans

Multi-session work needs a file, because context does not survive the session
and the plan is the only thing that does. Past a few steps it needs a folder —
`docs/exec-plans/<name>/` with a `README.md` and a `steps/` directory — because
the plan's state must be readable at a glance while one step may carry pages of
decisions.

- **`README.md` owns state**: goal, steps each marked `todo | doing | done |
  dropped`, and the condition that would abort the whole plan. Step files never
  restate status; nobody reopens a finished step to change `doing` to `done`.
- **A step earns a file** when it has decisions to record or is worth handing to
  a subagent — otherwise it is a line in the README, and the numbering gap
  (`01, 03`) is how "no file needed" stays distinguishable from "file missing".
- **A step file is written when the step is entered**, not upfront. Written in
  advance it is fiction, and fiction in a plan is indistinguishable from a
  decision that was actually made.
- **Every step file carries `## Consulted`** — existing skills (`find-skill`),
  prior art in other people's code, research. It may say "none, because this
  step only executes what 01 decided"; it may not be absent. Same shape as
  `<!-- unrouted: reason -->`: an exemption states its reason or becomes
  blanket. Prior art means their **code**, not their documentation, and a
  decision a paper drives is checked against that paper's implementation.
- `docs/exec-plans/tech-debt-tracker.md` is permanent. Anything found in passing
  goes here with the reading that revealed it and the blast radius — never fixed
  inline, because a batch that grows while you work is a batch that never lands.
- On completion the folder is deleted and a decision record replaces it, if
  anything was decided. Finished plans left in place are read as active work,
  and deleting the folder takes the step files with it — so anything worth
  keeping is promoted into the record, not left in `steps/`.

`docs/index.md` routes the `README.md` only; `check_docs_index.py` reaches the
steps through the links the README already has.

## Reference, and the generated property

Reference is retrieval infrastructure, and **its value is carried by working
examples rather than by the table**. Removing code examples from API
documentation dropped answer accuracy from 0.66–0.82 to 0.22–0.39 in the one
ablation that measured the components separately. A page that lists parameters
and shows no working call has given away most of what it was worth. Write
reference for what the model has no prior about — your APIs, your formats,
uncommon libraries; restating what is widely known costs context and returns
nothing.

A glossary belongs here and is worth more than it looks: it pins the vocabulary
every search depends on, and when it drifts, searches silently return less.

**Generated is a property, not a directory.** A generated file lives wherever
its content belongs and declares itself in its own first line — source, command,
and the gate. Regenerate, then `git diff --exit-code`. The gate keys on the
declaration rather than on the location, which is the dominant idiom in the
wild; without it these files are hand-edited within a month and then lie with
the authority of something that looks machine-produced.

## Keep the routing table honest

`docs/index.md` maps *task → read this → then edit this*. It is the only
document allowed to be about other documents, and it holds no knowledge of its
own — detail written back into it is paid by every reader who did not need it.

One gate keeps it from rotting, `scripts/gates/check_docs_index.py`, and it
checks both directions: every file under `docs/` appears in the table, and
every path the table names exists. Ten lines of checking, and it catches
drift the week it happens rather than the quarter.

## Scope every document

Open with what it covers and what it does not. Two lines. It tells the next
writer where new material goes, which is the difference between a document that
stays focused and one that becomes the place things get appended to.

## Give the document a reading trigger: `Governs:`

Every kind above is defined by *why someone opened it*, and one trigger has no
natural home: **"I am about to change code this document describes."** Nobody
opens a document for that, because knowing to open it requires already knowing
it exists.

One line in the document's first 60 lines fixes it:

```markdown
# How billing works

Governs: src/billing/, src/payments/gateway.py

...
```

Plain text at the start of a line — despite being described elsewhere as
frontmatter, it needs no `---` fence and works anywhere in the head of the file.
Comma- or space-separated.

**Its justification is freshness, not navigation, and that changed on evidence.**
Navigation is unsupported: in a preregistered ablation the agent never loaded
the catalog at all — it inferred the path from the question and read the file
directly. Freshness is a different matter. Drift is not an occasional lapse but
the normal state (of 3,000+ repositories surveyed, most carried a reference to a
code element that no longer existed at some point in their history), and stale
prose is measurably harmful rather than merely useless — misleading natural
language around code degraded reasoning by 23.2%. Since a purely descriptive
document's measured benefit is near zero, a *stale* one has negative expected
value.

A declared pair is the only thing that makes that mechanically detectable: this
document claims to describe that path, so when the path moves and the document
does not, something can say so. It buys two things:

- **Delivery at the one instant it matters.** A `PreToolUse` hook
  (`scripts/context/before_write.py`) says *"docs/billing.md governs this path"*
  **before** the write, alongside any `.claude/rules/` scoped to it. Nothing
  else in the harness can do that — and two corrections are owed here, both
  measured. It ran on `PostToolUse` and delivered *after* the file was already
  written, which is the wrong half of the moment: creating a file is when a
  convention is worth most. And it printed to stdout, which on every event
  except `UserPromptSubmit`, `UserPromptExpansion` and `SessionStart` goes to
  the debug log — so for its whole life it delivered nothing to anybody. The
  channel is `hookSpecificOutput.additionalContext`.

  It advises; it does not prevent. Measured, the first write lands wrong and
  the agent corrects on the retry. A rule that must not be violated belongs in
  a guard, which can refuse.
- **A checkable claim.** See `drift.py` below.

Be honest about the standing of this: **no measured work exists on declared
doc-to-code relationships at all.** Of 70 major repositories surveyed, 8
declared anything comparable and several of those left the declaration empty or
scoped to everything; none verified it in CI. This is untested ground we chose
deliberately, not a practice we adopted.

Three rules that are easy to get wrong:

1. **Targets match by path segment, not by prefix.** `Governs: src/bill`
   covers `src/bill` and everything under `src/bill/`, and does *not* reach
   `src/billing_old/`. A trailing slash is allowed and changes nothing. This was
   once plain prefix matching, and the trailing slash was load-bearing; both
   readers now agree and an index selftest case holds them there.
2. **A target that resolves to nothing is drift, and is reported.** It lands in
   the generated index report as a dangling target. This is the one signal
   that catches a document still describing a path that was deleted — invisible
   from the document's side and from the code's side, both.
3. **Govern exactly what you describe.** The line is a claim that this
   document explains how that code is supposed to work. Pointing it at a whole
   `src/` makes every edit deliver a document that answers nothing, and then the
   hook's output stops being read.

## Read the pairs back: `drift.py`

`Governs:` buys a third thing, and it is the one that pays later. A pair is a
named, checkable claim — *this document describes that code* — which turns "is
the documentation still true" from a summarising job into a small number of
specific comparisons.

```bash
python3 scripts/drift.py pairs      # which pairs are worth reading, and why
python3 scripts/drift.py prepare    # one packet per suspect pair, plus a brief
python3 scripts/drift.py report     # collect the findings
```

Three things about it are the whole design:

**The triage is free.** Git already knows whether the code moved after the
document did. Pairs where nothing governed has changed since the document's last
commit are skipped, which is the difference between a pass you run and one you
do not. It is a prior and not a verdict — a document can be wrong on the day it
is written, and `--all` reads every pair.

**It is not a gate.** Findings are *claims that two things disagree*, and a check
that is sometimes wrong gets switched off within a week. `check_docs_runnable.py`
is the gate: it catches a documented command that would not run, which is the
mechanical half of drift and the smaller half.

**A finding never says the document is wrong.** It says the two disagree. A
document encodes intent, and intent legitimately runs ahead of code — a rule the
team decided and has not built, a limitation recorded before it was removed. A
pass that quietly aligns documents to code deletes exactly that material and
reads beautifully afterwards. Which side moves is a human decision, and it is
often the code.

The first pass over this repository found six: two documents teaching a
workaround for a bug that had been fixed, a document denying a measurement
sitting in the directory it governed, two wrong line counts, and an incomplete
inventory. The second pass found nothing, which is also a result — `report`
records a pair as read-and-quiet, because an unreviewed pair and a clean one
must never print the same.

## References

| File | Read when |
|---|---|
| `references/kinds.md` | Templates for the four directories, and what is not a directory |

Related skills: `writing-checks` (the gates named above),
`consolidating-notes` (merging accumulated notes into these kinds),
`repo-index` (what the `governs` edges are used for).
