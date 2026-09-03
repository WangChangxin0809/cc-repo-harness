---
description: Read this machine's sessions in a repository into its .claude/wiki/. Nothing else changes.
argument-hint: "[path] [--since YYYY-MM-DD] [--sessions N]"
allowed-tools: Bash, Read, Task
---

Learn from the sessions this machine has run in the repository at `$1`
(default: the current directory). Call it `ROOT`.

**Only `ROOT/.claude/wiki/` changes.** The wiki is a record of what keeps
going wrong, written for the person who will turn a pattern into a guard.
No agent is routed to it, and nothing here proposes a change to the
repository: proposals are a separate instrument, and until it runs every
pattern stays `status: open`.

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

## 4. Hand back

Print the maintainer's log entry, the gate's verdict —

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/gates/check_wiki_hygiene.py --root ROOT
```

— and `git -C ROOT status --short .claude/wiki`. Do not commit: the person
reads the patterns first, and a pattern they disagree with is deleted, not
argued with.
