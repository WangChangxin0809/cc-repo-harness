# Tech debt

- **Covers**: things found in passing that are real, are not being fixed now,
  and would otherwise be forgotten. Each entry says what reading revealed it and
  what it would touch.
- **Does not cover**: work in flight (that is a plan folder), or anything with a
  decision behind it (that is a decision record).

Permanent, and empty is a legitimate state. Nothing found while doing something
else gets fixed inline — a batch that grows while you work is a batch that never
lands.

## Open

Nothing open.

Two entries were closed rather than carried, and both are worth naming because
the closing is the interesting part:

- **`on_stop.py` had no test of any kind.** Now five cases in
  `scripts/context/selftest.py`, each watched failing against a planted defect.
  The two that mattered were invisible by construction: it **fails open**, which
  is the inverse of every other check here, and it short-circuits on
  `stop_hook_active`. A broken fail-open traps the session; a broken
  short-circuit makes it unstoppable. Neither shows up in normal use.
- **The context budget gate counted one file out of four.** It now sums
  `CLAUDE.md`, `.claude/CLAUDE.md`, and every `.claude/rules/*.md` without
  `paths:` — all of which load at launch — and stops charging for HTML comments,
  which are stripped before injection. Before that, `.claude/rules/` was a
  complete bypass, and a repository using the documented `.claude/CLAUDE.md`
  layout returned "cannot judge" while carrying hundreds of always-on lines.
