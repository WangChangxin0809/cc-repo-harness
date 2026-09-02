#!/usr/bin/env python3
"""Guard: block editing a check until it can no longer say no.

The failure this stops is small, quiet and entirely rational in the moment. A
gate goes red. The change is right and the gate is wrong, or looks wrong, or
would take an hour to satisfy. So the gate is edited: an assertion deleted, a
`|| true` appended, a body replaced with `return 0`. Everything is green
again, and it will stay green for every change after this one.

That is what makes it a guard rather than a gate. Once the check cannot fail,
the thing that would have caught the mistake is the thing that changed, and no
later run can tell you it happened -- every subsequent green square is
indistinguishable from a green square that meant something.

## Only an edit, never a new file

A new check that always passes is a different problem, and it belongs to the
person reviewing it rather than to a hook: everybody's first commit of a check
is a stub. What this refuses is **replacing** existing content with content
that has no way to fail, which is the shape of a silencing and not of a
beginning. A `Write` to a path that does not exist yet is left alone.

## What counts as a check, and why the list is short

`gates/`, `guards/`, `tests/`, `test_*`, `*_test.*`, `*selftest*`, and
`.github/workflows/`. A wider net -- anything named `check_*`, say -- starts
refusing edits to `check_output.py`, and a guard that fires on ordinary work
is a guard somebody turns off. That is not hypothetical: `check_*.py` was in
this list until its own near-miss case caught it, and the real gates were
already covered by `gates/` anyway.

## Two ways a check stops being able to fail

**It loses every failure path.** No non-zero exit, no raise, no assert, no
`expect`, no `fail`. A Python check whose body becomes `return 0`, a shell
script that becomes `exit 0`.

**It gains a swallow.** `|| true`, `continue-on-error: true`, `--no-verify`,
`pytest.mark.skip`, `it.skip(`, `xit(`, `t.Skip(`. These keep the failure path
and route around it, which reads identically from outside.

A swallow is looked for on code lines only. A comment that *names* one -- a
workflow header saying no step may use `|| true` -- is the rule being written
down, not broken, and a guard that refuses the edit beneath it is a guard that
gets turned off. A line is a comment when its first non-blank character is
`#`, which is what YAML, shell and Python share; strings are not parsed.
"""

from __future__ import annotations

import os
import re

_IS_CHECK = re.compile(
    r"(?:^|/)(?:gates|guards|tests?)/"
    r"|(?:^|/)test_[^/]*$"
    r"|_test\.[A-Za-z0-9]+$"
    r"|(?:^|/)[^/]*selftest[^/]*$"
    r"|(?:^|/)\.github/workflows/[^/]+\.ya?ml$")

# A way for the file to report failure.
_CAN_FAIL = re.compile(
    r"\braise\b|\bassert\b|\bexpect\(|\bfail\b"
    r"|sys\.exit\(\s*(?![0O]\s*\))"
    r"|\bexit\s+[1-9]"
    r"|\breturn\s+[1-9]"
    r"|\bt\.Error|\bt\.Fatal"
    r"|::error::"
    r"|\bexit\(\s*[1-9]")

_SWALLOWS = (
    (re.compile(r"\|\|\s*true\b"), "`|| true`"),
    (re.compile(r"^\s*continue-on-error:\s*true\b", re.M),
     "`continue-on-error: true`"),
    (re.compile(r"--no-verify\b"), "`--no-verify`"),
    (re.compile(r"@?\bpytest\.mark\.skip\b"), "`pytest.mark.skip`"),
    (re.compile(r"\b(?:it|describe|test)\.skip\s*\("), "a skipped test"),
    (re.compile(r"\bxit\s*\(|\bxdescribe\s*\("), "a skipped test"),
    (re.compile(r"\bt\.Skip\s*\("), "`t.Skip`"),
    (re.compile(r"@Ignore\b|@Disabled\b"), "`@Ignore`"),
)

# Content too small to be a check either way -- a stub, a placeholder, a file
# being emptied before being written properly. Below this the rule cannot tell
# a silencing from a beginning, so it says nothing.
MIN_BODY = 12

REASON_MUTE = """\
Blocked: this replaces {name} with something that cannot fail.

    {preview}

Nothing in the new content raises, asserts, or exits non-zero, so from here on
it reports success for every change -- including the one it was written to
catch. No later run can tell you that happened: a green square from a check
that cannot go red looks exactly like a green square that meant something.

If the check is wrong, change what it checks and watch it fail on the case it
should catch. If it is genuinely obsolete, delete the file -- an absent check
is visible and a mute one is not.
"""

REASON_SWALLOW = """\
Blocked: this adds {what} to {name}.

The failure path is still there and nothing reaches it. A check that is routed
around reports success exactly like a check that passed, and the difference is
invisible from the outside -- which is the whole reason it gets added under
time pressure.

If a step is genuinely allowed to fail, say why in a comment beside it, so the
next person reads a decision instead of a workaround.
"""


def _name(path: str) -> str:
    return os.path.basename((path or "").replace("\\", "/")) or path


def _code_lines(body: str) -> str:
    """The body with `#` comment lines removed; line layout is otherwise kept."""
    return "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#"))


def check(tool_name: str, tool_input: dict) -> str | None:
    # An Edit replaces what is there. A Write may be a first draft, and
    # everybody's first commit of a check is a stub.
    if tool_name not in ("Edit", "MultiEdit"):
        return None
    path = (tool_input.get("file_path") or "").replace("\\", "/")
    if not _IS_CHECK.search(path):
        return None
    body = tool_input.get("new_string")
    if body is None:
        return None

    code = _code_lines(body)
    for pattern, what in _SWALLOWS:
        if pattern.search(code):
            return REASON_SWALLOW.format(what=what, name=_name(path))

    # The mute rule does not apply to a workflow. A YAML step does not raise
    # or assert -- its failure path is the exit code of whatever it runs, and
    # that is not in the text being edited. Reading `- run: pytest -q` as a
    # check that can no longer fail is precisely backwards. Workflows are held
    # to the swallow rule above, which is the one that fits them.
    if path.endswith((".yml", ".yaml")):
        return None

    if len(body.strip()) >= MIN_BODY and not _CAN_FAIL.search(body):
        preview = "\n    ".join(body.strip().splitlines()[:4])
        return REASON_MUTE.format(name=_name(path), preview=preview)
    return None


CASES = [
    # The probe: a gate's body replaced with one that returns success.
    ("Edit", {"file_path": "scripts/gates/check_something.py",
              "old_string": "", "new_string": "def main():\n    return 0\n"},
     True),
    ("Edit", {"file_path": "shared/scripts/gates/check_docs_index.py",
              "old_string": "", "new_string": "import sys\nsys.exit(0)\n"},
     True),
    ("Edit", {"file_path": "tests/test_billing.py", "old_string": "",
              "new_string": "def test_totals():\n    pass\n"}, True),
    # Routed around rather than muted.
    ("Edit", {"file_path": ".github/workflows/ci.yml", "old_string": "",
              "new_string": "      - run: pytest -q || true\n"}, True),
    ("Edit", {"file_path": ".github/workflows/ci.yml", "old_string": "",
              "new_string": "    continue-on-error: true\n"}, True),
    ("Edit", {"file_path": "tests/test_billing.py", "old_string": "",
              "new_string": "@pytest.mark.skip\ndef test_totals():\n"
                            "    assert total() == 3\n"}, True),
    ("Edit", {"file_path": "frontend/tests/cart_test.js", "old_string": "",
              "new_string": "it.skip('adds up', () => { expect(1).toBe(1) })"},
     True),
    # Near misses: a check being made stricter, and ordinary work elsewhere.
    ("Edit", {"file_path": "scripts/gates/check_something.py", "old_string": "",
              "new_string": "def main():\n    if broken():\n"
                            "        return 1\n    return 0\n"}, False),
    ("Edit", {"file_path": "tests/test_billing.py", "old_string": "",
              "new_string": "def test_totals():\n    assert total() == 3\n"},
     False),
    ("Edit", {"file_path": ".github/workflows/ci.yml", "old_string": "",
              "new_string": "      - run: pytest -q\n"}, False),
    # A comment may *mention* a swallow. This repository's own ci.yml header
    # says no step may use `|| true`, and editing a step beneath it was refused.
    ("Edit", {"file_path": ".github/workflows/ci.yml", "old_string": "",
              "new_string": "# Exit 2 is never a pass, which is the reason no\n"
                            "# step is allowed to swallow a status with `|| true`.\n"
                            "      - run: python3 scripts/check.py\n"}, False),
    # ...but a comment does not launder the code line beneath it.
    ("Edit", {"file_path": ".github/workflows/ci.yml", "old_string": "",
              "new_string": "# never `|| true` here\n"
                            "      - run: kill $PID || true\n"}, True),
    # The probe's own twin: an ordinary source edit.
    ("Edit", {"file_path": "src/main.py", "old_string": "",
              "new_string": "# an ordinary change\n"}, False),
    # A new check may legitimately begin as a stub; that is a review's job.
    ("Write", {"file_path": "shared/scripts/gates/check_new_thing.py",
               "content": "#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n"},
     False),
    # Too small to tell a silencing from a beginning.
    ("Edit", {"file_path": "tests/test_x.py", "old_string": "",
              "new_string": "\n"}, False),
    # `check_output` is not a check, and this is why the path list is short.
    ("Edit", {"file_path": "src/util/check_output.py", "old_string": "",
              "new_string": "def run(cmd):\n    return subprocess.run(cmd)\n"},
     False),
    ("Bash", {"command": "pytest -q || true"}, False),
]
