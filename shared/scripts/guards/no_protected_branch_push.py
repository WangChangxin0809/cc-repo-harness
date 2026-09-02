#!/usr/bin/env python3
"""Guard: block pushes that land directly on a protected branch.

Configure the branch names in .claude/guards.json (created by scaffold.py):

    {"protected_branches": ["main", "master", "release"]}

Why this is a guard and not a `permissions.deny` entry: the rule is conditional
on the *refspec*, not on the command. `git push upstream main` must be blocked
while `git push upstream feature/x` must not, and a deny pattern that catches the
first without the second cannot be written -- `Bash(git push:*)` blocks both.
Anything a deny rule can express, prefer a deny rule; this one it cannot.

Force-pushing anywhere is a separate matter and belongs in deny, since it has no
conditional form worth allowing:

    "deny": ["Bash(git push --force:*)", "Bash(git push -f:*)"]
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _shell import without_heredocs  # noqa: E402

DEFAULT_PROTECTED = ["main", "master"]
_PUSH = re.compile(r"\bgit\s+(?:-\S+\s+)*push\b([^|;&]*)")

REASON = """\
Blocked: this pushes directly to `{branch}`, which is protected.

Direct pushes to a shared trunk skip review and cannot be undone for anyone who
has already fetched. Branch first, then open a pull request:

    git switch -c <type>/<short-description>
    git push -u <remote> <type>/<short-description>

If this really is meant to land on `{branch}`, say so explicitly and go through
the review path rather than around it.

Protected branches are configured in .claude/guards.json.
"""


def _protected():
    for candidate in (".claude/guards.json", "guards.json"):
        try:
            with open(candidate, encoding="utf-8") as fh:
                value = json.load(fh).get("protected_branches")
                if isinstance(value, list) and value:
                    return [str(b) for b in value]
        except (OSError, ValueError):
            continue
    return DEFAULT_PROTECTED


def _current_branch():
    try:
        out = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def check(tool_name: str, tool_input: dict) -> str | None:
    if tool_name != "Bash":
        return None
    match = _PUSH.search(without_heredocs(tool_input.get("command", "")))
    if not match:
        return None

    protected = _protected()
    # Arguments after `git push`, minus flags: [remote, refspec...]
    args = [a for a in match.group(1).split() if not a.startswith("-")]

    for arg in args[1:]:                       # skip the remote
        # `HEAD:main`, `main`, `+main`, `local:main`
        target = arg.split(":")[-1].lstrip("+").removeprefix("refs/heads/")
        if target in protected:
            return REASON.format(branch=target)

    # No explicit refspec: git pushes the current branch. Only then does the
    # checkout state decide, so consult it here and not before -- asking git on
    # every push would cost a subprocess for calls that cannot be violations.
    if len(args) <= 1:
        branch = _current_branch()
        if branch in protected:
            return REASON.format(branch=branch)
    return None


CASES = [
    ("Bash", {"command": "git push upstream main"}, True),
    ("Bash", {"command": "git push origin HEAD:main"}, True),
    ("Bash", {"command": "git push -u origin master"}, True),
    ("Bash", {"command": "git push origin refs/heads/main"}, True),
    # Near misses: a feature branch, and a branch whose name merely contains the
    # protected one.
    ("Bash", {"command": "git push -u origin feature/new-thing"}, False),
    ("Bash", {"command": "git push origin fix/mainline-parser"}, False),
    ("Bash", {"command": "git push origin HEAD:feature/x"}, False),
    ("Bash", {"command": "git fetch origin main"}, False),
    ("Bash", {"command": "git log origin/main"}, False),
    ("Read", {"file_path": "x"}, False),
    # A heredoc body is data. This refused the command that was *writing* a
    # selftest case naming `git push origin main`, twice, while the guard
    # beside it was being fixed for the same class of mistake.
    ("Bash", {"command": "cat > t.py <<'EOF'\n"
                         "CASES = [('Bash', {'command': 'git push origin main | tail -5'},\n"
                         "          True)]\n"
                         "EOF"}, False),
]
