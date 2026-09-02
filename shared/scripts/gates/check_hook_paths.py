#!/usr/bin/env python3
"""Gate: a wired hook command must resolve from any working directory.

    python3 scripts/gates/check_hook_paths.py [--root .]

A hook runs in whatever directory Claude Code happens to be in, and that
changes on a `cd` and again inside a `git worktree`. A command written as a
bare relative path -- `python3 scripts/guards/dispatch.py` -- only resolves
when the session's cwd is the repository root, and it fails silently in the
worst direction: `python3 <missing>.py` exits 2, which is exactly the code
Claude Code reads as *block*. A broken path does not stop protecting, it
blocks every matching tool call while reporting an unreadable "can't open
file" as the reason. For a `Stop` hook it is worse: the `stop_hook_active`
short-circuit that prevents an unbreakable blocked-forever loop lives inside
the script that never runs, so the session cannot be ended at all.

This is a **gate**, not a guard. A guard reads one proposed tool call before
it runs; there is no tool call here to intercept -- the defect is a standing
property of committed configuration, sitting in the tree whether or not
anyone touches it this session. That is exactly the state a gate judges at
CI time, the same distinction `check_no_machine_paths.py` and
`check_layering.py` are built on.

## What counts as anchored

`${CLAUDE_PROJECT_DIR}/...` and `${CLAUDE_PLUGIN_ROOT}/...` are the two
placeholders Claude Code itself substitutes before running a command, so a
path behind either one resolves the same way from anywhere. An absolute path
resolves the same way from anywhere by construction. A bare program name with
no path separator -- `jq`, `git`, `python3` used as the interpreter itself --
is looked up on `PATH`, which does not depend on the working directory
either. All three are left alone.

What is not left alone: a script argument or a directly-invoked program that
names a filesystem path (contains a `/`) without any of the above anchors.
`scripts/guards/dispatch.py`, `./hook.py`, and `../shared/hook.py` are all
resolved relative to whatever directory the process happens to start in, and
that is precisely the bug this gate exists to catch a second time.

## What is deliberately not flagged

A shell one-liner such as `command -v jq >/dev/null || echo ... >&2` names no
script to run at all -- `jq` is a bare command word, and `/dev/null` is a
redirect target, not something a hook command needs to locate. Redirect
targets are stripped before judgment for the same reason: a relative *output*
path is a different, unrelated property from a relative *hook script* path,
and flagging it here would be answering a question nobody asked.

## Where it looks

Every `settings.json`, `settings.local.json`, and `hooks.json` anywhere under
`--root`, skipping `.git` and common vendor directories. That covers a
project's `.claude/settings.json`, a personal `.claude/settings.local.json`
that never reaches git, and a plugin's own `hooks/hooks.json` -- and it needs
no knowledge of where any particular repository chooses to keep them. A
repository that scaffolds its own wiring is judged the same way once that
wiring lands on disk: this gate reads the tree, not the scaffolder.

Exit 2 -- cannot judge -- for a hook-wiring file that does not parse as JSON,
or a command whose quoting cannot be tokenized at all. Exit 2 is never a pass.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys

# Programs that take a script path as an argument, rather than being the
# thing invoked. Matched on the basename, so `/usr/bin/python3` and `python3`
# are the same check.
INTERPRETERS = {
    "python", "python3", "python2",
    "node", "nodejs", "deno", "bun",
    "bash", "sh", "zsh", "dash", "ksh",
    "ruby", "perl", "pwsh", "powershell",
}

# `>`, `>>`, `<`, `<<`, and their numbered-descriptor forms (`2>`, `1>>`).
# `&>` and `&>>` too. Matched at the start of a token because shlex leaves a
# glued redirect (`>/dev/null`) as one word.
_REDIRECT = re.compile(r"^\d*(&>>|&>|>>|>|<<|<)")

_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

SKIP_DIRS = {".git", "node_modules", "vendor", "__pycache__", ".venv", "venv",
             "target", "dist", "build", ".mypy_cache", ".ruff_cache"}

WIRING_NAMES = {"settings.json", "settings.local.json", "hooks.json"}


def _split_pipeline(words):
    """Words, cut into the argv lists between `&&` `||` `;` `|` `&`."""
    pieces, current = [], []
    for w in words:
        if w in ("&&", "||", ";", "|", "&"):
            pieces.append(current)
            current = []
        else:
            current.append(w)
    pieces.append(current)
    return pieces


def _drop_redirects(words):
    """Strip `> file`, `>>file`, `2> /dev/null` and the like from one argv."""
    out, skip_next = [], False
    for w in words:
        if skip_next:
            skip_next = False
            continue
        if _REDIRECT.match(w):
            if _REDIRECT.fullmatch(w):
                skip_next = True  # the target is the next word, not this one
            continue
        out.append(w)
    return out


def _script_argument(words):
    """The path this argv names, if it names one at all -- else None.

    `env` is unwrapped first: `env python3 x.py` names `x.py`, not `env`,
    and stopping at `env` (always an absolute-looking bare word) would wave
    the real, unresolved argument through unexamined.
    """
    words = _drop_redirects(words)
    if not words:
        return None
    if os.path.basename(words[0]) == "env":
        rest = words[1:]
        i = 0
        while i < len(rest) and (rest[i].startswith("-") or _ASSIGNMENT.match(rest[i])):
            i += 1
        words = rest[i:]
        if not words:
            return None

    argv0 = words[0]
    if os.path.basename(argv0) in INTERPRETERS:
        for w in words[1:]:
            if w.startswith("-"):
                if w in ("-c", "-m"):
                    return None  # inline code or a module name, not a path
                continue
            return w
        return None
    if "/" in argv0:
        return argv0
    return None  # a bare program name: resolved on PATH, not on cwd


def unresolved_paths(command):
    """Path-like arguments in `command` that only resolve from one directory.

    None means the command could not be tokenized at all -- unbalanced
    quoting -- which the caller must treat as cannot-judge, not as clean."""
    try:
        words = shlex.split(command, posix=True)
    except ValueError:
        return None
    bad = []
    for piece in _split_pipeline(words):
        candidate = _script_argument(piece)
        if candidate is None:
            continue
        if candidate.startswith(("${", "/", "~")):
            continue
        bad.append(candidate)
    return bad


def _commands_in(data):
    """Every hook `command` string this parsed settings/hooks document wires."""
    out = []
    hooks = data.get("hooks") if isinstance(data, dict) else None
    for entries in (hooks or {}).values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for h in entry.get("hooks") or []:
                if isinstance(h, dict) and h.get("command"):
                    out.append(str(h["command"]))
    return out


def wiring_files(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name in WIRING_NAMES:
                out.append(os.path.join(dirpath, name))
    return sorted(out)


def findings(root):
    """(bad, cannot_judge): unresolved commands, and files that defeated judgment."""
    bad, cannot_judge = [], []
    for path in wiring_files(root):
        rel = os.path.relpath(path, root)
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            cannot_judge.append((rel, f"does not parse as JSON: {exc}"))
            continue
        for command in _commands_in(data):
            paths = unresolved_paths(command)
            if paths is None:
                cannot_judge.append((rel, f"cannot tokenize command: {command!r}"))
                continue
            for token in paths:
                bad.append((rel, command, token))
    return bad, cannot_judge


REMEDY = """
Anchor the command so it resolves the same way from any directory:

    python3 "${CLAUDE_PROJECT_DIR}/path/to/script.py"     # a project hook
    python3 "${CLAUDE_PLUGIN_ROOT}/path/to/script.py"     # a plugin hook

Both are quoted because these are shell command strings, and the docs ask for
quotes around the placeholder there. See docs/decisions/0055-a-relative-hook-
command-is-a-hook-that-is-not-there.md for why a relative path here fails as
a block, not as an absence.
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()

    root = os.path.abspath(a.root)
    if not os.path.isdir(root):
        print("could not judge: no such directory " + root, file=sys.stderr)
        return 2

    bad, cannot_judge = findings(root)
    if cannot_judge:
        print("%d hook-wiring file(s) could not be judged:" % len(cannot_judge),
              file=sys.stderr)
        for rel, why in cannot_judge:
            print("  %s: %s" % (rel, why), file=sys.stderr)
        return 2

    if not bad:
        print("every wired hook command resolves from any working directory")
        return 0

    print("%d wired hook command(s) reference a script by a path that only "
          "resolves from one directory:" % len(bad), file=sys.stderr)
    for rel, command, token in bad[:20]:
        print("  %s: %r  (unresolved: %s)" % (rel, command, token), file=sys.stderr)
    if len(bad) > 20:
        print("  ... and %d more" % (len(bad) - 20), file=sys.stderr)
    print(REMEDY, file=sys.stderr)
    return 1


# Unit-level cases: (command, must be reported).
CASES = (
    ('python3 "${CLAUDE_PROJECT_DIR}/shared/scripts/guards/dispatch.py"', False),
    ('python3 "${CLAUDE_PLUGIN_ROOT}/hooks/first_look.py"', False),
    ('python3 shared/scripts/guards/dispatch.py', True),
    ('python3 scripts/context/session_brief.py', True),
    ('python3 "${CLAUDE_PROJECT_DIR}/x.py"', False),
    ('/usr/bin/python3 "${CLAUDE_PROJECT_DIR}/x.py"', False),
    ('env python3 scripts/x.py', True),
    ('/abs/scripts/hook.py', False),
    ('./scripts/hook.py', True),
    ('jq --version', False),
    ('python3 -c "import os"', False),
    # The example straight from the routing skill: no script named at all.
    ('command -v jq >/dev/null || echo "install jq: brew install jq" >&2', False),
)


def selftest(verbose=True):
    import tempfile

    bad_cases = 0
    for command, want in CASES:
        got = bool(unresolved_paths(command))
        ok = got == want
        bad_cases += not ok
        if verbose or not ok:
            print("%s %-70s %s" % ("ok  " if ok else "FAIL", command[:70],
                                   "reported" if got else "allowed"))

    def wired(path, command, event="PreToolUse", matcher="Bash"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cfg = {"hooks": {event: [{"matcher": matcher,
                                  "hooks": [{"type": "command", "command": command}]}]}}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)

    # A planted relative hook command must fail the gate, by name.
    with tempfile.TemporaryDirectory() as d:
        wired(os.path.join(d, ".claude", "settings.json"),
              'python3 shared/scripts/guards/dispatch.py')
        rc = main(["--root", d])
        ok = rc == 1
        bad_cases += not ok
        print("%s a relative hook command fails the gate (exit %d)"
              % ("ok  " if ok else "FAIL", rc))

    # The near-miss: a shell one-liner naming no script must stay green.
    with tempfile.TemporaryDirectory() as d:
        wired(os.path.join(d, ".claude", "settings.json"),
              'command -v jq >/dev/null || echo "install jq" >&2')
        rc = main(["--root", d])
        ok = rc == 0
        bad_cases += not ok
        print("%s a shell one-liner with no script path passes (exit %d)"
              % ("ok  " if ok else "FAIL", rc))

    # An anchored command, in a plugin's hooks.json rather than settings.json,
    # must also pass -- proving the file-discovery is not settings-only.
    with tempfile.TemporaryDirectory() as d:
        wired(os.path.join(d, "hooks", "hooks.json"),
              'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/run.py"')
        rc = main(["--root", d])
        ok = rc == 0
        bad_cases += not ok
        print("%s an anchored plugin hooks.json passes (exit %d)"
              % ("ok  " if ok else "FAIL", rc))

    # Unparseable wiring must never look like a pass.
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, ".claude", "settings.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        rc = main(["--root", d])
        ok = rc == 2
        bad_cases += not ok
        print("%s a settings.json that does not parse cannot-judges (exit %d)"
              % ("ok  " if ok else "FAIL", rc))

    print("\n%s" % ("all cases pass" if not bad_cases
                    else "%d case(s) failed" % bad_cases))
    return 1 if bad_cases else 0


if __name__ == "__main__":
    sys.exit(main())
