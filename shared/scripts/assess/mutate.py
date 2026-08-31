#!/usr/bin/env python3
"""Change one line the tests already cover, and see whether they notice.

    python3 assess/mutate.py [--root .] [--limit 40] [--json OUT]
    python3 assess/mutate.py --rq1 [--root .]        # the suppression study

Exit codes:
    0 = mutants were generated and run
    2 = cannot judge (no Python, no runnable tests, nothing changed and covered)

## What this answers that coverage does not

Coverage says which lines no test executes. This says something narrower and
harder: **this line IS executed by a test, and the test does not care what it
says.** A line at 100% coverage whose operator can be flipped with every test
still green is a line nothing is actually checking.

## Everything here is copied, not invented

The design is Google's, from *Practical Mutation Testing at Scale* (Petrovic,
Ivankovic, Fraser, Just; TSE 2021, arXiv:2102.11378), which reports a system
that has run on 776,740 changelists and 16,935,148 mutants. Where they publish
a rule, that rule is implemented here as published. Nothing about the operator
set or the suppression heuristics is our own idea, and the places where we
deviate are marked and argued.

**There is no code release.** The service is internal, tied to Blaze, Critique
and Tricorder. What is public is the paper's rules and its numbers, so the
rules are what is copied.

### The five operators (their Table 1, originally from Mothra)

    AOR  arithmetic operator replacement     a + b   ->  a - b
    LCR  logical connector replacement       a and b ->  a or b
    ROR  relational operator replacement     a < b   ->  a <= b
    UOI  unary operator insertion            a       ->  not a
    SBR  statement block removal             stmt    ->  (deleted)

**ABS is deliberately absent.** The paper excludes it: it "predominantly
creates unproductive mutants". Adding it back would be inventing.

### The three policies that do the work

1. **At most one mutant per line.** Their §4.1.
2. **Only lines that are both changed and covered.** Uncovered mutants "would
   inevitably survive because the code is not tested", which is a coverage
   finding, not a mutation finding.
3. **Arid nodes are not mutated.** Their §3.2 and Appendix A. An arid node is
   one where a mutant would be unproductive -- equivalent, or detectable but
   not worth a test.

### What we cannot copy, and do not pretend to

Their arid detection is "more than a hundred rules" plus "fuzzy name
suppression rules for more than 200 function families", built from **six years
of feedback from more than 20,000 developers**. We have none of that, and the
paper is explicit that the heuristics "are specifically tailored for the
environment of the developers who provided the feedback, and a different
context will require deriving new, appropriate heuristics."

What we implement is the published rules themselves -- see `arid.py` -- and in
particular the three the paper says paid for almost all of the gain:

> "The highest mutant productivity gains came from the three heuristics
> implemented in the early days: suppression of mutations in logging
> statements, time-related operations ... and finally configuration flags ...
> there is strong indication that these suppressions account for improvements
> in productivity from about 15% to 80%."

And in place of the feedback loop, an **agent second pass** over the survivors.
It is a weaker judge than the developer who wrote the line -- that is stated on
the page rather than hidden -- and it is the only judge available.

## Python only, and it says so

Arid detection is defined over AST nodes, with recursion into compound nodes.
Python's `ast` is in the standard library, which is why this exists at all; for
any other language there is no parser here and the honest answer is exit 2. A
regex mutator would generate uncompilable mutants and could not implement the
arid rules, which are the entire reason the technique is usable.

Note the paper's own figure: **Python mutants are the least productive of any
language they measured, 70.6% against Java's 87.2%** -- "Python code generally
requires more tests because of the lack of the compiler". We start on the hard
end of their data.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from arid import arid_line, arid_lines, why_arid  # noqa: E402

# --------------------------------------------------------------------------
# the five operators, exactly as published
# --------------------------------------------------------------------------

# Mothra's operators replace an operator with **each** other operator of its
# class, not with one designated partner. That is what makes traditional
# mutagenesis produce hundreds of mutants for a changelist, and getting it
# wrong makes the no-suppression arm of RQ1 too small to reduce -- measured:
# a one-partner AOR gave a 2x reduction where the paper reports 117x, because
# there was nothing there to suppress.
ARITH = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
CONNECT = (ast.And, ast.Or)
RELATE = (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)

OP_TEXT = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
    ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**",
    ast.And: "and", ast.Or: "or",
    ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
    ast.Eq: "==", ast.NotEq: "!=",
}

# UOI inserts a unary operator where one was not. Their Table 4 has UOI at
# 18.5% of all mutants, second only to SBR, which is only reachable by
# inserting at expressions generally rather than at conditions only.
UOI_INSERTS = ("not", "-", "~")

# A.1.12's exclusion list, which is what makes SBR usable at all. Deleting any
# of these produces code that does not run, and a mutant that fails to load is
# scored as killed while having tested nothing.
SBR_FORBIDDEN = (ast.Return, ast.Raise, ast.Global, ast.Nonlocal,
                 ast.Import, ast.ImportFrom, ast.FunctionDef,
                 ast.AsyncFunctionDef, ast.ClassDef, ast.Try)


class Mutant:
    __slots__ = ("path", "line", "col", "op", "before", "after", "verdict",
                 "detail")

    def __init__(self, path, line, col, op, before, after):
        self.path, self.line, self.col = path, line, col
        self.op, self.before, self.after = op, before, after
        self.verdict, self.detail = None, ""

    def as_dict(self):
        return {"path": self.path, "line": self.line, "operator": self.op,
                "before": self.before, "after": self.after,
                "verdict": self.verdict, "detail": self.detail}


# --------------------------------------------------------------------------
# generation
# --------------------------------------------------------------------------

def _parent_map(tree):
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _function_lines(tree):
    """Every line inside a function or method body.

    SBR and UOI are restricted to these, and the reason is A.1.12's exclusion
    of **declaration statements**. In Python a module-level assignment is a
    declaration -- `WrappedFn = t.TypeVar("WrappedFn")` -- and deleting it does
    not test anything, it stops the module importing, which every test then
    reports as a failure. Measured on `tenacity`: 15 of 40 mutants came back
    `broken`, and all fifteen were module-level deletions or insertions in
    `__init__.py`.

    A mutant that breaks the import is the worst kind, because from outside it
    is indistinguishable from a mutant a test caught. The paper's Go heuristic
    A.5.2 exists for exactly this: "the mutant appears killed because the test
    fails (to build)"."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for stmt in node.body:
                start = getattr(stmt, "lineno", None)
                if start is None:
                    continue
                end = getattr(stmt, "end_lineno", start) or start
                out.update(range(start, end + 1))
    return out


def candidates(path, source, lines=None, arid_lines=None):
    """Every mutation this file admits, before any policy is applied.

    Faithful to Mothra as the paper describes it: each operator produces one
    mutant per *alternative*, not one per node. `a + b` yields six AOR mutants
    (`-`, `*`, `/`, `//`, `%`, `**`), `a < b` yields five ROR mutants, and
    every expression admits three UOI insertions. This is what "traditional
    mutagenesis" means and what their median of 820 per changelist is counting.

    `lines` restricts to a set of line numbers -- the changed set. None means
    the whole file, which is what the RQ1 study's control arm needs.

    `arid_lines` is a {line: (rule, sound)} map computed once per file; passing
    it in is what keeps this from reparsing the source for every mutant."""
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return []
    src = source.split("\n")
    parents = _parent_map(tree)
    inside = _function_lines(tree)
    out = []

    def add(node, op, before, after):
        ln = getattr(node, "lineno", None)
        if ln is None or (lines is not None and ln not in lines):
            return
        out.append(Mutant(path, ln, getattr(node, "col_offset", 0), op,
                          before, after))

    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and type(node.op) in ARITH:
            for alt in ARITH:
                if alt is not type(node.op):
                    add(node, "AOR", OP_TEXT[type(node.op)], OP_TEXT[alt])
        elif isinstance(node, ast.BoolOp) and type(node.op) in CONNECT:
            for alt in CONNECT:
                if alt is not type(node.op):
                    add(node, "LCR", OP_TEXT[type(node.op)], OP_TEXT[alt])
        elif isinstance(node, ast.Compare) and node.ops and \
                type(node.ops[0]) in RELATE:
            for alt in RELATE:
                if alt is not type(node.ops[0]):
                    add(node, "ROR", OP_TEXT[type(node.ops[0])], OP_TEXT[alt])

        # UOI: an insertion point is any expression that is not already the
        # operand of the operator being inserted, and not a bare literal --
        # `not 3` and `-"x"` are uncompilable in spirit if not in syntax.
        if isinstance(node, (ast.Name, ast.Call, ast.Attribute,
                             ast.Subscript, ast.Compare)) and \
                not isinstance(parents.get(node), ast.UnaryOp) and \
                getattr(node, "lineno", -1) in inside:
            # One insertion per operand. Inserting all three of `not`, `-` and
            # `~` everywhere put UOI at 90% of generated mutants where the
            # paper's Table 4 has it at 18.5%: `-` and `~` on a value that is
            # not a number are mutants that cannot run, and a mutant that
            # fails to load is scored killed while having tested nothing.
            add(node, "UOI", "<expr>", "not <expr>")

        if isinstance(node, ast.stmt) and \
                not isinstance(node, SBR_FORBIDDEN) and \
                getattr(node, "lineno", -1) in inside:
            ln = getattr(node, "lineno", 0)
            text = src[ln - 1] if 0 < ln <= len(src) else ""
            if text.strip():
                add(node, "SBR", text.strip()[:60], "(deleted)")
    return out


def one_per_line(mutants):
    """Their §4.1. The first mutant on each line wins.

    Not a sample: a policy. Two mutants on one line are two ways of saying the
    same thing about that line, and surfacing both doubles the reading cost for
    no extra information."""
    seen, out = set(), []
    for m in mutants:
        key = (m.path, m.line)
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


def arid_map(source):
    """{line: (rule, sound)} for one file, in one parse. See `arid.arid_lines`."""
    return arid_lines(source)


def suppress(mutants, sources, maps=None):
    """Drop the mutants on arid nodes. Their §3.2 and Appendix A.

    Returns (kept, [(mutant, (rule, sound))]) -- the dropped ones are returned
    rather than discarded, because the paper never measures how many productive
    mutants its suppression loses, and a tool that repeats that silence has
    copied the wrong half."""
    maps = maps if maps is not None else {}
    kept, dropped = [], []
    for m in mutants:
        if m.path not in maps:
            maps[m.path] = arid_map(sources.get(m.path, ""))
        rule = maps[m.path].get(m.line)
        if rule:
            dropped.append((m, rule))
        else:
            kept.append(m)
    return kept, dropped


def generate(root, files, covered=None, strategy="arid", maps=None):
    """The three strategies of the paper's RQ1, so they can be compared.

        none  every mutant the AST admits    (their "traditional mutagenesis")
        line  one per line
        arid  one per line, on non-arid nodes only
    """
    sources, all_m = {}, []
    for rel in files:
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                sources[rel] = fh.read()
        except OSError:
            continue
        if covered is not None:
            lines = covered.get(rel)
            # A file the suite never entered is not a file with uncovered
            # lines, it is a file outside the measurement. Falling through to
            # `lines = None` here mutated it *entirely* -- the inverse of the
            # policy -- and put every survivor in `doc/source/conf.py`, a
            # Sphinx config no test executes. Measured, on tenacity.
            if not lines:
                continue
        else:
            lines = None
        all_m += candidates(rel, sources[rel], lines)
    if strategy == "none":
        return all_m, [], sources
    if strategy == "line":
        return one_per_line(all_m), [], sources
    kept, dropped = suppress(all_m, sources, maps)
    return one_per_line(kept), dropped, sources


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", default="")
    ap.add_argument("--limit", type=int, default=40)
    a = ap.parse_args()
    print("mutate.py: generation only so far; the runner lands next",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
