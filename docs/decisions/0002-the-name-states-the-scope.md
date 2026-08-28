# 0002 — The name states the scope: `repo-agent-harness`

Date: 2026-08-28
Status: accepted

## Context

The plugin shipped as `agent-harness`. Two problems, and the second is the one
that mattered.

**It collided with a term of art.** In the Claude Agent SDK, *harness* names the
execution loop that drives a model through tool calls. A plugin called
`agent-harness` reads as an implementation of that loop. It is not one; it never
touches the loop. It configures the repository the loop is pointed at.

**It overclaimed its scope.** An unqualified `agent-harness` promises everything
an agent needs. What is here is narrower and better for being narrow:
conventions, guards, gates, and retrieval, placed at the moments a repository
gets read.

A name that has to be corrected in the first paragraph of the README is a name
that is doing damage before anyone reaches the README.

## Decision

**`repo-agent-harness`** — the direct rendering of *Repository Coding-Agent
Harness*. The qualifier does the work: it says which side of the boundary this
sits on, and it stops the name promising the whole problem.

The README now opens with an explicit *what this is / what this is not*, because
a qualifier narrows a name without explaining it, and "harness" still overlaps
with the SDK's meaning. That overlap is reduced here, not eliminated, and the
prose is what closes the gap.

Also renamed, for the same reason:

- The marketplace becomes `wangchangxin-plugins`. It was named after its single
  occupant, which is not what a marketplace is.
- The scaffolded decision record becomes `docs/decisions/0001-agent-conventions.md`,
  dropping `agent-harness` from its name. It is written into a repository whose
  entire acceptance test is that it outlives this plugin; a file named after the
  plugin, sitting in that repository, contradicted the thesis on its own
  filename.

## Consequences, including the ones that cost something

**Trust is reset.** The store moves from `~/.claude/agent-harness/` to
`~/.claude/repo-agent-harness/` and the old file is not read. Every repository
that had trusted its guards must trust them again. This is not worked around
with a migration: re-confirming trust after the trusting component changes its
identity is the behaviour you would want if the rename had been someone else's.
The hook says so once, by name, and `--trust` is one command.

**Gate hints no longer name a filename.** `check_layering.py` and
`check_context_budget.py` used to point at `docs/decisions/0001-agent-harness.md`
in their failure output. A repository scaffolded before this change does not have
that file, and a hint pointing at a path that does not exist is worse than a
vaguer hint. They now point at `docs/decisions/`.

**The repository is not renamed.** `/plugin marketplace add
WangChangxin0809/agent-harness` still resolves, and anyone who has already run it
keeps working. Renaming the repository would move every existing install onto a
GitHub redirect for the benefit of matching a string. If it is renamed later it
is a separate, announced change; the plugin name is what users type and it is
correct now.

## Rejected

- **`repo-conventions`, `agent-onboarding`, and other non-harness names.** They
  describe the documentation half and drop the enforcement half. The guards and
  gates are the part that makes this different from writing a good README.
- **Keeping `agent-harness` and explaining it in the docs.** That is the state
  this record exists to end. The correction was already in the README and it did
  not stop the name being read first.
- **Migrating the trust store.** Five lines, and it would silently carry a trust
  decision across a rename of the thing being trusted. Fails in the wrong
  direction.
