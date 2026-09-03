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
  variable expansion -- the target is invisible until it is too late, unless
  the same command already wrote that variable's value out in plain text
  (`VAR=literal`, or `for VAR in a b c`) earlier than the delete -- then the
  path was reviewable a line up, and it is the value that matters, not the
  spelling
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

# `$(...)` or a backtick anywhere in the arguments -- always computed, no
# variable can be reviewed around it away.
_SUBSHELL = re.compile(r"\$\(|`")

# The bare variables a delete's arguments actually reference.
_VAR_REF = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")

# `NAME=value` at the start of a statement, where `value` is the plain text
# that will reach the variable -- no `$`, no backtick, so it is already on
# the screen. `[^\s;&|]+` stops the value at the next separator, same as
# ARG_END does for a command's own arguments.
_LITERAL_ASSIGN = re.compile(
    r"(?:^|[;\n]|&&)\s*([A-Za-z_][A-Za-z0-9_]*)=([^\s;&|]+)")

# `for NAME in a b c` -- a loop whose list is written out, not produced.
_FOR_LITERAL = re.compile(
    r"\bfor\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\s+([^;\n]+?)\s*(?:;|\n)")

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


def _plain(value: str) -> bool:
    return "$" not in value and "`" not in value and not _is_tree(value)


def _literal_names(command: str, before: int) -> set[str]:
    """Every name the text before `before` has spelled out in full, by a plain
    assignment or a loop over a written-out list.

    Last write wins, and a later one that is not plain takes the name back:
    `T=build; T=$(echo /); rm -rf "$T"` spells T out once and then computes it,
    and only the computed value is the one that reaches the delete."""
    spelled = {}
    head = command[:before]
    for m in _LITERAL_ASSIGN.finditer(head):
        spelled[m.group(1)] = _plain(m.group(2))
    for m in _FOR_LITERAL.finditer(head):
        items = m.group(2)
        spelled[m.group(1)] = ("$" not in items and "`" not in items
                               and all(_plain(w) for w in items.split()))
    return {name for name, plain in spelled.items() if plain}


def _is_tree(value: str) -> bool:
    """A literal value is still unreviewable if the literal *is* the tree:
    `T=.` then `rm -rf "$T"` reads exactly like the safe case this exemption
    is for, and deletes the same thing `_THE_TREE` exists to stop -- `_THE_TREE`
    only sees the text `"$T"`, never the value `.` it stands for."""
    return value.strip("'\"").rstrip("/") in ("", ".", "..", "~")


def _reviewable(command: str, pos: int, rest: str) -> bool:
    """True when every computed-looking thing in `rest` is a variable whose
    value was already written out in plain text earlier in `command`."""
    if _SUBSHELL.search(rest):
        return False
    # `D=/tmp/x; rm -rf $D/../..` deletes `/`. The value was spelled out and
    # the path still is not: what a reader reviewed is not where this lands.
    if ".." in rest:
        return False
    referenced = set(_VAR_REF.findall(rest))
    if not referenced:
        return False
    return referenced <= _literal_names(command, pos)


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
        # `and not` rather than a nested `continue`: waiving the computed rule
        # must not skip the rule below it. `T=build; rm -rf "$T" .` is a
        # reviewable variable AND the tree, and the tree is why the rule exists.
        if _COMPUTED.search(rest) and not _reviewable(command, m.start(), rest):
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
    # A variable is not enough on its own -- it must have been *set* to
    # something plain. Assigning it from a subshell is exactly as
    # unreviewable as using the subshell directly.
    ("Bash", {"command": "T=$(mktemp -d)\nrm -rf \"$T\""}, True),
    ("Bash", {"command": "for f in $(ls); do rm -rf \"$f\"; done"}, True),
    # A literal assignment can still spell out the tree itself. `_THE_TREE`
    # never sees it -- it only reads the argument text, `"$T"` -- so this
    # exemption must refuse it on its own.
    ("Bash", {"command": "T=.\nrm -rf \"$T\""}, True),
    ("Bash", {"command": "T=~\nrm -rf \"$T\""}, True),
    ("Bash", {"command": "for d in . build; do rm -rf \"$d\"; done"}, True),
    # Waiving the computed rule must not waive the tree rule underneath it.
    ("Bash", {"command": "T=build\nrm -rf \"$T\" ."}, True),
    ("Bash", {"command": "T=build\nrm -rf \"$T\" /"}, True),
    # Spelled out once, then computed. The computed value is the one that
    # reaches the delete.
    ("Bash", {"command": "T=build\nT=$(echo /)\nrm -rf \"$T\""}, True),
    # A spelled-out value is not a spelled-out path.
    ("Bash", {"command": "D=/tmp/x\nrm -rf $D/../.."}, True),
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
    # A scratch directory the command just assigned to a variable, one line
    # up -- recorded refusing real work four times in one session.
    ("Bash", {"command": "T=~/developing/cc-repo-harness-template\n"
                         "rm -rf \"$T\"; mkdir -p \"$T\""}, False),
    ("Bash", {"command": "W=/tmp/x/scratch/tpl-dry\n"
                         "test -e \"$W\" && rm -rf \"$W\""}, False),
    ("Bash", {"command": "S=/tmp/x/scratch\n"
                         "rm -rf \"$S/brieftest\" && mkdir -p \"$S/brieftest\""}, False),
    # A loop variable walking a short, literal, written-out list.
    ("Bash", {"command": "for d in guards gates context; do\n"
                         "  rm -rf \"scripts/$d\"\n"
                         "  mkdir -p \"scripts/$d\"\n"
                         "done"}, False),
]
