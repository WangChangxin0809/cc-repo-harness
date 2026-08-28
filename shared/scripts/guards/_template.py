#!/usr/bin/env python3
"""Guard template. Copy to `<rule_name>.py` in this directory -- the dispatcher
picks it up automatically; files starting with `_` are skipped.

Before writing one, check the rule actually needs a guard:

* Absolute, no exceptions, no explanation needed  -> `permissions.deny`, free
* "Always invoke it this way"                     -> a wrapper script + a gate
  forbidding the bare form. This survives a harness change and removes the rule
  from the documentation rather than restating it.
* Judgeable from the worktree after the fact      -> a gate, cheaper
* Damage is complete the moment it runs           -> a guard. This file.
"""

from __future__ import annotations

REASON = """\
Blocked: <what is about to happen, in one line>.

<Why it is unrecoverable or undetectable afterwards. This is the part that
generalises -- it teaches the failure mode, not just this command.>

Instead:
    <the concrete replacement command>

Rule: <docs/path.md §n>
"""


def check(tool_name: str, tool_input: dict) -> str | None:
    """Return None to allow, or a reason string to block.

    Match narrowly and return early: a guard that only cares about Bash should
    cost nothing on a Read. The dispatcher cannot do this for you, because only
    this guard knows what it cares about.

    Write the reason as a REPLACEMENT, not a refusal. A bare block teaches
    nothing -- the model retries a variant or abandons a task it should have
    completed differently. A concrete substitute changes the next action.
    """
    if tool_name != "Bash":
        return None
    command = tool_input.get("command", "")
    if "PATTERN" in command:
        return REASON
    return None


# (tool_name, tool_input, should_block) -- read by selftest.py
#
# At least one True and one False are required; the runner fails the guard
# otherwise. A guard with only positive cases passes every test while blocking
# everything, and you find out when it has cost someone a day.
#
# Make at least one False case a NEAR MISS: something sharing the trigger
# substring but legitimate. That is where the matcher is actually wrong -- the
# obvious negatives ("git status") pass no matter how broken the pattern is.
CASES = [
    ("Bash", {"command": "the violating command"}, True),
    ("Bash", {"command": "a legitimate near miss"}, False),
    ("Read", {"file_path": "x"}, False),
]
