# The four directories, and what goes in them

**The top level is fixed. Inside each directory, organise however suits the
material.** That split is the whole convention, and both halves are load-bearing.

The fixed half comes from the one large-scale result available: OpenStack
mandates a shallow top level for every project repository and explicitly leaves
the interior free — *"within each top-level directory, project teams are free to
organize their content however seems most appropriate"* — and it held for about
a decade across hundreds of repositories, with roughly one deviation in seven.

The free half comes from two controlled studies that both found nothing. Ernst &
Robillard (2023, 65 participants) found no association between documentation
*format* and performance on understanding tasks; McMillan (2026, n=1650 agent
sessions) found no detectable effect from any of four file-structure variables.
So the templates below are **advice, not requirements**. Exactly one shape rule
survives as a requirement, and it is named where it applies.

Additions at the top level are allowed once `docs/index.md` routes them. A
directory that *forks* a required name — `adr/` for `decisions/`, `howto/` for
`how-to/` — is an error whether routed or not: two spellings of one bucket both
accumulate documents, and merging them later is a migration.
`check_docs_layout.py` holds this.

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
```

**The criterion is the one required shape in this file**, and it is required
because it is content rather than form — `SKILL.md` gives the measurement
behind that. A step that says what to run and what you should then observe is
the highest-value sentence a repository can contain.

Write the positive path. The set of wrong ways is unbounded and a document that
enumerates them is both longer and still incomplete. A prohibition worth keeping
goes where it fires — see the last section.

---

## `docs/reference/` — I need to look up a fact

```markdown
# Key formats

- **Covers**: the on-disk and on-wire shape of every key type.
- **Does not cover**: how to rotate one (`docs/how-to/rotate-signing-key.md`).

| Type | Encoding | Length | Where stored |
|---|---|---|---|
| signing | base64url | 32 B | `secrets/signing/` |

    # A signing key, minted and verified end to end:
    key=$(./scripts/keys.sh mint --label demo)
    ./scripts/keys.sh verify "$key"    # -> ok, active
```

**The examples carry the value, not the table.** Removing code examples from API
documentation dropped answer accuracy from 0.66–0.82 to 0.22–0.39 in the one
component ablation that measured it. A reference page that lists parameters and
shows no working call has given away most of what it was worth.

Reference earns its place mainly for what the model has no prior about — your
own APIs, uncommon libraries, project-specific formats. Restating something
widely known costs context and returns nothing.

A glossary belongs here and is worth more than it looks. It pins the project's
own vocabulary, which is what every search depends on.

---

## `docs/decisions/` — why is it like this?

```markdown
# 0042 — Signing key rotation stays manual

Date: 2026-03-04
Status: accepted          <!-- or: superseded by 0117 -->

## Context
<The forces. What made this a decision rather than an obvious step.>

## Decision
<What was chosen, stated so it can be checked against the code.>

## Rejected
- **Automatic rotation on a timer.** <Why not — concretely.>

## Consequences
<What is now true, including the costs. A record listing only benefits is a
pitch, and gets read as one.>

## Revisit when
<What would have to change.>
```

**The number comes from the pull request that introduces the record.** Numbers
are not continuous and are not meant to be. Write the file as `0000-<slug>.md`
and rename it when the pull request opens.

A counter looks tidier and breaks under concurrency: two contributors both take
the next number, both are right when they write it, and both land. Open edX's
decision directory carries four collided numbers from exactly this. Every scheme
that survived at scale takes its number from an identifier that already exists —
Rust from the pull request, Go and Kubernetes from the issue.

When a decision changes, write a new record with `Supersedes: 0042` and edit the
old one **only** to add `Superseded by: 0117`. Editing the original destroys the
one artifact that records what you used to believe and why — the part that stops
the idea being re-litigated every six months. Record what you rejected, for the
same reason.

Two things worth saying plainly. Decision records are for people, not agents: in observed
sessions, agents opened architecture and decision documents 4.0% of the time,
and there is no measured evidence they help an agent at all. And the genre
usually does not survive — about half of all repositories with decision records
have between one and five. Past roughly forty records it survives only where a
process pulls it, not a convention.

---

## `docs/exec-plans/` — what are we in the middle of?

`SKILL.md` says why multi-session work needs a file at all. Past a few steps
it needs a **folder**, and this is its shape: the plan's state has to be
readable at a glance while one step may carry pages of decisions.

```
docs/exec-plans/migrate-verifier/
    README.md              # state — the whole plan, at a glance
    CLAUDE.md              # only while in flight; deleted when it lands
    steps/
        01-shadow-verify.md
        03-cache-flush.md  # 02 has no file, deliberately
```

```markdown
# Migrate to the new verifier

Goal: every node verifying against the v2 verifier, old path deleted.
Abort if: v2 latency exceeds 40 ms p99 on any node — then revert and reopen 0042.

- [x] done    [Shadow-verify on one node](steps/01-shadow-verify.md)
- [>] doing   Roll to 10% — blocked on the cache flush landing
- [ ] todo    [Flush the verifier cache fleet-wide](steps/03-cache-flush.md)
- [~] dropped Dual-write the audit log — unnecessary, v2 writes it already
```

Four rules, each because it is the thing that will be quietly violated:

1. **The README owns state; step files never restate it.** Nobody reopens a
   finished step file to change `doing` to `done` — by then they are on the next
   step. Duplicated state drifts in one direction, silently.
2. **A step earns a file when it has decisions to record or is worth handing to
   a subagent.** Otherwise it is a line in the README.
3. **Numbering gaps are deliberate.** `01, 03` says step 02 has no file on
   purpose; renumbering turns "no file needed" into "file missing".
4. **A step file is written when the step is entered, not upfront.** Written in
   advance it is fiction, and fiction in a plan is indistinguishable from a
   decision that was actually made.
5. **`CLAUDE.md` lives and dies with the plan.** An active folder carries one,
   capped at 50 lines, holding only what is true *while this is in flight* — the
   invariant not to break, the branch, the one command that proves a step
   landed. Not the plan itself: that is the `README.md` next to it. The runtime
   delivers this file whenever anything in the folder is read, so the moment the
   last step closes, every line in it has stopped being true and none of it has
   stopped being delivered. `scripts/gates/check_plan_hygiene.py` fails on that,
   and `scripts/context/on_stop.py` runs it too — it is the only rule here whose
   cost is charged per turn instead of per pull request.

**The README's rows are milestones, not a task list.** What the current step
breaks into for the next ten minutes belongs in the runtime's own todo list: it
is live in the interface, it costs nothing to update, and it vanishes with the
session — which is correct, because nobody outside that session needed it. The
plan holds what outlives the session, and the test for which is one question:
*would someone opening this repository next week need it?* The goal, the abort
condition, and which steps exist pass. "Rerun the fixture builder" does not.

Get this wrong in the direction of detail and the README becomes a checklist
that needs updating twice an hour, which means it stops being updated at all,
which turns the one file whose whole job is stating where things stand into the
one file that is confidently wrong.

Every step file opens with `## Consulted` — existing skills, prior art in other
people's **code**, research. It may say "none, because this step only executes
what 01 decided"; it may not be absent. An exemption that states no reason
becomes a blanket one.

This is the kind with the best support after how-to. Agent working notes were
the second most-opened category of documentation in observed sessions at 25.1%,
behind only instruction files.

`tech-debt-tracker.md` is permanent and lives beside the plans. Anything found
in passing goes there with the reading that revealed it and the blast radius —
never fixed inline, because a batch that grows while you work never lands.

On completion, delete the folder and write a decision record if anything was
decided. Deleting takes the step files with it, so anything worth keeping is
promoted into the record rather than left in `steps/`.

---

## Two things that are not directories

**Troubleshooting is failure output.** It used to be a directory here. Agents
open troubleshooting documents 0.4% of the time and consult documentation
because something failed 7.5% of the time — the hoped-for behaviour, *agent hits
an error and reads the troubleshooting page*, essentially does not happen. But
structured guidance delivered **at** the error produced over 85% recovery
against 17% for an ambiguous signal. The content is valuable and the filing
cabinet is the wrong place for it.

So a symptom, its cause and its action go in the failure message of whatever
detects it:

> `blocked: git restore discards uncommitted work in the same file. Back up`
> `with cp first — see docs/how-to/reverting-safely.md`

**Generated is a property, not a place.** A generated file lives in the
directory its content belongs to and declares itself in its own first line:

```markdown
<!-- Generated by scripts/build_index.py --report. Do not edit.
     Regenerating this file must leave an empty git diff. -->
```

The gate keys on the declaration, not on the location — regenerate, then
`git diff --exit-code`. That is the dominant idiom in the wild, and without it
these files are hand-edited within a month and then lie with the authority of
something that looks machine-produced.
