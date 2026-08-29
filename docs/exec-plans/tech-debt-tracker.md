# Tech debt

- **Covers**: things found in passing that are real, are not being fixed now,
  and would otherwise be forgotten. Each entry says what reading revealed it and
  what it would touch.
- **Does not cover**: work in flight (that is a plan folder), or anything with a
  decision behind it (that is a decision record).

Permanent. Nothing found while doing something else gets fixed inline — a batch
that grows while you work is a batch that never lands.

## `on_stop.py` has no test of any kind

**Found by**: writing `shared/scripts/context/selftest.py`, after discovering
that `after_edit.py` had spent its whole life writing to a channel the model
never reads. `context/` had no selftest at all, which is why nobody noticed.
`on_stop.py` is the other file in that directory and is in the same position.

**Blast radius**: every scaffolded tier B repository wires it as a `Stop` hook.
Its two load-bearing properties are unverified:

- It **fails open** — exit 2 from a check means "could not judge" and must not
  block a stop. This is the inverse of a gate, and nothing proves it still holds.
- It short-circuits on `stop_hook_active`. If that broke, a session could not be
  ended at all.

**Why not now**: the delivery bug took priority, and a Stop hook needs cases
that assert on the *absence* of blocking, which is a different fixture shape
from the ones just written.

## The context budget gate is blind to two things it should count

**Found by**: reading the official memory documentation against
`gates/check_context_budget.py`, then running the gate on a repository built the
way the docs describe.

**Measured**: a repository with `.claude/CLAUDE.md` and 400 lines of unscoped
`.claude/rules/` returns `cannot judge: no CLAUDE.md at the repository root`,
exit 2 — for a tree carrying over 400 always-loaded lines.

**Blast radius**: three separate holes in one file.

1. `./CLAUDE.md` **or** `./.claude/CLAUDE.md` are both first-party locations.
   The gate only looks at the root one and returns 2 when it is absent, so a
   repository following the documented layout is never judged at all.
2. A rule with no `paths:` frontmatter is "loaded at launch with the same
   priority as `.claude/CLAUDE.md`". The gate counts none of them, which makes
   `.claude/rules/` a complete bypass: move content there and the cost is
   identical while the cap goes quiet.
3. The cap counts every line including HTML comments, which are stripped before
   injection and therefore cost nothing. Two different definitions of "line"
   live in one function.

**Why not now**: it is a gate correction with its own defect-injection round,
and it was found mid-way through the delivery fix.
