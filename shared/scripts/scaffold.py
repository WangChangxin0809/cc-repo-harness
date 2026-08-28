#!/usr/bin/env python3
"""Create the missing pieces of the harness. Additive and idempotent.

    python3 scaffold.py --root <repo> --tier {A,B,C} [--dry-run]

    0 = done          2 = cannot judge (not a git repository)

Nothing existing is ever overwritten. Every file it would have written but found
already present is reported as SKIP, because a half-built convention that
conflicts with what you are adding is the normal case, not the exception -- and
silently replacing someone's `CLAUDE.md` is a worse outcome than any missing
file. `settings.json` is merged additively after a `.bak` copy.

It also creates empty directories. That is deliberate: a directory is itself a
trigger. An agent that sees `docs/exec-plans/` writes its plan there; an agent
that sees nothing invents a location, and next month there are three.

Run `probe_repo.py` first. The tier decides what gets created; installing above
tier leaves machinery nobody needs, which rots and teaches everyone that the
harness is decorative.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

CLAUDE_MD = """\
# <project>

<One paragraph: what this is, and the one thing that is surprising about it.>

- **Covers**: rules that apply everywhere and cannot be enforced by a script.
- **Does not cover**: anything true of one directory only (that directory's own
  `CLAUDE.md`), anything a script can block (`scripts/guards/`), anything a
  script can detect (`scripts/gates/`). Detail added here is paid on every turn
  of every session, forever.

## Hard rules

1. <rule> -> <docs/path.md>

## Commands

```bash
./ci.sh              # the single acceptance entry point
./ci.sh --fast       # what to run while working
```

## Where to look

- Bird's eye view and invariants: ARCHITECTURE.md
- Full routing table: docs/index.md

<!-- Cap: 100 lines, enforced by scripts/gates/check_context_budget.py.
     Hitting the cap is a signal to move a rule one hop out, not to compress it. -->
"""

ARCHITECTURE_MD = """\
# Architecture

- **Covers**: how this system works, for someone who does not yet know what to
  ask. Read on demand, so it may be long.
- **Does not cover**: how to perform a task (`docs/how-to/`), why a specific
  choice was made (`docs/decisions/`).

<!-- Write this by hand. A generated rollup describes the current accident; a
     written one describes the intent, including the constraints that are not
     visible anywhere in the code. That is the whole reason this file exists. -->

## What it does

<Two or three paragraphs. What problem, for whom, and the shape of the answer.>

## Codemap

| Directory | Holds | Talks to |
|---|---|---|
| | | |

## Invariants

Properties that must hold across the whole system. For each one, say where it is
enforced -- a property with no enforcement point is an aspiration, and naming it
here without one is how it quietly stops being true.

1. <invariant> — enforced by <scripts/gates/…, a type, a schema>

## Constraints that are not visible in the code

<Deadlines, a vendor API's rate limit, a platform quirk, a decision made for a
reason that no longer applies but is expensive to undo. This section is the one
a newcomer cannot reconstruct by reading, and the one that saves the most time.>
"""

INDEX_MD = """\
# docs/ routing table

- **Covers**: mapping "what I am about to do" to "what to read, then where to edit".
- **Does not cover**: the knowledge itself — that lives in the document being
  pointed at. Detail written back into this table is paid by every reader who
  did not need it.

## Directories, partitioned by why you opened them

| Directory | You are here because | Shape |
|---|---|---|
| `how-to/` | I need to do a thing | Ordered steps: action → command → criterion |
| `reference/` | I need to look up a fact | Tables and rules, keyed for lookup |
| `troubleshooting/` | I hit a symptom | Symptom → cause → action |
| `decisions/` | Why is it like this? | Numbered, immutable, superseded not edited |
| `exec-plans/` | What are we in the middle of? | Goal, steps with state, abort condition |
| `generated/` | What is it right now? | Written from a truth source, never by hand |

## I want to X -> read Y -> then edit Z

| I want to | Read first | Then edit |
|---|---|---|
| Understand the system | [ARCHITECTURE.md](../ARCHITECTURE.md) | — |
| Know why the repo is shaped this way | [0001](decisions/0001-agent-conventions.md) | — |
| See what is in flight | [tech debt](exec-plans/tech-debt-tracker.md) | — |
"""

DECISION_0001 = """\
# 0001 — This repository carries its own harness

Date: <YYYY-MM-DD>
Status: accepted

## Context

Coding agents work here. Conventions written as prose in a single file were read
once per session, paid on every turn, and followed unevenly -- and the failures
were silent, because nothing distinguishes "the rule was followed" from "the
rule was never read".

The underlying constraint: knowledge only changes behaviour if it arrives at the
moment of acting. A repository has a fixed set of such moments, and each one has
a different cost and a different reach.

## Decision

Route every convention to the moment it is needed, and enforce mechanically
whatever can be enforced mechanically.

| Moment | Mechanism | Holds |
|---|---|---|
| Every turn | `CLAUDE.md`, capped | Rules with no local trigger |
| Session start | `SessionStart` hook | What is true only right now |
| Reading a subtree | nested `CLAUDE.md` | Rules local to one directory |
| Before an action | `scripts/guards/` | What review cannot undo |
| At CI time | `scripts/gates/` | Detectable states |
| On demand | `docs/`, skills | Everything else |

Consequences that follow, and are load-bearing:

- Knowledge lives in the repository, never in per-machine agent memory. Memory
  is invisible to review and cannot be corrected by a teammate.
- A rule that cannot tolerate a miss is never left to retrieval. Retrieval is
  best-effort by construction.
- Every check states, in its failure output, what to do and which document
  explains why. Failure output is the only text guaranteed to be read.

## Rejected

- **A longer `CLAUDE.md`.** <Why: the cost is per-turn and unbounded, and the
  content had no reading trigger.>
- **<the other real alternative you considered>.** <Why not.>

Record the alternatives honestly. A decision that lists only the winner reads as
inevitable, and the next person re-proposes what was already rejected.

## Revisit when

<What would have to become true. Without this, the record becomes folklore of a
different kind — permanent instead of forgotten.>
"""

TECH_DEBT = """\
# Tech debt tracker

- **Covers**: defects and shortcuts found in passing, with enough detail to act
  on later.
- **Does not cover**: work that is in flight — that gets its own file in this
  directory.

Something found while doing something else goes here rather than being fixed
inline. A batch that grows while you work is a batch that never lands, and a
fix bundled into an unrelated change is a fix nobody reviewed.

Each entry carries the reading that revealed it and the commit it was measured
on. A reading without a commit expires silently, and whoever inherits it
restarts from a number that stopped being true weeks ago.

| Found | Commit | What | Blast radius | Reading |
|---|---|---|---|---|
| | | | | |
"""

SECURITY_MD = """\
# Security

- **Covers**: how to report a vulnerability, and what this project treats as one.
- **Does not cover**: the rules themselves. Those are not prose, because prose
  is not enforcement:
  - what must never leave the machine → `scripts/guards/`
  - what must never enter the tree → `scripts/gates/`
  - why the boundary is drawn where it is → `docs/decisions/`

## Reporting

<Where to send it, and what response time to expect.>

## Threat model

The model itself belongs in a decision record, because it is a choice with
alternatives and it will be revisited. Link it here once written:

- `docs/decisions/00NN-threat-model.md`

## What is enforced, and where

| Rule | Enforced by |
|---|---|
| No credentials in the tree | `scripts/gates/` |
| No secrets piped to an outbound command | `scripts/guards/no_piped_outbound.py` |
"""

README_MD = """\
# <project>

<One paragraph, for someone who has never heard of this. What problem it solves,
for whom, and the one thing that is surprising about it. Not what it is built
with -- that answers a question nobody arrived with.>

- **Covers**: what this is, how to run it, and where to go next.
- **Does not cover**: how to work *on* it (CONTRIBUTING.md), how the pieces fit
  (ARCHITECTURE.md), how to perform a task (docs/how-to/).

## Quick start

```bash
<the shortest sequence from a fresh clone to something observably working>
```

<What you should see if it worked. A quick start with no success criterion
cannot be distinguished from a quick start that silently did nothing.>

## Requirements

- <runtime and version>

## Documentation

- Bird's eye view and invariants: [ARCHITECTURE.md](ARCHITECTURE.md)
- Everything else, routed: [docs/index.md](docs/index.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security issues go to
[SECURITY.md](SECURITY.md), not the issue tracker.

## License

<SPDX name> — see [LICENSE](LICENSE).
"""

CONTRIBUTING_MD = """\
# Contributing

- **Covers**: how to get a change accepted here — setup, the checks, and what a
  reviewer will look for.
- **Does not cover**: what the project is (README.md), how it works
  (ARCHITECTURE.md), why it is shaped this way (docs/decisions/).

## Before you open a pull request

```bash
./ci.sh --fast     # seconds; run this while working
./ci.sh            # everything; run this before pushing
```

Exit 2 is not a pass. It means a check could not judge — a missing tool, an
unparseable config — and it must be fixed rather than retried.

## What a reviewer checks

1. <the thing that actually gets changes sent back here>
2. Any new rule is enforced, not documented: an action a script can block goes
   to `scripts/guards/`, a state a script can detect goes to `scripts/gates/`.
3. A new check has been watched failing. `scripts/gates/selftest.py` proves it
   can turn red; a check nobody has seen fail is a file, not a check.

## Setup

```bash
<clone, dependencies, and the one environment thing people get wrong>
```
"""

CI_SH = """\
#!/usr/bin/env bash
# The single acceptance entry point. One roster, three lanes.
#
#   ./ci.sh --fast    seconds — what to run while working
#   ./ci.sh --unit    minutes — before pushing
#   ./ci.sh           everything
#
# Exit codes are the contract, and the third is the one people get wrong:
#   0 = judged, passed   1 = judged, failed   2 = COULD NOT JUDGE
# Exit 2 is never a pass. A check that returns 0 when it could not run
# manufactures a green that somebody will trust.
#
# Silent on success. Output on every green run trains everyone to skim, and
# then the one run that printed something goes unread.
set -uo pipefail

LANE="${1:-full}"
FAILED=0
UNJUDGED=0

run() {  # run <lane-floor> <name> <command...>
  local floor="$1" name="$2"; shift 2
  case "$LANE:$floor" in
    --fast:unit|--fast:full|--unit:full) return 0 ;;
  esac
  local out rc
  out="$("$@" 2>&1)"; rc=$?
  case $rc in
    0) ;;
    2) echo "== $name: COULD NOT JUDGE"; echo "$out"; UNJUDGED=1 ;;
    *) echo "== $name: FAILED"; echo "$out"; FAILED=1 ;;
  esac
}

# --- fast: seconds -----------------------------------------------------------
run fast "guards can still turn red" python3 scripts/guards/selftest.py
run fast "gates can still turn red"  python3 scripts/gates/selftest.py
run fast "always-on context budget"  python3 scripts/gates/check_context_budget.py
run fast "templates filled in"       python3 scripts/gates/check_templates_filled.py
run fast "docs routing table"        python3 scripts/gates/check_docs_index.py
run fast "documented commands run"   python3 scripts/gates/check_docs_runnable.py
run fast "public face"               python3 scripts/gates/check_community_health.py

# Uncomment if this repository is itself a Claude Code plugin. It checks the
# manifest, the component layout, and that no skill tells an agent to guess a
# path instead of using ${CLAUDE_PLUGIN_ROOT}. Left off by default because it
# exits 2 -- COULD NOT JUDGE -- without a .claude-plugin/, and an unjudgeable
# check wired in unconditionally makes every run of this script exit 2.
# run fast "plugin surface"          python3 scripts/gates/check_plugin_structure.py

# --- unit: minutes -----------------------------------------------------------
run unit "layering"                  python3 scripts/gates/check_layering.py
# run unit "tests"                   <your test command>

# --- full --------------------------------------------------------------------
# run full "integration"             <your integration command>

if [ "$UNJUDGED" = 1 ]; then exit 2; fi
exit "$FAILED"
"""

SESSION_BRIEF = '''#!/usr/bin/env python3
"""SessionStart: print what is only true right now.

Keep the output under ~20 lines. It is paid at every session start, and a brief
long enough to skim is a brief that gets skimmed. Everything here is knowledge
no file can hold -- which is exactly why it otherwise never gets delivered, and
the agent spends its first turns rediscovering it, or does not.
"""

import subprocess


def sh(*args):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def main():
    lines = []
    branch = sh("git", "rev-parse", "--abbrev-ref", "HEAD")
    dirty = sh("git", "status", "--porcelain")
    n = len(dirty.splitlines()) if dirty else 0
    lines.append(f"branch {branch or '?'} · "
                 f"{'clean' if not n else f'{n} uncommitted file(s)'}")

    behind = sh("git", "rev-list", "--count", "HEAD..@{u}")
    if behind and behind != "0":
        lines.append(f"{behind} commit(s) behind upstream")

    # Concurrent agent sessions writing to this repo. Left undetected this
    # produces edits that appear and vanish between reads, which is a very
    # confusing thing to debug and a very cheap thing to report.
    others = [p for p in sh("pgrep", "-af", "claude").splitlines()
              if "--print" not in p]
    if len(others) > 1:
        lines.append(f"!! {len(others)} agent session(s) appear active in this repo "
                     "— append to shared files rather than rewriting them")

    # TODO: add what is specific to this repo — which gates are currently red,
    # which plan in docs/exec-plans/ is in progress. Keep the total under ~20.
    print("\\n".join(lines))


if __name__ == "__main__":
    main()
'''

GUARDS_JSON = {
    "protected_branches": ["main", "master"],
    "_layers": "Declare the stack lowest-first to switch on check_layering.py",
    "layers": [],
    "layering_allow": [],
}

HOOKS = {
    "PreToolUse": dict(matcher="Bash",
                       command="python3 scripts/guards/dispatch.py"),
    "SessionStart": dict(matcher="*",
                         command="python3 scripts/context/session_brief.py"),
    "PostToolUse": dict(matcher="Edit|Write|MultiEdit",
                        command="python3 scripts/context/after_edit.py"),
}

# rel path -> (template, mode, minimum tier)
PLAN = [
    ("CLAUDE.md", CLAUDE_MD, 0o644, "A"),
    ("docs/index.md", INDEX_MD, 0o644, "A"),
    (".claude/guards.json", json.dumps(GUARDS_JSON, indent=2) + "\n", 0o644, "A"),
    ("scripts/context/session_brief.py", SESSION_BRIEF, 0o755, "A"),
    ("ARCHITECTURE.md", ARCHITECTURE_MD, 0o644, "B"),
    ("SECURITY.md", SECURITY_MD, 0o644, "B"),
    ("README.md", README_MD, 0o644, "B"),
    ("CONTRIBUTING.md", CONTRIBUTING_MD, 0o644, "B"),
    ("docs/decisions/0001-agent-conventions.md", DECISION_0001, 0o644, "B"),
    ("docs/exec-plans/tech-debt-tracker.md", TECH_DEBT, 0o644, "B"),
    ("ci.sh", CI_SH, 0o755, "B"),
]

# Directories that exist to be a trigger. A .gitkeep is what makes an empty
# directory survive a clone; without it the trigger is present only for whoever
# ran this script.
DIRS = [
    ("docs/how-to", "A"),
    ("docs/reference", "A"),
    ("docs/troubleshooting", "B"),
    ("docs/generated", "B"),
    ("scripts/selftests", "B"),
    ("scripts/baselines", "B"),
]

# source dir under this script -> destination under the repo, minimum tier
COPY = [
    ("guards", "scripts/guards", "A"),
    ("gates", "scripts/gates", "B"),
    ("index", "scripts/index", "C"),
]

TIER_ORDER = {"A": 0, "B": 1, "C": 2}


def at_least(tier, floor):
    return TIER_ORDER[tier] >= TIER_ORDER[floor]


def suggested_tier(root):
    """What probe_repo.py would have said. Returns None if it cannot be asked.

    Worth the import: the one failure mode a scaffolder cannot see is installing
    above tier, because the result looks like a more thorough job on the day it
    runs and like abandoned machinery six months later."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "probe_repo", os.path.join(HERE, "probe_repo.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        r = mod.probe(root)
        return r["tier"] if r else None
    except Exception:
        return None


def write(path, body, made, root, mode=0o644):
    rel = os.path.relpath(path, root)
    if os.path.exists(path):
        made.append(("SKIP", rel, "already exists"))
        return False
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, mode)
    made.append(("NEW", rel, ""))
    return True


def merge_settings(root, events, made):
    path = os.path.join(root, ".claude", "settings.json")
    rel = os.path.relpath(path, root)
    cfg, existed = {}, os.path.exists(path)
    if existed:
        try:
            with open(path, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except ValueError:
            made.append(("SKIP", rel, "does not parse — merge by hand"))
            return
        shutil.copy(path, path + ".bak")

    hooks = cfg.setdefault("hooks", {})
    added = []
    for event in events:
        spec = HOOKS[event]
        if spec["command"] in json.dumps(hooks.get(event, [])):
            continue
        hooks.setdefault(event, []).append({
            "matcher": spec["matcher"],
            "hooks": [{"type": "command", "command": spec["command"]}],
        })
        added.append(event)

    if not added and existed:
        made.append(("SKIP", rel, "hooks already wired"))
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")
    made.append(("MERGE" if existed else "NEW", rel,
                 f"+{', '.join(added)}" + (" (.bak saved)" if existed else "")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--tier", choices=["A", "B", "C"], default="B")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    if subprocess.run(["git", "rev-parse", "--git-dir"], cwd=root,
                      capture_output=True).returncode != 0:
        print("cannot judge: not a git repository", file=sys.stderr)
        return 2

    want = suggested_tier(root)
    if want and TIER_ORDER[a.tier] > TIER_ORDER[want]:
        print(f"note: this repository probes as tier {want}; you asked for "
              f"{a.tier}.\n      Machinery above tier is not neutral — it rots, "
              f"and its rot teaches\n      everyone that the harness is "
              f"decorative. Continuing.\n", file=sys.stderr)

    plan = [(rel, body, mode) for rel, body, mode, floor in PLAN
            if at_least(a.tier, floor)]
    dirs = [d for d, floor in DIRS if at_least(a.tier, floor)]
    copies = [(src, dst) for src, dst, floor in COPY if at_least(a.tier, floor)]
    events = ["PreToolUse", "SessionStart"] + (
        ["PostToolUse"] if at_least(a.tier, "B") else [])

    if a.dry_run:
        print(f"would scaffold tier {a.tier} into {root}:")
        for rel, _, _ in plan:
            state = "SKIP (exists)" if os.path.exists(os.path.join(root, rel)) else "NEW"
            print(f"  {state:<14} {rel}")
        for d in dirs:
            print(f"  {'DIR':<14} {d}/")
        for src, dst in copies:
            n = len([f for f in os.listdir(os.path.join(HERE, src))
                     if f.endswith(".py")])
            print(f"  {'COPY':<14} {dst}/  ({n} files)")
        print(f"  {'NEW':<14} scripts/context/after_edit.py")
        print(f"  {'MERGE':<14} .claude/settings.json  (+{', '.join(events)})")
        return 0

    made = []
    for rel, body, mode in plan:
        write(os.path.join(root, rel), body, made, root, mode)

    for d in dirs:
        keep = os.path.join(root, d, ".gitkeep")
        if os.path.isdir(os.path.join(root, d)) and not os.path.exists(keep):
            made.append(("SKIP", d + "/", "already exists"))
            continue
        write(keep, "", made, root)

    for src, dst in copies:
        target_dir = os.path.join(root, dst)
        os.makedirs(target_dir, exist_ok=True)
        for name in sorted(os.listdir(os.path.join(HERE, src))):
            if not name.endswith(".py"):
                continue
            target = os.path.join(target_dir, name)
            rel = os.path.relpath(target, root)
            if os.path.exists(target):
                made.append(("SKIP", rel, "already exists"))
                continue
            shutil.copy(os.path.join(HERE, src, name), target)
            os.chmod(target, 0o755)
            made.append(("NEW", rel, ""))

    if at_least(a.tier, "B"):
        target = os.path.join(root, "scripts", "context", "after_edit.py")
        if os.path.exists(target):
            made.append(("SKIP", os.path.relpath(target, root), "already exists"))
        else:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy(os.path.join(HERE, "context", "after_edit.py"), target)
            os.chmod(target, 0o755)
            made.append(("NEW", "scripts/context/after_edit.py", ""))

    merge_settings(root, events, made)

    width = max((len(p) for _, p, _ in made), default=10)
    for state, path, note in made:
        print(f"  {state:<6} {path:<{width}}  {note}")

    print("\n./ci.sh --fast is RED right now, and that is the point: every")
    print("template above still holds its placeholders, and")
    print("scripts/gates/check_templates_filled.py names each one. The red is")
    print("your to-do list, and it goes green when the list is done. LICENSE is")
    print("the one file not scaffolded — it is a legal choice, not a template.")

    print("\nNext, in order. Each step has one thing to check:")
    print("  1. python3 scripts/guards/selftest.py && python3 scripts/gates/selftest.py")
    print("     Both must pass before you trust either.")
    print("  2. Break one check on purpose; confirm its selftest goes red.")
    print("     Until you have seen it fail, you have a file, not a check.")
    print("  3. Read scripts/guards/*.py. The merge above wired them, so they now")
    print("     run before every Bash call in this repo — that is code you are")
    print("     handing the keys to, and it arrived from a scaffolder.")
    print("  4. Work the red list down: ./ci.sh --fast, fill what it names,")
    print("     repeat. Add a LICENSE. Then it is green from a clean worktree.")
    print("  5. Disconnect a hook on purpose and confirm ci.sh turns red.")
    print("     A suite that survives that is measuring nothing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
