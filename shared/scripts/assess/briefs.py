#!/usr/bin/env python3
"""Every question one dimension of a run could not answer, written out as files.

    python3 assess/briefs.py --run RUN.json --dimension N --out DIR [--root .]

    0 = wrote the briefs (possibly none)     2 = cannot judge

## Why this exists

The instrument leaves questions behind. Each module that leaves one has its
own brief -- `observe.brief`, `permitted.brief`, `judge.brief`, `truth.brief`,
`conflict.brief` -- and each answer goes back through its own flag on
`factsheet.py`. That is right for the modules, and wrong for the agent that
has to answer them: it had to know five module names, where each brief was
kept in the JSON, and which flag its answer fed. Five places to be wrong, and
the flags are how the readings reach the page, so a reader that gets one
wrong has done its work and left no trace of it.

So one call, by dimension. `--dimension 1` writes what dimension 1 left
unanswered and nothing else; each file names the flag its answer feeds. The
reader is told the dimension and the directory and needs to know nothing
about the modules -> 0048

A dimension with nothing to answer writes nothing and says so. That is the
usual case for 3 and 5, and it is not a failure: those two are read, not
answered.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import conflict as conflict_mod    # noqa: E402
import judge as judge_mod          # noqa: E402
import observe as observe_mod      # noqa: E402
import permitted as permitted_mod  # noqa: E402
import truth as truth_mod          # noqa: E402

# (dimension, name, key in the run, the flag its answer feeds, how to write)
#
# The order inside a dimension is the order the reader meets them. Every
# entry passes one test: the answer changes a row on the page. A brief whose
# answer is only read by a person is not here; that is the reading, and the
# reading is `review.py --brief`.
BRIEFS = (
    ("1", "observe", "observe", "--observe-answers",
     lambda r, root: observe_mod.brief(r.get("observe"))),
    ("1", "permitted", "permitted", "--legitimate-actions",
     lambda r, root: permitted_mod.brief(r.get("permitted"))),
    ("2", "mutants", "mutants", "--mutant-answers",
     lambda r, root: _mutant_brief(r, root)),
    ("4", "truth", "truth", "--truth-answers",
     lambda r, root: truth_mod.brief(r.get("truth"))),
    ("4", "conflict", "conflict", "--conflict-answers",
     lambda r, root: conflict_mod.brief(r.get("conflict"))),
)


def _mutant_brief(r, root):
    m = r.get("mutants")
    if not m:
        return ""
    got, _why = judge_mod.brief(m, root)
    return (got or {}).get("prompt") or ""


def write(run, dimension, out, root):
    """Write one file per brief this dimension left; return what was written.

    Each entry: {"name", "path", "flag"}. The answer to `path` is what the
    caller passes after `flag` on the next `factsheet.py --from` run."""
    root = root or run.get("root") or "."
    written = []
    os.makedirs(out, exist_ok=True)
    for dim, name, _key, flag, make in BRIEFS:
        if dim != str(dimension):
            continue
        text = make(run, root)
        if not text or not str(text).strip():
            continue
        path = os.path.join(out, f"{name}.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(str(text))
            if not str(text).endswith("\n"):
                fh.write("\n")
        written.append({"name": name, "path": path, "flag": flag,
                        "answer": os.path.join(out, f"{name}.answers.json")})
    return written


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", required=True, help="factsheet.py --json output")
    ap.add_argument("--dimension", required=True, choices="12345")
    ap.add_argument("--out", required=True, help="directory to write into")
    ap.add_argument("--root", default="",
                    help="the repository, when the run's own root has moved")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        with open(a.run, encoding="utf-8") as fh:
            run = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"cannot judge: {a.run} is not a run: {exc}", file=sys.stderr)
        return 2
    if "probe" not in run:
        print(f"cannot judge: {a.run} is not factsheet.py --json output",
              file=sys.stderr)
        return 2
    written = write(run, a.dimension, os.path.abspath(a.out), a.root)
    if a.json:
        print(json.dumps(written, indent=1))
        return 0
    if not written:
        print(f"  dimension {a.dimension} left nothing to answer -- it is "
              f"read, not answered")
        return 0
    print(f"  dimension {a.dimension}: {len(written)} brief(s)")
    for w in written:
        print(f"    {w['path']}\n      answer -> {w['answer']}   "
              f"feeds {w['flag']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
