#!/usr/bin/env python3
"""Run a test suite and record every line of the subject it executed.

    python3 assess/tracer.py ROOT OUT.json pytest -q [args...]

Written because the covered-line restriction is not optional. The mutation
paper only mutates lines that are **changed and covered**: a mutant on an
uncovered line "would inevitably survive because the code is not tested",
which is a coverage finding, reported by coverage, at a fraction of the cost.

Measured, on `tenacity` with the restriction dropped: every one of the five
survivors was in `doc/source/conf.py`, a Sphinx config no test executes and
none should. Without coverage the survivor list is dominated by files that
were never under test, and the survivability figure stops being comparable to
anything.

`coverage` would be the obvious tool and `shared/` may not depend on it, so
this is `sys.settrace`, which is standard library. It is slower and it is
always available, which is the trade this directory makes everywhere.
"""

from __future__ import annotations

import json
import os
import runpy
import sys


def main():
    if len(sys.argv) < 4:
        print(__doc__, file=sys.stderr)
        return 2
    root = os.path.abspath(sys.argv[1])
    out_path = sys.argv[2]
    module = sys.argv[3]
    seen = {}

    def line_event(frame, event, arg):
        if event == "line":
            path = frame.f_code.co_filename
            if path.startswith(root) and "site-packages" not in path:
                seen.setdefault(os.path.relpath(path, root), set()).add(
                    frame.f_lineno)
        return line_event

    def call_event(frame, event, arg):
        # Returning the per-line tracer only for frames inside the subject
        # keeps the cost off every frame in pytest and the standard library,
        # which is the difference between a suite that finishes and one that
        # does not.
        if event != "call":
            return None
        path = frame.f_code.co_filename
        if not path.startswith(root) or "site-packages" in path:
            return None
        return line_event

    sys.argv = sys.argv[3:]
    sys.path.insert(0, root)
    sys.settrace(call_event)
    try:
        # Two spellings, because both are how real suites are invoked:
        # `python -m pytest ...` and `python path/to/selftest.py`. A tracer
        # that only knew the first could not measure a repository whose tests
        # are scripts, which is most repositories that predate pytest and some
        # that never adopted it.
        if module.endswith(".py") or os.path.sep in module:
            runpy.run_path(os.path.join(root, module)
                           if not os.path.isabs(module) else module,
                           run_name="__main__")
        else:
            runpy.run_module(module, run_name="__main__", alter_sys=True)
    except SystemExit:
        pass
    except Exception as exc:                                   # noqa: BLE001
        print(f"tracer: the suite raised {type(exc).__name__}: {exc}",
              file=sys.stderr)
    finally:
        sys.settrace(None)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({k: sorted(v) for k, v in seen.items()}, fh)
    return 0


if __name__ == "__main__":
    sys.exit(main())
