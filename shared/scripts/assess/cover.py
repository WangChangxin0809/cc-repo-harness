#!/usr/bin/env python3
"""Statement, branch and MC/DC coverage — the three criteria, one pass.

    python3 assess/cover.py --root . --test-command "pytest -q"

Exit codes:
    0 = coverage was measured    2 = cannot judge (no command, or the
                                     instrumented suite would not run)

## Why coverage is here at all, given that it predicts almost nothing

The correlation between coverage and a suite's ability to find real bugs is
weak once you are looking at one project's one suite (Zhao, Zhou & Cohen 2026
put it at r <= 0.481 in the pooled view, and their strong figures are all
*between* generators, n=13). So a high number here says very little.

The inference runs one way, and in that direction it is not a correlation at
all -- it is a guarantee:

    a line no test executes cannot be caught by the `local-suite` rung,
    ever, for any defect

That is why coverage is reported as **what this measurement cannot see**
rather than as a score. It is the denominator of dimension 2: the replay only
reaches lines the repository's own history put a bug in, and mutation only
touches lines the suite executes. Coverage is the part of the repository both
of them are silent about, and silence that is not stated reads as a pass.

## The three criteria, and what each one's absence proves

* **Statement** -- this line never ran. Nothing tests it. The coarsest and
  the hardest to argue with; a file with zero executed lines is a finding on
  its own.
* **Branch** -- this decision was only ever taken one way. Classically: every
  error path in the file, never entered. A file can be 100% statement-covered
  and have no error handling exercised at all.
* **MC/DC** -- this condition never independently decided the outcome. In
  `if a and b`, if `b` is true in every test that reaches it, then `b` is not
  being tested: you could delete it and no test would notice. That is exactly
  a mutant we would generate, found without running the suite once per mutant.

The three are nested in strength -- MC/DC implies branch implies statement --
which is why they are reported together and why the weakest one is reported
first.

## How MC/DC is measured here, precisely

`sys.settrace` gives line events and nothing about the value of an individual
condition, so it cannot answer this. What can is the thing this directory
already does for mutation: rewrite the AST.

Every decision -- `if`, `while`, a ternary, a comprehension's `if`, and
deliberately not `assert` (see `decisions` for why) -- is found, its boolean
tree is walked to its atomic leaves, and each leaf is wrapped in a recorder
that returns the value unchanged. Short-circuiting is
preserved exactly, because a wrapped operand is still only evaluated when
Python reaches it -- and a condition that was **not** evaluated is recorded as
absent, never as False. Getting that wrong is the classic way to report MC/DC
that never happened.

The variant computed is the one short-circuit languages have to use. Two
observed evaluations of a decision are an *independence pair* for condition c
when:

    1. c was evaluated in both, with different values
    2. the decision's outcome differs between them
    3. every other condition evaluated in **both** has the same value

Conditions that short-circuited away in one of the two are treated as masked
rather than as disagreements. This is masking MC/DC over and/or trees, not
unique-cause MC/DC; unique-cause is usually unreachable in a language that
short-circuits, and claiming it would be claiming a stricter result than was
measured. A decision with a single condition satisfies MC/DC exactly when both
its outcomes were seen, which is branch coverage -- as the standard has it.

## What is not measured

Path coverage. The count is exponential in the number of decisions and the
denominator would be meaningless, which is the same reason no standard asks
for it.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

RECORDER = "_assess_cov"
TIMEOUT = 900


# --------------------------------------------------------------------------
# what counts as a decision, and what its conditions are
# --------------------------------------------------------------------------

def leaves(node):
    """The atomic conditions of a boolean expression.

    `and`/`or` are structure; `not` is structure over one operand. Everything
    else is a leaf, including a chained comparison -- `a < b < c` is one
    condition, not two, because it has one truth value."""
    if isinstance(node, ast.BoolOp):
        out = []
        for v in node.values:
            out += leaves(v)
        return out
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return leaves(node.operand)
    return [node]


def decisions(tree):
    """(node, test-attribute-holder) for every decision in the module.

    A decision is a boolean expression that *controls* something: a branch, a
    loop, a ternary, a comprehension filter. A boolean assigned to a variable
    is not a decision -- nothing has branched on it yet, and counting it would
    inflate the denominator with expressions no standard asks about.

    **`assert` is deliberately not a decision.** An assertion that has gone
    both ways is a test suite that failed, so in any repository whose suite is
    green every assertion is one-way by construction. Counting them would
    report every correct assertion in the repository as an uncovered branch,
    which is a denominator made entirely of noise -- and the noisier the
    repository's assertions, the worse it would score for having them."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While, ast.IfExp)):
            found.append((node, "test"))
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp,
                               ast.GeneratorExp)):
            for gen in node.generators:
                for i in range(len(gen.ifs)):
                    found.append((gen, ("ifs", i)))
    return found


# --------------------------------------------------------------------------
# instrumenting
# --------------------------------------------------------------------------

class Instrument(ast.NodeTransformer):
    """Wrap every atomic condition, and every decision, in a recorder call.

    The wrapper returns its argument unchanged and is placed *inside* the
    boolean tree, so `a and b` still does not evaluate `b` when `a` is false.
    That is the property the whole measurement rests on: an unevaluated
    condition must be recorded as absent, and it can only be absent if it was
    genuinely never reached."""

    def __init__(self, rel):
        self.rel = rel
        self.decisions = {}      # did -> {"line": n, "conditions": {cid: text}}
        self._next = 0

    def _id(self):
        self._next += 1
        return f"{self.rel}:{self._next}"

    def _wrap_conditions(self, node, did, table):
        if isinstance(node, ast.BoolOp):
            node.values = [self._wrap_conditions(v, did, table)
                           for v in node.values]
            return node
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            node.operand = self._wrap_conditions(node.operand, did, table)
            return node
        cid = len(table)
        try:
            text = ast.unparse(node)[:80]
        except Exception:                                  # noqa: BLE001
            text = "<condition>"
        table[cid] = text
        return ast.Call(
            func=ast.Name(id="_ASSESS_C", ctx=ast.Load()),
            args=[ast.Constant(value=did), ast.Constant(value=cid), node],
            keywords=[])

    def instrument(self, test, line):
        did = self._id()
        table = {}
        wrapped = self._wrap_conditions(test, did, table)
        self.decisions[did] = {"line": line, "conditions": table,
                               "count": len(table)}
        return ast.Call(
            func=ast.Name(id="_ASSESS_D", ctx=ast.Load()),
            args=[ast.Constant(value=did), wrapped], keywords=[])


def rewrite(rel, source):
    """(instrumented source, decision table) or (None, why)."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return None, f"could not parse: {exc}"
    inst = Instrument(rel)
    for node, where in decisions(tree):
        if isinstance(where, tuple):
            _k, i = where
            node.ifs[i] = inst.instrument(node.ifs[i],
                                          getattr(node.ifs[i], "lineno", 0))
        else:
            test = getattr(node, where)
            if test is None:
                continue
            setattr(node, where,
                    inst.instrument(test, getattr(node, "lineno", 0)))
    if not inst.decisions:
        return None, "no decisions in this file"

    # The import goes after the docstring and after any __future__ import,
    # because both are required to come first and a file that stops compiling
    # is a file we have removed from the measurement rather than measured.
    at = 0
    body = tree.body
    if body and isinstance(body[0], ast.Expr) and isinstance(
            body[0].value, ast.Constant) and isinstance(
            body[0].value.value, str):
        at = 1
    while at < len(body) and isinstance(body[at], ast.ImportFrom) and \
            body[at].module == "__future__":
        at += 1
    imp = ast.ImportFrom(
        module=RECORDER,
        names=[ast.alias(name="C", asname="_ASSESS_C"),
               ast.alias(name="D", asname="_ASSESS_D")],
        level=0)
    tree.body.insert(at, imp)
    ast.fix_missing_locations(tree)
    try:
        return ast.unparse(tree), inst.decisions
    except Exception as exc:                                # noqa: BLE001
        return None, f"could not unparse: {exc}"


# --------------------------------------------------------------------------
# the recorder that gets written into the subject
# --------------------------------------------------------------------------

RECORDER_SOURCE = '''\
"""Written by assess/cover.py. Records condition and decision outcomes.

Removed when the run finishes. If you are reading this in a repository, an
assessment was interrupted -- deleting it is safe and correct.
"""
import atexit
import json
import os

_buffers = {}
_seen = {}


def C(did, cid, value):
    """One atomic condition evaluated. Returns the value untouched."""
    _buffers.setdefault(did, {})[cid] = bool(value)
    return value


def D(did, value):
    """One decision finished. The conditions in its buffer are the ones that
    were actually evaluated; the rest short-circuited and are absent, which is
    not the same as false."""
    got = _buffers.pop(did, {})
    out = bool(value)
    key = (tuple(sorted(got.items())), out)
    _seen.setdefault(did, set()).add(key)
    return value


@atexit.register
def _dump():
    target = os.environ.get("ASSESS_COV_OUT")
    if not target:
        return
    data = {did: [[list(map(list, conds)), out] for conds, out in obs]
            for did, obs in _seen.items()}
    try:
        with open(f"{target}.{os.getpid()}", "w") as fh:
            json.dump(data, fh)
    except OSError:
        pass
'''


# --------------------------------------------------------------------------
# the analysis
# --------------------------------------------------------------------------

def independence(observations):
    """Which condition ids have an independence pair, masking MC/DC.

    Two observations are a pair for `c` when c is evaluated in both with
    different values, the outcomes differ, and every OTHER condition evaluated
    in both agrees. A condition that short-circuited away in one of the two is
    masked, not a disagreement -- that is the difference between masking and
    unique-cause MC/DC, and in a language with `and`/`or` the strict form is
    usually unreachable."""
    obs = [({int(k): bool(v) for k, v in dict(conds).items()}, bool(out))
           for conds, out in observations]
    shown = set()
    for i, (ci, oi) in enumerate(obs):
        for cj, oj in obs[i + 1:]:
            if oi == oj:
                continue
            both = set(ci) & set(cj)
            differ = [c for c in both if ci[c] != cj[c]]
            if len(differ) == 1:
                shown.add(differ[0])
    return shown


def analyse(table, seen):
    """Per-decision: was it taken both ways, and is each condition shown
    independent?"""
    rows = []
    for did, meta in table.items():
        obs = seen.get(did, [])
        outcomes = {bool(o) for _c, o in obs}
        total = meta["count"]
        if not obs:
            rows.append({"id": did, "line": meta["line"], "conditions": total,
                         "reached": False, "both_ways": False,
                         "independent": 0, "texts": meta["conditions"]})
            continue
        indep = independence(obs)
        if total == 1:
            # The standard's own degenerate case: with one condition, MC/DC is
            # satisfied exactly when both outcomes were seen.
            indep = {0} if len(outcomes) == 2 else set()
        rows.append({"id": did, "line": meta["line"], "conditions": total,
                     "reached": True, "both_ways": len(outcomes) == 2,
                     "independent": len(indep & set(range(total))),
                     "texts": meta["conditions"]})
    return rows


def summarise(rows, statements=None):
    dec = len(rows)
    reached = [r for r in rows if r["reached"]]
    both = [r for r in reached if r["both_ways"]]
    conds = sum(r["conditions"] for r in rows)
    indep = sum(r["independent"] for r in rows)
    compound = [r for r in rows if r["conditions"] > 1]
    return {
        "decisions": dec,
        "decisions_reached": len(reached),
        "branch_covered": len(both),
        "branch": (len(both) / dec) if dec else None,
        "conditions": conds,
        "conditions_independent": indep,
        "mcdc": (indep / conds) if conds else None,
        "compound_decisions": len(compound),
        "statements": statements,
        "unreached": [r for r in rows if not r["reached"]][:40],
        "one_way": [r for r in reached if not r["both_ways"]][:40],
        "not_independent": [
            {**r, "missing": r["conditions"] - r["independent"]}
            for r in reached if r["independent"] < r["conditions"]][:40],
    }


# --------------------------------------------------------------------------
# statements
# --------------------------------------------------------------------------

def executable_lines(source):
    """The lines a statement starts on.

    An approximation of what a coverage tool calls an executable line, using
    only `ast`. Docstrings are excluded because executing one is not evidence
    of anything, and a file of constants would otherwise report full coverage
    for having been imported."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    out, docstrings = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            first = (node.body or [None])[0]
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docstrings.add(getattr(first, "lineno", -1))
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt):
            line = getattr(node, "lineno", None)
            if line and line not in docstrings:
                out.add(line)
    return out


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

def sources(root, files=None):
    out = subprocess.run(["git", "-c", "core.quotePath=false", "ls-files",
                          "*.py"], cwd=root, capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return [p for p in out.stdout.split()
            if "test" not in p.lower() and (files is None or p in files)]


def sh(cmd, cwd, timeout, env=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout,
                          env={**os.environ, **(env or {})})


def assess(root, command, work, files=None):
    """Instrument, run the suite once, and read the three criteria off it.

    Everything is written into `root` and taken back out again, so `root` must
    already be a clone -- `run_mutants` and `catch` both make one and this is
    called with theirs. An instrument that leaves anything behind in the
    repository it was pointed at has changed the thing it was measuring."""
    sys.path.insert(0, HERE)
    from ecosystems import find                            # noqa: PLC0415
    _eco, cmd = find(root)
    if command:
        cmd = command if isinstance(command, list) else command.split()
    if cmd is None:
        return None, ("cannot judge: no runnable test command — pass "
                      "--test-command")
    if not hasattr(ast, "unparse"):
        return None, "cannot judge: ast.unparse needs Python 3.9 or newer"
    paths = sources(root, files)
    if not paths:
        return None, "cannot judge: not a git repository, or no source files"

    os.makedirs(work, exist_ok=True)
    caches = {os.path.join(dirpath, "__pycache__")
              for dirpath, dirnames, _f in os.walk(root)
              if "__pycache__" in dirnames}
    base = sh(cmd, root, TIMEOUT)
    if base.returncode != 0:
        tail = (base.stdout or base.stderr).strip().splitlines()
        return None, ("cannot judge: the suite is not green before "
                      "instrumenting " + (tail[-1][:120] if tail else ""))

    originals, table, skipped = {}, {}, []
    for rel in paths:
        full = os.path.join(root, rel)
        try:
            with open(full, encoding="utf-8") as fh:
                src = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        originals[rel] = src
        done, meta = rewrite(rel, src)
        if done is None:
            skipped.append((rel, meta))
            continue
        table.update(meta)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(done)
    if not table:
        _restore(root, originals, caches)
        return None, "cannot judge: no decisions found in any source file"

    out_path = os.path.join(work, "cov")
    recorder = os.path.join(root, RECORDER + ".py")
    try:
        with open(recorder, "w", encoding="utf-8") as fh:
            fh.write(RECORDER_SOURCE)
        run = sh(cmd, root, TIMEOUT,
                 {"ASSESS_COV_OUT": out_path,
                  "PYTHONPATH": root + os.pathsep
                  + os.environ.get("PYTHONPATH", "")})
        instrumented_green = run.returncode == 0
        seen = _collect(work)
    finally:
        _restore(root, originals, caches)
        if os.path.exists(recorder):
            os.remove(recorder)
        # And the recorder's own bytecode, which is the one piece of our
        # scaffolding that `_restore` cannot know about: it was never one of
        # the subject's files.
        cache = os.path.join(root, "__pycache__")
        if os.path.isdir(cache):
            for name in os.listdir(cache):
                if name.startswith(RECORDER + ".") and name.endswith(".pyc"):
                    try:
                        os.remove(os.path.join(cache, name))
                    except OSError:
                        pass
            if cache not in caches:
                try:
                    if not os.listdir(cache):
                        os.rmdir(cache)
                except OSError:
                    pass

    if not seen:
        tail = (run.stdout or run.stderr).strip().splitlines()
        return None, ("cannot judge: the instrumented suite recorded nothing "
                      + (tail[-1][:120] if tail else ""))

    rows = analyse(table, seen)
    r = summarise(rows)
    r["command"] = " ".join(cmd)
    r["files_instrumented"] = len(originals) - len(skipped)
    r["files_skipped"] = len(skipped)
    # Reported, never swallowed. Instrumentation that changes what the suite
    # does has measured a different program, and the reader has to be able to
    # discount the branch and MC/DC figures because of it.
    r["instrumented_green"] = instrumented_green

    # After the restore, and it runs the suite once more on the untouched
    # tree -- which regenerates exactly the bytecode the restore just removed.
    # So the sweep happens here, at the true end, not in the finally above.
    stmt = _statements(root, originals, cmd)
    if stmt:
        r["statements"] = stmt
    _sweep(root, originals, caches)
    return r, ""


def _sweep(root, originals, caches):
    """Remove bytecode for the files we touched, and any __pycache__ we made.

    A directory that was already there before we started is the subject's and
    stays, empty or not."""
    dirs = {os.path.join(root, "__pycache__")}
    for rel in originals:
        dirs.add(os.path.join(os.path.dirname(os.path.join(root, rel)),
                              "__pycache__"))
    stems = {os.path.basename(rel)[:-3] for rel in originals} | {RECORDER}
    for cache in dirs:
        if not os.path.isdir(cache):
            continue
        for name in os.listdir(cache):
            if name.endswith(".pyc") and name.split(".", 1)[0] in stems:
                try:
                    os.remove(os.path.join(cache, name))
                except OSError:
                    pass
        if cache not in caches:
            try:
                if not os.listdir(cache):
                    os.rmdir(cache)
            except OSError:
                pass


def _restore(root, originals, caches=()):
    """Put every file back, and take our bytecode with us.

    Restoring the source is not enough. Running the instrumented tree leaves
    `__pycache__/<name>.cpython-*.pyc` compiled from the *instrumented* source,
    and a `.pyc` is the thing Python reaches for first. It revalidates against
    size and mtime so it would almost certainly be regenerated -- almost is not
    a property an instrument should rely on when the alternative is deleting a
    file we created."""
    for rel, src in originals.items():
        full = os.path.join(root, rel)
        try:
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(src)
        except OSError:
            pass
        cache = os.path.join(os.path.dirname(full), "__pycache__")
        stem = os.path.basename(full)[:-3]
        if not os.path.isdir(cache):
            continue
        for name in os.listdir(cache):
            if name.startswith(stem + ".") and name.endswith(".pyc"):
                try:
                    os.remove(os.path.join(cache, name))
                except OSError:
                    pass
        # Only ours, and only if we made it: a __pycache__ that was already
        # there is the subject's and stays.
        if cache not in caches:
            try:
                if not os.listdir(cache):
                    os.rmdir(cache)
            except OSError:
                pass


def _collect(work):
    """Merge every process's dump. A suite that forks writes one file each."""
    seen = {}
    for name in sorted(os.listdir(work)):
        if not name.startswith("cov."):
            continue
        try:
            with open(os.path.join(work, name), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        for did, obs in data.items():
            got = seen.setdefault(did, [])
            for conds, out in obs:
                got.append(([tuple(c) for c in conds], out))
    return seen


def _statements(root, originals, cmd):
    """Statement coverage, from the existing covered-line machinery.

    Deliberately measured on the UNinstrumented tree: the instrumented copy
    has different line numbers, and a statement figure taken off it would be
    about a program that does not exist."""
    try:
        import run_mutants as run_mod                      # noqa: PLC0415
        covered = run_mod.covered_lines(root, cmd)
    except Exception:                                      # noqa: BLE001
        return None
    if not covered:
        return None
    total, hit, dark = 0, 0, []
    for rel, src in originals.items():
        lines = executable_lines(src)
        if not lines:
            continue
        got = lines & set(covered.get(rel, ()) or ())
        total += len(lines)
        hit += len(got)
        if not got:
            dark.append({"path": rel, "lines": len(lines)})
    if not total:
        return None
    dark.sort(key=lambda d: -d["lines"])
    return {"executable": total, "executed": hit, "rate": hit / total,
            "files_with_none": dark[:40],
            "files_with_none_total": len(dark)}


def render(r):
    out = ["", f"  measured under `{r['command']}`", ""]
    if not r.get("instrumented_green"):
        out += ["  !! the suite was GREEN before instrumenting and is not "
                "green after.",
                "     Instrumentation changed what the program does, so the "
                "branch and",
                "     MC/DC figures below are about a program that is not "
                "quite this one.", ""]
    st = r.get("statements")
    if st:
        out.append(f"  statement  {100 * st['rate']:.1f}%   "
                   f"{st['executable'] - st['executed']} of "
                   f"{st['executable']} executable line(s) never run")
        if st["files_with_none_total"]:
            out.append(f"             {st['files_with_none_total']} file(s) "
                       f"have no executed line at all:")
            for d in st["files_with_none"][:5]:
                out.append(f"               {d['path']}  ({d['lines']} lines)")
    else:
        out.append("  statement  NOT measured — no coverage tool and the "
                   "tracer could not run")
    if r["branch"] is not None:
        # Never reached and reached-but-one-way are different findings and the
        # fix for them is different: the first needs a test that gets there at
        # all, the second needs a test that gets there with the other answer.
        # Reporting one number for both leaves the reader with neither.
        cold = r["decisions"] - r["decisions_reached"]
        oneway = r["decisions_reached"] - r["branch_covered"]
        out.append(f"  branch     {100 * r['branch']:.1f}%   "
                   f"of {r['decisions']} decision(s): {cold} never reached, "
                   f"{oneway} reached but only ever went one way")
    if r["mcdc"] is not None:
        out.append(f"  MC/DC      {100 * r['mcdc']:.1f}%   "
                   f"{r['conditions'] - r['conditions_independent']} of "
                   f"{r['conditions']} condition(s) never independently "
                   f"decided the outcome")
        out.append(f"             ({r['compound_decisions']} decision(s) have "
                   f"more than one condition — where that count is small, "
                   f"MC/DC is nearly branch coverage)")
    out.append("")
    if r["unreached"]:
        out.append("  decisions no test ever reaches:")
        for d in r["unreached"][:6]:
            out.append(f"    {d['id'].rsplit(':', 1)[0]}:{d['line']}  "
                       + "; ".join(list(d["texts"].values())[:2]))
        out.append("")
    if r["one_way"]:
        out.append("  decisions reached, but only ever taken one way:")
        for d in r["one_way"][:6]:
            out.append(f"    {d['id'].rsplit(':', 1)[0]}:{d['line']}  "
                       + "; ".join(list(d["texts"].values())[:2]))
        out.append("")
    if r["not_independent"]:
        out.append("  conditions that never decided anything on their own:")
        for d in r["not_independent"][:6]:
            out.append(f"    {d['id'].rsplit(':', 1)[0]}:{d['line']}  "
                       f"{d['missing']} of {d['conditions']}  "
                       + "; ".join(list(d["texts"].values())[:2]))
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--test-command", default="")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    work = tempfile.mkdtemp(prefix="assess-cover-")
    r, why = assess(root, a.test_command or None, work)
    if r is None:
        print(why, file=sys.stderr)
        return 2
    print(render(r))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
