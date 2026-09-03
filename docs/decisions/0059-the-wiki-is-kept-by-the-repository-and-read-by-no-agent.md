# 0059 · The wiki is kept by the repository and read by no agent

**Date:** 2026-09-03. **Status:** accepted, and built: the seed and its gate,
the extractor, the replay, the maintainer, and the proposer behind
`/learn --propose`.

## Context

WikiSkill (arXiv 2608.27454) compiles an agent's execution traces into a
persistent wiki, proposes skills from the wiki, and keeps a proposal only when
it scores strictly better on held-out tasks. Two of its findings decide the
shape here. Giving the proposer the wiki raised the average from 48.7 to 63.7;
giving the *inference* agent the same wiki lowered it from 63.7 to 60.9. And its
held-out sets are hundreds of like tasks — spreadsheets, search queries — which
a single repository does not have: a few dozen fix-shaped commits, each a
different bug, against a codebase that keeps moving.

This repository already has the raw material. One session's transcript on this
machine holds 76 guard refusals, 134 tool errors, 131 stop-hook verdicts and
338 user messages, none of which anything reads.

## Decision

**The wiki lives in the repository, under `.claude/wiki/`, and nothing routes
an agent to it.** It is state a team shares, so it is committed; it is not
behaviour, so it survives the plugin being uninstalled without doing anything.
It is not under `docs/`, because `docs/` is where an agent goes to look things
up, and the whole point is that it must not.

**The output of a pattern is a guard, a gate or a rule — not a skill.** A skill
changes what the agent does, and measuring that needs a held-out set the
repository cannot supply. A guard changes what can *happen*, and its held-out
set is free: the transcripts' own tool calls, thousands of them, through which
a candidate must refuse every recorded instance of the pattern and nothing
else. Skills stay a plugin-level product, validated over the corpus, where the
paper's design applies as written.

**The seed is copied once.** `scaffold.py` installs `index.md`, `logs.md`,
`impact.md` and an empty `patterns/` at tier B and never overwrites them: after
the first `/learn` they are the repository's own record.

**A gate keeps it a record.** `check_wiki_hygiene.py` fails when a pattern
lacks `count`, `sessions`, `route` or `status`; when a shipped pattern names a
file that is not there; or when a credential-shaped string got in. It exits 0
when there is no wiki, because a repository that never ran `/learn` has
nothing wrong.

## Consequences

- The extractor, the replay, the maintainer and the proposer are
  instruments and stay in the plugin (`shared/scripts/wiki/`, `agents/wiki/`). They read transcripts on the machine
  and write patterns; they may open a pull request that adds a guard, and may
  not merge it. A diagnostic that starts fixing what it finds has stopped
  being a diagnostic (0021).
- Raw transcripts never enter the tree. They hold personal content and, in
  refused commands, sometimes tokens. The extractor redacts; the gate is the
  second wall.
- `docs/index.md` does not mention `.claude/wiki/`. The index in the wiki
  itself says what it is, for the person who finds it.
- The rejected-proposal rows in `impact.md` are the memory that stops the
  same proposal being made twice. They are written by the proposer and never
  by hand.
