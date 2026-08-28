#!/usr/bin/env python3
"""Guard: block piping an outbound action into another command.

A shell pipeline exits with the status of its LAST command. So:

    git push upstream main | tail -5

reports success whenever `tail` succeeds -- which is always. The push can fail
for auth, for a rejected non-fast-forward, for a hook, and the caller sees exit
0 and a few lines of output that look plausible. Every later step then proceeds
on the belief that the change is published.

This is a guard rather than a gate because the false success is consumed
immediately: by the time any check runs, the decision to move on has been made.

Only *mutating* commands are matched. `gh pr list | head` and `curl -s <url> |
jq` are read-only and extremely common; blocking them would get this guard
disabled. `set -o pipefail` in the same command makes the pipeline honest, and
is accepted.
"""

from __future__ import annotations

import re

_OUTBOUND = [
    (re.compile(r"\bgit\s+(?:-\S+\s+)*push\b"), "git push"),
    (re.compile(r"\bdocker\s+push\b"), "docker push"),
    (re.compile(r"\bnpm\s+publish\b"), "npm publish"),
    (re.compile(r"\bgh\s+(?:pr\s+(?:create|merge)|release\s+create|repo\s+create)\b"),
     "gh (mutating)"),
    (re.compile(r"\b(?:curl|wget)\b[^|]*"
                r"(?:-X\s*(?:POST|PUT|DELETE|PATCH)\b|--data\b|-d\s|--upload-file\b)"),
     "curl/wget with a request body"),
]
_PIPEFAIL = re.compile(r"set\s+-[a-zA-Z]*o?\s*\w*\bpipefail\b|set\s+-o\s+pipefail")

REASON = """\
Blocked: an outbound action ({what}) is piped into another command.

A pipeline's exit status is its LAST command's, so a failed {what} reports
success as long as the tail of the pipe succeeds. Nothing downstream can tell
the difference, and the work proceeds as if the change had been published.

Run it on its own and read the status:
    {what} ...          # let its own output and exit code stand

If you need the output filtered, capture first, then filter:
    out=$({what} ... 2>&1); status=$?
    echo "$out" | tail -5
    exit $status

Or make the pipeline honest, if this is a script you control:
    set -o pipefail
"""


def _segments(command: str):
    """Split on single `|`, leaving `||` alone."""
    return re.split(r"(?<!\|)\|(?!\|)", command)


def check(tool_name: str, tool_input: dict) -> str | None:
    if tool_name != "Bash":
        return None
    command = tool_input.get("command", "")
    if "|" not in command or _PIPEFAIL.search(command):
        return None
    parts = _segments(command)
    if len(parts) < 2:
        return None
    for segment in parts[:-1]:          # anything but the last is upstream
        for pattern, what in _OUTBOUND:
            if pattern.search(segment):
                return REASON.format(what=what)
    return None


CASES = [
    ("Bash", {"command": "git push upstream main | tail -5"}, True),
    ("Bash", {"command": "git push 2>&1 | tee push.log"}, True),
    ("Bash", {"command": "docker push myimage:latest | cat"}, True),
    ("Bash", {"command": "curl -X POST https://api.example.com/v1/x -d @body.json | jq ."},
     True),
    # Near misses: read-only pipes, and the honest form.
    ("Bash", {"command": "git push upstream main"}, False),
    ("Bash", {"command": "gh pr list | head -20"}, False),
    ("Bash", {"command": "curl -s https://api.example.com/v1/x | jq ."}, False),
    ("Bash", {"command": "git log --oneline | head"}, False),
    ("Bash", {"command": "set -o pipefail; git push upstream main | tail -5"}, False),
    # The outbound command is LAST, so the pipeline's status is its own.
    ("Bash", {"command": "cat patch.txt | git apply"}, False),
    ("Read", {"file_path": "x"}, False),
]
