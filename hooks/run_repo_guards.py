#!/usr/bin/env python3
"""Run the *repository's own* guards — but only ones you have explicitly trusted.

This is the one thing a plugin can do that a skill cannot, and it is worth being
precise about both what it is for and what it costs.

Guards live in the target repository under `scripts/guards/` so that they keep
working after this plugin is uninstalled — that is the whole acceptance
criterion of the harness. But a repository that has guards and has not yet wired
`.claude/settings.json` gets no protection at all, which is the exact window in
which someone is most likely to lose work. This hook covers that window.

## Why the trust gate exists

Running `scripts/guards/dispatch.py` means executing code from the repository,
and that dispatcher imports every `.py` beside it. Without a gate, the sequence

    git clone <a repository you have never read>
    cd <it> && <any Bash tool call>

executes that repository's code, with no prompt, because *this* plugin's hook is
already approved. That launders an unreviewed repo's code through an approval
the user gave to something else. Claude Code deliberately asks before honouring
a project's own `settings.json` hooks; a plugin must not be the way around that.

So: nothing in a repository runs until its guard set has been trusted by path
*and* by content digest. Adding or editing a guard changes the digest and
revokes trust until you look at the change and trust it again. That friction is
the point — it is exactly one look per change to code that runs before every
command you type.

    python3 run_repo_guards.py --trust     # from inside the repository
    python3 run_repo_guards.py --status
    python3 run_repo_guards.py --forget

Trust is per-machine state, not knowledge, so it lives outside the repository —
in `$CLAUDE_CONFIG_DIR/agent-harness/trusted-guards.json` (default `~/.claude`).
That is not a violation of "knowledge lives in the repository": a statement that
*this* machine's user has read *that* code is not a fact about the project, and
committing it would let a pull request grant itself trust.

## The better answer, in one line

Wire the dispatcher into the repository's own `.claude/settings.json`. Then the
repo owns its guards, Claude Code's normal project-trust prompt applies, this
hook stays out of the way, and everything keeps working with the plugin gone.
`scaffold.py` does this for you; this hook exits silently once it is done.

## Cost

This runs before every Bash call in every repository the plugin is enabled for.
A Python interpreter start is ~45 ms and cannot be optimised away from inside;
in the trusted-but-unwired window there is a second one for the dispatcher,
~85 ms total. If that matters to you, wire the dispatcher into the repo (above)
and this hook goes back to a single early-exiting start.

## Contract, per PreToolUse

    stdin  = JSON  {"tool_name": ..., "tool_input": {...}}
    exit 0 = allow (stdout is not shown to the model)
    exit 2 = block; stderr is fed back to the model as the reason
    other  = non-blocking error; stderr is surfaced to the user

Failures here are deliberately non-blocking. A bug in this file must not become
a wall that nobody can get past. The repository's own `selftest.py` is what
proves the guards themselves work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

GUARD_DIR = os.path.join("scripts", "guards")
DISPATCH = os.path.join(GUARD_DIR, "dispatch.py")
SETTINGS = (os.path.join(".claude", "settings.json"),
            os.path.join(".claude", "settings.local.json"))


# --------------------------------------------------------------------------
# repository and trust store
# --------------------------------------------------------------------------

def repo_root(start):
    """Nearest ancestor containing .git. Returns None outside a repository."""
    cur = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def repo_wires_it_already(root):
    """True if the repo invokes the dispatcher from its own settings, in which
    case this hook must stay out: running it twice doubles the latency on every
    Bash call and prints the block reason twice."""
    for rel in SETTINGS:
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                if "guards/dispatch.py" in fh.read():
                    return True
        except OSError:
            continue
    return False


def guard_files(root):
    """Every .py under scripts/guards/, relative and sorted. These are exactly
    the files that get executed, so these are exactly the files hashed."""
    base = os.path.join(root, GUARD_DIR)
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames
                       if d not in ("__pycache__",) and not d.startswith(".")]
        for name in sorted(filenames):
            if name.endswith(".py"):
                out.append(os.path.relpath(os.path.join(dirpath, name), root))
    return sorted(out)


def digest(root):
    """Content digest over the guard set. Names are hashed too, so moving code
    between files does not preserve trust. Returns None if it cannot be read —
    unreadable is not trusted."""
    h = hashlib.sha256()
    for rel in guard_files(root):
        try:
            with open(os.path.join(root, rel), "rb") as fh:
                body = fh.read()
        except OSError:
            return None
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(hashlib.sha256(body).digest())
    return h.hexdigest()


def store_path():
    cfg = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude")
    return os.path.join(cfg, "agent-harness", "trusted-guards.json")


def load_store():
    try:
        with open(store_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"version": 1, "repos": {}}
    if not isinstance(data, dict) or not isinstance(data.get("repos"), dict):
        return {"version": 1, "repos": {}}
    return data


def save_store(data):
    """Atomic, 0600. Two sessions may write this at once; a half-written trust
    file that happens to parse would be the worst possible outcome."""
    path = store_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


# --------------------------------------------------------------------------
# hook mode
# --------------------------------------------------------------------------

NOT_TRUSTED = """\
agent-harness: {root} has guards in scripts/guards/ that are NOT running.

{what}

Those files execute before every Bash command, so nothing here runs them until
you have read them and said so. Review them, then pick one:

  1. Let the repository own its guards. Survives this plugin being removed, and
     is what scaffold.py wires for you. In .claude/settings.json:

     {{"hooks": {{"PreToolUse": [{{"matcher": "Bash", "hooks":
        [{{"type": "command", "command": "python3 scripts/guards/dispatch.py"}}]}}]}}}}

  2. Or trust this checkout, on this machine only:

     python3 "{self}" --trust

Said once per change to the guard set, then silent.
"""


def hook(raw, root):
    dispatch = os.path.join(root, DISPATCH)
    if not os.path.exists(dispatch) or repo_wires_it_already(root):
        return 0

    try:
        json.loads(raw or "{}")
    except ValueError:
        return 0

    current = digest(root)
    store = load_store()
    record = store["repos"].get(root) or {}

    if current is None or record.get("digest") != current:
        # Not trusted, or the guard set changed since it was. Say so once per
        # distinct guard set -- a warning on every Bash call is a warning that
        # gets muted, and then the real one is muted with it.
        if record.get("notified") == current and current is not None:
            return 0
        store["repos"].setdefault(root, {}).update(
            {"notified": current, "digest": record.get("digest")})
        save_store(store)
        what = ("Its guard files could not be read."
                if current is None else
                "Changed since you trusted them:" if record.get("digest")
                else "Never trusted on this machine:")
        listing = "\n".join(f"    {f}" for f in guard_files(root)[:12])
        sys.stderr.write(NOT_TRUSTED.format(
            root=root, what=what + ("\n" + listing if listing else ""),
            self=os.path.abspath(__file__)))
        return 1

    try:
        proc = subprocess.run([sys.executable, dispatch], input=raw, text=True,
                              capture_output=True, cwd=root, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"agent-harness: could not run repo guards: {exc}", file=sys.stderr)
        return 0

    if proc.returncode == 2:
        sys.stderr.write(proc.stderr)
        return 2
    if proc.returncode != 0:
        # The dispatcher itself is broken. Say so once, on stderr, and allow --
        # see the module docstring on why this fails open.
        sys.stderr.write(proc.stderr)
        return 1
    return 0


# --------------------------------------------------------------------------
# management modes
# --------------------------------------------------------------------------

def cmd_trust(root):
    files = guard_files(root)
    if not files:
        print(f"nothing to trust: no .py under {root}/{GUARD_DIR}",
              file=sys.stderr)
        return 2
    current = digest(root)
    if current is None:
        print("cannot judge: a guard file could not be read", file=sys.stderr)
        return 2

    print(f"Trusting {len(files)} file(s) in {root}. These run before every "
          f"Bash call:")
    for rel in files:
        print(f"  {rel}")
    print("\nIf you have not read them, stop and read them now — this is the "
          "only prompt.\n")

    store = load_store()
    store["repos"][root] = {"digest": current, "notified": current}
    if not save_store(store):
        print(f"could not write {store_path()}", file=sys.stderr)
        return 2
    print(f"trusted   digest {current[:16]}…\nrecorded  {store_path()}")
    print("\nAny edit to any of those files revokes this and asks again.")
    print("Better still: wire `python3 scripts/guards/dispatch.py` as a "
          "PreToolUse hook in\nthe repo's own .claude/settings.json — then the "
          "repository owns it and this\nplugin is no longer in the path.")
    return 0


def cmd_forget(root):
    store = load_store()
    if store["repos"].pop(root, None) is None:
        print(f"not trusted: {root}")
        return 0
    save_store(store)
    print(f"forgot    {root}")
    return 0


def cmd_status(root):
    store = load_store()
    record = store["repos"].get(root) or {}
    current = digest(root)
    files = guard_files(root)
    print(f"repo      {root}")
    print(f"guards    {len(files)} file(s) in {GUARD_DIR}/")
    print(f"wired     {'yes — this plugin stays out of the path' if repo_wires_it_already(root) else 'no'}"
          f"   (.claude/settings*.json)")
    if not files:
        state = "n/a"
    elif current is None:
        state = "unreadable — treated as untrusted"
    elif record.get("digest") == current:
        state = f"trusted ({current[:16]}…)"
    elif record.get("digest"):
        state = "STALE — the guard set changed since it was trusted"
    else:
        state = "never trusted on this machine"
    print(f"trust     {state}")
    print(f"store     {store_path()}")
    return 0


def main():
    ap = argparse.ArgumentParser(add_help=True, description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--trust", action="store_true",
                   help="trust this repository's guard set, at its current content")
    g.add_argument("--forget", action="store_true", help="revoke that trust")
    g.add_argument("--status", action="store_true", help="show what is trusted here")
    ap.add_argument("--root", default=".")
    a = ap.parse_args()

    if a.trust or a.forget or a.status:
        root = repo_root(a.root)
        if root is None:
            print("cannot judge: not inside a git repository", file=sys.stderr)
            return 2
        return (cmd_trust if a.trust else
                cmd_forget if a.forget else cmd_status)(root)

    raw = sys.stdin.read()
    root = repo_root(os.getcwd())
    if root is None:
        return 0
    return hook(raw, root)


if __name__ == "__main__":
    sys.exit(main())
