#!/usr/bin/env python3
"""Say once, per repository, what that repository looks like from here.

A SessionStart hook that prints a short paragraph the first time this plugin
sees a repository, and never again in it.

## Why once, and not every session

This plugin's entire argument is that standing context is paid on every turn
and mostly not read. A notice that reappeared every session would be that same
mistake one level up: furniture within a fortnight, and noise the session after
that -- noise which costs tokens and teaches people to skip the first screen,
which is where a `SessionStart` hook puts things that genuinely could not be
known any other way.

So the marker is per-machine state, not knowledge, and lives beside the trust
store in `$CLAUDE_CONFIG_DIR/cc-repo-harness/first-look.json`. Writing it
into the repository would put a fact about one person's laptop into everybody's
diff, and the second clone would see the notice the first one already dismissed.

The numbers are recorded alongside the marker, unused. Speaking again when they
have moved a long way is a plausible second version of this file; it is not
this one, because nobody has yet watched the first version be too quiet.

## Why it only reads

Three parts of the assessment are not free, and none of them run here:

    blast.py   fires the repository's own hooks -- that executes repo code
    catch.py   clones the repo and runs its test suite -- minutes of CPU
    the agent  costs tokens

Doing any of those because somebody installed a plugin helps itself to a
machine and a bill that were never offered. What runs here is `probe_repo.py`:
it reads files and asks git for a list of them. The notice ends with the
command that does the rest, and then waits to be asked.

That division is hard rule 4 in practice. A plugin may report on a repository.
It may not change what the repository does, and it may not start doing things
to one because it happens to be installed.

## Contract, per SessionStart

    stdin  = JSON  {"cwd": ..., "source": "startup"|"resume"|"clear"|"compact"}
    exit 0 = stdout is added to the session's context
    other  = non-blocking error; stderr is surfaced to the user

Every failure path exits 0 in silence *and still records the marker*. A
diagnostic that cannot run is not an emergency, and one that announces its own
breakage at the top of every session is worse than one that is absent.

    python3 first_look.py --status    # what was seen here, and when
    python3 first_look.py --forget    # see it again in this repository
"""

from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
ASSESS = os.path.join(PLUGIN, "shared", "scripts", "assess")
FACTSHEET = os.path.join(ASSESS, "factsheet.py")
TEMPLATE = "https://github.com/WangChangxin0809/cc-repo-harness-template"
PROBE = os.path.join(PLUGIN, "shared", "scripts", "probe_repo.py")


# --------------------------------------------------------------------------
# repository and marker store
# --------------------------------------------------------------------------

def repo_root(start):
    """Nearest ancestor containing .git. None outside a repository."""
    cur = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def store_path():
    cfg = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude")
    return os.path.join(cfg, "cc-repo-harness", "first-look.json")


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
    """Atomic, 0600 -- same treatment as the trust store beside it. Several
    sessions start at once often enough that a half-written file which happens
    to parse would show the notice again in repositories that had seen it."""
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


def mark(root, record):
    data = load_store()
    data["repos"][root] = record
    save_store(data)


# --------------------------------------------------------------------------
# the free half
# --------------------------------------------------------------------------

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:                                    # noqa: BLE001
        return None
    return mod


def moments(probe):
    """Which of the seven delivery moments carry anything.

    Imported from the fact sheet rather than reimplemented: two answers to
    "is moment 5 filled" that drift apart would make the notice and the
    assessment disagree about the same repository, and the notice is the one
    nobody would check."""
    sys.path.insert(0, ASSESS)
    fs = load("factsheet", FACTSHEET)
    if fs is None:
        return None, None
    keys = sorted(k for k in probe["moments"] if k[0].isdigit())
    return ([k.split("_")[0] for k in keys if fs.filled_moment(probe, k)],
            [k.split("_")[0] for k in keys if not fs.filled_moment(probe, k)])


def look(root):
    """The paragraph, or None if this cannot be measured from here."""
    probe_mod = load("probe_repo", PROBE)
    if probe_mod is None:
        return None, None
    try:
        p = probe_mod.probe(root)
    except Exception:                                    # noqa: BLE001
        return None, None
    if p is None:
        return None, None

    filled, empty = moments(p)
    if filled is None:
        return None, None
    d, by = p["discipline"], p["skill_tokens_by_origin"]

    record = {"first_seen": datetime.datetime.now().isoformat(timespec="seconds"),
              "tier": p["tier"], "source_files": p["source_files"],
              "tokens": p["always_on_skill_tokens"], "moments_filled": filled,
              "gates": d["gates"], "guards": d["guards"]}

    lines = [
        "cc-repo-harness, first session here. Nothing has been changed or run.",
        "",
        f"  tier {p['tier']} · {p['source_files']} source files",
        f"  ~{p['always_on_skill_tokens']} tokens/turn of standing context "
        f"({by['repo']} this repo, {by['plugin']} installed plugins)",
        f"  delivery moments: {','.join(filled) or 'none'} wired · "
        f"{','.join(empty) or 'none'} empty",
        f"  checks: {d['gates']} gates, {d['guards']} guards, "
        f"{d['selftests']} selftests",
    ]
    # A repository with nothing in it has nothing to assess. It has a
    # starting point, and the one thing worth saying is where.
    if p["source_files"] == 0 and p["tracked_files"] <= 3:
        lines += [
            "",
            "  Nothing tracked yet. A new repository starts from the template --",
            "  CI, checks and docs layout included, START-HERE.md as the list:",
            f"    {TEMPLATE}",
        ]
    lines += [
        "",
        "That is the free half of the assessment: files read, git asked for a",
        "list. The rest needs saying so, because it fires this repository's own",
        "hooks and runs its test suite --",
        "",
        f"    python3 {FACTSHEET} --root .",
        "",
        "Said once per repository. --forget on hooks/first_look.py to see it again.",
    ]
    return "\n".join(lines), record


# --------------------------------------------------------------------------
# modes
# --------------------------------------------------------------------------

def hook(raw, cwd):
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    # A compaction is mid-session. Whatever this had to say was said at start,
    # or is about to be said the first time; repeating it into a freshly
    # trimmed context is the one place it would cost the most.
    if payload.get("source") == "compact":
        return 0

    root = repo_root(payload.get("cwd") or cwd)
    if root is None:
        return 0
    if root in load_store()["repos"]:
        return 0

    text, record = look(root)
    # Marked either way. A repository this cannot measure is not one to retry
    # measuring at the top of every session for the rest of its life.
    mark(root, record or {"first_seen": datetime.datetime.now().isoformat(
        timespec="seconds"), "measured": False})
    if text:
        print(text)
    return 0


def cmd_status(root):
    seen = load_store()["repos"]
    print(f"first-look store: {store_path()}")
    if root is None:
        print("  not inside a git repository")
        return 0
    rec = seen.get(root)
    if rec is None:
        print(f"  {root}\n    not seen yet — the notice would appear next session")
    else:
        print(f"  {root}\n    first seen {rec.get('first_seen', '?')}"
              + ("" if rec.get("measured", True) else " (could not measure)"))
    if len(seen) > 1:
        print(f"  and {len(seen) - 1} other repositor"
              f"{'y' if len(seen) == 2 else 'ies'}")
    return 0


def cmd_forget(root):
    if root is None:
        print("not inside a git repository", file=sys.stderr)
        return 1
    data = load_store()
    if data["repos"].pop(root, None) is None:
        print(f"{root} had not been seen anyway")
        return 0
    save_store(data)
    print(f"forgotten: {root}\nthe notice appears again next session")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Say once, per repository, what it looks like from here.")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--forget", action="store_true")
    ap.add_argument("--now", action="store_true",
                    help="print the notice regardless of the marker, and do "
                         "not record one")
    a = ap.parse_args()

    cwd = os.getcwd()
    if a.status:
        return cmd_status(repo_root(cwd))
    if a.forget:
        return cmd_forget(repo_root(cwd))
    if a.now:
        root = repo_root(cwd)
        if root is None:
            print("not inside a git repository", file=sys.stderr)
            return 1
        text, _ = look(root)
        print(text or "cannot judge: probe_repo.py could not read this tree")
        return 0 if text else 2

    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    except OSError:
        raw = ""
    try:
        return hook(raw, cwd)
    except Exception:                                    # noqa: BLE001
        # Non-blocking by construction. A bug here must not become the thing
        # that greets every session in every repository.
        return 0


if __name__ == "__main__":
    sys.exit(main())
