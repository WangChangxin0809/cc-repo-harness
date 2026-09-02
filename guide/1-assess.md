# Assess a repository

- **Covers**: stage 1 — how each row on the fact sheet is measured, where the
  machine stops and the agent's reading begins, and what a bad reading costs.
- **Does not cover**: writing the checklist ([2](2-checklist.md)) or deciding
  what to do about it ([3](3-decide.md)).

An agent runs the instrument first, then holds its numbers while it reads:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/factsheet.py \
        --root . --html assessment.html --json assessment.json
```

`--html` writes a self-contained page, which is what a person reads. `--json` is
what [re-measuring](5-re-measure.md) will need later; keep it. The defect replay
is on by default, runs the repository's own tests, and names the command before
running it; `--no-full` skips it and dimension 2 abstains.

The [`repo-assessor`](../agents/repo-assessor.md) agent does all of this,
including the reading. It never changes the repository. The reading is done
by [`assess-reader`](../agents/assess/reader.md), one per dimension, and
their answers go back onto the page through `--from`, which reads a run back
without running the suite again.

## Three rules that shape every row

**A row nobody can judge is not printed.** Not as zero, not as unknown: absent.
A repository with no Go toolchain installed has no Go branch coverage, and `0%`
there would read as a failing grade for something never measured.

**A row about nothing in the repository is printed, and red.** No test file,
no pipeline, no document, no `.claude/`: each is a measurement of the
repository, in the words *absent in the repository, not unread*. The test that
separates it from the rule above: would a clone on a fully equipped machine
change the row? If not, it is measured -> [0047](../docs/decisions/0047-absence-in-the-repository-is-measured-absence-on-the-machine-is-not.md)

**Every number carries its denominator.** *Three of six destructive actions
refused* means nothing without *and none of the repository's own legitimate
work was refused*, because a hook that refuses everything gets six of six.

Where a row says *agent judges*, the machine narrows and stops. It collects the
evidence, discards what is certainly not a finding, and hands over the rest.
That is a better question than *read this and tell me what you think*, and
still not a verdict. Each such row has a flag on `factsheet.py` for feeding the
verdicts back in (`--observe-answers`, `--mutant-answers`, and so on); unjudged
candidates are counted neither way.

Each entry below has the same shape: what the row asks, how it is measured,
where the reading begins, and what a bad reading costs. The reasoning behind a
row lives in the decision record it links to.

---

## 1 — Execution: what can the agent do here?

### 1.1 Dangerous behaviour

*Asks:* are destructive actions refused, recorded, or left revertible?

Six destructive actions are offered to the repository's real hooks and **never
run**: the payload is presented and the answer is read, because a hook that is
configured and a hook that fires are different things. What is graded is what
undoing the action would cost:

| | Class | Undo | Examples |
|---|---|---|---|
| **A** | fully recoverable | one git command, by anyone | edit, create, delete a tracked file |
| **B** | git recovers, state is lost | reflog, and knowing it exists | commit, merge, rebase |
| **C** | it left the machine | social; others already have it | publishing, remotes, CI config, lockfile |
| **D** | no clean recovery | nothing local holds the old state | untracked files deleted, uncommitted work overwritten, refs destroyed, a secret committed |

What the harness owes rises with the class and falls with how often the action
is legitimate: nothing for A and B, a trace for most of C, a hard block only for
D actions that are rarely right. Below D a false block costs more than a miss;
at D it does not.

*Bad reading costs:* an agent acting in good faith can destroy uncommitted work,
and nothing says no.

### 1.2 Legitimate work

*Asks:* does the repository's own ordinary work still get through?

Two halves. Each destructive probe carries a legitimate twin, and a twin that is
also refused disqualifies its probe. Then an agent proposes twenty or so actions
that are unambiguously fine in *this* repository, and they are fired through the
same machinery, so the two numbers are comparable:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/permitted.py --root .
```

*Agent judges* which actions are legitimate, from what the machine collects: the
commands CI runs, the commands the documentation tells a person to run, the
hooks actually wired. Which rights are legitimate is a property of the
repository, not of the command; deleting a build directory is routine in one
tree and a catastrophe in another
-> [0038](../docs/decisions/0038-a-guard-that-refuses-everything-scores-full-marks.md)

*Bad reading costs:* without this row, 1.1 is free to any repository that
refuses everything. A block here is a finding about the guard, not necessarily
a fault; a team may deliberately require a human for its deploy.

### 1.3 Can an agent watch its own change run?

*Asks:* can an agent run the thing, drive it, read its logs, see its surface?

Six angles, collected without starting anything: ways to run, port and
container isolation, where logs go, what surface a person sees, what drives it,
and whether it tears itself down.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/observe.py --root .
```

*Agent judges.* Repositories differ too much for a threshold: a tree of scripts
with no service to isolate and no log to tail is the right shape for what it
is, and only somebody who has read it can say so.

*Bad reading costs:* every change is argued for on inspection alone, and the
first time anyone finds out is in production.

---

## 2 — Validation: how late is a defect caught?

Every row here is graded against one ladder, because *caught* is not a yes or
no. The later the rung, the more it cost:

```
before-write   a guard refused it            costs nothing
same-turn      a post-write hook caught it   costs one turn
local-suite    the local check script        costs minutes
--- the cliff: the session ends, the context is gone ---
ci             the server                    costs a round trip
never          nothing                       it is in main
```

### 2.1 Coverage

*Asks:* what does no test execute at all?

Taken from **the ecosystem's own tool, never from one written here**
-> [0033](../docs/decisions/0033-the-tools-do-the-measuring.md). If the
repository already leaves a report on disk (`coverage.json`, `lcov.info`,
Cobertura or JaCoCo XML, `coverage.out`, gcov JSON) that is read instead of
regenerated; for C, C++, Rust and Java it is the only path, because those
builds cannot be driven blind.

| Language | Tool | line | function | branch | MC/DC |
|---|---|---|---|---|---|
| Python | `coverage.py --branch` | yes | — | yes | — |
| JavaScript, TypeScript | `c8` / `nyc` -> lcov | yes | yes | yes | — |
| Java, Kotlin | JaCoCo | yes | method | yes | — |
| C# / .NET | coverlet -> Cobertura | yes | — | yes | — |
| Ruby | SimpleCov | yes | — | yes | — |
| Go | `go tool cover` | statement | — | **none** | — |
| C, C++ | GCC 14 `-fcondition-coverage` | yes | yes | yes | yes |
| C, C++ | Clang 18 `-fcoverage-mcdc` | yes | yes | yes | yes |
| Rust | `cargo llvm-cov --mcdc` | yes | yes | yes | nightly |
| Ada, C, C++, Rust | GNATcoverage | yes | yes | yes | yes |

Where a criterion cannot be produced, the row is absent, not zero.

That table is what can be *read*. What the replay can *run* on its own is
narrower: `npm test`, `pytest`, `cargo test`, `go test`, `make test`, and a
command the repository's own documents declare, found at the root or up to
two directories below it. Java, Kotlin, C#, Ruby and Dart are read from
reports the repository already produces and are never driven blind. For
anything else, `--test-command` runs through `bash -c`, in a clean clone of
`HEAD`, and must exist at the older commits the replay parks at.

*Bad reading costs:* coverage says little upward, since high coverage is not
evidence of good tests. It is airtight downward: a line no test executes
**cannot** be caught at `local-suite`. That is the only inference drawn.

### 2.2 Mutation

*Asks:* which changes to covered lines did the tests fail to notice?

Off by default; `--mutate N` turns it on, because it runs the suite once per
mutant. The selection follows *Practical Mutation Testing at Scale: A View from
Google* ([arXiv:2102.11378](https://arxiv.org/abs/2102.11378)) and nothing in
it is invented here:

- **Only covered lines.** A mutant on an uncovered line is a coverage result,
  which 2.1 already gave.
- **Arid nodes suppressed.** Logging, debug output, defensive branches: every
  rule in [`arid.py`](../shared/scripts/assess/arid.py) is transcribed from the
  paper's appendix, with their examples kept in the docstrings.
- **One mutant per line.** Ten on one line is ten reports of one missing test.

Each survivor walks the same ladder a real defect walks.

*Agent judges* each survivor; a change the tests ignored is not automatically a
defect
-> [0030](../docs/decisions/0030-mutation-is-the-second-injection-and-a-survivor-is-never-a-finding.md)

### 2.3 Real defect replay

*Asks:* where were this repository's own defects first caught, and how long did
that take?

A fix from the repository's history is put back: the files it touched are
returned to their state at its parent, so the defect actually happened here and
the fix is the answer key.

Two rows keep the ladder honest. **Caught by a test that already existed**
is the control: the replay keeps the fix's own regression test, which was
written to fail on exactly this defect, so `local-suite` is near-certain by
construction. The control puts source *and* tests back to before the fix and
runs the whole suite; red means a test that predates the fix saw the defect,
and the ordinary answer is that none did. **Defects outside the suite's
reach** are the ones nothing went red on *and* the suite never executed the
file they are in, by the command's own `cd` or by coverage. They are not
counted as surviving: *one defect survives past the end of a session* is a
sentence about the repository, and the honest sentence there is about the
command.

*Bad reading costs:* this is the strongest evidence on the page. A synthetic bug
only measures whether *our* idea of a defect resembles what this repository
checks for. If the toolchain is not installed, the row abstains
-> [0029](../docs/decisions/0029-the-floor-is-itemised-and-the-replay-can-be-told-how-to-run.md)

### 2.4 The layers behind the ladder

*Asks:* which rungs exist, which are wired and silent, which are absent?

A rung reading `0` means two different things, **wired and silent** or **not
there at all**, and the ladder prints the same character for both. This row is
the inventory, printed above the ladder
-> [0032](../docs/decisions/0032-a-rung-cannot-be-read-without-the-layer-behind-it.md)

Each replayed defect is fired at the hooks its **own commit** wired, not at
what HEAD wires today; a hook added last month cannot have caught a defect
from March, and the row says *replayed before it was wired* for those. A hook
whose script cannot start is reported as broken, never as a catch.

The shapes the layers usually take, as a starting point for the reading rather
than a checklist:

| Rung | Usually | Typically catches | Costs |
|---|---|---|---|
| before-write | a `PreToolUse` hook, a guard script | the action nobody should take at all | nothing |
| same-turn | a `PostToolUse` hook: formatter, type-check, lint on the file just written | syntax, types, style, an import that does not resolve | one turn |
| local-suite | `make test`, `pre-commit`, the repository's own check script | anything the tests assert about | minutes |
| ci | the server workflow | what only a clean machine reveals | a round trip, after the session ended |
| rule | a sentence in `CLAUDE.md` | nothing, on its own | tokens, every turn |

`rule` is on the list because it is **not a rung**. A document cannot be fired
at, so it can never be shown working. It is often not even delivered: a
`paths:` rule loads when a matching file is read, never on a Write or anything
through Bash, as
[`context/before_write.py`](../shared/scripts/context/before_write.py) measures.

*Bad reading costs:* "add CI" and "your CI caught nothing" are different
advice, and the ladder alone cannot say which one you need.

---

## 3 — Reliable delivery: is verification required, or merely possible?

### 3.1 Tested

*Asks:* do changes that add or repair behaviour arrive with something verifying
them?

The denominator is narrow on purpose. Renames, reformats and dependency bumps
owe no test, so they are read off the commit type and excluded. An untyped
subject is counted, not guessed at
-> [0039](../docs/decisions/0039-tidying-is-not-an-untested-change.md)

Tests are located and named directory by directory, so a poor percentage can
be told apart from a suite the instrument did not find. The row carries both
denominators, typed and every change to source, because a branch whose
commits carry types and one whose do not would otherwise give two
percentages that cannot be compared; re-measure against the one whose
mode matches. Changes to the
verifying machinery itself are singled out: a workflow change owes no unit
test and still owes evidence.

### 3.2 Verified

*Asks:* does the repository **require** the check, rather than merely offer it?

The half a machine can settle is the merge gate, which has three states:

```
nothing runs on pull requests
something runs, and a red run can be merged past
something is required, and it cannot
```

The first two are read from the workflow file alone. The third is a
branch-protection setting; a `403` reading it is not an answer, a `404` is
-> [0034](../docs/decisions/0034-running-and-being-required-are-different-settings.md)
Steps that could turn a red run green (`|| true`, `continue-on-error`) are
listed, not counted, since legitimate uses exist.

*Agent judges* the other half, from what 1.3 collected and what the repository
asks for in writing: a definition of done, a pull-request template, a
checklist demanding the change was exercised, and whether anything enforces
it.

*Bad reading costs:* the green tick, the badge and the workflow file all show
that something *ran*. Whether it was *required* is invisible from all three.
Whether the checks *work* is dimension 2's question; this one asks only whether
they can be walked around.

The four rows below read the pipeline itself, and only for GitHub Actions;
another host abstains. Matrix breadth, caching, job count and reusable
workflows are conventions and are not read
-> [0044](../docs/decisions/0044-the-pipeline-is-read-for-what-it-does-not-what-it-resembles.md)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/pipeline.py --root .
```

### 3.3 Scope

*Asks:* which changes run which checks, and which run none?

Every workflow on pull requests is read for `paths:` and `paths-ignore:`. One
workflow with no filter means every change is checked. When all of them carry
a filter, the row names what a change can touch and run nothing. A filter
that leaves out `.github/workflows` is called out on its own: an edit to the
pipeline is then the one change the pipeline never checks. A job-level filter
(`paths-filter`) is listed and not read, since which checks run is computed
inside the run.

*Agent judges.* A filter is usually deliberate. The reading is whether what it
skips can break anything, and a docs-only change is exactly the one that
breaks a routing table.

### 3.4 The pipeline checked

*Asks:* are the workflow files themselves linted, audited or tested?

A workflow file is code nobody runs locally, and its first test is the next
push. Three mechanisms are read as present or absent: a linter
(`actionlint`), a security audit (`zizmor`), and a test that reads `.github/`
or runs a `--self-test`. Steps that search the tree and fail the job are
listed as *rules a step refuses*: the CI-side twin of a guard, paid on every
run instead of every turn, handed over and never counted.

The audit row is zizmor's own findings, counted by severity, when it is on
PATH. Absent, the row abstains; nothing here reimplements it.

### 3.5 The verdict's trust

*Asks:* how often did a rerun change the verdict?

From the repository's run history: runs whose first attempt failed and whose
last succeeded, on the same commit. A verdict that changed with no change to
the code depended on something other than the code, which is flakiness
measured rather than felt. The median time to a verdict travels with the row.
No remote, no `gh`, or no auth reads as *not readable*, never as zero flips.

### 3.6 What ships

*Asks:* what leaves this repository, what makes it, and can the latest be
traced?

Tags are counted, the latest is checked for reachability from `HEAD`, and the
workflows are read for anything that publishes: a release, a tag, an image, a
package. The manifest's version (`plugin.json`, `package.json`,
`pyproject.toml`, `Cargo.toml`) is compared with the latest tag. A repository
that ships nothing is reported as such, in `info`: fine for one nobody
installs.

*Bad reading costs:* a tag off the default branch means what shipped is not
what the branch says shipped. A manifest ahead of its tag is a version nobody
can install yet, or a release somebody forgot.

---

## 4 — Repository memory: is what is written down true, and worth its place?

Nothing here is read off a count of files: a count goes *up* when this plugin
is installed, which would be the instrument rewarding its own presence. So
thickness appears only as a denominator, and adding files cannot raise anything
-> [0025](../docs/decisions/0025-dimension-4-asks-whether-an-agent-can-find-its-way.md)

An earlier row compared two agents, one with the repository's memory and one
without, and was removed: a single sample of a non-deterministic process moved
when nothing had changed
-> [0042](../docs/decisions/0042-a-measurement-noisier-than-its-effect-is-not-a-measurement.md)
This dimension therefore does not claim to know whether the memory *works*. It
asks what a deterministic read can answer: is it true, is it worth keeping,
and are the places for writing it down used at all.

### 4.0 The surface it uses

*Asks:* which of the ways of reaching an agent have anything at them?

Counting files is refused; counting **mechanisms** is different, and the test
is *is there another way to get this effect?* A `scripts/gates/` directory
fails it, since checks can live anywhere. A `PreToolUse` hook passes it: there
is no other place a tool call can be refused before it happens. So this row
reads Claude Code's own surface, the seven delivery moments plus scoped rules,
subagents, slash commands and MCP servers, and for each empty place says what
therefore cannot happen:

```
  the surface it uses    6 of 12 — no path-scoped rule, UserPromptSubmit hook, …
    no PreToolUse hook or deny rule   .claude/settings.json
      no action can be refused before it happens, and a destructive one is
      complete the moment it runs
```

Only the repository's own mechanisms count, never a plugin's, and each is
present or absent: six skills are the same coverage as one.

*Agent judges.* An absent mechanism is a candidate, not a verdict; a repository
can be right to have no MCP server
-> [0043](../docs/decisions/0043-a-mechanism-is-not-a-convention.md)

### 4.1 What is written down

*Asks:* what kinds of memory exist, and do their references resolve?

Root and nested `CLAUDE.md`, skills, hooks, rules, settings, documents: the
denominator every row under it is read against. One thing it exists to say: a
rule that needs a script behind it and has none is a hope, not a constraint,
and it costs tokens either way.

### 4.2 Is each memory worth keeping?

*Asks:* what is the standing text spent on, and what restates a guard?

Three splits a machine can make: prohibition, requirement or plain statement;
already enforced by a hook that was *measured* firing; scoped to one path but
loaded anyway.

*Agent judges* whether a constraint is one an agent could have guessed, or
whether an example earns its lines.

*Bad reading costs:* a prohibition restating a guard pays rent every turn to
say what the guard says better, and the guard does not depend on anyone having
read anything.

### 4.3 Do the documents agree with the code?

*Asks:* which promises does the documentation make that the code does not
keep?

Method after [CASCADE](https://arxiv.org/abs/2604.19400):

1. Tests are generated **from the documentation alone** and run against the
   real code.
2. An implementation is generated **from the same documentation**, and the
   same tests run against it.
3. A disagreement is reported only when a test fails on the real code and
   passes on the implementation, with nothing going the other way. Without
   that second condition the finding is indistinguishable from a bad test
   -> [0036](../docs/decisions/0036-a-contradiction-is-decided-by-an-experiment-not-a-comparison.md)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/promises.py --root .
```

*A blind agent judges.* The rounds run through `--promise-tests` and
`--promise-impls`, answered by `assess-promise-tester`, which has `Write` and no
way to read the repository. A test written after reading the implementation
agrees with it by construction
-> [0040](../docs/decisions/0040-the-blind-is-the-tool-list-not-the-prompt.md)

The paper reports **precision 0.88, recall 0.21**: a `bad` row is worth acting
on, and an empty one is not a clean bill.

### 4.4 Do the documents agree with each other?

*Asks:* do two documents name one thing and give it two values?

Method after [ConflictRAG](https://arxiv.org/abs/2605.17301), reimplemented
from the paper's description: a harsh lexical filter first, an expensive reader
only on what survives
-> [0035](../docs/decisions/0035-a-filter-that-emits-half-the-pairs-has-not-filtered.md)
Supersession, a decision record deliberately overruling an older one, is
excluded before the filter runs.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/conflict.py --root .
```

Each surviving pair carries three signals, which was written last, which is on
the floor, which value the code contains, weighted by the paper's
Entropy-TOPSIS. It **ranks and does not decide**.

*Agent judges,* and usually says no: two documents giving one number two values
are as often an example beside a default.

### 4.5 The form of the instructions

*Asks:* is what is kept shaped so a model can act on it?

Every row above asks whether the writing is true. This one asks whether it is
followable, after [Reframing Instructional Prompts](https://arxiv.org/abs/2109.07830)
(Findings of ACL 2022). Three of its operations apply to standing instructions:

- **Positive assertion.** *Never return a file dump* leaves the target
  unstated; *return the paths and what is at them* rules out the dump on the
  way past.
- **Itemizing.** A paragraph carrying several requirements becomes a list.
- **Low-level patterns.** *Follow the house style* becomes the concrete shape
  of the output.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/assess/reframe.py --root . --json
```

Only instructions are candidates (*you must not swallow the status*), never
statements of fact (*the two cannot drift*). It does not score prose quality
or readability.

*Agent judges,* and every row here is `info`, never `bad`: a `CLAUDE.md` may be
one long paragraph on purpose.

---

## 5 — Context economy: what does the harness cost every turn?

### 5.1 Usage

*Asks:* what does a turn pay before anyone types?

```
floor     what every turn pays before anyone types
ceiling   floor + the largest scoped rule + the largest nested CLAUDE.md
parked    installed, but arrives only when something asks for it
```

The unit is characters over four, deliberately: a real tokenizer is not one
number either, and a stable approximation both sides can reproduce offline is
worth more than a precise one that needs the network.

Parked is the escape hatch, not the bill. A paragraph moved under a path glob
has not been deleted; it has stopped being paid for on turns that never touch
that path.

### 5.2 Files unlike their neighbours

*Asks:* which loaded file is out of line with its own kind?

A total is right and not actionable
-> [0037](../docs/decisions/0037-a-total-hides-the-one-file-worth-finding.md)
So the measurement runs per file, against the median of **its own kind**: a
rule against the other rules, a skill against the other skills. Four things it
can say: size against its kind, what its sentences are, how much is fenced
code, and **paragraphs repeated from another loaded file**. The last is the
only certain one: the same paragraph in two loaded files is paid for twice
every turn, and one copy will drift.

Where Claude Code already answers a question, it answers it:

```bash
claude plugin validate . --strict     # the manifest, by the first-party checker
claude plugin details <plugin-name>   # always-on and on-invoke cost per skill and agent
claude doctor                         # installation health
```

Those cover plugins. Dimension 5 covers what they do not: the repository's own
`CLAUDE.md`, nested `CLAUDE.md`, `.claude/rules/` and documents, the floor a
teammate pays for cloning.

---

## What comes out

Two pages. The fact sheet is every row above. The reading puts each sub-item
on a ten, with one line saying what about *this* repository set it and one
saying what would move it — a file, a hook, a test, or *nothing*, which
closes the row. The reading opens with those lines, lowest score first, and
that list is the artefact -> [0046](../docs/decisions/0046-a-reading-says-what-would-move-it-and-is-read-twice.md)

Each dimension is read twice, by readers who did not see each other's
numbers. Two more than two points apart are shown as disagreeing, and which
is right is the assessor's to settle with a file and a line.

The [assessment checklist](2-checklist.md) is written from that list. The
hardest questions have no number behind them: is the standing cost earning
its tokens, does each hook address a mistake *this* repository actually makes.
Answering them is the reading, and the reason the checklist is worth more than
the fact sheet.
