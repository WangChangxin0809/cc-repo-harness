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

- **`no_piped_outbound.py` reads the body of a heredoc as a command.** Writing
  a Python patch script whose *text* contains `git push ... | tail` is refused
  as a piped outbound action. It happened four times in one session while
  building the recurrence counter, and it is what the counter recorded first in
  this repository — its own guard's false positive, which is a fair test of the
  instrument and a real cost to whoever hits it.

  Found by: `_recurrence.py --report`, on the day it was written.
  Would touch: `shared/scripts/guards/no_piped_outbound.py`, plus cases in
  `guards/selftest.py` — the near-misses matter more than the hits here.

  Not fixed now because narrowing a guard is the change most likely to make it
  stop catching the thing it exists for, and the correct narrowing is not
  obvious: a heredoc body is not reliably distinguishable from a command by
  pattern-matching, which is the same limitation `dispatch.py` already documents
  about guards in general. The honest options are to strip `<<'EOF' ... EOF`
  regions before matching, or to accept it. Either needs a session that is
  about this rather than one that keeps tripping over it.

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
