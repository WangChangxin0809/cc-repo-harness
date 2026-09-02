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
script that becomes `exit 0`. A guard fails by returning a reason, so under
`guards/` a `return` of anything but `None`, `0`, `False` or an empty string
is a failure path too. During this repository's own assessment a reader
replaced a whole guard with a shorter one that still returned its reason, and
this file refused it as mute, because it only knew how a gate or a test says
no.

**It gains a swallow.** `|| true`, `continue-on-error: true`, `--no-verify`,
`pytest.mark.skip`, `it.skip(`, `xit(`, `t.Skip(`. These keep the failure path
and route around it, which reads identically from outside.

A swallow is looked for on code lines only. A comment that *names* one -- a
workflow header saying no step may use `|| true` -- is the rule being written
down, not broken, and a guard that refuses the edit beneath it is a guard that
gets turned off. A line is a comment when its first non-blank character is
`#`, which is what YAML, shell and Python share; strings are not parsed.

## Judged on the file, not on the edit

The mute rule reads the file as it will be after the edit -- `old_string`
replaced by `new_string`, the whole file when `old_string` is empty, which is
how the instrument sends one, every entry of a MultiEdit in order -- and
refuses only when the file could fail before and cannot after. Judged on the
edited text alone, a reworded comment or a changed constant in a check is
"something that cannot fail", because a partial edit rarely carries a failure
path in its own lines. That never fired while the dispatcher was wired to
Bash alone; the first Edit it saw would have had this guard switched off
within the hour.

A file this guard cannot read is judged on the new content alone when the
edit replaces all of it, and left alone when it does not: a partial edit to a
file nobody can see is not judgeable, and the dispatcher fails open by design.
An `old_string` that is not in the file is left alone too; the edit would not
apply.
"""

from __future__ import annotations

import os
import re

_SELF = os.path.abspath(__file__)

_IS_CHECK = re.compile(
    r"(?:^|/)(?:gates|guards|tests?|selftests?)/"
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

# Some checks report failure by returning a reason rather than by raising:
# a guard returns one from `check()`, and a selftest case returns the problem
# it found, or None. For those, any `return` but None, 0, False or an empty
# string is a failure path -- judging them by `assert` alone reads a whole
# convention as mute and refuses ordinary work on it.
_BY_RETURN = re.compile(r"(?:^|/)guards/|(?:^|/)selftests?/")
_GUARD_CAN_FAIL = re.compile(
    _CAN_FAIL.pattern
    + r"|\breturn[ \t]+(?!None\b|0\b|False\b|[\"']{2}|#)\S")

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

# A file left too small to be a check either way -- a stub, a placeholder, a
# file being emptied before being written properly. Below this the rule cannot
# tell a silencing from a beginning, so it says nothing.
MIN_BODY = 12

REASON_MUTE = """\
Blocked: after this edit {name} cannot fail.

    {preview}

Nothing left in the file raises, asserts, exits non-zero or, for a guard,
returns a reason, so from here on it reports success for every change --
including the one it was written to catch. No later run can tell you that
happened: a green square from a check that cannot go red looks exactly like a
green square that meant something.

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


def _edits(tool_name: str, tool_input: dict) -> list:
    """Each replacement the call proposes, as (old, new, everywhere)."""
    entries = ([tool_input] if tool_name == "Edit"
               else tool_input.get("edits") or [])
    out = []
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("new_string"), str):
            out.append((entry.get("old_string") or "", entry["new_string"],
                        bool(entry.get("replace_all"))))
    return out


def _read(path: str) -> str | None:
    """The file as it is now, or None when it cannot be read."""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, ValueError):
        return None


def _apply(text: str, edits: list) -> str | None:
    """The file after the edits, or None when one of them would not apply."""
    for old, new, everywhere in edits:
        if not old:
            text = new
        elif old not in text:
            return None
        else:
            text = text.replace(old, new, -1 if everywhere else 1)
    return text


def _preview(edits: list) -> str:
    """The first lines of what the edit puts in -- or, when it only removes,
    of what it takes out."""
    put = [line for _, new, _ in edits for line in new.strip().splitlines()]
    if put:
        return "\n    ".join(put[:4])
    gone = [line for old, _, _ in edits for line in old.strip().splitlines()]
    return "\n    ".join(["removed:"] + gone[:3])


def check(tool_name: str, tool_input: dict) -> str | None:
    # An Edit replaces what is there. A Write may be a first draft, and
    # everybody's first commit of a check is a stub.
    if tool_name not in ("Edit", "MultiEdit"):
        return None
    path = (tool_input.get("file_path") or "").replace("\\", "/")
    if not _IS_CHECK.search(path):
        return None
    edits = _edits(tool_name, tool_input)
    if not edits:
        return None

    for _, new, _ in edits:
        code = _code_lines(new)
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

    can_fail = _GUARD_CAN_FAIL if _BY_RETURN.search(path) else _CAN_FAIL
    before = _read(tool_input.get("file_path") or "")
    if before is None:
        # A file this guard cannot see. When the edit replaces all of it, the
        # new content is the file and is judged as such; when it does not,
        # there is nothing to judge, and this dispatcher fails open.
        if edits[0][0]:
            return None
        before, could = "", True
    else:
        could = bool(can_fail.search(before))
    after = _apply(before, edits)
    if after is None or not could:
        return None
    if len(after.strip()) >= MIN_BODY and not can_fail.search(after):
        return REASON_MUTE.format(name=_name(path), preview=_preview(edits))
    return None


# The reader's replacement of no_computed_delete.py, shortened. It returns a
# reason, so it can still say no.
_STILL_REFUSES = (
    "import re\n"
    "\n"
    "_COMPUTED = re.compile(r\"\\$\\(|`\")\n"
    "REASON = \"Blocked: {command} deletes a list of paths that does not "
    "exist yet.\"\n"
    "\n"
    "\n"
    "def check(tool_name, tool_input):\n"
    "    if tool_name != \"Bash\":\n"
    "        return None\n"
    "    command = tool_input.get(\"command\", \"\")\n"
    "    if command.startswith(\"rm \") and _COMPUTED.search(command):\n"
    "        return REASON.format(command=command)\n"
    "    return None\n"
    "\n"
    "\n"
    "CASES = [\n"
    "    (\"Bash\", {\"command\": \"rm -rf $(git ls-files)\"}, True),\n"
    "    (\"Bash\", {\"command\": \"rm -rf build/\"}, False),\n"
    "]\n")

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
    # A directory of cases, not a file with `selftest` in its name. This
    # repository split a 6074-line `assess/selftest.py` into
    # `assess/selftests/*_cases.py`, and 192 cases walked out from behind
    # this guard in one commit: the basename rule below stopped matching and
    # nothing in the directory rule did. Its own assessment found it, by
    # aiming the silencing probe at `blast_cases.py` and getting through.
    ("Edit", {"file_path": "shared/scripts/assess/selftests/blast_cases.py",
              "old_string": "", "new_string": "def case_x(t):\n    pass\n"},
     True),
    ("Edit", {"file_path": "scripts/selftest/cases_for_gates.py",
              "old_string": "", "new_string": "import sys\nsys.exit(0)\n"},
     True),
    # And a case module being made stricter is still ordinary work.
    ("Edit", {"file_path": "shared/scripts/assess/selftests/blast_cases.py",
              "old_string": "", "new_string": "def case_x(t):\n"
                            "    if wrong(t):\n        return 'it broke'\n"
                            "    return None\n"}, False),
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
    # The guard refused a guard. During this repository's own assessment a
    # reader replaced the whole of no_computed_delete.py with a shorter guard
    # that still returned its reason and still had a blocking case, and this
    # file called it mute: it only knew how a gate or a test says no. And the
    # mute rule is judged on the file after the edit, not on the edited text,
    # because a partial edit rarely carries a failure path in its own lines --
    # a reworded comment or a changed constant is not a silencing.
    ("Edit", {"file_path": _SELF, "old_string": "MIN_BODY = 12",
              "new_string": "MIN_BODY = 12  # below this a stub and a "
                            "silencing look alike"}, False),
    ("MultiEdit", {"file_path": _SELF,
                   "edits": [{"old_string": "MIN_BODY = 12",
                              "new_string": "MIN_BODY = 12  # a stub and a "
                                            "silencing look alike"}]}, False),
    ("Edit", {"file_path": "scripts/guards/no_thing.py", "old_string": "",
              "new_string": _STILL_REFUSES}, False),
    # ...and a guard that can no longer refuse is still a silencing, however
    # the edit arrives. A MultiEdit was never judged at all before this.
    ("Edit", {"file_path": _SELF, "old_string": "",
              "new_string": "def check(tool_name, tool_input):\n"
                            "    return None\n"}, True),
    ("MultiEdit", {"file_path": _SELF,
                   "edits": [{"old_string": "",
                              "new_string": "def check(tool_name, tool_input):\n"
                                            "    return None\n"}]}, True),
]
