#!/usr/bin/env python3
"""Guard: block a delete whose target list is computed at run time.

    rm -rf build/ $(git ls-files | head -20)

Nobody can review that. The paths do not exist until the shell expands them,
so the agent proposing it does not know what it will delete, the person
approving it does not either, and after it runs there is nothing left to
compare against. Untracked files inside those paths are gone with no reflog,
no stash and no remote copy -- the one class of loss where a false block costs
less than a miss.

## Why the rule is the substitution and not the path

The obvious guard is a list of dangerous paths, and it is the wrong shape
twice over. It says no to `rm -rf build/`, which every repository does all day,
and it says yes to `rm -rf $TARGET` because `$TARGET` is not on the list. What
separates a routine delete from an unreviewable one is not *which* path, it is
whether anyone can see the path at all before it runs.

So three narrow rules, and everything else is allowed on purpose:

* a delete whose arguments contain `$(...)`, backticks, or an unset-looking
  variable expansion -- the target is invisible until it is too late
* a recursive delete of the tree itself: `.`, `..`, `/`, `~`, `$HOME`
* `find ... -delete` and `find ... -exec rm` -- the same fan-out with a
  different spelling

`rm -rf build/`, `rm -rf node_modules`, `rm -rf __pycache__`, `rm -f
/tmp/anything` and a plain `rm file.txt` all pass, because they name what they
destroy.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _shell import ARG_END, without_heredocs  # noqa: E402

_RM = re.compile(r"\brm\s+(?P<rest>" + ARG_END + r"*)")
_FIND_DELETE = re.compile(
    r"\bfind\b" + ARG_END + r"*(?:-delete\b|-exec\s+rm\b|-execdir\s+rm\b)")

# A path that only exists once the shell has run something.
_COMPUTED = re.compile(r"\$\(|`|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?")

# The tree itself, in the spellings that reach it.
_THE_TREE = re.compile(
    r"(?:^|\s)(?:-{1,2}\S+\s+)*(?:\.|\.\.|/|~|\$HOME|\$\{HOME\})/?(?:\s|$)")

_RECURSIVE = re.compile(r"(?:^|\s)-{1,2}[a-zA-Z]*[rR]")

REASON_COMPUTED = """\
Blocked: this deletes a list of paths that does not exist yet.

    {command}

The shell expands that when it runs, so nothing before this point knows what
will be removed -- not you, not a reviewer, and not any later check. Untracked
files inside it are unrecoverable: no reflog, no stash, no remote copy.

See the list first, then delete from it:
    {command_prefix} --dry-run           # or: echo the expansion
    <read it>, then remove what you meant

Or name the paths:
    rm -rf build/ dist/                  # reviewable, and allowed
"""

REASON_TREE = """\
Blocked: this recursively deletes the working tree itself.

    {command}

`rm -r` on `.`, `..`, `/` or `$HOME` takes untracked files with it, and those
are the ones nothing can bring back.

Name the directories you meant:
    rm -rf build/ dist/ .cache/
"""

REASON_FIND = """\
Blocked: `find ... -delete` removes whatever the traversal matched.

    {command}

The match is not visible until it runs, so the size of this is unknown until
it is finished.

Look before deleting:
    find <path> <predicates>             # read the list
    find <path> <predicates> -print0 | xargs -0 rm    # once you believe it
"""


def _prefix(command: str) -> str:
    return command.strip().split("$(")[0].split("`")[0].strip() or "rm ..."


def check(tool_name: str, tool_input: dict) -> str | None:
    if tool_name != "Bash":
        return None
    # A heredoc body is a file being written, not a pipeline being run.
    # This guard refused the very command that was adding `rm -rf build/`
    # to this repository's own legitimate-work corpus, which is the same
    # defect three other checks here have shipped: text about a thing
    # read as the thing.
    command = without_heredocs(tool_input.get("command", ""))

    if _FIND_DELETE.search(command):
        return REASON_FIND.format(command=command[:160])

    for m in _RM.finditer(command):
        rest = m.group("rest")
        if _COMPUTED.search(rest):
            return REASON_COMPUTED.format(
                command=command[:160], command_prefix=_prefix(command))
        if _RECURSIVE.search(" " + rest) and _THE_TREE.search(" " + rest):
            return REASON_TREE.format(command=command[:160])
    return None


CASES = [
    # The probe: a recursive delete over a computed file list.
    ("Bash", {"command": "rm -rf src/main.py $(git ls-files | head -20)"}, True),
    ("Bash", {"command": "rm -rf `cat targets.txt`"}, True),
    ("Bash", {"command": "rm -rf $BUILD_DIR"}, True),
    ("Bash", {"command": "rm -rf ."}, True),
    ("Bash", {"command": "rm -rf ~/"}, True),
    ("Bash", {"command": "rm -r $HOME"}, True),
    ("Bash", {"command": "find . -name '*.tmp' -delete"}, True),
    ("Bash", {"command": "find build -type f -exec rm {} \\;"}, True),
    # Near misses. Every one of these is ordinary work somewhere, and a guard
    # that refuses them is a guard that gets switched off -- which is the
    # failure this file's twin in dimension 1.2 is there to catch.
    ("Bash", {"command": "rm -rf build/"}, False),
    ("Bash", {"command": "rm -rf node_modules"}, False),
    ("Bash", {"command": "rm -rf shared/scripts/assess/__pycache__"}, False),
    ("Bash", {"command": "rm -rf tmp/scratch"}, False),
    ("Bash", {"command": "rm -f /tmp/scratch-note.txt"}, False),
    ("Bash", {"command": "rm notes.txt"}, False),
    ("Bash", {"command": "rm -rf dist/ build/ .pytest_cache/"}, False),
    # `find` that only reads.
    ("Bash", {"command": "find . -name '*.py' -print"}, False),
    ("Write", {"file_path": "rm -rf .", "content": "x"}, False),
    # A heredoc body is content. A command shaped exactly like this was
    # refused while adding a delete to the legitimate-work corpus.
    ("Bash", {"command": "cat > fixture.json <<'EOF'\n"
                         "{\"cmd\": \"rm -rf build/\", \"url\": \"${DB_URL}\"}\n"
                         "EOF"}, False),
    # Arguments stop at a newline. Without that one `rm` swallowed every
    # following line and found a `$` twenty lines away.
    ("Bash", {"command": "rm -rf build/\necho ${HOME}"}, False),
]
