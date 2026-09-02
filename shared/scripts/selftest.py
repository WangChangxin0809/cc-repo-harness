#!/usr/bin/env python3
"""Prove the plugin's own acceptance criterion, the one stated in prose.

    python3 shared/scripts/selftest.py [--verbose] [--case NAME]

    0 = every case held    1 = a case failed    2 = cannot run

The README's claim is literal: install it, run the bootstrap, **uninstall the
plugin**, hand a fresh agent a real task, and the repository must still teach it
the conventions. Every other selftest here runs with the plugin sitting on disk,
so none of them can tell a repository that stands on its own from one quietly
reaching back into the checkout it was scaffolded from. That difference is
invisible to the person who ran the scaffolder and total for the teammate who
clones afterwards.

## Why this is a script and not thirty lines of CI shell

It used to be thirty lines of CI shell. That put the judgement in the one place
this project tells everyone else never to put it: a hook wiring, where it cannot
be run before pushing, cannot be tested, and dies with the CI provider. The rule
is the same rule as `moments.md` states for `.claude/settings.json` -- the
wiring is one line, the judgement lives in `scripts/`.

Which also means it runs on a laptop, which is where an acceptance test that
takes ninety seconds needs to run if anyone is going to run it before pushing.
"""

from __future__ import annotations

import argparse
import json
import collections
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(os.path.dirname(HERE))

BLOCKING = json.dumps(
    {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}})
BENIGN = json.dumps(
    {"tool_name": "Bash",
     "tool_input": {"command": "git push origin feature/x"}})


def sh(args, cwd=None, stdin=None):
    return subprocess.run(args, cwd=cwd, input=stdin, text=True,
                          capture_output=True, timeout=600)


def fresh_repo():
    """A minimal but real git repository. Not empty: a repo with no source at
    all probes as something no user has, and the scaffolder's decisions are
    driven by what it finds."""
    tmp = tempfile.mkdtemp(prefix="harness-acceptance-")
    os.makedirs(os.path.join(tmp, "src"))
    with open(os.path.join(tmp, "src", "a.py"), "w", encoding="utf-8") as fh:
        fh.write("def a():\n    return 1\n")
    sh(["git", "init", "-q", "."], cwd=tmp)
    sh(["git", "add", "-A"], cwd=tmp)
    sh(["git", "-c", "user.email=selftest@example.com", "-c",
        "user.name=selftest", "commit", "-qm", "init"], cwd=tmp)
    return tmp


def fill_placeholders(root):
    """Do what an author does in an afternoon, in one pass.

    Crude on purpose. The case is not "did the prose come out well", which no
    script can judge; it is "does the red list terminate" -- a scaffold whose
    gates stay red after every placeholder is gone is a scaffold that can never
    be finished, and that is detectable.
    """
    for dirpath, _dirs, names in os.walk(root):
        if ".git" in dirpath.split(os.sep):
            continue
        for name in names:
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(re.sub(r"<[^<>\n]{2,}>", "written by a human", body))
    with open(os.path.join(root, "LICENSE"), "w", encoding="utf-8") as fh:
        fh.write("MIT\n")


def scaffold(root, tier, from_dir=PLUGIN, dry=False):
    return sh([sys.executable,
               os.path.join(from_dir, "shared", "scripts", "scaffold.py"),
               "--root", root, "--tier", tier] + (["--dry-run"] if dry else []))


def ci(root, lane="--fast"):
    """Run the scaffolded repository's own entry point.

    `git add -A` first, and not as housekeeping. `fresh_repo()` commits before
    the scaffolder runs, so everything the scaffolder writes is untracked --
    and every gate that enumerates through `git ls-files` (check_docs_runnable,
    check_no_machine_paths, the nested-CLAUDE.md half of check_context_budget)
    then reads an empty file list and passes having examined nothing.

    That is the exact failure this whole repository is about: a check that
    cannot see its subject reports the same green as a check that looked. It
    hid a real defect for the life of this suite -- two skills documenting
    `${CLAUDE_PLUGIN_ROOT}/shared/scripts/consolidate.py`, a path that resolves
    only while the plugin is installed, in a repository whose one promise is
    that it outlives the plugin.

    Here rather than in each case, because the next case to be added would
    otherwise have to remember."""
    sh(["git", "add", "-A"], cwd=root)
    return sh(["./ci.sh", lane], cwd=root)


# ---------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------

def case_scaffold_reaches_green(tier):
    """A fresh scaffold is red for the placeholders, and only for those.

    Both halves are load-bearing. Red-on-fresh is what makes the red list a
    to-do list rather than an insult; green-once-filled is the claim that the
    list terminates. A release shipped in which it did not, and every gate here
    passed on the scaffolder's own output.
    """
    def run():
        repo = fresh_repo()
        try:
            out = scaffold(repo, tier)
            if out.returncode != 0:
                return f"scaffold --tier {tier} exited {out.returncode}: " \
                       f"{out.stderr.strip()[:300]}"

            first = ci(repo)
            if first.returncode == 0:
                return "a fresh scaffold was green; the placeholders in it " \
                       "should have made it red"
            body = first.stdout + first.stderr
            if "unfilled placeholder" not in body:
                return ("red, but not for the placeholders it is supposed to "
                        f"name: {body.strip()[:300]}")

            fill_placeholders(repo)
            second = ci(repo)
            if second.returncode != 0:
                return (f"still not green with every placeholder filled "
                        f"(exit {second.returncode}): "
                        f"{(second.stdout + second.stderr).strip()[:400]}")
            return None
        finally:
            shutil.rmtree(repo, ignore_errors=True)
    return run


def case_the_brief_names_the_plan_in_flight():
    """SessionStart is where "what is only true right now" is delivered, and the
    one fact a new session cannot reconstruct by reading is which plan was
    already underway. An agent without it starts something parallel, or
    re-derives the plan from the tree; both look like progress.

    The other half is precision. The first version matched `doing` anywhere in
    the file and named a plan whose README merely *explains* the state words as
    the one in progress. A brief that misreads a plan is not read twice, so the
    prose case is planted here too and must not be reported.
    """
    repo = fresh_repo()
    try:
        scaffold(repo, "B")
        plans = os.path.join(repo, "docs", "exec-plans")
        for name, body in (
            ("shipping", "# Shipping\n\n- [x] done   Build it\n"
                         "- [ ] doing  Publish it\n"),
            ("closed", "# Closed\n\n- [x] done   All of it\n"),
            ("conventions", "# Conventions\n\nNobody reopens a finished step "
                            "to change `doing` to `done`.\n"),
        ):
            os.makedirs(os.path.join(plans, name), exist_ok=True)
            with open(os.path.join(plans, name, "README.md"), "w",
                      encoding="utf-8") as fh:
                fh.write(body)

        said = sh([sys.executable, "scripts/context/session_brief.py"],
                  cwd=repo).stdout
        if "shipping" not in said:
            return ("the brief did not name the plan with a step marked "
                    f"`doing`: {said.strip()[:300]}")
        if "closed" in said:
            return ("a plan with every step done was reported in flight: "
                    f"{said.strip()[:300]}")
        if "conventions" in said:
            return ("a plan whose prose merely mentions `doing` was reported "
                    f"in flight: {said.strip()[:300]}")
        return None
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def case_every_shipped_rule_is_scoped():
    """A rule with no `paths:` is loaded at launch, at the same priority as
    `.claude/CLAUDE.md`, in every session that repository ever has.

    So an unscoped rule in payload is a permanent context charge levied on
    somebody who never asked for it, and it is invisible: the file looks like
    every other rule, and `check_context_budget.py` only notices once the sum
    crosses the cap. One rule of twenty lines never crosses it, and is paid
    forever.
    """
    repo = fresh_repo()
    try:
        scaffold(repo, "B")
        rules = os.path.join(repo, ".claude", "rules")
        found = sorted(f for f in os.listdir(rules)) if os.path.isdir(rules) else []
        shipped = [f for f in found if f.endswith(".md")]
        if not shipped:
            return f"no rules were installed at tier B; found {found}"
        for name in shipped:
            with open(os.path.join(rules, name), encoding="utf-8") as fh:
                head = fh.read(600)
            if not re.search(r"^paths:", head, re.M):
                return (f".claude/rules/{name} declares no `paths:`, so it "
                        "loads at launch in every session of every repository "
                        "this is copied into")
        return None
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def case_tier_a_ships_working_guards():
    """Tier A has no ci.sh, so the case above cannot see it at all.

    It is also the tier most repositories will actually install, being the
    floor. Judge what it does ship: guards that pass their own selftest and a
    settings.json that wires them.
    """
    repo = fresh_repo()
    try:
        out = scaffold(repo, "A")
        if out.returncode != 0:
            return f"scaffold --tier A exited {out.returncode}"

        selftest = sh([sys.executable, "scripts/guards/selftest.py"], cwd=repo)
        if selftest.returncode != 0:
            return (f"the guards it shipped do not pass their own selftest "
                    f"(exit {selftest.returncode}): "
                    f"{(selftest.stdout + selftest.stderr).strip()[:300]}")

        settings = os.path.join(repo, ".claude", "settings.json")
        if not os.path.exists(settings):
            return "no .claude/settings.json, so nothing runs the guards"
        with open(settings, encoding="utf-8") as fh:
            wiring = fh.read()
        if "scripts/guards/dispatch.py" not in wiring:
            return ("settings.json does not wire scripts/guards/dispatch.py, "
                    "so the guards are files that never run")
        return None
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def case_a_guard_behind_a_narrower_matcher_turns_the_selftest_red():
    """A guard that judges a Write, wired at `matcher: "Bash"`, never runs.

    This repository shipped exactly that: no_committed_credential and
    no_silenced_check judge Write and Edit, dispatch.py was wired for Bash
    only, and both were files that never ran in a live session. Nothing said
    so, because the dispatcher fails open and an unasked guard looks like a
    quiet one. The guards' selftest is what runs in the fast lane, so it is
    what says so: every tool a guard can refuse must be one its wiring can
    show it."""
    repo = fresh_repo()
    try:
        if scaffold(repo, "A").returncode != 0:
            return "scaffold --tier A failed"
        settings = os.path.join(repo, ".claude", "settings.json")
        with open(settings, encoding="utf-8") as fh:
            cfg = json.load(fh)
        for group in cfg["hooks"]["PreToolUse"]:
            if any("guards/dispatch.py" in h["command"] for h in group["hooks"]):
                group["matcher"] = "Bash"
        with open(settings, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
        out = sh([sys.executable, "scripts/guards/selftest.py"], cwd=repo)
        text = out.stdout + out.stderr
        if out.returncode != 1:
            return (f"the guards' selftest exited {out.returncode} with a guard "
                    f"that refuses a Write wired behind matcher \"Bash\" -- "
                    f"nothing says that guard never runs")
        if "Write" not in text or "matcher" not in text:
            return ("the selftest went red without naming the tool and the "
                    f"matcher, so nobody can fix it from the message: {text[:300]}")
    finally:
        shutil.rmtree(repo, ignore_errors=True)
    return None


def case_dry_run_describes_the_run_that_happens():
    """`--dry-run` must name exactly the files the real run creates.

    It did not. The preview printed `NEW scripts/context/<a context script>`
    unconditionally while the writer gated that copy on tier B, so a tier A
    `--dry-run` promised a file the actual run never wrote. Found by scaffolding
    this repository onto itself -- nothing here scaffolds a *tier A* repo and
    then looks at what landed, so both halves were individually plausible.

    A preview exists to be approved before the thing happens. One that
    describes a different run is worse than none, because none is not trusted.
    """
    for tier in ("A", "B"):
        repo = fresh_repo()
        try:
            preview = scaffold(repo, tier, dry=True)
            if preview.returncode != 0:
                return f"--dry-run --tier {tier} exited {preview.returncode}"
            # `  COPY           scripts/guards/  (6 files)` -- the path is the
            # second field, not the last one.
            promised = {
                line.split()[1].rstrip("/")
                for line in preview.stdout.splitlines()
                if line.strip().startswith(("NEW", "COPY", "DIR"))
            }
            if scaffold(repo, tier).returncode != 0:
                return f"scaffold --tier {tier} failed after its own dry run"

            for rel in sorted(promised):
                if not os.path.exists(os.path.join(repo, rel)):
                    return (f"tier {tier}: --dry-run promised {rel}, and the "
                            f"real run did not create it")
        finally:
            shutil.rmtree(repo, ignore_errors=True)
    return None


def case_hooks_survive_the_working_directory_moving():
    """Every wired hook must resolve from any directory, not just the root.

    A hook runs in whatever directory Claude is currently in. That changes on a
    `cd` and again inside a worktree, so a relative command silently stops
    resolving -- and the way it fails is the trap. `python3 <missing>.py` exits
    2, which is exactly the code Claude Code reads as *block*. So a broken path
    does not quietly stop protecting; it blocks every matching tool call with an
    unreadable "can't open file".

    The Stop hook is worse. Its `stop_hook_active` short-circuit, the thing that
    stops an unbreakable loop, lives inside the script that never runs. A
    relative path there means the session cannot be ended at all -- the exact
    failure that script's fail-open design exists to prevent, defeated from
    outside it.

    Asserts the placeholder is present rather than running the hooks, because
    only Claude Code substitutes ${CLAUDE_PROJECT_DIR} and a test that
    substituted it itself would be testing its own substitution."""
    repo = fresh_repo()
    try:
        if scaffold(repo, "B").returncode != 0:
            return "scaffold --tier B failed"
        path = os.path.join(repo, ".claude", "settings.json")
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)

        commands = [entry["command"]
                    for matchers in cfg.get("hooks", {}).values()
                    for matcher in matchers
                    for entry in matcher.get("hooks", [])]
        if not commands:
            return "no hook commands were wired at all"
        for command in commands:
            if "${CLAUDE_PROJECT_DIR}" not in command:
                return (f"hook command resolves relative to the working "
                        f"directory: {command!r}")
    finally:
        shutil.rmtree(repo, ignore_errors=True)
    return None


def case_personal_permission_grants_cannot_be_committed():
    """A scaffolded repository must never be able to commit settings.local.json.

    Claude Code writes that file by itself the moment someone grants a
    permission, and it holds grants rather than preferences. Committed, it does
    not merely leak one person's setup -- it *applies* to everyone who clones,
    so one approval silently becomes the whole team's.

    This was found by opening our own `.claude/`. It looked safe, and it was:
    the file was ignored by the developer's *global* gitignore, on one machine.
    The repository itself had no such line and neither did anything we
    scaffolded. That is the worst shape a defect can have -- invisible exactly
    to whoever would notice it, and present for everybody else.

    `core.excludesFile=/dev/null` is what makes this test mean anything; without
    it, the machine running the suite would pass on its own configuration."""
    for existing in (None, "node_modules/\n*.log\n"):
        repo = fresh_repo()
        try:
            sh(["git", "config", "core.excludesFile", os.devnull], repo)
            if existing is not None:
                with open(os.path.join(repo, ".gitignore"), "w",
                          encoding="utf-8") as fh:
                    fh.write(existing)
            if scaffold(repo, "B").returncode != 0:
                return "scaffold --tier B failed"

            local = os.path.join(repo, ".claude", "settings.local.json")
            os.makedirs(os.path.dirname(local), exist_ok=True)
            with open(local, "w", encoding="utf-8") as fh:
                fh.write('{"permissions": {"allow": ["Bash(curl evil.sh)"]}}\n')

            sh(["git", "add", "-A"], repo)
            staged = sh(["git", "diff", "--cached", "--name-only"], repo).stdout
            if "settings.local.json" in staged:
                return ("settings.local.json is staged for commit — one "
                        "person's permission grants would apply to everyone")

            # And the pre-existing content must survive: appending is the only
            # safe thing to do to a file a stranger's repository already owns.
            if existing:
                with open(os.path.join(repo, ".gitignore"), encoding="utf-8") as fh:
                    body = fh.read()
                for line in existing.strip().splitlines():
                    if line not in body:
                        return f".gitignore lost a pre-existing line: {line}"
        finally:
            shutil.rmtree(repo, ignore_errors=True)
    return None


def case_skills_are_copied_and_outlive_the_plugin():
    """The teaching travels with the repository, not with the plugin.

    Five skills used to live in the plugin, where Claude Code keeps every
    installed skill's name and description in context -- so they cost about 890
    tokens a turn in EVERY repository on the machine, including repositories
    that had never asked this plugin for anything. Copied into the repository
    instead, the people who chose them pay, their teammates get them without
    installing anything, and everybody else pays nothing.

    Which means the copy has to be real: `SKILL.md`, its `references/`, and
    still there after the plugin is gone. -> docs/decisions/0024
    """
    staging = tempfile.mkdtemp(prefix="harness-skill-copy-")
    copy = os.path.join(staging, "plugin")
    repo = fresh_repo()
    try:
        shutil.copytree(PLUGIN, copy,
                        ignore=shutil.ignore_patterns(".git", "__pycache__"))
        out = scaffold(repo, "C", from_dir=copy)
        if out.returncode != 0:
            return f"scaffold exited {out.returncode}: {out.stderr[-200:]}"
        shutil.rmtree(copy, ignore_errors=True)

        base = os.path.join(repo, ".claude", "skills")
        if not os.path.isdir(base):
            return "no .claude/skills/ was written"
        got = sorted(os.listdir(base))
        for name in ("writing-docs", "writing-checks", "repo-index"):
            if name not in got:
                return f"{name} was not copied; got {got}"
            if not os.path.exists(os.path.join(base, name, "SKILL.md")):
                return f"{name} arrived without its SKILL.md"

        # A skill whose references did not come with it is a skill with dead
        # links, and the plugin it could have read them from is gone.
        refs = os.path.join(base, "writing-checks", "references")
        if os.path.isdir(os.path.join(PLUGIN, "shared", "skills",
                                      "writing-checks", "references")):
            if not os.path.isdir(refs) or not os.listdir(refs):
                return "writing-checks arrived without its references/"
        return None
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(repo, ignore_errors=True)


def case_a_tier_a_repo_is_not_given_every_skill():
    """Tier is a budget. Installing above it leaves machinery nobody needs,
    and machinery that rots teaches everyone the machinery is decorative."""
    repo = fresh_repo()
    try:
        out = scaffold(repo, "A")
        if out.returncode != 0:
            return f"scaffold exited {out.returncode}"
        base = os.path.join(repo, ".claude", "skills")
        got = sorted(os.listdir(base)) if os.path.isdir(base) else []
        if "repo-index" in got:
            return f"tier A was given the tier C retrieval skill: {got}"
        if "writing-docs" not in got:
            return f"tier A did not get writing-docs: {got}"
        return None
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def case_survives_the_plugin_being_deleted():
    """The acceptance criterion, mechanised.

    Scaffold from a *copy* of the plugin, delete the copy, and only then judge.
    Deleting it is what makes this different from every other case: a path baked
    into settings.json or into a copied script keeps working while the original
    checkout is still there, and breaks for the teammate who never had it.
    """
    staging = tempfile.mkdtemp(prefix="harness-plugin-copy-")
    copy = os.path.join(staging, "plugin")
    repo = fresh_repo()
    try:
        shutil.copytree(PLUGIN, copy,
                        ignore=shutil.ignore_patterns(".git", "__pycache__"))
        out = scaffold(repo, "C", from_dir=copy)
        if out.returncode != 0:
            return f"scaffold from the copy exited {out.returncode}"
        fill_placeholders(repo)

        # Nothing scaffolded may name the place it came from.
        for dirpath, dirs, names in os.walk(repo):
            dirs[:] = [d for d in dirs if d != ".git"]
            for name in names:
                path = os.path.join(dirpath, name)
                try:
                    with open(path, encoding="utf-8") as fh:
                        if copy in fh.read():
                            rel = os.path.relpath(path, repo)
                            return (f"{rel} refers back to the plugin checkout "
                                    f"it was scaffolded from")
                except (OSError, UnicodeDecodeError):
                    continue

        shutil.rmtree(copy, ignore_errors=True)

        result = ci(repo)
        if result.returncode != 0:
            return (f"./ci.sh --fast exits {result.returncode} once the plugin "
                    f"is gone: {(result.stdout + result.stderr).strip()[:400]}")

        # ci.sh proves the guards' selftest passes. It does not prove the
        # dispatcher answers a real payload, which is the thing that has to work
        # before every command anyone types.
        blocked = sh([sys.executable, "scripts/guards/dispatch.py"],
                     cwd=repo, stdin=BLOCKING)
        if blocked.returncode != 2:
            return (f"a push to a protected branch was not blocked "
                    f"(exit {blocked.returncode})")
        if not blocked.stderr.strip():
            return "blocked, but with no reason on stderr for the model to read"
        allowed = sh([sys.executable, "scripts/guards/dispatch.py"],
                     cwd=repo, stdin=BENIGN)
        if allowed.returncode != 0:
            return (f"a push to a feature branch was blocked "
                    f"(exit {allowed.returncode}); a guard that blocks "
                    f"everything gets switched off within a day")

        index = sh([sys.executable, "scripts/index/build.py", "--root", "."],
                   cwd=repo)
        if index.returncode != 0:
            return f"scripts/index/build.py exits {index.returncode}"
        return None
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(repo, ignore_errors=True)


def case_scaffolding_twice_changes_nothing():
    """Re-running the scaffolder must add nothing it already added.

    The docstring at the top of scaffold.py has always claimed "additive and
    idempotent", and the second half stopped being true the day the wired
    commands gained quotes around `${CLAUDE_PROJECT_DIR}`. The duplicate check
    was a substring test against `json.dumps` of the stored hooks, and
    serialising turns a stored `"` into `\\"` -- so the raw command was never a
    substring of its own serialised form, and every re-run appended a copy of
    every hook. Two guard dispatchers on one Bash call, two Stop hooks on one
    turn, and a settings.json that still reads as plausible.

    Nothing caught it because every case here scaffolds once, into a fresh
    repository. Upgrading is the whole reason this plugin persists after the
    first run, so the second run is the case that was missing.
    """
    repo = fresh_repo()
    try:
        first = scaffold(repo, "B")
        if first.returncode != 0:
            return f"the first scaffold failed: {first.stderr.strip()[:300]}"
        settings = os.path.join(repo, ".claude", "settings.json")
        with open(settings, encoding="utf-8") as fh:
            before = json.load(fh)

        second = scaffold(repo, "B")
        if second.returncode != 0:
            return f"the second scaffold failed: {second.stderr.strip()[:300]}"
        with open(settings, encoding="utf-8") as fh:
            after = json.load(fh)

        seen = collections.Counter()
        for event, entries in after.get("hooks", {}).items():
            for entry in entries:
                for hook in entry.get("hooks", []):
                    seen[(event, hook.get("command"))] += 1
        dupes = [f"{e} -> {c}" for (e, c), n in sorted(seen.items()) if n > 1]
        if dupes:
            return ("re-running the scaffolder duplicated wired hooks, so each "
                    "fires twice per event:\n    " + "\n    ".join(dupes))
        if json.dumps(before, sort_keys=True) != json.dumps(after,
                                                            sort_keys=True):
            return ("the second run changed settings.json without adding a "
                    "hook — it must be a no-op")
        return None
    finally:
        shutil.rmtree(repo, ignore_errors=True)


CASES = [
    ("a guard behind a narrower matcher turns the selftest red",
     case_a_guard_behind_a_narrower_matcher_turns_the_selftest_red),
    ("skills are copied into the repository and outlive the plugin",
     case_skills_are_copied_and_outlive_the_plugin),
    ("a tier A repository is not given every skill",
     case_a_tier_a_repo_is_not_given_every_skill),
    ("tier B scaffold reaches green from a clean worktree",
     case_scaffold_reaches_green("B")),
    ("tier C scaffold reaches green from a clean worktree",
     case_scaffold_reaches_green("C")),
    ("tier A ships guards that are wired and pass their own selftest",
     case_tier_a_ships_working_guards),
    ("--dry-run describes the run that actually happens",
     case_dry_run_describes_the_run_that_happens),
    ("wired hooks survive the working directory moving",
     case_hooks_survive_the_working_directory_moving),
    ("the session brief names the plan in flight, and only that one",
     case_the_brief_names_the_plan_in_flight),
    ("every rule shipped into a repository declares paths:",
     case_every_shipped_rule_is_scoped),
    ("personal permission grants cannot be committed",
     case_personal_permission_grants_cannot_be_committed),
    ("scaffolding twice changes nothing the second time",
     case_scaffolding_twice_changes_nothing),
    ("the repository survives the plugin being deleted",
     case_survives_the_plugin_being_deleted),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--case", help="substring of one case label, to run alone")
    a = ap.parse_args()

    if shutil.which("git") is None:
        print("cannot run: git not on PATH", file=sys.stderr)
        return 2
    if not os.path.exists(os.path.join(HERE, "scaffold.py")):
        print(f"cannot run: no scaffold.py beside {HERE}", file=sys.stderr)
        return 2

    selected = [(label, fn) for label, fn in CASES
                if not a.case or a.case in label]
    if not selected:
        print(f"cannot run: no case matching {a.case!r}", file=sys.stderr)
        return 2

    failures = []
    for label, fn in selected:
        try:
            problem = fn()
        except Exception as exc:
            problem = f"raised {type(exc).__name__}: {exc}"
        if problem:
            failures.append(f"{label}\n    {problem}")
        elif a.verbose:
            print(f"  ok  {label}")

    if failures:
        print(f"\n{len(failures)} of {len(selected)} acceptance case(s) "
              f"failed:\n", file=sys.stderr)
        for f in failures:
            print(f"  {f}\n", file=sys.stderr)
        return 1
    if a.verbose:
        print(f"{len(selected)} acceptance cases: the scaffold reaches green, "
              f"and the repository outlives the plugin")
    return 0


if __name__ == "__main__":
    sys.exit(main())
