# 0055 — A relative hook command is a hook that is not there

Date: 2026-09-02
Status: accepted

## Context

`aafdc0113` fixed every wired hook in this repository: `.claude/settings.json`
named its scripts as `python3 shared/scripts/guards/dispatch.py`, a path that
only resolves when the session's working directory happens to be the
repository root. A hook runs in whatever directory Claude Code is currently
in, and that changes on a `cd` and again inside a `git worktree`. Nothing
here failed loudly. `python3 <missing>.py` exits 2, which is exactly the code
Claude Code reads as *block* — so a broken path did not stop protecting, it
blocked every matching `Bash`/`Write`/`Edit` call with an unreadable "can't
open file" as the reason. The `Stop` hook was worse: its `stop_hook_active`
short-circuit, the mechanism that prevents an unbreakable blocked-forever
loop, lived inside the script that never ran, so the session could not be
ended at all from outside a worktree whose root was not the cwd.

This repository's own assessment named the gap at dimension 2.4: the defect
was caught only by the slow local-suite rung, `shared/scripts/selftest.py`'s
acceptance case, run before a push. Nothing in the fast, same-turn layer
caught it — because the same layer that would have refused the dangerous
edit was exactly the layer the defect silently disabled. A same-turn check
that reads the wiring state directly, rather than depending on the wiring it
is judging to be intact first, closes that hole.

## Decision

**`check_hook_paths.py` is a gate, not a guard.** The defect is a standing
property of committed configuration — a fact sitting in the tree whether or
not anyone touches it this session — not a proposed action to intercept. That
is the same distinction `check_no_machine_paths.py` and `check_layering.py`
are built on, and CLAUDE.md's own routing rule: what must never enter the
tree is a guard's job, a state a script can detect is a gate's.

It reads every `settings.json`, `settings.local.json`, and `hooks.json`
anywhere under the tree — a project's `.claude/settings.json`, a personal
`.claude/settings.local.json` that never reaches git, and a plugin's own
`hooks/hooks.json` alike — and flags a wired command that names a script by a
bare relative path. `${CLAUDE_PROJECT_DIR}/...`, `${CLAUDE_PLUGIN_ROOT}/...`,
an absolute path, and a bare program name resolved on `PATH` are all left
alone; so is a shell one-liner that names no script at all, such as
`command -v jq >/dev/null || echo ... >&2` — treating a redirect target or a
bare command word as an unresolved script path would make the gate
indistinguishable from one that fires on every hook.

It ships in `shared/scripts/gates/`, so `scaffold.py`'s `COPY` table carries
it into every scaffolded repository the same way it carries every other
gate, and it needs nothing from this repository specifically to run there:
it reads the tree it is given, not `scaffold.py`'s own `HOOKS` template.
Verified against the real defect directly: checked out into a bare clone at
`aafdc0113^`, it reports all four relative commands in `.claude/settings.json`
by name; at `aafdc0113`, it is clean.

## Consequences

Every scaffolded repository's `ci.sh` now runs this gate in the fast lane,
alongside the other checks that need nothing but a fresh clone. A repository
that hand-edits its own hook wiring after scaffolding — the exact way this
defect was introduced here — gets the same same-commit feedback this
repository now has, rather than discovering it only when a hook silently
stops firing from inside a worktree.
