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

## Statements and quotes

A pipe hides the status of the statement it is in, and of no other. `git push
origin topic; git log --oneline | head` pipes the log, not the push, and the
remedy REASON recommends -- capture, then filter -- has exactly that shape. So
the command is split into statements at `;`, `&&`, `||` and newlines first,
and only an outbound command upstream of a `|` in the *same* statement counts.

Quoted text is data. `echo '{"command":"git push origin topic"}' | python3
dispatch.py` is how the dispatcher is tested, and the push in it is a string.
A separator inside quotes splits nothing, and what is inside quotes is blanked
before matching; `_shell.py` holds both rules. The first version of this guard
did neither, and refused both of those commands during this repository's own
assessment. A guard that refuses its own remedy is a guard somebody turns off.

The limit: this is not a shell parser. `echo "$(git push origin topic)" |
tail` is double-quoted text and is missed, and so is `bash -c 'git push origin
topic | tail'`; a `;` inside `$( )` or `( )` splits a statement early. That is
the trade for the two false positives above, and it is the kind of miss a guard
already lives with -- `B=push; git $B origin topic | tail` sails through, as
dispatch.py's docstring says.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _shell import statements  # noqa: E402

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
# `|` or `|&`. A statement never holds `||`: that is a separator, and
# statements() has already split on it.
_PIPE = re.compile(r"\|&?")

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


def check(tool_name: str, tool_input: dict) -> str | None:
    if tool_name != "Bash":
        return None
    command = tool_input.get("command", "")
    if "|" not in command:
        return None
    # Heredoc bodies and quoted text are data, blanked before anything is read:
    # a `|` or a `;` inside them separates nothing, and `git push` inside them
    # runs nothing. Pipefail is looked for on the same text, so a string that
    # merely mentions it does not set it.
    parts = statements(command)
    if any(_PIPEFAIL.search(statement) for statement in parts):
        return None
    for statement in parts:
        segments = _PIPE.split(statement)
        for segment in segments[:-1]:       # anything but the last is upstream
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
    # Heredoc bodies are content. Both of these were refused for real while
    # writing this repository's own decision records, which is the whole
    # reason the body is stripped.
    ("Bash", {"command": "cat > docs/branching.md <<'EOF'\n"
                         "| action | allowed |\n|---|---|\n"
                         "| git push to a feature branch | yes |\nEOF"}, False),
    ("Bash", {"command": "cat > note.md <<EOF\n"
                         "run `git push` on its own | never in a pipe\nEOF"},
     False),
    # ...and a real pipe on the same line as a heredoc still counts.
    ("Bash", {"command": "cat > f.txt <<'EOF'\nharmless\nEOF\n"
                         "git push origin main | tail -1"}, True),
    # Statements and quotes. Both of the first two were refused for real during
    # this repository's own assessment -- the reading for dimension 1 on
    # 2026-09-02 named them -- and the first is the remedy this guard's own
    # REASON recommends. A guard that refuses its own remedy is a guard
    # somebody turns off. The push is in one statement and the pipe in another;
    # or the push is a string, echoed into the dispatcher the way blast.py and
    # the selftests do it.
    ("Bash", {"command": "out=$(git push origin instrument-fixes 2>&1); "
                         "status=$?; echo \"$out\" | tail -5; exit $status"},
     False),
    ("Bash", {"command": "echo '{\"tool_name\":\"Bash\",\"tool_input\":"
                         "{\"command\":\"git push origin main\"}}' "
                         "| python3 shared/scripts/guards/dispatch.py; "
                         "echo exit=$?"}, False),
    ("Bash", {"command": "git push origin main; git log --oneline | head"}, False),
    ("Bash", {"command": "git push origin main && npm test 2>&1 | tail -20"},
     False),
    # ...and a pipe in the push's own statement still counts, however that
    # statement is reached or the pipe is spelled.
    ("Bash", {"command": "echo start; git push origin main | tail -5"}, True),
    ("Bash", {"command": "out=$(git push origin main 2>&1 | tail -3)"}, True),
    ("Bash", {"command": "git push origin main |& tee push.log"}, True),
    ("Bash", {"command": "git push origin main 2>&1 |tee x"}, True),
    # The seams of the quote handling, each a near miss for a simpler version
    # of it: an escaped quote opens no string, an escaped quote inside double
    # quotes closes none, a backslash before a newline joins the lines instead
    # of ending the statement, and pipefail inside a string is not set.
    ("Bash", {"command": r"echo don\'t; git push origin main | tail -5"}, True),
    ("Bash", {"command": r'echo "{\"tool_name\":\"Bash\",\"tool_input\":'
                         r'{\"command\":\"git push origin main | tail\"}}" '
                         r'| python3 scripts/guards/dispatch.py'}, False),
    ("Bash", {"command": "git push origin main \\\n  | tail -5"}, True),
    ("Bash", {"command": "echo 'set -o pipefail'; git push origin main | tail -5"},
     True),
]
