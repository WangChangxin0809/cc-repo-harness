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
# `shared/skills/`, a sibling of this directory: skills are payload too.
SKILL_SRC = os.path.join(os.path.dirname(HERE), "skills")

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
| `decisions/` | Why is it like this? | Numbered from the PR, superseded not edited |
| `exec-plans/` | What are we in the middle of? | One folder per plan: `README.md` owns state, `steps/` owns substance |

**This top level is fixed; inside each directory, organise however suits the
material.** `scripts/gates/check_docs_layout.py` holds the top level and checks
nothing below it. A directory that forks a required name — `adr/`, `howto/`,
`plans/` — is an error even when routed, because two spellings of one bucket
both accumulate documents and merging them later is a migration. Additions are
fine once a row below routes into them.

Two things are deliberately not directories. **A symptom and its fix belong in
the failure output** of the guard or gate that detects it, not in a file nobody
opens while stuck. **Generated is a property**: such a file lives where its
content belongs and declares its source in its own first line, and the gate is
that regenerating leaves an empty `git diff`.

A plan past a few steps is a folder, not a file. `README.md` carries the goal,
the abort condition, and every step's state; a step earns its own file under
`steps/` only when it has decisions to record. Step files never restate status —
nobody reopens a finished one to change `doing` to `done` — and each opens with
`## Consulted` saying what was searched before the work started, or why nothing
was. The routing table below points at the `README.md` only.

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
run fast "hooks reach the model"     python3 scripts/context/selftest.py
run fast "always-on context budget"  python3 scripts/gates/check_context_budget.py
run fast "templates filled in"       python3 scripts/gates/check_templates_filled.py
run fast "docs routing table"        python3 scripts/gates/check_docs_index.py
run fast "docs top level"            python3 scripts/gates/check_docs_layout.py
run fast "no file too long to read"  python3 scripts/gates/check_file_size.py
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

# Every command references its script through ${CLAUDE_PROJECT_DIR}, never
# relatively. A hook runs in whatever directory Claude is currently in, which
# changes on a `cd` and again inside a worktree -- and `python3 <missing>.py`
# exits 2, the same code Claude Code reads as *block*. So a relative path does
# not quietly stop protecting: it blocks every matching tool call with an
# unreadable "can't open file". For the Stop hook it is worse still, because the
# stop_hook_active short-circuit lives inside the script that never runs, and
# the session cannot be ended at all.
#
# Quoted because these are shell form; the docs ask for quotes around any path
# placeholder there.
# Context scripts: hook-wired, copied one file at a time rather than by
# directory, because `context/` also holds things a target repository has no use
# for. One list feeds the dry run, the writer and the hook wiring -- when this
# was two code paths, a tier A `--dry-run` promised a file the real run never
# wrote.
#
# A script declares *every* event it answers, because two of them need two. The
# pair on before_write.py is not a convenience: `InstructionsLoaded` is how it
# learns which rules Claude Code already delivered, and without that half it
# would inject a second copy of every rule the native loader had just loaded.
CONTEXT_SCRIPTS = [
    ("before_write.py", [("PreToolUse", "Bash|Write|Edit|MultiEdit"),
                         ("InstructionsLoaded", "path_glob_match")], "B"),
    # The last moment anything can be said to an agent. Every other hook fires
    # while work is happening; none covers finishing with the tree red, which
    # is the failure a person discovers later, from CI, after the agent is gone.
    ("on_stop.py", [("Stop", "*")], "B"),
    # The rung between a guard refusing a call and the agent choosing to run
    # the tests: the check runs *because an edit happened*, with the reasoning
    # that produced the edit still in front of the model.
    #
    # Tier B, with the rest of `context/`, and not C: `context/selftest.py`
    # ships at B and has cases for this file, so a higher floor here would
    # ship a suite testing something that is not in the tree. The scaffold
    # selftest caught exactly that, which is what it is for.
    ("same_turn.py", [("PostToolUse", "Write|Edit|MultiEdit")], "B"),
    # Ships with them and answers to no event. A hook nobody can watch fail is
    # how `after_edit.py` spent its whole life printing to a channel the model
    # never reads, with a passing test that asserted on the wrong boundary.
    ("selftest.py", [], "B"),
]

# (event, matcher, command, minimum tier). A list and not a dict keyed by event,
# because one event legitimately carries more than one hook: `PreToolUse` runs
# both the guard dispatcher, which can refuse a call, and before_write.py, which
# only informs. They stay two processes on purpose -- folded into one, a crash
# in the informer would take the guards down with it, and guards failing open is
# a decision that belongs to dispatch.py alone.
HOOKS = [
    ("PreToolUse", "Bash|Write|Edit|MultiEdit|NotebookEdit",
     'python3 "${CLAUDE_PROJECT_DIR}/scripts/guards/dispatch.py"', "A"),
    ("SessionStart", "*",
     'python3 "${CLAUDE_PROJECT_DIR}/scripts/context/session_brief.py"', "A"),
] + [
    (event, matcher,
     'python3 "${CLAUDE_PROJECT_DIR}/scripts/context/%s"' % name, floor)
    for name, pairs, floor in CONTEXT_SCRIPTS for event, matcher in pairs
]

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
    # A `.gitkeep` and never a `.md`. Every `.md` in here is a rule, and one
    # without `paths:` frontmatter loads at launch at the same priority as
    # `.claude/CLAUDE.md` -- so a README explaining the directory would be a
    # permanent context charge for a note aimed at whoever opened the folder.
    #
    # The directory ships empty because the cost of filling it is now visible:
    # check_context_budget.py counts unscoped rules against the same cap as
    # CLAUDE.md and reports scoped ones separately. Without that feedback this
    # would be a bypass with a welcome mat.
    (".claude/rules", "B"),
    ("docs/reference", "A"),
    ("scripts/selftests", "B"),
    ("scripts/baselines", "B"),
]

# source dir under this script -> destination under the repo, minimum tier
COPY = [
    ("guards", "scripts/guards", "A"),
    ("gates", "scripts/gates", "B"),
    ("index", "scripts/index", "C"),
]

# Skills, copied whole -- `SKILL.md` and whatever `references/` it carries.
#
# They live in the repository rather than in the plugin because a plugin skill
# costs every session in EVERY repository on the machine: Claude Code keeps a
# listing of every installed skill's name and description in context, so six of
# them charged about 890 tokens a turn to people who had never asked this
# plugin for anything. Copied here, a repository pays for the ones it chose,
# its teammates get them without installing anything, and everyone else pays
# nothing.
#
# `bootstrap-repo-harness` is the exception and stays in the plugin: it is how
# somebody arrives at any of this, and a skill nobody can discover teaches
# nobody.  -> docs/decisions/0024
SKILLS = [
    ("writing-docs", "A"),
    ("writing-checks", "B"),
    ("writing-github-docs", "B"),
    ("consolidating-notes", "B"),
    ("repo-index", "C"),
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


# Claude Code writes `.claude/settings.local.json` by itself when someone grants
# a permission, and that file holds grants rather than preferences. Committed,
# it does not merely leak one person's setup -- it *applies* to everyone who
# clones, so one person's approval silently becomes the whole team's. The file
# is personal by design and no repository should ever carry it.
IGNORE_LINES = [
    (".claude/settings.local.json",
     "Personal permission grants. Committed, they apply to everyone who clones."),
]


def ensure_gitignore(root, made):
    """Append what must never be committed, without disturbing what is there.

    Appends rather than writes: a target repository almost always has a
    .gitignore already, and replacing it would be the most destructive thing
    this script could do."""
    path = os.path.join(root, ".gitignore")
    rel = ".gitignore"
    try:
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
    except OSError:
        body = ""

    existing = {ln.strip() for ln in body.splitlines()}
    missing = [(pat, why) for pat, why in IGNORE_LINES if pat not in existing]
    if not missing:
        made.append(("SKIP", rel, "already ignores what it must"))
        return

    block = "" if not body or body.endswith("\n") else "\n"
    for pat, why in missing:
        block += f"\n# {why}\n{pat}\n"
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(block)
    except OSError as exc:
        made.append(("SKIP", rel, f"could not append: {exc}"))
        return
    made.append(("NEW" if not body else "APPEND", rel,
                 f"+{len(missing)} pattern(s)"))


def merge_settings(root, wanted, made):
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
    for event, matcher, command in wanted:
        # Keyed on the command, not the event: an event can hold several hooks
        # and re-running the scaffolder must add each missing one without
        # duplicating the ones already there.
        #
        # Compared against the parsed structure and not against `json.dumps` of
        # it. It was the latter, and that silently stopped working the day these
        # commands gained quotes around `${CLAUDE_PROJECT_DIR}`: serialising
        # turns the stored `"` into `\"`, so the raw command was never a
        # substring of its own serialised form and every re-run appended a
        # duplicate. Two guard dispatchers on one Bash call, two Stop hooks on
        # one turn -- and the file still looked plausible.
        if any(h.get("command") == command
               for entry in hooks.get(event, []) or []
               for h in entry.get("hooks", []) or []):
            continue
        hooks.setdefault(event, []).append({
            "matcher": matcher,
            "hooks": [{"type": "command", "command": command}],
        })
        added.append(event)

    if not added and existed:
        made.append(("SKIP", rel, "hooks already wired"))
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")
    # De-duplicated for the report only. One event legitimately gains more than
    # one hook, and printing "PreToolUse, ..., PreToolUse" reads as a bug in the
    # scaffolder rather than as two hooks on one event.
    shown = list(dict.fromkeys(added))
    made.append(("MERGE" if existed else "NEW", rel,
                 f"+{', '.join(shown)}" + (" (.bak saved)" if existed else "")))


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
    skills = [name for name, floor in SKILLS
              if at_least(a.tier, floor) and os.path.isdir(
                  os.path.join(SKILL_SRC, name))]
    context_scripts = [(name, floor) for name, _, floor in CONTEXT_SCRIPTS
                       if at_least(a.tier, floor)]
    wanted_hooks = [(event, matcher, command)
                    for event, matcher, command, floor in HOOKS
                    if at_least(a.tier, floor)]

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
        for name in skills:
            print(f"  {'COPY':<14} .claude/skills/{name}/")
        # Driven by the same list as the real run. A preview whose only job is
        # to be trusted before you approve it must not describe a different run.
        for name, _ in context_scripts:
            print(f"  {'NEW':<14} scripts/context/{name}")
        print(f"  {'APPEND':<14} .gitignore  "
              f"(+{len(IGNORE_LINES)} pattern(s) that must never be committed)")
        print(f"  {'MERGE':<14} .claude/settings.json  "
              f"(+{', '.join(sorted({e for e, _, _ in wanted_hooks}))})")
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

    for name in skills:
        target = os.path.join(root, ".claude", "skills", name)
        rel = os.path.relpath(target, root)
        if os.path.exists(target):
            made.append(("SKIP", rel, "already exists"))
            continue
        shutil.copytree(os.path.join(SKILL_SRC, name), target)
        made.append(("NEW", rel, ""))

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

    for name, _ in context_scripts:
        target = os.path.join(root, "scripts", "context", name)
        rel = os.path.relpath(target, root)
        if os.path.exists(target):
            made.append(("SKIP", rel, "already exists"))
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy(os.path.join(HERE, "context", name), target)
        os.chmod(target, 0o755)
        made.append(("NEW", rel, ""))

    ensure_gitignore(root, made)
    merge_settings(root, wanted_hooks, made)

    width = max((len(p) for _, p, _ in made), default=10)
    for state, path, note in made:
        print(f"  {state:<6} {path:<{width}}  {note}")

    # Everything below used to be printed at every tier while describing a
    # tier B install. A tier A user was handed five numbered steps of which
    # three named files that tier does not install -- `scripts/gates/`,
    # `ci.sh` -- as the very first thing they read. Instructions that do not
    # resolve teach the reader that the instructions are decorative, and that
    # lesson is learned in the first minute and applies to everything after.
    gated = at_least(a.tier, "B")

    if gated:
        print("\n./ci.sh --fast is RED right now, and that is the point: every")
        print("template above still holds its placeholders, and")
        print("scripts/gates/check_templates_filled.py names each one. The red is")
        print("your to-do list, and it goes green when the list is done. LICENSE is")
        print("the one file not scaffolded — it is a legal choice, not a template.")
    else:
        print("\nCLAUDE.md is scaffolded with placeholders and nothing at this")
        print("tier will name them for you: check_templates_filled.py ships with")
        print("the gates, from tier B up. So the to-do list is a file you read")
        print("rather than a command you run — and if that sounds like something")
        print("you will forget, that is the argument for tier B, not for")
        print("scaffolding one gate by hand.")

    print("\nNext, in order. Each step has one thing to check:")
    print("  1. python3 scripts/guards/selftest.py"
          + (" && python3 scripts/gates/selftest.py" if gated else ""))
    print("     %s must pass before you trust %s."
          % (("Both", "either") if gated else ("It", "it")))
    print("  2. Break one check on purpose; confirm its selftest goes red.")
    print("     Until you have seen it fail, you have a file, not a check.")
    print("  3. Read scripts/guards/*.py. The merge above wired them, so they now")
    print("     run before every Bash, Write and Edit in this repo — code you are")
    print("     handing the keys to, and it arrived from a scaffolder.")
    if gated:
        print("  4. Work the red list down: ./ci.sh --fast, fill what it names,")
        print("     repeat. Add a LICENSE. Then it is green from a clean worktree.")
        print("  5. Disconnect a hook on purpose and confirm ci.sh turns red.")
        print("     A suite that survives that is measuring nothing.")
    else:
        print("  4. Fill CLAUDE.md and docs/index.md by hand, and add a LICENSE.")
        print("  5. Disconnect the PreToolUse hook on purpose and confirm the")
        print("     guard stops firing. Until you have watched that, the wiring")
        print("     is an assumption.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
