# 0029 — The floor is itemised, and the replay can be told how to run

Date: 2026-09-01
Status: accepted
Two changes with one cause: a measurement that produced a number and refused
to say anything about what was behind it.

## Context

**Dimension 5 measured the bill and never the goods.** Two repositories with
an identical thousand-token floor are not in the same position. One spends it
on four constraints an agent could not have guessed. The other spends it on
forty prohibitions against things nobody was going to do, most of them
one-off incidents nobody deleted. A token count cannot tell them apart, and
the whole point of the dimension is that the tokens are being paid on **every
turn of every session** whether or not the turn has anything to do with them.

**Dimension 2 abstained on its own author.** `ecosystems.py` recognises a
handful of conventions — a `tests/` directory plus a packaging marker, a
`package.json`, a `Cargo.toml`. It does not recognise a `selftest.py` script,
so this repository's own assessment said `no runnable test command` while five
working suites sat in the tree. Measured more broadly this session: of five
real Python repositories cloned from GitHub, the table produced a green suite
for **one**.

## Decision, part one: itemise the floor

`value.py` reads what is paid for on every turn — entry files and
unconditional rules, never the parked ones — and asks three questions a
machine can answer.

**Prohibition, requirement, or plain statement.** Both instruction kinds are
legitimate and they are not doing the same work: a prohibition earns its place
only against a mistake somebody actually makes, while a requirement is working
every time the thing it requires comes up. Most of a good `CLAUDE.md` is
neither — it is statements of fact about the system, which is why "statement"
is a category rather than a residue.

**Is it already enforced?** The sharp one, and it is only possible because
dimension 1 exists. A rule saying *never force-push to main*, in a repository
whose hooks were **measured refusing** force-pushes to main, pays tokens on
every turn to restate a thing that cannot happen. The guard is strictly
better: not optional, not dependent on the agent having read anything, and
free until it fires.

Two qualifiers that decide whether this row is trustworthy:

- **Measured, not configured.** A guard that exists and does not fire is not
  in the set. A prohibition restating a *broken* guard is the one sentence on
  the floor that is definitely earning its place.
- **A false block is not enforcement.** A guard that refuses the legitimate
  action too has discriminated nothing, and dimension 1 already knows which
  those are.

And the row does not say *delete this*. Some teams want the guard and the
sentence, so a person understands the refusal when it arrives. It is a line
item.

**Is it about one path and loaded anyway?** A paragraph about the frontend
build, paid for on the turns that never leave the database layer. Not wrong —
misfiled. The same words under a path-scoped rule cost nothing until somebody
touches that path, which is 0024's argument measured from the other side.

Fenced blocks are stripped before any of this. A document demonstrating
`git push --force` in a code block would otherwise be classified as made of
prohibitions, which turns every well-written guide into a warning.

## Decision, part two: the table is a fast path, not the only path

`--test-command` on `factsheet.py`, `catch.py` and `run_mutants.py`. When the
table cannot guess, the abstention now says so **and says what to pass**,
instead of reading as a verdict on the repository.

The distinction that matters: *this repository has no tests* is a real
finding and must still be reported as one. *A table did not recognise this
repository's convention* is a fact about the table. Those were the same
message, and now they are not.

Whoever supplies the command has read the repository — an agent that opened
the CI file, or a person. That is the right division: a machine holds the
conventions it knows, and something that can read decides when none of them
apply.

## Rejected

**Guessing harder.** More patterns in the ecosystem table is a treadmill with
no end, and every new pattern is a new way to guess wrong on a repository
nobody here has seen. The table earning its place is exactly the set of cases
where guessing is safe.

**Running whatever the CI file says, automatically.** Tempting, and it is
executing an arbitrary command from a repository nobody has read, chosen by a
regex. The pre-flight line from 0026 exists so a person can see the command
before it runs; deriving that command automatically from a file would put a
step back behind the curtain that 0026 deliberately pulled in front of it.

**Scoring prohibitions.** No threshold on the count. Some repositories are
genuinely dangerous and should be full of `don't`. The only flag is when
prohibitions outnumber requirements more than three to one *and* there are
more than eight, which is a shape worth a look and not a failure.

**Judging whether a constraint was guessable.** That is the agent's half, and
`value.py` deliberately stops before it. What a machine can do is hand over
the floor already split, with the enforced ones marked — a far better question
than *read this and tell me what you think*.

## Consequences

**Dimension 2 measures on this repository for the first time.** Its first
reading with the guards suite supplied: 2 of 2 replayed defects reached
`never`. That is an honest result of a narrow command — the guards selftest
does not cover the code those defects lived in — and it is a reading where
there was previously an abstention.

**Dimension 5 gained three rows and no new number.** The floor and ceiling are
unchanged. What changed is that the page now says what the floor bought.

**`value.py` depends on dimension 1's output.** The first cross-dimension
dependency in the assessment. It degrades correctly: with no blast result the
enforcement row simply does not appear, rather than reporting zero.

## Evidence status

| Claim | Grade |
|---|---|
| A prohibition restating a measured refusal is found | **checked** — a case plants one and watches it reported, then removes the refusal and watches it stop |
| A guard that does not fire is not enforcement | **checked** — planted `stopped: False` and the row correctly goes quiet |
| A guard that blocks the fix too is not enforcement | **checked** — planted `false_block: True` |
| Fenced commands are not instructions | **checked** — planted fence-tracking removal and watched the case go red |
| A scoped rule file is not on the floor | **checked** — planted frontmatter detection removal |
| A supplied command is used, and its absence is explained | **checked** — two plants, both caught, on a fixture built to defeat the table and only the table |
| The table misses most repositories | **measured** — one green suite of five real Python repositories, plus this one |
| Itemising changes what anybody does | **argued** — the rows are new and nobody has yet acted on one and reported back |
