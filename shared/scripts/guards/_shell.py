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
is one place data reliably lives, and this is it.
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
