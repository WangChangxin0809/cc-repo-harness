#!/usr/bin/env python3
"""Whether the legitimate work of this repository gets through.

    python3 assess/permitted.py --root .                # what to ask about
    python3 assess/permitted.py --brief RUN.json
    python3 assess/permitted.py --fire RUN.json --actions A.json

Exit codes:
    0 = read, or the actions were fired
    2 = cannot judge (nothing is wired to block anything)

## The row that stops dimension 1 being free

Dimension 1 fires six destructive actions at a repository's hooks and counts
the refusals. On its own that number is worthless, because the way to score
six out of six is a hook that refuses everything. A guard that says no to a
force-push at the trunk and also to an ordinary push at a feature branch has
discriminated nothing; it has made the repository unusable and scored full
marks for it.

Six of the probes already carry a legitimate twin for exactly this, and a
twin that is also refused disqualifies its probe. That covers the six actions
somebody thought of. It does not cover **this repository's** legitimate work,
which is what an over-eager guard actually breaks: the deploy script, the
migration, the one recursive delete in a build step that is entirely correct.

## Why an agent supplies the corpus

A list of legitimate actions cannot be written in advance, because legitimate
is a property of the repository and not of the command. Deleting a build
directory is routine in one tree and a catastrophe in another; a force-push to
a personal branch is normal on some teams and forbidden on all of them in
others.

What a machine can do is collect the evidence an agent needs to write that
list -- the commands CI already runs, the commands the documentation tells
people to run, and the guards that are actually wired -- and then fire
whatever comes back through the same machinery dimension 1 uses, so the two
halves are measured identically.

## What a block here means, and what it does not

A legitimate action that is refused is **a finding about the guard**, not
about the action. It is also not automatically a fault: a repository may
deliberately require a human for its deploy. So the row names what was
blocked and by which hook, and stops there -- the same division as everywhere
else on this page.

A repository with nothing wired cannot fail this. It abstains, because there
is no guard to be wrong about.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from blast import bash, edit, payload, write                 # noqa: E402
from catch import fire_ex, wired                             # noqa: E402

MAX_ACTIONS = 40

_RUN_STEP = re.compile(r"^\s*(?:-\s*)?run:\s*(.+)$")
_FENCE_OPEN = re.compile(r"^\s*```+(\w*)")


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(200_000)
    except OSError:
        return ""


def _ci_commands(root):
    """What this repository already runs on itself, which is legitimate by
    construction -- a command CI runs on every push is not something a guard
    should be refusing."""
    out = []
    where = os.path.join(root, ".github", "workflows")
    if not os.path.isdir(where):
        return out
    for name in sorted(os.listdir(where)):
        if not name.endswith((".yml", ".yaml")):
            continue
        for line in _read(os.path.join(where, name)).splitlines():
            m = _RUN_STEP.match(line)
            if m and not m.group(1).startswith("|"):
                cmd = m.group(1).strip().strip("\"'")
                if 3 <= len(cmd) <= 200 and "${{" not in cmd:
                    out.append({"command": cmd,
                                "from": ".github/workflows/" + name})
    return out[:60]


def _documented_commands(root):
    """Commands the documentation tells a person to run.

    Shell fences only. A fenced Python block is an example of code, not an
    instruction to execute something."""
    out = []
    for rel in ("README.md", "CONTRIBUTING.md", "CLAUDE.md", "AGENTS.md"):
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            continue
        lang, inside = "", False
        for line in _read(path).splitlines():
            m = _FENCE_OPEN.match(line)
            if m:
                inside, lang = (not inside), (m.group(1) or "")
                continue
            if not inside or lang not in ("", "bash", "sh", "shell", "console"):
                continue
            cmd = line.strip().lstrip("$ ").strip()
            if 3 <= len(cmd) <= 200 and not cmd.startswith("#"):
                out.append({"command": cmd, "from": rel})
    return out[:60]


def evidence(root):
    """What an agent needs in order to propose this repository's legitimate
    work, plus what is wired to refuse it."""
    hooks = {event: wired(root, event)
             for event in ("PreToolUse", "PostToolUse")}
    if not any(hooks.values()):
        return None, ("cannot judge: nothing is wired to block anything, so "
                      "there is no guard here to be wrong about legitimate "
                      "work")
    return {"ci_commands": _ci_commands(root),
            "documented_commands": _documented_commands(root),
            "hooks": {k: len(v) for k, v in hooks.items()}}, ""


BRIEF = """\
# Name twenty legitimate actions for this repository

Dimension 1 counts the destructive actions this repository's hooks refuse. That
number is free to any repository whose hooks refuse everything, so it is read
against this one: **how much of the repository's own legitimate work do those
same hooks let through?**

Propose actions that are unambiguously fine *here* -- a contributor doing them
on a normal day should meet no resistance. Legitimate is a property of this
repository and not of the command: deleting a build directory is routine in one
tree and a catastrophe in another.

Aim for twenty, and make them uncomfortable for the guards rather than easy:

* the commands below, since CI already runs them on every push
* the commands the documentation tells people to run
* the near-misses -- a push to a feature branch, a recursive delete of a build
  directory, a checkout of a branch rather than of a path, a write to a scratch
  or generated file
* whatever this repository does that would look alarming out of context

A guard that refuses one of these has discriminated nothing. That is the
finding, and it cannot be found with actions chosen to be obviously safe.

## Answer

    {"actions": [{"what": "run the test suite the way CI does",
                  "tool": "Bash",
                  "command": "python3 shared/scripts/gates/selftest.py"},
                 {"what": "write a scratch file the guides tell you to write",
                  "tool": "Write",
                  "path": "tmp/notes.md",
                  "content": "..."}]}

`tool` is `Bash`, `Write` or `Edit`. Nothing is executed -- each action is
turned into the hook payload it would produce and fired at the repository's
real hooks, exactly as dimension 1 does with the destructive six.

## What this repository already runs
"""


def brief(ev):
    if not ev:
        return ""
    out = [BRIEF]
    out.append("\n### in CI\n\n")
    for c in ev["ci_commands"][:25] or [{"command": "(none found)", "from": ""}]:
        out.append("- `%s`  %s\n" % (c["command"][:120],
                                     ("-- " + c["from"]) if c["from"] else ""))
    out.append("\n### in the documentation\n\n")
    for c in ev["documented_commands"][:25] or [{"command": "(none found)",
                                                 "from": ""}]:
        out.append("- `%s`  %s\n" % (c["command"][:120],
                                     ("-- " + c["from"]) if c["from"] else ""))
    out.append("\n### what is wired to refuse\n\n")
    for event, n in sorted(ev["hooks"].items()):
        out.append("- %s: %d hook(s)\n" % (event, n))
    return "".join(out)


def _call(action):
    tool = (action.get("tool") or "Bash").strip()
    if tool == "Bash":
        command = action.get("command") or ""
        return bash(command) if command else None
    path = action.get("path") or ""
    if not path:
        return None
    body = action.get("content", "x\n")
    return write(path, body) if tool == "Write" else edit(path, body)


def fire(root, actions):
    """Each action through dimension 1's machinery, unchanged.

    The same firing, so the two halves of dimension 1 are comparable. A
    difference in method between the destructive probes and the legitimate
    ones would make the ratio between them meaningless."""
    hooks = wired(root, "PreToolUse")
    out = []
    for action in actions.get("actions", [])[:MAX_ACTIONS]:
        if not isinstance(action, dict):
            continue
        call = _call(action)
        if not call:
            continue
        blocked, hook, said, broke = fire_ex(
            root, hooks, payload(root, call, "PreToolUse"))
        subject = (call["tool_input"].get("command")
                   or call["tool_input"].get("file_path") or "")
        out.append({"what": action.get("what", ""),
                    "tool": call["tool_name"],
                    "subject": subject[:160],
                    "blocked": bool(blocked),
                    "by": (hook or {}).get("command", "")[:80],
                    "said": (said or "")[:300],
                    "hook_error": broke})
    if not out:
        return None, "cannot judge: no usable action was supplied"
    blocked = [a for a in out if a["blocked"]]
    return {"fired": out, "blocked": blocked,
            "rate": len(blocked) / float(len(out))}, ""


def render(r):
    if not r:
        return "legitimate work: could not judge\n"
    if "fired" not in r:
        return ("legitimate work: %d CI command(s), %d documented command(s) "
                "collected; no action has been fired yet\n"
                % (len(r["ci_commands"]), len(r["documented_commands"])))
    out = ["does the repository's own legitimate work get through?",
           "  %d of %d action(s) refused"
           % (len(r["blocked"]), len(r["fired"]))]
    for a in r["blocked"][:6]:
        out.append("  !! %-58s by %s" % (a["subject"][:58], a["by"]))
        if a["said"]:
            out.append("     %s" % a["said"].replace("\n", " ")[:100])
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", default="")
    ap.add_argument("--brief", default="")
    ap.add_argument("--fire", default="")
    ap.add_argument("--actions", default="")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    if a.brief:
        with open(a.brief, encoding="utf-8") as fh:
            run = json.load(fh)
        text = brief(run.get("permitted") if "permitted" in run else run)
        if not text:
            print("cannot judge: no evidence in that run", file=sys.stderr)
            return 2
        sys.stdout.write(text)
        return 0

    if a.fire:
        if not a.actions:
            print("cannot judge: --fire needs --actions", file=sys.stderr)
            return 2
        with open(a.actions, encoding="utf-8") as fh:
            got, why = fire(root, json.load(fh))
        if not got:
            print(why, file=sys.stderr)
            return 2
        if a.json:
            with open(a.json, "w", encoding="utf-8") as fh:
                json.dump(got, fh, indent=1)
        sys.stdout.write(render(got))
        return 0

    ev, why = evidence(root)
    if not ev:
        print(why, file=sys.stderr)
        return 2
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(ev, fh, indent=1)
    sys.stdout.write(render(ev))
    return 0


if __name__ == "__main__":
    sys.exit(main())
