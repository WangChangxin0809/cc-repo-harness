# 0028 — Mutation testing, copied from a paper and checked against its numbers

Date: 2026-09-01
Status: accepted
Adds a second way to introduce a defect: change one line the tests already
cover and see whether anything notices. The design is not ours — it is
transcribed from Google's published system — and this record is mostly about
which of their numbers we reproduced and which we did not.

## Context

Dimension 2 had exactly one way in: take a real fix from the repository's own
history back to its parent. That is a strong design — the defect actually
happened, and the fix is the answer key — and it is narrow in a way the page
now says out loud. It can only find failure modes that already became a commit
here.

Mutation testing asks a different and harder question than coverage. Coverage
says *no test executes this line*. Mutation says *a test executes this line,
and does not care what it says*.

## The design is copied. There is no code to copy.

*Practical Mutation Testing at Scale: A View from Google* (Petrovic, Ivankovic,
Fraser, Just; TSE 2021, arXiv:2102.11378) reports 776,740 changelists and
16,935,148 mutants. **No code was released** — the service is internal, tied to
Blaze, Critique and Tricorder. What is public is the rules and the numbers, so
the rules are what is copied:

- The five operators of their Table 1 (AOR, LCR, ROR, UOI, SBR), each replacing
  an operator with **every** alternative of its class, as Mothra does.
- **ABS deliberately absent**, because they exclude it as "predominantly
  creat[ing] unproductive mutants".
- One mutant per line (§4.1); only changed and covered lines (§2.1–2.2).
- 24 of Appendix A's ~35 arid rules, each with the paper's own soundness verdict
  attached, and each carrying its section number and its example.

Vendoring `mutmut` or `cosmic-ray` was not an option anyway: `shared/` is
standard library only. Python's `ast` is stdlib, which is why this exists at
all, and why it is **Python only** and abstains elsewhere rather than
regex-mutating a language it cannot parse.

## What we reproduced, and what we did not

Full numbers in `docs/generated/mutation-study.json`. Four claims, three
reproducible without their feedback loop:

| Claim | Paper | Ours | |
|---|---|---|---|
| survivability | 13.2% Python | 7.1% (tenacity, 200 mutants) | **in range** |
| RQ1 as an **end state** | median 7 per changelist | median 1–16 across six repos | **met** |
| RQ1 as a **ratio** | 117× | 4–7× | **missed** |
| arid rate | 90.9% of lines | 17.8% of 18,727 lines | **missed** |
| productivity | 82% (70.6% Python) | 76.5% combined | **met, with a caveat** |
| productivity 15% → 89% | six years, 20,000 developers | — | **not attempted** |

### The ratio miss is not a defect, and the arid miss is

The reduction ratio cannot match because **the input differs by an order of
magnitude**. Their no-suppression arm has a median of 820 mutants per
changelist; on `requests` it is 4. A Google changelist is much larger than an
open-source commit. What should match is the *end state* — a handful of mutants
per change, small enough to read — and it does.

The arid rate is a real gap and it is worth being precise about why. 17.8%
against 90.9%, over 18,727 mutable lines of real Python. The rule breakdown
says what happened: `LOG` fires 530 times in this repository and 11 times in
`records`, and does not reach the top four rules in `click`, `tenacity`, `tqdm`
or `requests`. They measured C++ and Java service code where logging and
monitoring sit on nearly every line. The paper says as much:

> "these heuristics are specifically tailored for the environment of the
> developers who provided the feedback, and a different context will require
> deriving new, appropriate heuristics."

**Their 90.9% is a property of their corpus, not of the method.** Transcribing
the remaining eleven appendix rules would not close it.

## Productivity, and the one rule that is ours

Their definition is operational: a mutant is productive if the developer who
wrote the line clicked "Please fix". 66,798 clicks, 20,000 developers, six
years. That cannot be reconstructed, so an agent is asked the same question and
**the page names the judge**. It is a weaker judge than theirs and the two
figures are not equivalent.

Two readings:

- **Our own guards: 7 of 8 productive, 87.5%.** The survivors are real: the
  same `if tool_name != "Bash":` line is deletable from three separate guards
  with the whole suite green, because every non-Bash test case carries no
  `command` key and so asserts nothing.
- **`tenacity`: 6 of 13 productive, 46.2%** — and the judge said why. Four of
  the seven unproductive were one pattern written twice: `if acc: break` under
  `acc = acc or f(x)`, where the `or` has already short-circuited and the guard
  cannot change the result.

That feedback became a rule, which is exactly the paper's own process:

> "This process is manual: if we decide a certain mutation is not productive
> and that the whole class of mutants should not be created, the rule is added
> to the expert function."

`SHORTCIRCUIT` is the only rule in `arid.py` not transcribed from Appendix A.
Its *category* is theirs (A.1.22, "the early return ... has no effect on the
behavior"); its trigger is ours. With it, tenacity goes to 6 of 9, **66.7%**,
and the combined figure is 13 of 17, **76.5%**.

### The caveat that has to travel with that number

**The rule was derived from tenacity's own mutants and then applied to them.**
That is fitting to the set it is measured on. The guards figure is independent
of the rule and is 87.5%; tenacity's is not and is 66.7% — *below* the bar on
its own. A claim that this generalises needs a repository the rule was not
derived from, and one has not been run.

## Five bugs that only a real run found

Each of these passed every test that existed when it was written, and each is
now a case:

1. **AOR offered one alternative, not all.** The no-suppression arm was 7×
   too small, so there was nothing for suppression to remove — a 2× reduction
   where the paper reports 117×.
2. **A.1.8 fired on any literal 0 or 1**, not on a *no-op* child, so `a + 1`
   was suppressed. Most arithmetic in any tree was being silently skipped.
3. **An uncovered file was mutated entirely.** When coverage was supplied but a
   file had no entry, the code fell through to "mutate everything" — the
   inverse of the policy. Every survivor on `tenacity` was in `doc/source/conf.py`.
4. **A suite that could not import scored as a kill.** `ModuleNotFoundError`
   exits 1 and contains no "importerror". This is the exact inflation the
   paper's Go heuristic A.5.2 exists to prevent, and it survived until a case
   checked the *verdict* rather than the rendered output.
5. **Module-level statements were deletable.** 15 of 40 mutants came back
   broken, all of them deletions in `__init__.py`. A.1.12 excludes declaration
   statements, and in Python a module-level assignment is one.

## Two things the paper does not discuss, and a repository needs

**Flaky suites.** `tenacity`'s timing-sensitive tests fail roughly one run in
three. A mutant is scored killed whenever the suite goes red, so a flaky
baseline inflates kills by an unknown amount. The baseline is run three times
and the page says `FLAKY` when it disagrees with itself.

**Hanging mutants.** Flipping one comparison in a backoff loop ran for 166
seconds against a 2.8 second baseline. The per-mutant budget is derived from
the green suite (8× the fastest baseline), and a timeout is **its own verdict**
— behaviour changed observably, and no test asserted anything, so it is neither
killed nor survived.

## Rejected

**Computing a mutation score.** The paper refuses to and says why: mutagenesis
is probabilistic, so "only a fraction of all possible mutants are generated".
A percentage over a sample chosen by heuristics is not comparable to anything.

**Copying the paper's silence about unsound rules.** They mark 18 of 35 rules
unsound, say the unsound ones gave the larger gains, and never measure what
those rules suppress that they should not. Suppressions here are counted
separately by soundness and both numbers are printed.

**Timing CI locally, and other convenient substitutes.** Same principle as
0026: a number measuring the wrong thing is worse than no number.

**Mutating anything but Python.** No parser, and the arid rules are defined
over AST nodes with recursion into compound ones. A regex mutator would produce
uncompilable mutants and could implement none of the rules that make the
technique usable.

## Evidence status

| Claim | Grade |
|---|---|
| The operators and 24 arid rules are the paper's | **checked** — each carries its Appendix A section and example in its docstring |
| Survivability lands in the paper's range | **measured** — 7.1% over 200 mutants on tenacity, against 13.2% |
| The end-state mutant count matches | **measured** — medians 1–16 across six repositories, against 7 |
| The reduction ratio does not, and why | **measured** — 4–7× across six repositories, with the no-suppression arm differing by an order of magnitude |
| The arid rate is a property of their corpus | **measured** — 17.8% over 18,727 lines, with the per-rule breakdown showing LOG at 530 here and 11 in `records` |
| Productivity clears 70% combined | **measured once**, 13 of 17, by an agent judge — and the rule that got tenacity there was derived from tenacity's own mutants |
| The tool finds real holes | **measured** — `if tool_name != "Bash":` is deletable from three of our own guards with the suite green |
| It generalises to a repository the rule was not derived from | **not established** — this is the open one |
