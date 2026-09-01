#!/usr/bin/env python3
"""Guard: block file restores that destroy work no later check can find.

`git checkout -- <path>` and `git restore <path>` discard uncommitted edits to
that path, and they do not restore untracked files at all. Once the command has
run there is nothing left to detect -- no gate, no review, no test can tell you
what was there. That is what makes this a guard rather than a gate: the damage is
complete at the moment of execution.

The `-b` / `-B` / branch-switch forms of `git checkout` are untouched. They are
the overwhelmingly common use, and a guard that blocked them would be switched
off within a day.

Deliberate: matching is textual, so the pattern also fires inside a quoted string
(`echo "never run git checkout -- x"`). Teaching the matcher to ignore quoted
text means teaching it to ignore anything that reaches the shell indirectly,
which is an exemption channel rather than a fix. The false positive is rare and
self-explaining; the exemption would be silent.
"""

from __future__ import annotations

import re

# `git checkout -- x`, `git checkout HEAD -- x`, `git checkout .`
#
# `--ours` and `--theirs` are excluded with `-b`/`-B`. They are only meaningful
# while a merge or rebase is unresolved, and what they overwrite is the
# conflict-marked file git wrote a moment ago -- not work anybody authored.
# Blocking them leaves no ordinary way to resolve a conflict at all, which is
# how this was found: taking one side of an eight-file merge on this
# repository was refused, and the way through was to write git's own index
# stages out by hand.
_CHECKOUT_RESTORE = re.compile(
    r"\bgit\s+(?:-\S+\s+)*checkout\b"
    r"(?![^|;&]*\s-{1,2}[bB]\b)"
    r"(?![^|;&]*\s--(?:ours|theirs)\b)"
    r"[^|;&]*?(?:\s--\s|\s\.\s*$|\s\.\s*[|;&])"
)
# `git restore x` -- but `--staged` alone only touches the index, which is safe.
_RESTORE = re.compile(r"\bgit\s+(?:-\S+\s+)*restore\b(?![^|;&]*--staged\b)")

REASON = """\
Blocked: this restores files in a way that cannot be undone or detected.

`git checkout -- <path>` and `git restore <path>` discard uncommitted edits to
those paths, and they do not restore untracked files at all -- afterwards there
is no trace of what was lost, so no later check can catch the mistake.

Instead, back up first and restore from the copy:
    cp <path> <path>.bak      # then edit freely
    cp <path>.bak <path>      # restore exactly what you had

If you genuinely intend to discard work, say so explicitly and stash instead:
    git stash push -- <path>  # recoverable
"""


def check(tool_name: str, tool_input: dict) -> str | None:
    if tool_name != "Bash":
        return None
    command = tool_input.get("command", "")
    if _CHECKOUT_RESTORE.search(command) or _RESTORE.search(command):
        return REASON
    return None


CASES = [
    ("Bash", {"command": "git checkout -- src/main.py"}, True),
    ("Bash", {"command": "git checkout HEAD -- config/app.yaml"}, True),
    ("Bash", {"command": "git restore src/"}, True),
    ("Bash", {"command": "cd /repo && git checkout -- ."}, True),
    # Near misses: same verb, legitimate intent. These are where the regex is
    # most likely to be wrong, so they carry more weight than the positives.
    ("Bash", {"command": "git checkout -b feature/new-thing"}, False),
    ("Bash", {"command": "git checkout main"}, False),
    ("Bash", {"command": "git checkout -B release origin/release"}, False),
    ("Bash", {"command": "git restore --staged src/main.py"}, False),
    # Resolving a conflict, not discarding work: what these overwrite is the
    # conflict-marked file git wrote, and there is no other ordinary way to
    # take a side.
    ("Bash", {"command": "git checkout --ours -- shared/scripts/x.py"}, False),
    ("Bash", {"command": "git checkout --theirs -- docs/index.md"}, False),
    ("Bash", {"command": "git status"}, False),
    ("Bash", {"command": "echo 'never run git checkout -- x'"}, True),
    ("Read", {"file_path": "git checkout -- x"}, False),
]
