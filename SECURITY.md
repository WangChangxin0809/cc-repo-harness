# Security policy

## What this plugin does on your machine

Worth stating plainly, because most of it runs without being asked:

- **A `PreToolUse` hook** (`hooks/run_repo_guards.py`) runs before every `Bash`
  call in any repository where the plugin is enabled. It can execute that
  repository's own `scripts/guards/dispatch.py` — but only after you have
  trusted that repository's guard set explicitly, by path and by content
  digest (see below). It never runs anything from this plugin's own directory,
  and it can only block a command — never modify or rewrite one.
- **`scaffold.py`** writes files into a repository you point it at. It never
  overwrites an existing file, and it copies `.claude/settings.json` to `.bak`
  before merging hooks into it.
- **`build.py`** reads git-tracked files and writes a graph under `.index/`.
- Nothing here makes a network request, and nothing sends anything anywhere.

## The trust gate, and why it is not optional

Running a repository's `dispatch.py` means executing code from that repository,
and that dispatcher imports every `.py` beside it. Ungated, this sequence would
be arbitrary code execution:

    git clone <REPO>        # a repository nobody here has read
    cd <REPO> && <command>  # any Bash tool call at all

and it would be worse than the general case, because it launders an unread
repo's code through an approval you granted to *this plugin*. Claude Code
deliberately prompts before honouring a project's own `settings.json` hooks. A
plugin must not become the way around that prompt.

So nothing runs until it is trusted, by absolute path and by a SHA-256 digest
over every `.py` in `scripts/guards/`. Editing, adding, or removing a guard
changes the digest and revokes trust until you look at the change:

```bash
python3 hooks/run_repo_guards.py --status
python3 hooks/run_repo_guards.py --trust     # lists the files first
python3 hooks/run_repo_guards.py --forget
```

Trust records live in `$CLAUDE_CONFIG_DIR/cc-repo-harness/trusted-guards.json`
(default `~/.claude`), mode 0600, written atomically. They are deliberately
*outside* the repository: a repository that could grant itself trust in a pull
request would not be granting anything.

The residual consequence, stated plainly: once you have trusted a repository's
guard set, code from that repository runs before your Bash commands until it
changes. That is the intended behaviour and it is what makes guards work — but
the better end state is to wire `scripts/guards/dispatch.py` into the
repository's own `.claude/settings.json`, which `scaffold.py` does. Then the
repo owns its guards under Claude Code's normal project trust, and this hook is
no longer in the path at all.

## Reporting a vulnerability

Open a [private security advisory](../../security/advisories/new) on this
repository. Please do not use the public issue tracker.

Expect an acknowledgement within about a week. This is a small project; an
honest slow number beats a fast one that is not met.

## What counts

- The `PreToolUse` hook executing anything from a repository whose guard set has
  not been trusted at its current content — including any way to make the
  digest match while the executed bytes differ.
- Anything that writes a trust record without the user having run `--trust`,
  a repository doing so for itself above all.
- The `PreToolUse` hook running anything other than the target repository's
  `scripts/guards/dispatch.py`.
- A guard that can be made to allow a command it exists to block, by any input
  reaching it through the hook payload.
- `scaffold.py` overwriting or destroying an existing file.
- Any path here that executes content from a repository being *indexed* rather
  than merely reading it.

## What does not count

- Guards being bypassable by someone who can already edit `scripts/guards/`.
  They are a mistake-prevention mechanism, not a sandbox, and anyone with write
  access to the repository can remove them.
- The textual matching in the shipped guards producing false positives on
  commands inside quoted strings. That is a deliberate trade, explained in
  `skills/writing-checks/references/guard-contract.md`: exempting quoted text
  would create a channel that anything can be moved into.
