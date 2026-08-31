# The guard contract

Read this when writing a guard module, or when a guard is installed and nothing
appears to happen.

## Input

`PreToolUse` writes one JSON object to stdin:

```json
{
  "session_id": "…",
  "tool_name": "Bash",
  "tool_input": {"command": "git restore src/", "description": "…"}
}
```

`tool_input` differs per tool. `Bash` carries `command`; `Edit` and `Write`
carry `file_path` and the content; `MultiEdit` carries a list. Write against the
tools your `matcher` actually selects, and treat every key as optional — a
missing key must not raise, because a guard that crashes on an unfamiliar
payload is a guard that fails on the next tool that gets added.

## Output

| Exit | Meaning | Where the output goes |
|---|---|---|
| 0 | allow | stdout is discarded |
| 2 | **block** | stderr is fed back to the model as the reason |
| other | non-blocking error | stderr surfaces as a warning |

Exit 2 is the only blocking code. Anything else lets the call through, which
means a guard that raises an exception fails **open** — deliberately: this runs
before every matching tool call, and one syntax error must not become a wall
nobody can get past. The selftest is what catches the broken module.

## The stderr text is an instruction, not a log line

It is the only prose in the repository guaranteed to be read at the moment it is
relevant, by a reader who has already made the mistake. Give it three things:

```
blocked: `git restore` discards uncommitted work in the same file, and does not
restore untracked files at all.
Back up first:  cp <file> <file>.bak
Why: docs/decisions/0007-no-destructive-restore.md
```

What was matched, what to do instead, and where the reasoning lives.

## Module shape

The dispatcher imports every `*.py` in `scripts/guards/` except `dispatch.py`,
`selftest.py`, and anything starting with `_`. A module needs two things:

```python
def check(tool_input: dict) -> str | None:
    """Return the block reason, or None to allow."""

CASES = [
    ({"command": "git restore src/"}, "discards uncommitted"),   # must block
    ({"command": "git restore --staged src/"}, None),            # must NOT block
]
```

`CASES` pairs an input with the substring its reason must contain, or `None` for
"must be allowed". The selftest structurally requires at least one of each.

The non-blocking case is not optional. A guard with only blocking cases can
become a wall that matches everything, and every such guard ends the same way:
people find a phrasing that slips past it, and then the guard is enforcing
nothing while still looking installed.

## Matching is textual, and that is a choice

The starters match the command string, including text inside quotes. That means
`echo "never run git restore"` is blocked, which is a false positive.

It is the right trade, and the reason is worth stating because the fix looks so
obvious: exempting quoted text creates an exemption channel. Anything that needs
to get past the guard can be moved into a string — a heredoc, a `-c` argument, a
variable expanded later — and the guard is then enforcing nothing on exactly the
commands most likely to be doing something unusual. The false positive costs one
rephrasing; the exemption channel costs the guard.

The same reasoning applies to normalizing operators away. Stripping a `!` to
avoid a false positive is how a check starts approving what it exists to forbid.
When a false positive tempts you to open a general exemption, narrow the pattern
instead.

## Proving one

```bash
cp scripts/guards/no_destructive_restore.py /tmp/g.bak
# make the regex never match — a SILENT defect, not a crash
python3 scripts/guards/selftest.py     # must name exactly this guard, and say
                                       # which case it failed to block
cp /tmp/g.bak scripts/guards/no_destructive_restore.py
```

Restore with `cp`, never `git checkout --` — that discards unrelated uncommitted
work in the same file and does not restore untracked files at all, so it can
silently destroy the thing you were in the middle of proving.
