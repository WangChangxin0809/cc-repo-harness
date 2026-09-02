#!/usr/bin/env python3
"""Shared shell-text helpers. Underscore-prefixed, so `dispatch` skips it.

## The bug this exists to stop happening a fourth time

Three separate checks in this project have shipped the same defect: **text
*about* a thing read as the thing**.

* a collector that scanned for logging stacks found `grafana`, `jaeger` and
  `playwright` in a repository that had none, because it read its own keyword
  list
* a merge-gate check flagged this repository's own CI comment, which says no
  step may swallow a status with `|| true`, as a step swallowing a status
* `no_piped_outbound` refused a decision record twice, because the document's
  prose named an outbound command and its markdown table contained a pipe

The fourth was `no_computed_delete` refusing the command that was *adding*
`rm -rf build/` to a fixture, because the fixture text was inside a heredoc.

Every one of them is a matcher reading data as code. In a shell command there
are two places data reliably lives, a heredoc body and a quoted string, and
the helpers for both are here.
"""

from __future__ import annotations

import re

# `cmd <<'EOF' ... EOF`, `cmd <<-EOF ... EOF`, quoted or bare delimiter.
_HEREDOC = re.compile(
    r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1\s*?\n.*?^\s*\2\s*$",
    re.S | re.M)


def without_heredocs(command: str) -> str:
    """The command with every heredoc body replaced by a marker.

    The redirection itself is kept, so a check that cares about *where* the
    write goes can still see it; only the payload is removed."""
    return _HEREDOC.sub("<<HEREDOC", command or "")


# Where one command's arguments stop. A newline ends them as surely as a `;`
# does, and leaving it out let a single `rm` swallow twenty lines of a
# following heredoc -- which is how the second half of that fourth bug worked.
ARG_END = r"[^|;&\n]"


# The second place data lives: between quotes. `echo '{"command":"docker push
# x"}' | python3 dispatch.py` is how the dispatcher gets tested, and the push
# in it is a string. Blank the string and no matcher can read it as code.
def without_quotes(command: str) -> str:
    r"""The command with the inside of every quoted string replaced by spaces.

    Same length, quote marks kept, so an offset into the result is an offset
    into the original. Backslashes are honoured where the shell honours them,
    outside quotes and inside double quotes: `don\'t` opens no string, and
    `"say \"hi\" again"` closes at the last mark, not the second. The
    backslash and the character it escapes are blanked as a pair, so `\|` is
    not a pipe, and a backslash before a newline joins the two lines instead
    of ending a statement.

    Not a shell parser, on purpose. `$( )`, backticks and `$'...'` are not
    tracked, and an unterminated quote blanks the rest of the command -- which
    the shell would have refused to run anyway."""
    out = []
    quote = None                    # the mark that opened the current string
    i, n = 0, len(command or "")
    while i < n:
        c = command[i]
        if c == "\\" and quote != "'" and i + 1 < n:
            out.append("  ")
            i += 2
            continue
        if quote is None:
            if c in "'\"":
                quote = c
            out.append(c)
        elif c == quote:
            quote = None
            out.append(c)
        else:
            out.append(" ")
        i += 1
    return "".join(out)


# Where one statement ends and the next begins, once quotes and heredoc
# bodies are blank. `||` is listed so that what is left of `|` is a pipe.
_STATEMENT_END = re.compile(r";|&&|\|\||\n")


def statements(command: str) -> list[str]:
    """The command's top-level statements: what `;`, `&&`, `||` and a newline
    separate when they stand outside quotes and heredoc bodies.

    The pieces come back with those bodies and quoted text already blanked,
    because that is the only form in which the split is right. `||` is a
    separator here and not a pipe, so any `|` left inside a piece is one.

    A `;` inside `$( )` or `( )` splits the statement early: substitutions
    and groups are not tracked. See `without_quotes` for what else is not."""
    return _STATEMENT_END.split(without_quotes(without_heredocs(command)))
