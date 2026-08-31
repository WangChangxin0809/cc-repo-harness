#!/usr/bin/env python3
"""Apply each mutant, run the tests, and record whether anything noticed.

    python3 assess/run_mutants.py --root REPO [--limit 30] [--json OUT]

Exit codes:
    0 = mutants were run and a verdict reached for each
    2 = cannot judge (no Python, no runnable tests, no mutable covered lines)

## The three policies, applied here rather than described

`mutate.py` generates; this decides what is worth running and runs it.

1. **Only changed and covered lines.** Their §2.1-2.2. A mutant on an
   uncovered line "would inevitably survive because the code is not tested",
   which is a coverage finding reported by coverage, at a fraction of the cost.
2. **One mutant per line.** Their §4.1.
3. **Arid nodes are not mutated.** Their §3.2 and Appendix A, via `arid.py`.

## Coverage without a dependency

`shared/` is standard library only, so coverage is measured with `trace` --
which is stdlib, and slow. It is run **once**, over the whole suite, and the
line set is reused for every mutant. Where the subject repository has
`coverage` installed in its own environment that is used instead, because it
is the same measurement an order of magnitude faster; that is using what the
subject has, not depending on it.

If neither works, the covered-line restriction is **dropped and said to be
dropped**. Silently mutating uncovered lines would fill the report with
survivors that mean nothing.

## Killed is not the same as caught

A mutant is `killed` when the suite goes red, `survived` when it stays green,
and `broken` when the suite could not run at all -- an import error, a syntax
error from the mutation itself. `broken` is **not** killed. A mutant that stops
the suite loading looks exactly like a mutant a test caught, and counting it as
a kill inflates the score with mutants that tested nothing. The paper's own
Go statement-deletion heuristic (A.5.2) exists for precisely this reason:
"Deleting statements or blocks of statements almost invariably produces
unbuildable code and the mutant appears killed because the test fails (to
build)."
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mutate as mutate_mod  # noqa: E402
from ecosystems import find, sh  # noqa: E402

TEST_TIMEOUT = 300


# --------------------------------------------------------------------------
# applying a mutant to the source
# --------------------------------------------------------------------------

class _Rewrite(ast.NodeTransformer):
    """Apply exactly one mutation, identified by (line, col, operator).

    Done on the AST and unparsed, not by string surgery, because a textual
    replacement of `+` hits the `+` inside a string literal on the same line
    and produces a mutant that tests the wrong thing while looking right."""

    def __init__(self, m):
        self.m, self.done = m, False

    def _at(self, node):
        return (not self.done
                and getattr(node, "lineno", None) == self.m.line
                and getattr(node, "col_offset", None) == self.m.col)

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if self.m.op == "AOR" and self._at(node):
            alt = _OP_BACK.get(self.m.after)
            if alt is not None:
                node.op = alt()
                self.done = True
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        if self.m.op == "LCR" and self._at(node):
            alt = _OP_BACK.get(self.m.after)
            if alt is not None:
                node.op = alt()
                self.done = True
        return node

    def visit_Compare(self, node):
        self.generic_visit(node)
        if self.m.op == "ROR" and self._at(node):
            alt = _OP_BACK.get(self.m.after)
            if alt is not None and node.ops:
                node.ops[0] = alt()
                self.done = True
            return node
        if self.m.op == "UOI" and self._at(node):
            self.done = True
            return ast.UnaryOp(op=ast.Not(), operand=node)
        return node

    def _uoi(self, node):
        if self.m.op == "UOI" and self._at(node):
            self.done = True
            return ast.UnaryOp(op=ast.Not(), operand=node)
        return node

    def visit_Name(self, node):
        return self._uoi(node)

    def visit_Call(self, node):
        self.generic_visit(node)
        return self._uoi(node)

    def visit_Attribute(self, node):
        self.generic_visit(node)
        return self._uoi(node)

    def visit_Subscript(self, node):
        self.generic_visit(node)
        return self._uoi(node)

    def generic_visit(self, node):
        # SBR: the statement at the mutation point is replaced by `pass`,
        # which is A.1.12's own prescription -- "in Python a block with `pass`"
        # -- and is what keeps the deletion from changing the indentation
        # structure into something that will not parse.
        for field, value in ast.iter_fields(node):
            if not isinstance(value, list):
                continue
            for i, item in enumerate(value):
                if isinstance(item, ast.stmt) and self.m.op == "SBR" and \
                        self._at(item):
                    value[i] = ast.Pass(lineno=item.lineno,
                                        col_offset=item.col_offset)
                    self.done = True
        return super().generic_visit(node)


_OP_BACK = {"+": ast.Add, "-": ast.Sub, "*": ast.Mult, "/": ast.Div,
            "//": ast.FloorDiv, "%": ast.Mod, "**": ast.Pow,
            "and": ast.And, "or": ast.Or,
            "<": ast.Lt, "<=": ast.LtE, ">": ast.Gt, ">=": ast.GtE,
            "==": ast.Eq, "!=": ast.NotEq}


def apply(source, m):
    """The mutated source, or None if the mutation could not be placed.

    None matters: a mutant that could not be applied must not be counted as
    anything. Scoring it killed inflates the result and scoring it survived
    deflates it; it simply did not happen."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    rw = _Rewrite(m)
    tree = rw.visit(tree)
    if not rw.done:
        return None
    ast.fix_missing_locations(tree)
    try:
        return ast.unparse(tree)
    except (AttributeError, ValueError):
        return None            # ast.unparse is 3.9+; below that, no mutants


# --------------------------------------------------------------------------
# coverage
# --------------------------------------------------------------------------

def covered_lines(root, cmd):
    """{file: {lines}} the test suite actually executes, or None.

    Two routes, in this order. `coverage` if the *subject* has it installed,
    because it is the same measurement much faster -- that is using what the
    subject has, not depending on it. Otherwise `tracer.py`, which is
    `sys.settrace` and therefore always available.

    None when neither can answer, and the caller must then say the restriction
    was dropped rather than quietly mutating uncovered lines. That is not a
    formality: measured on `tenacity` with coverage unavailable, every one of
    the five survivors was in `doc/source/conf.py`, a Sphinx config no test
    executes and none should."""
    probe = sh([sys.executable, "-c", "import coverage"], root, 60)
    if probe.returncode == 0:
        sh([sys.executable, "-m", "coverage", "run", "--source=."] + cmd,
           root, TEST_TIMEOUT)
        rep = sh([sys.executable, "-m", "coverage", "json", "-o", "-"],
                 root, 120)
        if rep.returncode == 0:
            try:
                data = json.loads(rep.stdout)
            except ValueError:
                data = None
            if data and data.get("files"):
                return {f: set(v.get("executed_lines") or [])
                        for f, v in data["files"].items()}

    # The stdlib route takes `python -m <module>` or `python <script.py>`.
    if len(cmd) < 2:
        return None
    rest = cmd[2:] if cmd[1] == "-m" else cmd[1:]
    if not rest:
        return None
    tmp = tempfile.mkdtemp(prefix="assess-trace-")
    try:
        out_json = os.path.join(tmp, "covered.json")
        sh([sys.executable, os.path.join(HERE, "tracer.py"), root, out_json]
           + rest, root, TEST_TIMEOUT * 4)
        if not os.path.exists(out_json):
            return None
        with open(out_json, encoding="utf-8") as fh:
            data = json.load(fh)
        return {k: set(v) for k, v in data.items()} or None
    except (OSError, ValueError):
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

def run_one(root, rel, mutated, cmd, backup, budget=TEST_TIMEOUT):
    full = os.path.join(root, rel)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(mutated)
    try:
        out = sh(cmd, root, budget)
    finally:
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(backup)
    tail = (out.stdout or out.stderr).strip().splitlines()
    detail = tail[-1][:160] if tail else f"exit {out.returncode}"
    if out.returncode == 124:
        # Its own verdict. A mutant that makes the suite hang has changed
        # behaviour observably, so it is not a survivor -- but no test
        # *asserted* anything either, so calling it killed credits the suite
        # with a catch it did not make. Measured on `tenacity`, a retry
        # library: flipping a comparison in a backoff loop ran for 166 seconds
        # against a 2.8 second baseline before anything stopped it.
        return "timeout", f"the suite did not finish in {budget}s"
    if out.returncode == 0:
        return "survived", detail
    # A suite that could not load is not a suite that caught something.
    low = (out.stdout + out.stderr).lower()
    # `ModuleNotFoundError` exits 1 and contains no "importerror", so a suite
    # that could not import came back scored as a **kill** -- the exact
    # inflation this classification exists to prevent, and it survived until a
    # case checked the verdict rather than the rendering.
    if out.returncode in (2, 3, 4, 5, 124, 127) or any(
            k in low for k in (
                "error while loading", "importerror", "modulenotfounderror",
                "no tests ran", "internalerror", "errors during collection",
                "syntaxerror", "indentationerror", "unable to import")):
        return "broken", detail
    return "killed", detail


def assess(root, limit=30, files=None, work=None, command=None):
    """`command` overrides the ecosystem table's guess.

    The table is a fast path that knows a handful of conventions, and a
    repository it has never seen will not match one of them -- measured: of
    five real Python repositories cloned to test this, the table produced a
    green suite for one. So a caller who has read the repository, agent or
    person, can say how its tests run, and the table is only the default."""
    eco, cmd = find(root)
    if command:
        cmd = command if isinstance(command, list) else command.split()
        eco = eco or type("Given", (), {"name": "given", "tool": None})()
    if cmd is None:
        return None, ("cannot judge: no runnable test command"
                      + (f" ({eco.name} needs {eco.tool})" if eco else ""))
    if not hasattr(ast, "unparse"):
        return None, "cannot judge: ast.unparse needs Python 3.9 or newer"

    out = subprocess.run(["git", "-c", "core.quotePath=false", "ls-files",
                          "*.py"], cwd=root, capture_output=True, text=True)
    if out.returncode != 0:
        return None, "cannot judge: not a git repository"
    sources = [p for p in out.stdout.split()
               if "test" not in p.lower() and (files is None or p in files)]
    if not sources:
        return None, "cannot judge: no non-test Python files"

    # The baseline is run three times, not once, because a mutant is scored
    # killed whenever the suite goes red -- for any reason, including its own
    # flakiness. Measured on `tenacity`, whose timing-sensitive retry tests
    # fail roughly one run in three under load: a single green baseline says
    # nothing about whether the reds that follow are the mutants' doing.
    #
    # The paper does not discuss flaky tests. At Google's scale a flaky suite
    # is somebody else's problem before it reaches mutation testing; on a
    # repository handed to us it is the common case, and a kill count taken
    # over a flaky suite is inflated by an unknown amount.
    greens, last, spent = 0, None, []
    for _ in range(3):
        t = time.monotonic()
        last = sh(cmd, root, TEST_TIMEOUT)
        spent.append(time.monotonic() - t)
        greens += 1 if last.returncode == 0 else 0
    if greens == 0:
        tail = (last.stdout or last.stderr).strip().splitlines()
        return None, ("cannot judge: the suite is not green before any mutant "
                      + (tail[-1][:120] if tail else ""))
    flaky = greens < 3
    # Every mutant gets a budget derived from the green suite, not a fixed
    # ceiling. A suite that runs in 2.8 seconds and has not finished in 30 has
    # been changed observably; waiting the full five minutes for it measures
    # nothing and costs the run.
    budget = max(20, int(8 * min(spent)) + 5)

    covered = covered_lines(root, cmd)
    mutants, dropped, srcs = mutate_mod.generate(
        root, sources, covered if covered else None, "arid")
    if not mutants:
        return None, "cannot judge: no mutable, covered, non-arid line"

    # Round-robin by file, not the first `limit` in walk order. Taking the
    # prefix put all 40 of tenacity's mutants in `tenacity/__init__.py` and
    # measured one file while reporting on a repository.
    by_file = {}
    for m in mutants:
        by_file.setdefault(m.path, []).append(m)
    spread, queues = [], list(by_file.values())
    while len(spread) < limit and any(queues):
        for q_ in queues:
            if q_ and len(spread) < limit:
                spread.append(q_.pop(0))
    mutants = spread
    rows, t0 = [], time.monotonic()
    for m in mutants:
        src = srcs.get(m.path)
        if src is None:
            continue
        mutated = apply(src, m)
        if mutated is None:
            m.verdict, m.detail = "unplaceable", "the mutation could not be applied"
        else:
            m.verdict, m.detail = run_one(root, m.path, mutated, cmd, src,
                                          budget)
        rows.append(m.as_dict())

    counted = [r for r in rows if r["verdict"] in ("killed", "survived")]
    survived = [r for r in counted if r["verdict"] == "survived"]
    return {
        "ecosystem": eco.name, "command": " ".join(cmd),
        "coverage": (f"measured — {sum(len(v) for v in covered.values())} "
                     f"line(s) executed across {len(covered)} file(s)")
                    if covered else
                    "NOT available — the covered-line restriction was "
                    "dropped, so survivors below include lines no test "
                    "executes and the figure is not comparable to the paper's",
        "generated": len(mutants), "suppressed": len(dropped),
        "flaky": flaky,
        "rows": rows,
        "killed": len(counted) - len(survived),
        "survived": len(survived),
        "broken": len([r for r in rows if r["verdict"] == "broken"]),
        "timeout": len([r for r in rows if r["verdict"] == "timeout"]),
        "budget_seconds": budget,
        "unplaceable": len([r for r in rows if r["verdict"] == "unplaceable"]),
        "survivability": (len(survived) / len(counted)) if counted else None,
        "seconds": round(time.monotonic() - t0, 1),
    }, ""


def render(r):
    lines = ["", f"  {r['generated']} mutant(s) run against `{r['command']}` "
                 f"in {r['seconds']}s", f"  coverage: {r['coverage']}", ""]
    if r.get("flaky"):
        lines.append("  !! the suite is FLAKY — it was not green on all three")
        lines.append("     baseline runs. Every figure below is an upper bound")
        lines.append("     on kills: a mutant is scored killed whenever the")
        lines.append("     suite goes red, including when it would have anyway.")
        lines.append("")
    lines.append(f"  killed      {r['killed']}")
    lines.append(f"  survived    {r['survived']}")
    if r["broken"]:
        lines.append(f"  broken      {r['broken']}   (the suite could not "
                     f"load — NOT counted as killed)")
    if r.get("timeout"):
        lines.append(f"  timeout     {r['timeout']}   (the suite hung past "
                     f"{r.get('budget_seconds')}s — behaviour changed, but no "
                     f"test asserted it)")
    if r["unplaceable"]:
        lines.append(f"  unplaceable {r['unplaceable']}")
    if r["survivability"] is not None:
        lines.append("")
        lines.append(f"  survivability {100 * r['survivability']:.1f}%   "
                     f"(the paper reports 13.2% for Python, 12.5% overall)")
    lines.append("")
    for row in r["rows"]:
        if row["verdict"] == "survived":
            lines.append(f"   !! {row['path']}:{row['line']}  {row['operator']}"
                         f"  {row['before']} -> {row['after']}")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--test-command", default="",
                    help="how this repository's tests run, when the ecosystem "
                         "table cannot work it out (it often cannot)")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    r, why = assess(root, a.limit, command=a.test_command or None)
    if r is None:
        print(why, file=sys.stderr)
        return 2
    print(render(r))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=2, ensure_ascii=False)
        print(f"  written to {a.json}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
