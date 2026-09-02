# Assess a repository

This is how the assessment works and why each row is on the page. An agent runs
the instrument first and then holds it while it reads:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/factsheet.py \
        --root . --html assessment.html --json assessment.json
```

`--html` writes a self-contained page — no network, no fonts, no scripts — which
is the thing a person actually reads. The defect replay is on by default: it
runs the repository's own tests, so it names the command before running it, and
`--no-full` skips it at the cost of dimension 2 abstaining.

The [`repo-assessor`](../agents/repo-assessor.md) agent does all of this,
including the reading. It never changes the repository.

## Two rules that shape every row below

**A row nobody can judge is not printed.** Not printed as zero, not printed as
"unknown" — absent. A repository with no Go toolchain installed has no Go branch
coverage, and printing `0%` there reads as a failing grade for something that
was never measured. An absent row is a question this repository does not raise.

**Every number carries its denominator.** *Three of six destructive actions
refused* means nothing without *and none of the repository's own legitimate work
was refused*, because a hook that refuses everything gets six of six. Each
dimension has a row for what the repository **could** catch and a row for what it
**did**.

Where a row says *agent judges*, the machine narrows and stops. It collects the
evidence, discards what is certainly not a finding, and hands over the rest —
which is a far better question than *read this and tell me what you think*, and
still not a verdict.

---

## 1 — Execution: what can the agent do here?

### 1.1 Dangerous behaviour

Some actions have effects nobody can undo. Before an agent takes one, the
repository should refuse it, record it, or leave it revertible.

Six destructive actions are aimed at the repository's real hooks and **never
run** — the payload is offered, the answer is read, because a hook that is
configured and a hook that fires are different things. What is graded is what it
would cost to undo:

| | Class | Undo | Examples |
|---|---|---|---|
| **A** | fully recoverable | one git command, by anyone | edit, create, delete a tracked file |
| **B** | git recovers, state is lost | reflog, and knowing it exists | commit, merge, rebase |
| **C** | it left the machine | social — others already have it | publishing, remotes, CI config, lockfile |
| **D** | no clean recovery | nothing local holds the old state | untracked files deleted, uncommitted work overwritten, refs destroyed, a secret committed |

Class alone decides nothing — a commit is B and happens fifty times a day. The
second axis is how often the action is legitimate, and the two together say what
the harness owes: **nothing** for A and B, **leave a trace** for most of C, and a
**hard block** only for D actions that are rarely right. The asymmetry flips at
the D line: below it a false block costs more than a miss, at D it does not.

*Why it earns its place:* a bad reading here means your uncommitted work can be
destroyed by an agent acting in good faith, and nothing says no.

### 1.2 Legitimate work

An agent needs certain rights to finish a task. Which rights are legitimate is a
property of the repository, not of the command — deleting a build directory is
routine in one tree and a catastrophe in another — so no list written in advance
survives contact with a repository nobody has seen.

Two halves. Six of the destructive probes carry a legitimate twin, and a twin
that is also refused disqualifies its probe. Then the repository's **own** work:
an agent proposes twenty or so actions that are unambiguously fine here, and they
are fired through the same machinery, so the two numbers are comparable.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/permitted.py --root .
```

The machine supplies the evidence to write that list with — the commands CI
already runs on every push, the commands the documentation tells a person to run,
the hooks that are actually wired — and the agent supplies the list.
*Agent judges* -> [0038](../docs/decisions/0038-a-guard-that-refuses-everything-scores-full-marks.md)

*Why it earns its place:* without it, 1.1 is free to any repository that refuses
everything and has improved nothing. A block here is a finding about the guard,
not necessarily a fault — a team may deliberately require a human for its deploy.

### 1.3 Can an agent watch its own change run?

An agent has to convince itself its change works. Sometimes reading the code is
not enough: it needs to run the thing, drive it, read a log, see the screen.

Six angles, collected without starting anything: ways to run, port and container
isolation, where logs go, what surface a person sees, what drives it, and whether
it tears itself down. Repositories differ too much for a threshold, so the
collection is offline and the reading is not.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/observe.py --root .
```

*Agent judges.* A tree of scripts with no service to isolate and no log to tail
is the right shape for what it is, not a gap — and only somebody who has read the
repository can say which it is.

*Why it earns its place:* a bad reading means every change is argued for on
inspection alone, and the first time anyone finds out is in production.

---

## 2 — Validation: how late is a defect caught?

Everything in this dimension is graded against one ladder, because *caught* is
not a yes or no. The later the rung, the more it cost:

```
before-write   a guard refused it            costs nothing
same-turn      a post-write hook caught it   costs one turn
local-suite    the local check script        costs minutes
--- the cliff: the session ends, the context is gone ---
ci             the server                    costs a round trip
never          nothing                       it is in main
```

### 2.1 Coverage

Line, function, branch, and MC/DC where it exists — taken from **the ecosystem's
own tool and never from one written here**. `coverage.py`, `lcov`, JaCoCo,
Cobertura, `go tool cover`, `gcov`, whichever the repository already has; if it
produces a report on disk, that is read instead.

What each ecosystem can actually produce, and what it cannot:

| Language | Tool | line | function | branch | MC/DC |
|---|---|---|---|---|---|
| Python | `coverage.py --branch` | yes | — | yes | — |
| JavaScript, TypeScript | `c8` / `nyc` -> lcov | yes | yes | yes | — |
| Java, Kotlin | JaCoCo | yes | method | yes | — |
| C# / .NET | coverlet -> Cobertura | yes | — | yes | — |
| Ruby | SimpleCov | yes | — | yes | — |
| Go | `go tool cover` | statement | — | **none** | — |
| C, C++ | GCC 14 `-fcondition-coverage` | yes | yes | yes | **yes** (masking) |
| C, C++ | Clang 18 `-fcoverage-mcdc` | yes | yes | yes | **yes** (masking) |
| Rust | `cargo llvm-cov --mcdc` | yes | yes | yes | **nightly** |
| Ada, C, C++, Rust | GNATcoverage | yes | yes | yes | **yes** (certification) |

Two things fall out of that table. **Go has no branch coverage at all** — not a
gap in this instrument, a gap in the toolchain. And **MC/DC exists only where a
compiler computes it**: GCC and Clang arrived at masking MC/DC independently,
and Python, Java, JavaScript, C# and Ruby have nothing at any price. Where a
criterion cannot be produced, the row is **absent, not zero** — writing `0%`
there reads as a failing grade for something nobody measured
-> [0033](../docs/decisions/0033-the-tools-do-the-measuring.md)

Reports already on disk are read rather than regenerated, in whichever format
the repository happens to leave them: `coverage.json`, `lcov.info`,
`coverage.xml` / Cobertura, JaCoCo XML, `coverage.out`, `gcov` JSON. For C, C++,
Rust and Java that is the only path, because those builds cannot be driven
blind.

*Why it earns its place:* coverage predicts very little in the upward direction —
high coverage is not evidence of good tests. It is airtight downward: a line no
test executes **cannot** be caught at `local-suite`. That is the only inference
drawn from it.

### 2.2 Mutation — Google's method, not ours

The generator is a transcription of *Practical Mutation Testing at Scale: A View
from Google* (Petrovic, Ivankovic, Fraser, Just; TSE 2021,
[arXiv:2102.11378](https://arxiv.org/abs/2102.11378)) and its predecessor *State
of Mutation Testing at Google* (ICSE-SEIP 2018). Nothing about the selection is
invented here. Three of their findings do all the work:

**Mutate only covered lines.** A mutant on an uncovered line survives because the
code is untested — a coverage result, which 2.1 already gave at a fraction of the
cost.

**Suppress arid nodes.** Their central result: most surviving mutants are
*unproductive* — trivially equivalent to the original, or in code where no test
should exist (logging, debug output, defensive branches). Every rule in
[`arid.py`](../shared/scripts/assess/arid.py) is transcribed from Appendix A of
that paper, rule by rule, with their examples kept in the docstrings so the
transcription can be checked. Without this step the output is unreadable, which
is the finding, not a detail.

**One mutant per line.** Ten mutants on one line is ten reports of the same
missing test.

Each surviving mutant then walks the same ladder a real defect walks, and an
agent rules on each: a change the tests ignored is not automatically a defect.
Opt-in with `--mutate`, since it runs the suite once per mutant.

*Agent judges.*

### 2.3 Real defect replay

A fix from this repository's own history, put back: the files the fix touched are
taken to their state at its parent, so the defect actually happened here and the
fix is the answer key.

*Why it earns its place:* this is the strongest evidence on the page. A synthetic
bug measures whether *our* idea of a defect resembles what this repository checks
for. And if the toolchain is not installed it abstains rather than scoring zero —
a repository whose tests cannot run here is not a repository with bad tests.

### 2.4 What could have caught it

The layer inventory, printed above the ladder. A rung reading `0` means two
different things — **wired and silent**, or **not there at all** — and the ladder
prints the same character for both. A rung nothing reached is a third thing
again: the walk stops at the first red.

The shapes these layers usually take. This table is a starting point for the
reading, not a checklist to tick off — repositories differ enough that what
occupies a rung here may be unrecognisable there, and only somebody who has read
the repository can say what its `local-suite` actually is:

| Rung | Usually | Typically catches | Costs |
|---|---|---|---|
| before-write | a `PreToolUse` hook, a guard script | the action nobody should take at all | nothing |
| same-turn | a `PostToolUse` hook: formatter, type-check, lint on the file just written | syntax, types, style, an import that does not resolve | one turn |
| local-suite | `make test`, `pre-commit`, the repository's own check script | anything the tests assert about | minutes |
| ci | the server workflow | what only a clean machine reveals: a missing dependency, a platform difference, a test that passes only locally | a round trip, after the session ended |
| rule | a sentence in `CLAUDE.md` | nothing, on its own | tokens, every turn |

`rule` is on that list precisely because it is **not a rung**. A document cannot
be fired at, so it can never be shown working — and a repository whose only
defence against a mistake is a paragraph asking nicely has a layer that looks
present and catches nothing.

A rule with no script behind it is also often not *delivered*: a `paths:`
rule loads only when Claude reads a matching file, never on a Write, Glob,
Grep or anything through Bash — measured in
[`context/before_write.py`](../shared/scripts/context/before_write.py), and
asked for in `anthropics/claude-code#38487`, `#23478`, `#27861` and `#36334`,
all closed.

*Why it earns its place:* "add CI" and "your CI caught nothing" are different
pieces of advice, and the ladder alone cannot tell you which one you need.

---

## 3 — Reliable delivery: is verification required, or merely possible?

### 3.1 Tested

When a change adds behaviour, a test for it should arrive in the same change.
Otherwise nobody knows the behaviour still holds once the next twenty changes
land on top.

The denominator is narrow on purpose. A rename across forty files, a reformat and
a dependency bump all touch source and none of them owe a test, so they are read
off the commit type and excluded. **An untyped subject is counted, not guessed
at** — inferring intent from free-form English would shrink the denominator on
every repository at once, every reading would improve and nothing would have
changed -> [0039](../docs/decisions/0039-tidying-is-not-an-untested-change.md)

Two things make the number traceable. The tests are located and **named directory
by directory**, because a percentage nobody can trace back looks the same whether
coverage is poor or the suite is simply somewhere the instrument did not look.
And changes to the machinery that does the verifying are singled out, without
narrowing: a workflow change owes no unit test and still owes evidence, because
when it breaks, the thing that would have caught the mistake is the thing that
changed.

### 3.2 Verified

Does the repository **require** an agent to show that a change was checked,
before that change counts as done?

Verification is not only a test suite, and this is the row where that matters.
Plenty of changes are best verified by running the thing and reading the log, by
opening the page and looking at it, by replaying a request — the evidence 1.3
collects. 1.3 asks whether an agent *could* do any of that. This asks whether
anything *makes* it.

The half a machine can settle is the merge gate, and it has three states rather
than two:

```
nothing runs on pull requests
something runs, and a red run can be merged past
something is required, and it cannot
```

The first two separate offline from the workflow file alone; the third is a
branch-protection setting, and a `403` reading it is **not** an answer while a
`404` is -> [0034](../docs/decisions/0034-running-and-being-required-are-different-settings.md)
Steps that could turn a red run green (`|| true`, `continue-on-error`) are
listed but not counted as findings: legitimate uses exist, and the ones carrying
a comment saying why are a signal an agent can use and a counter cannot.

The other half is the agent's reading, from what 1.3 collected and what the
repository asks for in writing: is there a definition of done, a pull-request
template, a checklist that demands the change was actually exercised — and does
anything enforce it, or is it a paragraph asking nicely?

*Why it earns its place:* every surface a person normally sees — the green tick,
the badge, the workflow file — shows only that something *ran*. Whether it was
*required* is invisible from all three, and a repository where verification is
merely possible is one where whether work is accepted depends on who happened to
be looking.

Whether the checks *work* is dimension 2's job. This row only asks whether they
can be walked around.

---

## 4 — Repository memory: is what is written down true, and worth its place?

Nothing below is read off a count of files. A count says a repository is better
for having adopted somebody else's conventions, and it goes *up* when you
install this plugin — the instrument rewarding its own presence. So thickness
appears here as a **denominator** and never as a score: adding files cannot
raise anything on this page, and adding wrong ones lowers it
-> [0025](../docs/decisions/0025-dimension-4-asks-whether-an-agent-can-find-its-way.md).

There used to be a row above these that answered a better question. A pair of
agents read the same questions — one on this tree, one on a copy with
`CLAUDE.md` and `.claude/` removed — and the difference between them was the
measurement of what the repository's memory is worth. It was removed: each run
is a single sample of a non-deterministic process, the reported number is the
difference of two such samples, and the budget that made the pair affordable is
exactly what stopped it being averaged. It moved when nothing had changed, and
a page that improves on a rerun has spent its credibility
-> [0042](../docs/decisions/0042-a-measurement-noisier-than-its-effect-is-not-a-measurement.md)

**So this dimension no longer claims to know whether the memory works.** It
asks the question a single deterministic read can answer: is what is written
down still true, and is it worth what it costs to keep? What is lost is the
positive claim — *this `CLAUDE.md` is carrying an agent* — and nothing here
replaces it.

### 4.1 Dimensions

What kinds of memory exist: root and nested `CLAUDE.md`, skills, hooks, rules,
settings, documents. This is the denominator that every row under it is read
against.

One thing this row exists to say: a rule that needs a script behind it and does
not have one is not a constraint, it is a hope — and it often does not reach the
agent at all (2.4). It costs tokens either way. That decides both what a rule
costs (dimension 5) and whether it is delivered (dimension 1), so it is worth
knowing per file rather than in aggregate.

### 4.2 Is each memory worth keeping?

Context is the scarcest thing an agent has, so anything paid for on every turn
has to earn it. Three splits a machine can make: prohibition, requirement or
plain statement; already enforced by a hook that was *measured* firing; scoped to
one path but loaded anyway.

*Agent judges.* A machine cannot tell whether a constraint is one an agent could
have guessed, or whether an example earns its lines.

*Why it earns its place:* a prohibition restating a guard that already refuses the
thing is paying rent every turn to say what the machine says better — the guard is
not optional and does not depend on anyone having read anything.

### 4.3 Do the documents agree with the code? (CASCADE)

Where the documentation and the code disagree, an agent writing against the
documentation writes the wrong thing. Method after
[CASCADE](https://arxiv.org/abs/2604.19400):

1. Tests are generated **from the documentation alone** and run against the real
   code.
2. An implementation is generated **from the same documentation** and the same
   tests run against it.
3. The two runs cross into `p2p / f2f / f2p / p2f`, and a disagreement is
   reported only when **`f2p > 0` and `p2f == 0`** — the test fails on the real
   code and passes on the code the document describes, with nothing going the
   other way.

That second condition is the whole method. Without it the finding is
indistinguishable from a bad test, and the naive baseline reports roughly 27
false positives per 71 real ones
-> [0036](../docs/decisions/0036-a-contradiction-is-decided-by-an-experiment-not-a-comparison.md)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/promises.py --root .
```

*A blind agent judges.* The rounds are driven through the factsheet's
`--promise-tests` and `--promise-impls`, and the agent that answers them is
`repo-promise-tester`, which is given `Write` and **no way to read the
repository at all**. That is not a rule it is asked to respect: a test written
after reading the implementation agrees with it by construction, so the
crossing would report `p2p` on everything and find nothing, silently, forever.
The assessor cannot answer for it either, having already read the tree — the
same disqualification as 4.1's probe
-> [0040](../docs/decisions/0040-the-blind-is-the-tool-list-not-the-prompt.md)

Two numbers travel with the row: **precision 0.88, recall 0.21**. Seven of
eight findings are real, and a fifth of what is there is found — so a `bad` row
is worth acting on and an empty one is not a clean bill.

### 4.4 Do the documents agree with each other? (ConflictRAG)

Two documents naming the same thing with two different values will send two
agents in two directions. Method after
[ConflictRAG](https://arxiv.org/abs/2605.17301): a cheap filter first, an
expensive reader only on what survives. Their code and prompts are promised
"upon acceptance" and the paper is still only submitted, so what is here is a
reimplementation of a described method, not a library being followed.

The filter is lexical and deliberately harsh — one rule, not three. Its own
author's repository produced 553 candidates before it was narrowed, and a filter
that emits half the pairs has not filtered, it has moved the reading problem
somewhere else -> [0035](../docs/decisions/0035-a-filter-that-emits-half-the-pairs-has-not-filtered.md)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/conflict.py --root .
```

*Agent judges,* and it usually says no: two documents giving one number two
values are as often an example beside a default. Supersession — a decision record
that deliberately overrules an older one — is contradiction on purpose and is
excluded before the filter runs.

Each surviving pair carries three signals — which was written last, which is
on the floor, which value the code contains — put through the paper's
**Entropy-TOPSIS** (§III-C), the one part of it needing no model at all. The
run prints what each signal was worth: a criterion that came out the same on
every candidate is weighted to zero rather than repeated at the reader. It
**ranks and does not decide** — the agent still says which to believe, because
a diagnostic that picks winners has stopped being a diagnostic
-> [0021](../docs/decisions/0021-the-repository-keeps-the-harness-the-plugin-keeps-the-instrument.md)

### 4.5 Is it written in a shape a model can follow? (Reframing)

Every row above asks whether the writing is *true*. This one asks whether it is
*followable*, which is a separate question with a separate answer: an
instruction can be accurate, worth every token it costs, and still be a
paragraph carrying four requirements that compete with each other for
attention.

Method after [Reframing Instructional Prompts to GPTk's
Language](https://arxiv.org/abs/2109.07830) (Mishra, Khashabi, Baral, Choi and
Hajishirzi, Findings of ACL 2022). They rewrote task instructions without
changing what those instructions asked for, and task performance moved by a
wide margin — including on models large enough that people had assumed the
wording no longer mattered. Three of their operations survive the trip from a
benchmark prompt to a repository's standing instructions:

- **Positive assertion.** The paper's hardest case. A constraint given only as
  a negation leaves the target unstated, so the reader has to infer it. *Never
  return a file dump* says nothing about what to return; *return the paths and
  what is at them* does, and rules out the dump on the way past.
- **Itemizing.** A paragraph carrying several requirements becomes a list, one
  per item. In prose they compete; in a list each one is addressed.
- **Low-level patterns.** An abstract requirement — *follow the house style*,
  *use it appropriately* — becomes the concrete shape of the output.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/reframe.py --root . --json
```

*Agent judges,* and this one abstains harder than most: every row is `info`,
never `bad`. A `CLAUDE.md` may be one long paragraph on purpose, and a bare
prohibition may be the whole of what there is to say. What the machine can do
is find the openings and stop.

The distinction that makes it usable is **deontic against alethic**: *you must
not swallow the status* is an instruction, *the two cannot drift* is a fact
about how something works. Only the first is a thing reframing can change, and
the first version of this counted both — 116 findings across 19 files, most of
them the repository describing itself to itself. What it does not do is score
prose quality, count adverbs, or grade readability. Those measure writing.

---

## 5 — Context economy: what does the harness cost every turn?

### 5.1 Usage

Three numbers, all in characters over four:

```
floor     what every turn pays before anyone types
ceiling   floor + the largest scoped rule + the largest nested CLAUDE.md
parked    installed, but arrives only when something asks for it
```

The unit is an approximation on purpose. A real tokenizer is not one number
either — it changes between model families, and the same file has counted about
30% differently across them — and a stable approximation both sides can reproduce
offline is worth more here than a precise number that needs the network and still
is not the model's own.

Parked is the escape hatch, not the bill. A repository that moves a paragraph
under a path glob has not deleted it; it has stopped paying for it on turns that
never touch that path.

### 5.2 Files unlike their neighbours

A total is right and not actionable. Twelve hundred tokens across twenty lean
files and twelve hundred across nineteen lean files and one bloated one are the
same number and not the same problem, and nobody can act on the sum
-> [0037](../docs/decisions/0037-a-total-hides-the-one-file-worth-finding.md)

So the same measurement runs **per unit**, and each file is compared to the
median of **its own kind** — a rule against the other rules, a skill against the
other skills. A threshold chosen here would be a threshold chosen for a
repository nobody has seen, and comparing a skill to a decision record reports
every skill as huge, which is a fact about two genres.

Four things it can say: size against its own kind (with a floor, because three
times nothing is still nothing), what its sentences are, how much of it is fenced
code, and **paragraphs it repeats from another loaded file** — the sharpest of the
four and the only one that is certain rather than suggestive, because the same
paragraph in two loaded files is paid for twice every turn and one copy will
drift.

#### Use the first-party checkers first

Where Claude Code already answers a question, it answers it — the same rule as
2.1, and for the same reason. Reinventing somebody else's tool is the most
expensive way to be less correct than they are.

```bash
claude plugin validate . --strict     # the manifest, by the first-party checker
claude plugin details <plugin-name>   # component inventory and token cost
claude doctor                         # installation health; /doctor in-session fixes
```

`claude plugin details` is the one worth running before reading anything below
it: it prints **always-on** and **on-invoke** cost per skill and per agent,
straight from the party that does the loading. On this repository it reports
~670 always-on tokens across six components — a number nobody here had to
estimate. `/skill-doctor` reports on skills from inside a session.

What those do not cover, and what dimension 5 is therefore for, is the
**repository's own** memory: `CLAUDE.md`, nested `CLAUDE.md`, `.claude/rules/`,
and the documents. A plugin's cost is the plugin author's problem; the floor a
teammate pays for cloning this repository is nobody else's.

---

## What comes out

One artefact: the [assessment checklist](2-checklist.md). Five sections in the
order that ignoring them costs you, and every row points at something specific in
the repository.

The hardest questions are the ones with no number behind them — is the standing
cost earning its tokens, which sentences are waffle, does each hook address a
mistake *this* repository actually makes. Answering them is the reading, and it
is the reason the checklist is worth more than the fact sheet.

Keep the fact sheet's `--json`. [Re-measuring](5-re-measure.md) later needs the
earlier file, and it is the only way anything here can claim to have helped.
