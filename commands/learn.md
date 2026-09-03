---
description: Read this machine's sessions into the repository's .claude/wiki/. Changes nothing else.
argument-hint: "[path] [--since YYYY-MM-DD] [--sessions N] [--propose [pattern]]"
allowed-tools: Bash, Read, Task
---

Learn from the sessions this machine has run in the repository at `$1`
(default: the current directory). Call it `ROOT`.

**Without `--propose`, only `ROOT/.claude/wiki/` changes.** The wiki is a
record of what keeps going wrong, written for the person who will turn a
pattern into a guard. No agent is routed to it.

`--propose` adds one step at the end that may write a guard and open a pull
request. It never merges one. Adding something that refuses an action changes
what the repository does for everyone working in it, and that is a person's
decision -> 0059.

Work in a directory outside the repository — `mktemp -d` — and call it `W`.

## 1. Extract

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/wiki/extract.py \
        --root ROOT --out W/packet.json --digest W/digest.md
```

Pass `--since` and `--sessions` through if given. Exit 2 means there are no
transcripts for this repository on this machine: say so and stop. Print the
one-line summary it ends with.

## 2. Seed the wiki if it is not there

If `ROOT/.claude/wiki/index.md` does not exist, copy the seed:

```bash
mkdir -p ROOT/.claude/wiki/patterns
cp -n ${CLAUDE_PLUGIN_ROOT}/shared/wiki/index.md \
      ${CLAUDE_PLUGIN_ROOT}/shared/wiki/logs.md \
      ${CLAUDE_PLUGIN_ROOT}/shared/wiki/impact.md ROOT/.claude/wiki/
```

A repository scaffolded at tier B already has it.

## 3. Maintain

Spawn one `wiki-maintainer` with `DIGEST=W/digest.md`, `PACKET=W/packet.json`,
`WIKI=ROOT/.claude/wiki`, `ROOT`. It reads the digest, writes patterns, and
replies with the log entry it appended.

## 4. Reconcile what was proposed

Every pattern with `status: proposed` names a pull request in its `impact.md`
row. Ask what happened to it:

```bash
gh pr view <n> --repo <ROOT's remote> --json state --jq .state
```

- `MERGED` — set the pattern to `status: shipped`, and the row's outcome to
  `shipped #<n>`.
- `CLOSED` — set it back to `status: open`, the outcome to `rejected #<n>`,
  and append one line to the pattern saying what the refusal was, so the next
  run does not propose the same fix again.
- `OPEN` — leave both alone.

No `gh`, no remote, or a repository it cannot see: leave every pattern alone
and say so in one line. A status you could not confirm is not a status.

Without this, a proposal that landed still reads as pending, and `impact.md`
never says whether the loop works.

## 5. Propose, only if asked

Skip this entirely unless `--propose` was passed.

Take the patterns with `route: guard` and `status: open`, highest `count`
first. If `--propose` named one, take that one only. If none qualifies, say
so in one line and go to step 6 — a run that proposes nothing is the normal
result, and the bar is the maintainer's: seen in two sessions, or three
times in one.

Spawn **one** `wiki-proposer` per pattern, and one at a time rather than
in parallel: each ends in a branch and a pull request, and two agents
branching from the same worktree collide. Give it `PATTERN`, `PACKET=W/packet.json`,
`WIKI`, `ROOT`, and a fresh `W/pN` as its scratch directory.

Each replies with its `impact.md` row and either a pull request URL or the
reason there is none. Do not re-run one that rejected: the row is the record
that it was tried.

## 6. Hand back

Print the maintainer's log entry, the gate's verdict —

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/gates/check_wiki_hygiene.py --root ROOT
```

— and `git -C ROOT status --short .claude/wiki`. Do not commit the wiki: the
person reads the patterns first, and a pattern they disagree with is deleted,
not argued with. If a proposer opened a pull request, print its URL last, and
say plainly that nothing has been merged.
