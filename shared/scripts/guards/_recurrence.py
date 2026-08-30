#!/usr/bin/env python3
"""Count how often the same shape of command is refused here, and say something
once when it stops looking like an accident.

    python3 scripts/guards/_recurrence.py --report    # what has recurred
    python3 scripts/guards/_recurrence.py --forget

Underscored, so `dispatch.py` does not try to load it as a guard.

## What this counts, and what it does not

It counts **blocks**. It cannot count violations of a rule that lives in prose,
because if a script could detect those the rule would already be a gate -- that
is the whole reason it is prose. Claiming otherwise would be the same trick as
scoring a repository on whether it looks like ours.

So the signal is narrower than "the agent keeps breaking the rule", and more
useful than it sounds: a guard that refuses the same shape of command over and
over is not a guard doing its job, it is a habit meeting a speed bump. Habits
are cheaper to move than to keep stopping.

## Where the shape comes from

Four mechanisms solve this problem in public, and they agree on the order:
normalise, hash, count, act at a threshold.

  git rerere    hashes the *normalised* conflict preimage, so that branch names
                and line numbers do not fork the identity, and keeps the result
                in `.git/rr-cache/` -- per checkout, never committed
  Sentry        groups events by fingerprint, and lets an event override the
                fingerprint, because automatic normalisation is a guess
  fail2ban      counts per (jail, host) and acts when `maxretry` is reached
                within `findtime` -- the window is what separates a habit from
                a coincidence spread over two years
  the agent-memory writing: three of the same correction is a rule, and the
                decision to keep it stays with a person

All four are here. The normalisation is below, the override is `fingerprint()`
on a guard module, the window is `WINDOW_DAYS`, and the threshold produces a
paragraph rather than a file.

## Why the count is not in the tree

`.git/agent-harness/`, following rerere. A count that lived under version
control would produce a diff on every session, conflict on every merge, and
record one laptop's habits as a fact about the project. What deserves to be
committed is the *conclusion* -- a deny rule, a selftest case, a decision
record -- and a person writes that. The count is an observation; the file it
argues for is a judgement.

## It must never block

Everything here is wrapped by the caller and fails open. A counter that broke
the guard dispatcher would trade a real protection for a bookkeeping nicety.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time

THRESHOLD = 3
WINDOW_DAYS = 14
STORE = "recurrence.json"

# How many tokens of a command survive into its shape.
#
# The operand rule caps operands at three; nothing capped the flags, and a
# heredoc is one enormous "command" whose body is full of things that start
# with a dash. The first refusal this counter recorded in its own repository
# produced a shape three hundred characters long made of `-rf` and `--force`
# taken from the *text* of a script, which is unreadable in --report and
# groups nothing with anything.
#
# Truncating can only ever over-group, and over-grouping here is the harmless
# direction: two commands sharing their first dozen tokens are the same habit
# for the purpose of "you keep doing this".
KEEP = 12

# A run of hex long enough to be an object id, a number, and a quoted string.
# Normalising these is what stops `git reset --hard a1b2c3d` and the same
# command tomorrow from looking like two unrelated events.
_SHA = re.compile(r"\b[0-9a-f]{7,40}\b")
_NUM = re.compile(r"\b\d+\b")
_QUOTE = re.compile(r"""['"]""")


def git_dir(root):
    """`.git` is a directory in a clone and a file in a worktree."""
    p = os.path.join(root, ".git")
    if os.path.isdir(p):
        return p
    try:
        with open(p, encoding="utf-8") as fh:
            line = fh.read().strip()
    except OSError:
        return None
    if not line.startswith("gitdir:"):
        return None
    d = line.split(":", 1)[1].strip()
    return d if os.path.isdir(d) else None


def store_path(root):
    d = git_dir(root)
    return os.path.join(d, "agent-harness", STORE) if d else None


# --------------------------------------------------------------------------
# the shape of a command
# --------------------------------------------------------------------------

def normalize(command):
    """The shape of a command, with the parts that differ every time removed.

    Verbatim: the program, its subcommand, and every flag -- `git push` and
    `git push --force` are different habits and must not merge. Abstracted:
    operands, which are the branch, the path, the object id that make two runs
    of the same habit look unrelated.
    """
    text = _QUOTE.sub("", " ".join(str(command).split()))
    text = _SHA.sub("<sha>", text)
    text = _NUM.sub("<n>", text)
    out, seen_operand = [], 0
    for i, tok in enumerate(text.split()):
        if i < 2 or tok.startswith("-"):
            out.append(tok)
        else:
            seen_operand += 1
            if seen_operand <= 3:            # keep the arity, drop the values
                out.append("<arg>")
        if len(out) >= KEEP:
            out.append("…")
            break
    return " ".join(out)


def fingerprint(guard_name, tool_input, mod=None):
    """(guard, shape) hashed -- unless the guard says otherwise.

    A guard knows what its own rule is about and this file does not. One that
    refuses several spellings of one mistake should collapse them itself, by
    exposing `fingerprint(tool_input) -> str`; without that, three spellings
    count as three separate things and the threshold is never reached.
    """
    shape = None
    fn = getattr(mod, "fingerprint", None)
    if callable(fn):
        try:
            shape = fn(tool_input)
        except Exception:                                # noqa: BLE001
            shape = None
    if not shape:
        shape = normalize(tool_input.get("command", ""))
    key = hashlib.sha256(f"{guard_name}\0{shape}".encode()).hexdigest()[:16]
    return key, shape


# --------------------------------------------------------------------------
# the store
# --------------------------------------------------------------------------

def load(root):
    path = store_path(root)
    if not path:
        return {"version": 1, "seen": {}}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"version": 1, "seen": {}}
    if not isinstance(data, dict) or not isinstance(data.get("seen"), dict):
        return {"version": 1, "seen": {}}
    return data


def save(root, data):
    path = store_path(root)
    if not path:
        return False
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def record(root, guard_name, tool_input, mod=None, now=None):
    """Count one refusal. Returns the entry, or None if nothing could be kept.

    Timestamps outside the window are dropped rather than kept and filtered:
    an entry hit twice a year for a decade should not grow without limit, and
    a count that includes them is not the number anyone wants."""
    now = time.time() if now is None else now
    key, shape = fingerprint(guard_name, tool_input, mod)
    data = load(root)
    entry = data["seen"].get(key)
    if not isinstance(entry, dict):
        entry = {"guard": guard_name, "shape": shape, "hits": [], "announced": 0}

    cutoff = now - WINDOW_DAYS * 86400
    entry["hits"] = [t for t in entry.get("hits", [])
                     if isinstance(t, (int, float)) and t >= cutoff] + [now]
    entry["shape"], entry["guard"] = shape, guard_name
    data["seen"][key] = entry
    if not save(root, data):
        return None
    return entry


def announce(root, entry, now=None):
    """The paragraph, once, when the count first reaches the threshold.

    Once because this plugin's own argument is that repeated text stops being
    read. The second time it would be furniture and the third it would be the
    thing people learn to scroll past -- attached, as it happens, to the one
    message that has to land."""
    if entry is None or len(entry["hits"]) < THRESHOLD or entry.get("announced"):
        return None
    now = time.time() if now is None else now
    entry["announced"] = 1
    data = load(root)
    for key, other in data["seen"].items():
        if other.get("shape") == entry["shape"] and \
                other.get("guard") == entry["guard"]:
            data["seen"][key]["announced"] = 1
    save(root, data)

    days = max(1, int((now - min(entry["hits"])) / 86400 + 0.5))
    return (
        f"--- this has now happened {len(entry['hits'])} times in {days} day"
        f"{'' if days == 1 else 's'} ---\n"
        f"\n"
        f"    {entry['shape']}      (refused by {entry['guard']})\n"
        f"\n"
        f"Three is where a habit stops being an accident, and a speed bump is\n"
        f"the wrong tool for a habit. Two questions, and a file either way:\n"
        f"\n"
        f"  Is it the same thing every time? Then the rule belongs earlier than\n"
        f"  a guard — `permissions.deny` in .claude/settings.json, or branch\n"
        f"  protection on the server. A guard is the third line, not the first.\n"
        f"\n"
        f"  Did a variant get through in between? Then the matcher is too\n"
        f"  narrow, and that is a new case in scripts/guards/selftest.py.\n"
        f"\n"
        f"Counted in .git/, never committed, and said once. What gets committed\n"
        f"is whichever of those two you decide on.\n"
        f"    python3 scripts/guards/_recurrence.py --report")


def observe(root, guard_name, tool_input, mod=None):
    """Everything above, wrapped. Returns a paragraph or None, and never raises.

    The caller is a hook that is in the middle of refusing something. A
    bookkeeping error here must not cost that refusal its reason, and must not
    turn a working guard into a crash that fails open."""
    try:
        return announce(root, record(root, guard_name, tool_input, mod))
    except Exception:                                    # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def repo_root(start):
    cur = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def cmd_report(root):
    data = load(root)
    rows = sorted(data["seen"].values(), key=lambda e: -len(e.get("hits", [])))
    rows = [r for r in rows if r.get("hits")]
    if not rows:
        print("nothing has been refused here in the last "
              f"{WINDOW_DAYS} days")
        return 0
    print(f"refusals in the last {WINDOW_DAYS} days, most repeated first\n")
    for r in rows:
        n = len(r["hits"])
        flag = "  <-- at the threshold" if n >= THRESHOLD else ""
        shape = r["shape"]
        if len(shape) > 60:
            shape = shape[:59] + "…"
        print(f"  {n:>3}x  {r['guard']:<28} {shape}{flag}")
    print(f"\n{store_path(root)}")
    return 0


def cmd_forget(root):
    path = store_path(root)
    if path and os.path.exists(path):
        os.remove(path)
        print(f"forgotten: {path}")
    else:
        print("nothing counted here yet")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="What keeps getting refused in this repository.")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--forget", action="store_true")
    a = ap.parse_args()
    root = repo_root(os.getcwd())
    if root is None:
        print("cannot judge: not inside a git repository", file=sys.stderr)
        return 2
    if a.forget:
        return cmd_forget(root)
    return cmd_report(root)


if __name__ == "__main__":
    sys.exit(main())
