# Security policy

## What this plugin does on your machine

Worth stating plainly, because most of it runs without being asked:

- **A `PreToolUse` hook** (`hooks/run_repo_guards.py`) runs before every `Bash`
  call in any repository where the plugin is enabled. It executes that
  repository's own `scripts/guards/dispatch.py` if the file exists and the
  repository has not already wired it. It never runs anything from this plugin's
  own directory, and it can only block a command — never modify or rewrite one.
- **`scaffold.py`** writes files into a repository you point it at. It never
  overwrites an existing file, and it copies `.claude/settings.json` to `.bak`
  before merging hooks into it.
- **`build.py`** reads git-tracked files and writes a graph under `.index/`.
- Nothing here makes a network request, and nothing sends anything anywhere.

The consequence to be aware of: enabling this plugin means a repository can
cause code in *that repository* to run before your Bash commands. That is the
intended behaviour — it is what makes guards work in the window before someone
wires them — but it is worth knowing before you enable it against a repository
you do not trust.

## Reporting a vulnerability

Open a [private security advisory](../../security/advisories/new) on this
repository. Please do not use the public issue tracker.

Expect an acknowledgement within about a week. This is a small project; an
honest slow number beats a fast one that is not met.

## What counts

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
