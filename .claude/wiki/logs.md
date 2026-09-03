# Evolution log

One entry per `/learn` run, appended by the maintainer and never edited: which
sessions were read, which patterns were created or grew, what was proposed.
Newest at the bottom.

## 2026-09-03

Read 17 sessions, 2026-08-28 .. 2026-09-03. First run: the wiki was empty.

Created:
- `outbound-action-piped-into-another-command` — 42 hits, shipped, still 20/42
  reproduce against today's guard.
- `waiting-for-a-job-run-as-a-foreground-loop` — 21 hits across 4 sessions,
  open, no guard yet.
- `computed-delete-guard-blocks-a-just-assigned-variable` — 4 hits in one
  session, open, a gap in an existing guard.

Grown: none.

Chosen not to record:
- `no_destructive_restore.py` refusals (11x, 2 sessions) — mostly
  guard-development dogfooding from before its `--ours`/`--theirs` fix
  landed; the 3 that still fire today are the guard's own documented
  quote-blindness tradeoff or correct catches.
- 4 of the 8 `no_computed_delete.py` refusals — a heredoc/newline-crossing
  shape already fixed mid-run; replaying them no longer reproduces.
- `no_protected_branch_push.py` refusals (2x, one session) — below the bar.
- classifier auto-mode denials (5x) — five unrelated actions (a server bound
  to 0.0.0.0, a force-push, a branch-protection edit, a read), no shared
  trigger.
- WebFetch "Socket is closed" (5x, one session) — network flakiness, not a
  repository mistake.
- Bash exit 1 / exit 2 / exit 128 (82x / 11x / 7x) — only the exit code was
  captured, not the error text, and the commands underneath are unrelated.
- Write "File has been modified since read" (2x) — the tool's own guard
  working; too thin to name a shared cause.
