#!/usr/bin/env python3
"""Prepare the second pass over surviving mutants, and grade what comes back.

    python3 assess/judge.py --brief RUN.json          # what to ask
    python3 assess/judge.py --grade RUN.json --answers ANSWERS.json

Exit codes:
    0 = the brief was written, or the answers were graded
    1 = graded, and productivity came in under the bar
    2 = cannot judge (no run, no survivors)

## Why an agent, and what it is standing in for

The paper's definition of a good mutant is entirely operational:

    "Given Google's high accuracy and actionability requirements for surfacing
    code findings during code reviews, we rely on developer feedback as the
    best available measure for mutant productivity."

A mutant is **productive** if the person who wrote that line clicked
"Please fix". 66,798 such clicks, from more than 20,000 developers, over six
years. That is the denominator behind their 82%, and it is not something a
tool can reconstruct.

So the second pass asks an agent the same question that button asks, and the
page says who is answering. This is the honest position and it has two halves
that must both be stated:

* An agent that did not write the code is a **weaker judge** than one who did.
  The paper's own numbers are not a ceiling we should expect to reach.
* It is nonetheless the only judge available, and it is a far better one than
  the alternative on offer, which is nobody.

## One call, not one per mutant

Their §5.3 and the survivability figures put the median at 2 surviving mutants
per changelist and the 99th percentile at 43. All of them fit in one prompt.
Asking per mutant would multiply the cost by the count for no gain, and this
project's budget discipline is that agents are spent on judgement, once.

## The question is not "is this a bug"

It is the paper's, and the distinction is the whole of it:

    would a test written to kill this mutant be a test worth having?

Their own worked example is `new ArrayList(64)` -> `new ArrayList(16)`. You
*can* write a test that asserts the initial capacity. That test asserts the
implementation rather than the specification, and writing it makes the suite
worse. Killable and unproductive at the same time.

## What is recorded, and why it is worth recording

Every verdict is written back with the mutant's operator, its rule context and
the surrounding source. Google turned six years of these into a hundred
suppression rules; the format here is chosen so the same thing is possible
later, not because it is possible now.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# The bar this project has been asked to clear. The paper's Python figure.
BAR = 0.70
PAPER_PYTHON = 0.706
PAPER_ALL = 0.82


def enclosing(source, line, span=14):
    """The function a mutant sits in, so the judge sees why the line exists.

    A mutation shown alone is unjudgeable -- `> ` became `>=` says nothing
    without the loop around it. The enclosing function is the smallest unit
    that carries intent, which is the thing being judged."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", start)
            if start <= line <= end and (best is None or start > best.lineno):
                best = node
    lines = source.split("\n")
    if best is None:
        lo, hi = max(0, line - span // 2), min(len(lines), line + span // 2)
    else:
        lo = best.lineno - 1
        hi = min(len(lines), getattr(best, "end_lineno", best.lineno))
        if hi - lo > 60:                    # a long function: window the line
            lo, hi = max(lo, line - span), min(hi, line + span)
    out = []
    for i in range(lo, hi):
        mark = ">>" if i + 1 == line else "  "
        out.append(f"{mark} {i + 1:>5}  {lines[i]}")
    return "\n".join(out)


BRIEF = """\
# Second pass over surviving mutants

Each block below is a single-line change to code that **the test suite already
executes**, which the suite did not notice: every test still passed with the
change in place.

For each one, answer the question the mutation-testing literature actually
asks, which is not whether the change is a bug:

> Would a test written to catch this change be a test worth having?

Say **productive** when the answer is yes: the line encodes behaviour somebody
depends on, and a suite that cannot tell the difference has a real hole.

Say **unproductive** when the answer is no. The three shapes that matter:

1. **Equivalent** — the change cannot alter observable behaviour at all.
2. **Killable but not worth killing** — you could write a test that catches it,
   and that test would assert the implementation rather than the specification.
   The literature's own example: changing a pre-allocated capacity from 64 to
   16. A test asserting the initial capacity would catch it, and would make the
   suite worse, because it pins a decision nobody promised.
3. **Not this suite's job** — logging, metrics, debug output, configuration
   defaults, or anything whose correctness is not what these tests exist to
   establish.

Judge the mutation in front of you. Do not go looking for other problems in the
code, do not suggest refactors, and do not soften a verdict because the code is
otherwise good.

## Answer format

Write JSON to the path you were given, and nothing else:

```json
{"verdicts": [{"id": 0, "verdict": "productive", "why": "one sentence"},
              {"id": 1, "verdict": "unproductive", "why": "one sentence"}]}
```

One entry per block, `id` matching. `why` is one sentence and is the part a
person will read; "it is unproductive" is not a reason.

---

"""


def brief(run, root):
    """The whole prompt: the instructions above, then every survivor in place."""
    survivors = [r for r in run.get("rows", []) if r["verdict"] == "survived"]
    if not survivors:
        return None, "no surviving mutants — there is nothing to judge"
    parts, index = [BRIEF], []
    cache = {}
    for i, row in enumerate(survivors):
        path = row["path"]
        if path not in cache:
            try:
                with open(os.path.join(root, path), encoding="utf-8") as fh:
                    cache[path] = fh.read()
            except OSError:
                cache[path] = ""
        parts.append(
            f"## {i}. `{path}`:{row['line']} — {row['operator']}\n\n"
            f"The change: `{row['before']}` became `{row['after']}`\n\n"
            f"```python\n{enclosing(cache[path], row['line'])}\n```\n")
        index.append({"id": i, "path": path, "line": row["line"],
                      "operator": row["operator"], "before": row["before"],
                      "after": row["after"]})
    return {"prompt": "\n".join(parts), "index": index}, ""


def grade(run, answers):
    """Productivity, and the verdicts behind it. Never a bare percentage.

    An unanswered survivor is **not** counted either way. Treating silence as
    unproductive would let a judge raise the score by answering less, and
    treating it as productive would do the reverse; either way the number would
    stop being about the mutants."""
    survivors = [r for r in run.get("rows", []) if r["verdict"] == "survived"]
    got = {}
    for v in (answers.get("verdicts") or []):
        try:
            got[int(v["id"])] = v
        except (KeyError, TypeError, ValueError):
            continue
    rows, productive, judged = [], 0, 0
    for i, row in enumerate(survivors):
        v = got.get(i)
        verdict = (v or {}).get("verdict", "")
        verdict = verdict if verdict in ("productive", "unproductive") else ""
        if verdict:
            judged += 1
            productive += 1 if verdict == "productive" else 0
        rows.append({**row, "judged": verdict or "not answered",
                     "why": (v or {}).get("why", "")})
    rate = (productive / judged) if judged else None
    return {
        "survivors": len(survivors), "judged": judged,
        "unanswered": len(survivors) - judged,
        "productive": productive, "unproductive": judged - productive,
        "productivity": rate,
        "bar": BAR, "met": (rate is not None and rate >= BAR),
        "paper_python": PAPER_PYTHON, "paper_all": PAPER_ALL,
        "judge": "an agent that did not write this code — a weaker judge than "
                 "the paper's, whose 82% comes from 66,798 clicks by the "
                 "developers who wrote the lines",
        "rows": rows,
    }


def render(g):
    out = ["", f"  {g['judged']} of {g['survivors']} surviving mutant(s) judged"]
    if g["unanswered"]:
        out.append(f"  {g['unanswered']} unanswered — counted neither way")
    out.append("")
    if g["productivity"] is None:
        out.append("  productivity: COULD NOT JUDGE — nothing came back")
        return "\n".join(out + [""])
    out.append(f"  productive    {g['productive']}")
    out.append(f"  unproductive  {g['unproductive']}")
    out.append("")
    out.append(f"  productivity  {100 * g['productivity']:.1f}%   "
               f"{'MET' if g['met'] else 'MISSED'} the {100 * g['bar']:.0f}% bar")
    out.append(f"                the paper reports {100 * g['paper_python']:.1f}% "
               f"for Python, {100 * g['paper_all']:.0f}% overall")
    out.append(f"  judged by     {g['judge']}")
    out.append("")
    for r in g["rows"]:
        mark = {"productive": "!!", "unproductive": "· ",
                "not answered": "??"}.get(r["judged"], "??")
        out.append(f"  {mark} {r['path']}:{r['line']}  {r['operator']}  "
                   f"{r['before']} -> {r['after']}")
        if r["why"]:
            out.append(f"       {r['why'][:110]}")
    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief", default="", help="run JSON from run_mutants.py")
    ap.add_argument("--grade", default="", help="the same run JSON")
    ap.add_argument("--answers", default="", help="JSON the judge wrote")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    if a.brief:
        with open(a.brief, encoding="utf-8") as fh:
            run = json.load(fh)
        b, why = brief(run, root)
        if b is None:
            print(f"cannot judge: {why}", file=sys.stderr)
            return 2
        target = a.out or "mutant-brief.md"
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(b["prompt"])
        with open(target + ".index.json", "w", encoding="utf-8") as fh:
            json.dump(b["index"], fh, indent=2)
        print(f"  brief for {len(b['index'])} survivor(s) written to {target}")
        return 0

    if a.grade:
        with open(a.grade, encoding="utf-8") as fh:
            run = json.load(fh)
        if not a.answers:
            print("cannot judge: --grade needs --answers", file=sys.stderr)
            return 2
        with open(a.answers, encoding="utf-8") as fh:
            answers = json.load(fh)
        g = grade(run, answers)
        print(render(g))
        if a.out:
            with open(a.out, "w", encoding="utf-8") as fh:
                json.dump(g, fh, indent=2, ensure_ascii=False)
        return 0 if g["met"] else 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
