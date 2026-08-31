# 0024 — Skills are payload, except the one that finds them

Date: 2026-08-31
Status: accepted
Moves five of six skills out of the plugin and into the repositories that
chose them.

## Context

Claude Code keeps a listing of every installed skill's name and description in
the context window, so the model knows what is available. That listing is paid
on **every turn of every session in every repository on the machine** — not
only in repositories that use this plugin, and not only in sessions about
harnesses.

This plugin shipped six skills. Measured at characters over four:

| | tokens/turn |
|---|---|
| `bootstrap-repo-harness` | ~173 |
| `writing-docs` | ~168 |
| `consolidating-notes` | ~146 |
| `writing-github-docs` | ~146 |
| `writing-checks` | ~131 |
| `repo-index` | ~124 |
| **total** | **~888** |

The number surfaced from this project's own instrument, pointed at this project:
about a third of the standing cost it was reporting on a subject repository was
**the instrument's own weight**. The fact sheet labelled it honestly — *from
plugins installed on this machine, which this repository cannot fix* — and that
honesty is what made it obvious that the fix was ours.

## Decision

Five skills move to `shared/skills/` and are copied into `.claude/skills/` by
`scaffold.py`, at the tier that earns them. `bootstrap-repo-harness` stays in
the plugin.

Installing the plugin now costs ~173 tokens a turn instead of ~888, a reduction
of 81%. A repository that was bootstrapped pays for the skills it chose, and
its teammates get them **without installing anything**.

## Why the entry point is the exception

A skill nobody can discover teaches nobody. `bootstrap-repo-harness` is how a
person arrives at any of this, so it has to be present before there is a
repository to copy it into. It is the one skill whose value is in being found,
and the only one worth charging every session for.

## Why this is not a workaround

It is what this repository's own split already says. `shared/` is **payload** —
things a repository needs in order to work, copied in, and still working after
the plugin is uninstalled. A skill that teaches somebody how to write a gate for
*their* repository is exactly that: it belongs to the repository, travels with
it in version control, and outlives us.

It also strengthens hard rule 4 rather than bending it. The plugin keeps what
protects a person from a repository, what teaches a person how to arrive, and
what measures a repository. The teaching that a specific repository has adopted
now lives in that repository, where its teammates can read it and change it.

## Rejected

**Trimming the descriptions instead.** It would have saved roughly half and
changed nothing structural. But a description is the only thing the model has to
decide whether a skill applies, so cutting keywords buys tokens with triggering
accuracy — and that failure is silent: the skill simply does not fire, and
nobody learns why. Trading a measurable cost for an unmeasurable one is a bad
trade even when the arithmetic looks good.

**`disable-model-invocation: true`.** It stops the model from choosing a skill,
but the documentation does not say the listing drops the description, and the
listing is what costs. Claiming a saving here without measuring it would be the
kind of thing this project keeps catching in other people's work.

**`skillOverrides: "name-only"`.** Real, documented, and effective — and it is a
*user* setting. Solving our cost problem by asking every user to configure
around us is not a fix, it is a support burden with a nicer name.

## Consequences

**A skill is not available before bootstrapping.** Working in a repository that
has never been scaffolded, `writing-checks` is not there. This is the real cost
of the change. It is acceptable because the skills describe how to build the
harness this plugin installs, so the moment they are wanted is the moment
`bootstrap-repo-harness` runs — and that one is still present. Reading them
before that is still possible; they are files in a plugin on disk.

**The five cross-reference each other by name.** Inside a bootstrapped
repository they are all present, so the references resolve. From
`bootstrap-repo-harness`, a reference now points at something that may not exist
yet, and it says so rather than pretending.

**Uninstalling the plugin leaves them behind.** That is the point.

## Evidence status

| Claim | Grade |
|---|---|
| Every installed skill's description is in context on every turn | **checked** against the first-party documentation: *"Claude Code loads a listing of skill names and descriptions into context... The listing always contains every skill name"* |
| ~888 → ~173 tokens/turn | **measured**, characters over four, the same unit the fact sheet reports |
| Cutting descriptions costs triggering accuracy | **argued**, not measured. It is the reason that option was rejected, and it is the weakest claim here |
| The copy survives the plugin being deleted | **checked**: a selftest scaffolds from a copy of the plugin, deletes the copy, and then looks for `SKILL.md` and its `references/` |
