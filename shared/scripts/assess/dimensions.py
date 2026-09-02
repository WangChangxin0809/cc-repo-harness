#!/usr/bin/env python3
"""The five dimensions, computed from what the other probes already gathered.

    python3 assess/dimensions.py [--root .] [--json]

This module holds no opinions about what a good repository looks like. It turns
raw observations into five groups, each of which can say one of three things:

    measured   here is the number, and here is what it means
    open       nothing here was found, which is itself the finding
    abstained  this could not be judged -- and that is never a zero

The third is the one that keeps the instrument honest. A repository whose tests
cannot run on this machine is not a repository with bad tests, and scoring it as
one would throw away exactly the repositories whose suites are fine.

## Why the grouping is not cosmetic

A flat list of numbers makes every finding look equally urgent, so the reader
picks by whichever line they understood first. Grouped by dimension, a reading
can say *what kind* of trouble a repository is in -- and the five kinds have
different costs, which is the whole reason to separate them.
"""

from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import history as history_mod
import reframe as reframe_mod  # noqa: E402

# A rule with no `paths:` loads at launch; one with `paths:` loads only when
# Claude reads a matching file. The distinction decides both what a rule costs
# (dimension 5) and whether it is delivered at all (dimension 1).
PATHS_KEY = re.compile(r"^paths:[^\S\n]*", re.M)

# Where a repository might keep a record of its own mistakes. Matched by name
# because there is no convention -- the point is to find one whatever it is
# called, not to check whether this project's naming was adopted.
RECORD_HINTS = ("postmortem", "post-mortem", "incident", "retro", "lessons",
                "tech-debt", "techdebt", "known-issues", "gotcha", "pitfall",
                "troubleshoot", "faq", "decisions", "adr", "changelog")

# Above this, a commit that says "fix" also did four other things, and nothing
# in it can be attributed to any one file. `history.py` draws the same line for
# the same reason, and dimension 4 read the history without it for a while:
# every count then ranked files by how busy they are, which is a fact about
# file size and not about rework.
FOCUSED = 3

# A commit whose subject says it repaired something. Deliberately the same
# question `history.py` asks, in both languages it knows -- two matchers that
# disagreed would let dimension 4 count repairs dimension 2 cannot replay.
FIX_SUBJECT = re.compile(
    r"\b(fix(e[sd])?|bug|repair|correct|patch|hotfix)\b"
    r"|修(?!改)|订正|解决|改回", re.I)
REVERT_SUBJECT = re.compile(
    r"^revert\b|回滚|回退|还原|撤销|撤回", re.I)

# A path that verifies something, by the shape of its NAME. Test suites are
# named from a small and stable vocabulary, so a list works here.
#
# It is deliberately not the only mechanism: a repository whose checks live in
# `gates/` is verifying too, and those are found by shape instead (probe's
# `check_dirs`), because a repository's own word for the directory is not
# guessable. A matcher that knew only names read this project's own history --
# whose checks are `selftest.py` files under `gates/` -- as 33 code changes out
# of 33 with nothing behind them.
VERIFIES = re.compile(r"(^|/)(tests?|spec|specs|__tests__|e2e)(/|$)"
                      r"|(^|/)(test_|conftest|selftest)"
                      r"|(_test|\.test|\.spec|_spec|_selftest)\.[a-z]+$", re.I)

# An absolute path pinned to one machine, hardcoded in something that is
# supposed to run. Two shapes, and the second was missed until an agent read
# the files this regex had already scored:
#
#   a home directory   /home/<author>/.cache/ms-playwright/.../chrome
#   an install root    C:\Program Files (x86)\Microsoft\Edge\...\msedge.exe
#
# Both were in the same repository -- one script assuming Linux, the other
# assuming Windows, so no single machine could run both, while from outside the
# repository looked like it had viewport coverage.
#
# Deliberately not "any absolute path": `/tmp/shot.png` as an output argument is
# fine, and flagging it would make the row noise. The list is the places
# software gets installed per-machine, and nothing else.
PINNED_PATH = re.compile(
    r"""['"](/home/[^/'"]+/[^'"]*|/Users/[^/'"]+/[^'"]*"""
    r"""|/Applications/[^'"]*|/opt/[^'"]*"""
    r"""|[A-Za-z]:\\{1,2}Users\\{1,2}[^\\'"]+[^'"]*"""
    r"""|[A-Za-z]:\\{1,2}Program Files[^'"]*)['"]""")

RUNNABLE_EXT = (".py", ".js", ".mjs", ".cjs", ".ts", ".sh", ".bash", ".rb",
                ".pl", ".ps1")

# Rare, and load-bearing: when one of these changes and nothing verifies it,
# the thing that would have caught the mistake is the thing that changed.
CRITICAL_PATH = re.compile(
    r"(^|/)\.github/workflows/|(^|/)\.gitlab-ci\.yml$|(^|/)Jenkinsfile$"
    r"|(^|/)(Dockerfile|docker-compose[^/]*\.ya?ml)$"
    r"|(^|/)(Makefile|justfile|noxfile\.py|tox\.ini)$"
    r"|(^|/)(pyproject\.toml|package\.json|go\.mod|Cargo\.toml)$"
    r"|(^|/)\.pre-commit-config\.ya?ml$|(^|/)requirements[^/]*\.txt$", re.I)

# A command that actually runs a suite, as it appears inside a CI file. The
# question is not whether a repository has CI -- almost every one does -- but
# whether the pipeline runs the verdict or only lints, builds and deploys. A
# green tick from a workflow that never invoked a test is the exact failure
# this dimension is named after.
RUNNER = re.compile(
    r"\b(pytest|tox|nox|unittest|jest|vitest|mocha|karma|cypress|playwright"
    r"|go test|cargo test|rspec|minitest|phpunit|dotnet test|ctest|bats"
    r"|gradle(w)? +test|mvn +(-\S+ +)*test|swift test)\b"
    r"|\b(npm|yarn|pnpm|bun) +(run +)?(test|check)\b"
    r"|\b(make|just) +(test|check|ci)\b", re.I)

# Something in a pipeline that looks like a path it runs. Loose on purpose:
# it is handed straight to `_verifies`, which decides.
PATH_TOKEN = re.compile(r"[\w./-]*[\w]/[\w./-]+|[\w-]+\.[a-z]{1,4}\b")

# Where a pipeline definition lives, across the hosts a stranger's repository
# might use. Directories are walked; plain names are read.
CI_FILES = (".github/workflows", ".gitlab-ci.yml", ".circleci/config.yml",
            "Jenkinsfile", "azure-pipelines.yml", ".travis.yml",
            "bitbucket-pipelines.yml", ".woodpecker.yml", ".drone.yml")

# Directories that hold somebody else's code, or build output. Walking into
# them finds thousands of vendored tests that this repository does not run.
NOT_OURS = ("node_modules", "vendor", "venv", ".venv", "env", "dist", "build",
            "target", "__pycache__", "site-packages", "third_party",
            "coverage", ".tox", ".next", "out")

# One command that returns a verdict. Any of these counts; the name is not the
# point, the existence of something runnable is.
VERDICT_FILES = (
    ("pytest.ini", "pytest"), ("tox.ini", "tox"), ("noxfile.py", "nox"),
    ("Makefile", "make"), ("justfile", "just"), ("ci.sh", "ci.sh"),
    ("scripts/ci.sh", "scripts/ci.sh"), ("Cargo.toml", "cargo test"),
    ("go.mod", "go test"), ("build.gradle", "gradle"), ("pom.xml", "maven"),
)


def chars(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return len(fh.read())
    except OSError:
        return 0


def tokens(n_chars):
    """Characters over four.

    Not a tokenizer. Claude Code's own context accounting uses the same
    approximation, and the alternative -- a real tokenizer -- is not one number
    either: the tokenizer changes between model families, and the same file has
    counted about 30% differently across them. A stable approximation both
    sides can reproduce offline is worth more here than a precise number that
    needs the network and still is not the model's own."""
    return n_chars // 4


def _rule_files(root):
    out = []
    for base in (os.path.join(root, ".claude", "rules"),):
        for here, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if f.endswith(".md"):
                    out.append(os.path.join(here, f))
    return sorted(out)


def _scoped(path):
    """Does this rule carry `paths:` frontmatter?"""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            head = fh.read(4096)
    except OSError:
        return False
    if not head.startswith("---"):
        return False
    end = head.find("\n---", 3)
    return bool(PATHS_KEY.search(head[:end if end > 0 else len(head)]))


def _hook_commands(root):
    """Every hook command string this repository wires, with its event."""
    out = []
    for rel in (os.path.join(".claude", "settings.json"),
                os.path.join(".claude", "settings.local.json")):
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        for event, entries in (data.get("hooks") or {}).items():
            for entry in entries if isinstance(entries, list) else []:
                for h in (entry.get("hooks") or []):
                    if h.get("command"):
                        out.append((event, str(h["command"])))
    return out


# -- 1 -----------------------------------------------------------------------

def controlled_execution(root, probe, blast, observe=None, judged=None,
                         permitted=None):
    """Can an agent working here in good faith destroy something?

    Three questions, and the third is easy to mistake for a different
    dimension's. Refusing the destructive action is 1.1; letting the
    legitimate one through is 1.2, without which the first is free to any
    repository that refuses everything. Watching what it just did is 1.3 --
    the same triple an agent needs in order to act at all."""
    rows = []
    if blast is None:
        headline = "nothing is wired to refuse anything"
        state = "open"
        rows.append({"label": "destructive probes", "value": "not asked",
                     "flag": "bad",
                     "note": "no .claude/ — the probes have nothing to ask, "
                             "so every one of them would go through"})
    else:
        b = blast["rows"]
        stopped = [x for x in b if x["stopped"] and not x["false_block"]]
        false_blocks = [x for x in b if x["false_block"]]
        broken = [x for x in b if x.get("hook_error")]
        loose = [x["probe"] for x in b if not x["stopped"] and not x["deny_rules"]]
        state = "measured"
        headline = f"{len(stopped)} of {len(b)} destructive actions are refused"
        rows.append({
            "label": "refused before they happen",
            "value": f"{len(stopped)}/{len(b)}",
            "flag": "ok" if len(stopped) == len(b) else
                    ("bad" if not stopped else "warn"),
            "note": ("open: " + ", ".join(loose)) if loose else
                    "every probe was refused"})
        rows.append({
            "label": "legitimate work blocked",
            "value": str(len(false_blocks)),
            "flag": "bad" if false_blocks else "ok",
            "note": ", ".join(x["probe"] for x in false_blocks) if false_blocks
                    else "no legitimate action was refused — which is not "
                         "optional; a harness that refuses both has improved "
                         "nothing"})
        if broken:
            rows.append({
                "label": "hooks that ran and broke",
                "value": str(len(broken)),
                "flag": "bad",
                "note": "a guard that crashes is worse than no guard — "
                        "everybody believes they are covered: "
                        + ", ".join(x["probe"] for x in broken)})

    # 1.3, and it prints only once somebody has judged it. Six counts are
    # evidence, not a verdict, and a row with an empty verdict reads as a
    # failing grade for the repository when it is really a limit of the
    # instrument. The evidence and the brief sit in the JSON either way, so
    # nothing is lost by waiting for an answer.
    if observe and judged:
        counts = " · ".join("%s %d" % (a, len(observe.get(a) or []))
                            for a in ("run", "isolation", "logs", "surface",
                                      "drive", "teardown"))
        rows.append({
            "label": "can an agent watch its own change run",
            "value": judged["verdict"],
            "flag": {"yes": "ok", "partly": "warn", "no": "bad"}[judged["verdict"]],
            "note": judged["prose"] + "  [" + counts + "]"})

    if blast and blast.get("local_only"):
        rows.append({
            "label": "refusals that only exist locally",
            "value": f"{blast['local_only']} of {blast['hooks']} hooks",
            "flag": "warn",
            "note": "wired in settings.local.json, which is one person's "
                    "machine and is not committed — a teammate cloning this "
                    "repository is not protected by it"})

    rules = _rule_files(root)
    if rules:
        scoped = [p for p in rules if _scoped(p)]
        cmds = _hook_commands(root)
        delivers = [c for e, c in cmds
                    if "rule" in c.lower() and e in ("PreToolUse", "PostToolUse")]
        if scoped:
            rows.append({
                "label": "path-scoped rules",
                "value": f"{len(scoped)} of {len(rules)}",
                "flag": "ok" if delivers else "warn",
                "note": ("delivered by a hook as well as by the loader"
                         if delivers else
                         "a scoped rule loads when Claude READS a matching "
                         "file — not when it creates one, and not when it "
                         "writes through the shell. Nothing here fills that "
                         "gap. See anthropics/claude-code#38487")})

    # The row that stops 1.1 being free. Six of six refusals is what a hook
    # that refuses everything scores, so the count above is read against how
    # much of this repository's own legitimate work the same hooks let
    # through. The six paired twins cover the actions somebody thought of;
    # this covers the actions this repository actually performs.
    if permitted and permitted.get("fired"):
        blocked = permitted["blocked"]
        rows.append({
            "label": "legitimate work refused",
            "value": "%d of %d action(s)" % (len(blocked),
                                             len(permitted["fired"])),
            "flag": "bad" if blocked else "ok",
            "note": ("; ".join("%s — %s" % (a["subject"][:60], a["by"][:40])
                               for a in blocked[:3])
                     + ". A guard that refuses one of these has discriminated "
                       "nothing, and the refusals counted above are worth that "
                       "much less"
                     if blocked else
                     "the commands CI runs, the commands the documentation "
                     "gives, and the near-misses all went through — so the "
                     "refusals counted above are refusals of the right things")})

    return {"n": 1, "name": "Controlled Execution",
            "question": "Can an agent working here in good faith destroy "
                        "something, and does anything stop it?",
            "state": state, "headline": headline, "rows": rows}


# -- 2 -----------------------------------------------------------------------

def secs(v):
    """Seconds, in the units a person waits in. None reads as an abstention."""
    if v is None:
        return "?"
    if v < 1:
        return f"{v:.1f}s"
    if v < 90:
        return f"{v:.0f}s"
    if v < 5400:
        return f"{v / 60:.0f}m"
    return f"{v / 3600:.1f}h"


def change_validation(defects, catch, catch_why, ladder, mutants=None,
                      mutants_why="", judged=None, cover=None,
                      cover_why="", probe=None, value=None):
    """When a defect is introduced, how late is it caught?"""
    rows = []
    if defects is None:
        return {"n": 2, "name": "Change Validation",
                "question": "When a defect is introduced, how late is it caught?",
                "state": "abstained", "headline": "the history cannot be read",
                "rows": []}

    if defects["shallow"]:
        rows.append({"label": "defects available to replay", "value": "—",
                     "flag": "info",
                     "note": "shallow clone — clone with history to replay"})
    else:
        rows.append({
            "label": "defects available to replay",
            "value": str(defects["replayable"]),
            "flag": "info" if defects["replayable"] else "warn",
            "note": "reverts, and fixes that touched a test — this "
                    "repository's own, not synthetic ones"})

    if mutants:
        rows.append({
            "label": "how the defect got in",
            "value": "2 ways: a fix reverted (%d), a covered line "
                     "mutated (%d)" % (len(catch["rows"]) if catch else 0,
                                       mutants["generated"]),
            "flag": "info",
            "note": "the first is this repository's own history — the files a "
                    "fix touched are taken back to their state at its parent, "
                    "so the defect actually happened here and the fix is the "
                    "answer key. The second is synthetic: one line the "
                    "tests already execute, changed. Both walk the same "
                    "ladder and are counted in the same row — a mutated "
                    "defect a hook refuses is caught before it is "
                    "written, exactly like a real one. The difference "
                    "is that a mutant nothing catches must be judged a "
                    "defect before it counts as one."})
    else:
        rows.append({
            "label": "how the defect got in",
            "value": "1 way: the repository's own fix, reverted",
            "flag": "info",
            "note": "the files the fix touched are taken back to their state "
                    "at its parent, so the defect is one that actually "
                    "happened here and the fix is the answer key. It is the "
                    "only injection that ran: nothing was mutated"
                    + (f" — {mutants_why.replace('cannot judge: ', '')}"
                       if mutants_why else ", and --mutate was not passed")
                    + ". A repository can be caught early by this and still "
                      "have failure modes nothing on this page looks for."})

    rows += coverage_rows(cover, cover_why)

    # Both injections feed ONE ladder. A mutant is a change to a file, so
    # every moment that can see a change can see it, and the question is the
    # same for both: where is this first caught? Only the mutants need a
    # second opinion about whether they are defects at all.
    mut_counts, pending, real, dropped = (
        mutant_ladder(mutants, judged) if mutants else ({}, 0, [], []))

    if catch:
        counts = {k: 0 for k in ladder}
        unusable = [r for r in catch["rows"] if not r["rung"]]
        for row in catch["rows"]:
            if row["rung"]:
                counts[row["rung"]] += 1
        placed = sum(counts.values())
        late = counts.get("ci", 0) + counts.get("never", 0)

        if not placed:
            # Every replay was unusable. Reporting a ladder of zeros here
            # would print a perfect score for a repository nothing was
            # measured on -- the exact failure this dimension is supposed to
            # be immune to. It happened: two defects whose tests could not run
            # for want of an installed dependency came out as "0 of 2 survive",
            # flagged green.
            why = (unusable[0].get("detail") or "the replay was unusable"
                   ) if unusable else "the replay was unusable"
            state = "abstained"
            headline = why.replace("unusable — ", "")
            rows.append({"label": "replay", "value": "could not judge",
                         "flag": "info",
                         "note": f"{len(unusable)} defect(s) could not be put "
                                 f"back: {why}. A repository whose tests "
                                 f"cannot run here is not a repository with "
                                 f"bad tests."})
        else:
            state = "measured"
            for k, v in mut_counts.items():
                counts[k] = counts.get(k, 0) + v
            placed = sum(counts.values())
            late = counts.get("ci", 0) + counts.get("never", 0)
            headline = (f"{late} of {placed} defects survive past the end of "
                        f"a session")
            rows.append(interception_layers(probe, catch, mutants, value,
                                            ladder, counts))
            rows.append({"label": "where each was first caught",
                         "value": "  ".join(f"{k}:{counts[k]}" for k in ladder),
                         "flag": "bad" if late else "ok",
                         "note": "the cliff sits between local-suite and ci: "
                                 "the session ends, the context is gone, and "
                                 "everything after it is paid for twice"
                                 + (f". {sum(mut_counts.values())} of these "
                                    f"came from mutation, the rest from this "
                                    f"repository's own history"
                                    if mut_counts else "")})

            # The rung name says the order. Only the seconds say the order
            # spans four orders of magnitude, which is the whole reason the
            # cliff is a cliff and not a slope.
            timed = []
            for k in ladder:
                got = sorted(r["seconds"] for r in catch["rows"]
                             if r.get("rung") == k
                             and r.get("seconds") is not None)
                if got:
                    timed.append(f"{k}:{secs(got[len(got) // 2])}")
            if timed:
                rows.append({
                    "label": "and how long that took",
                    "value": "  ".join(timed),
                    "flag": "info",
                    "note": "median per rung. Hook and suite times are this "
                            "machine's; the ci figure is this repository's own "
                            "run history, because what is waited on there is a "
                            "queue that does not exist here"
                            + ("" if catch.get("ci_seconds") is not None else
                               " - and it could not be read, so ci shows ?")})
            if unusable:
                rows.append({
                    "label": "defects that could not be put back",
                    "value": str(len(unusable)),
                    "flag": "info",
                    "note": (unusable[0].get("detail") or "")[:150]
                            + " — these are outside the count above, not "
                              "inside it as successes"})
    elif catch_why:
        state = "abstained"
        headline = catch_why.replace("cannot judge: ", "")
        rows.append({"label": "replay", "value": "could not judge",
                     "flag": "info",
                     "note": headline + " — a repository whose tests cannot "
                             "run here is not a repository with bad tests"})
    else:
        state = "open"
        headline = "not replayed — --no-full was passed"
        rows.append({"label": "replay", "value": "not run", "flag": "info",
                     "note": "the replay is on by default; drop --no-full "
                             "to put each defect back and record where it "
                             "is first caught"})

    if mut_counts and state != "measured":
        # The history half produced nothing -- no test command, a shallow
        # clone, --no-full. Mutation still walked the same ladder, so the
        # dimension has a reading and reporting it as unmeasured would throw
        # away something somebody paid for.
        placed = sum(mut_counts.values())
        late = mut_counts.get("ci", 0) + mut_counts.get("never", 0)
        if placed:
            state = "measured"
            headline = (f"{late} of {placed} mutated defects survive past the "
                        f"end of a session")
            rows.append(interception_layers(probe, catch, mutants, value,
                                            ladder, mut_counts))
            rows.append({
                "label": "where each was first caught",
                "value": "  ".join(f"{k}:{mut_counts.get(k, 0)}"
                                   for k in ladder),
                "flag": "bad" if late else "ok",
                "note": "all of these came from mutation; the repository's own "
                        "history did not supply any. The cliff sits between "
                        "local-suite and ci"})

    if mutants:
        rows += mutation_rows(mutants, ladder, judged)

    return {"n": 2, "name": "Change Validation",
            "question": "When a defect is introduced, how late is it caught?",
            "state": state, "headline": headline, "rows": rows}


def interception_layers(probe, catch, mutants, value, ladder, counts):
    """What there is to catch anything with, so a zero on the ladder is
    readable.

    `before-write: 0` had two completely different meanings and the page
    printed the same character for both:

    * nothing is wired at that moment -- the layer does not exist
    * three hooks are wired and not one of them caught anything

    The second is far worse and it looked identical to the first. A rung
    cannot be read without knowing what stands behind it, so the inventory is
    printed immediately above the ladder and the ladder is read against it.

    `rule` is in the list and has no rung, deliberately. A sentence in
    CLAUDE.md saying *never do X* is an interception layer -- it is trying to
    stop the same defect -- but it cannot be measured by injection, because
    firing a payload at a document does nothing. Testing it means giving an
    agent the rule and the task and seeing whether it writes the defect
    anyway: stochastic, expensive, and not repeatable. So it is counted and
    marked unenforced, which is the honest reading: a layer nobody can show
    working."""
    hooks = (catch or {}).get("hooks") or (mutants or {}).get("hooks") or {}
    moments = (probe or {}).get("moments") or {}
    disc = (probe or {}).get("discipline") or {}
    deny = (moments.get("5_before_action") or {}).get("permissions_deny", 0)
    pre = hooks.get("PreToolUse", (moments.get("5_before_action") or {})
                    .get("PreToolUse", 0)) + deny
    post = hooks.get("PostToolUse", 0)
    suite = bool((catch or {}).get("command") or (mutants or {}).get("command"))
    # Two different questions, and conflating them reported this repository --
    # five required checks on a protected branch -- as having no CI rung at
    # all. `catch["ci"]` is a command the replay could *run in the bench*, and
    # it recognises `ci.sh` and `make ci`: one of which this plugin scaffolds.
    # Grading a repository on whether it adopted our convention is the thing
    # 0025 rejected. Whether the rung *exists* is the probe's question, and it
    # already knew about the workflow.
    ci_runnable = bool((catch or {}).get("ci") or (mutants or {}).get("ci"))
    ci = ci_runnable or bool(disc.get("ci_entry"))

    # How many defects actually got as far as each rung. The walk stops at the
    # first red, so a lower rung showing 0 is *expected* when the rungs above
    # it caught everything -- nothing ever reached it. Calling that silent
    # would report a repository that catches defects early as one whose suite
    # does not work.
    total = sum(counts.get(k, 0) for k in ladder)
    reached, seen = {}, 0
    for k in ladder:
        reached[k] = total - seen
        seen += counts.get(k, 0)

    def state(exists, rung, what):
        if not exists:
            return f"{rung}: none wired"
        got = counts.get(rung, 0)
        if got:
            return f"{rung}: {what}, {got} caught"
        if not reached.get(rung, 0):
            return f"{rung}: {what}, nothing reached it"
        return f"{rung}: {what}, 0 of {reached[rung]} caught"

    bits = [
        state(pre, "before-write",
              f"{pre} hook(s)" + (f" incl. {deny} deny rule(s)"
                                  if deny else "")),
        state(post, "same-turn", f"{post} hook(s)"),
        state(suite, "local-suite",
              f"{len(disc.get('check_dirs') or [])} check dir(s)"),
        state(ci, "ci", ", ".join(disc.get("ci_entry") or []) or "an entry point")
        + ("" if ci_runnable or not ci else
           " (no entry point the replay could run here, so nothing was fired "
           "at it)"),
    ]
    unenforced = 0
    if value:
        unenforced = max(0, value.get("prohibitions", 0)
                         - len(value.get("already_enforced") or []))
    if unenforced:
        bits.append(f"rule: {unenforced} unenforced, no rung")

    empty = [b.split(":")[0] for b in bits if "none wired" in b]
    silent = [b.split(":")[0] for b in bits if " of " in b
              and b.endswith(" caught") and ", 0 of " in b
              # ...except the guards. They are a *destructive-action* layer,
              # and the defects walked past them here are ordinary bugs out of
              # this repository's own history. A guard that blocked one would
              # be a false block, which dimension 1 counts against a
              # repository -- so `before-write: 0 of N` is the correct
              # outcome, and flagging it red is a threshold no repository can
              # ever meet however good its guards are. Whether they work is
              # dimension 1's question and it is asked there properly, by
              # firing destructive actions at them -> 0038
              and not b.startswith("before-write")]
    return {
        "label": "what could have caught it",
        "value": " · ".join(bits),
        "flag": "bad" if silent else ("warn" if empty else "ok"),
        "note": ("a layer that is wired and caught nothing is a different "
                 "finding from a layer that does not exist, and the ladder "
                 "below prints the same 0 for both. A rung nothing reached "
                 "is neither: the walk stops at the first red"
                 + (f". Wired and silent: {', '.join(silent)}" if silent else "")
                 + (". `before-write` catching none of these is the right "
                    "outcome, not a silence: these are ordinary defects, and "
                    "a guard that blocked one would be a false block. "
                    "Dimension 1 is where the guards are fired at"
                    if pre else "")
                 + (f". Not wired at all: {', '.join(empty)}" if empty else "")
                 + (". `rule` has no rung because a document cannot be fired "
                    "at — it is a layer nobody can show working"
                    if unenforced else ""))}


def coverage_rows(c, why=""):
    """What the ladder cannot speak about, placed before it rather than after.

    Coverage predicts almost nothing in the direction people usually read it:
    for one project's one suite, its correlation with actually finding bugs is
    weak (Zhao, Zhou & Cohen 2026, r <= 0.481 pooled). Read the other way it is
    not a correlation at all but a guarantee -- a line no test executes cannot
    be caught at the `local-suite` rung, for any defect, ever.

    So these rows are the **denominator of the two injections below them**. The
    replay only reaches lines this repository's history put a bug in; mutation
    only touches lines the suite already executes. Coverage is the part both of
    them are silent about, and silence that is not stated reads as a pass.

    The numbers come from the ecosystem's own tool. A criterion that tool does
    not produce gets no row, and gets named in a row of its own instead: Go has
    no branch coverage at all, and a Go repository reading `0 of 0 branches`
    would be a lie about the language rather than a fact about the code."""
    if not c:
        if not why:
            return []
        return [{"label": "what no test executes", "value": "could not judge",
                 "flag": "info",
                 "note": why.replace("cannot judge: ", "")
                         + " — so the rows below are silent about an unknown "
                           "share of this repository, rather than about a "
                           "known one"}]

    LABEL = {"statement": "statements no test executes",
             "function": "functions no test enters",
             "branch": "branches never taken both ways",
             "mcdc": "conditions that never decided anything"}
    rows, criteria = [], c.get("criteria") or {}
    for key in ("statement", "function", "branch", "mcdc"):
        got = criteria.get(key)
        if not got:
            continue
        share = (1.0 - got["covered"] / got["total"]) if got["total"] else 0.0
        rows.append({
            "label": LABEL[key],
            "value": "%d of %d  (%.0f%%)" % (got["missing"], got["total"],
                                             100 * share),
            "flag": "bad" if share > 0.5 else "info",
            "note": "%s, %s" % (c.get("tool", "the ecosystem's tool"),
                                c.get("how", "measured"))})

    absent = [k for k in ("statement", "function", "branch", "mcdc")
              if k not in criteria]
    if absent and rows:
        rows.append({
            "label": "criteria this tool does not produce",
            "value": ", ".join(absent),
            "flag": "info",
            "note": "absent, not zero. No mainstream tool outside the "
                    "compilers computes MC/DC at all, and Go's tooling has no "
                    "branch coverage — so a missing row here is a fact about "
                    "the ecosystem, not about this repository"})
    return rows


def mutant_ladder(m, judged=None):
    """Where each mutant was first caught -- and which ones are defects.

    Three groups, and the difference between them is the whole design:

    * **Caught somewhere.** A hook refused it, or the suite went red, or CI
      did. Something asserted about that line, so the change is a real defect
      by construction and no second opinion is needed.
    * **Caught nowhere, and judged a defect.** An agent read the enclosing
      code and said a test catching this would be a test worth having. It
      belongs at `never`, and it is the most expensive row on the page.
    * **Caught nowhere, and judged not a defect.** It leaves the count
      entirely. `never` is only a failure if the thing that was never caught
      was worth catching, and the paper's own figure says three survivors in
      ten are not: an initial capacity, a log line, a default nobody promised.

    Unjudged survivors are in none of the three. They are `pending`, and they
    are reported as pending rather than parked at `never`, because counting
    them there would let a repository look worse for having bought a
    measurement nobody has finished reading."""
    counts = {k: 0 for k in m.get("ladder", {})} or {}
    for k in m.get("ladder", {}):
        counts[k] = m["ladder"][k]
    pending = counts.get("never", 0)
    counts["never"] = 0
    real, dropped = [], []
    for row in (judged or {}).get("rows", []):
        if row.get("judged") == "productive":
            real.append(row)
        elif row.get("judged") == "unproductive":
            dropped.append(row)
    counts["never"] = len(real)
    return counts, max(0, pending - len(real) - len(dropped)), real, dropped


def mutation_rows(m, ladder_names, judged=None):
    """The rows dimension 2 gains from the second injection.

    A surviving mutant is a **candidate**, never a finding. The paper this is
    copied from reports 70.6% of the survivors it showed Python developers
    being worth acting on, which also means most of the rest were not. Any row
    here that reads as a defect count would be wrong three times in ten, and
    the page has no way to tell which three -- only an agent that reads the
    enclosing code does, which is why the brief exists."""
    counted = m["killed"] + m["survived"]
    rows = []
    if not counted:
        rows.append({"label": "mutated lines", "value": "could not judge",
                     "flag": "info",
                     "note": "every mutant was unplaceable, or broke the "
                             "suite's own loading — neither is a verdict "
                             "about the repository"})
        return rows

    # The caveats come first on purpose. A figure taken over a flaky suite, or
    # over lines no test executes, is not the figure the paper reports, and
    # printing it above its own caveat invites the comparison it cannot
    # support.
    if m.get("flaky"):
        rows.append({
            "label": "!! the suite is flaky",
            "value": "not green on all 3 baseline runs",
            "flag": "warn",
            "note": "a mutant counts as caught whenever the suite goes red — "
                    "including when it would have gone red anyway. Every "
                    "mutation figure here is an upper bound on what this "
                    "repository really catches"})
    if not m.get("coverage", "").startswith("measured"):
        rows.append({
            "label": "!! coverage was not available",
            "value": "the covered-line restriction was dropped",
            "flag": "warn",
            "note": "so the mutated lines include lines no test executes, "
                    "which reach `never` by construction and say nothing "
                    "about this repository. Not comparable to the paper's "
                    "figure"})

    _c, pending, real, dropped = mutant_ladder(m, judged)
    if pending:
        rows.append({
            "label": "mutants nothing caught, awaiting judgement",
            "value": f"{pending} pending",
            "flag": "warn",
            "note": "NOT yet defects, and deliberately not counted at `never`. "
                    "Roughly three in ten will be lines nothing should assert "
                    "about, and this page cannot tell which — only something "
                    "that reads the enclosing code can. The brief for that "
                    "pass is in the JSON under `mutant_brief`; feed the "
                    "verdicts back with --mutant-answers"})
    if real or dropped:
        rows.append({
            "label": "of those, judged real defects",
            "value": f"{len(real)} of {len(real) + len(dropped)}",
            "flag": "bad" if real else "ok",
            "note": f"{len(dropped)} "
                    f"{'was' if len(dropped) == 1 else 'were'} judged not "
                    f"worth a test and left the "
                    f"count entirely — `never` is only a failure when the "
                    f"thing never caught was worth catching. Judged by an "
                    f"agent that did not write this code, which is a weaker "
                    f"judge than the paper's 66,798 developer clicks"
                    + ("; first: " + (real or dropped)[0].get("why", "")[:90]
                       if (real or dropped)[0].get("why") else "")})

    if m.get("suppressed"):
        rows.append({
            "label": "changes not worth making",
            "value": f"{m['suppressed']} suppressed",
            "flag": "info",
            "note": "mutants an arid-node rule threw away before running "
                    "anything — a changed log string, a timeout constant, a "
                    "flag default. 25 rules transcribed from the paper's "
                    "Appendix A; one was not, and is marked where it is "
                    "defined"})

    outside = []
    if m.get("broken"):
        outside.append(f"{m['broken']} broke the suite's loading")
    if m.get("timeout"):
        outside.append(f"{m['timeout']} hung past {m.get('budget_seconds')}s")
    if m.get("false_block"):
        outside.append(f"{m['false_block']} refused by a hook that refused the "
                       f"original line too")
    if outside:
        rows.append({
            "label": "mutants outside the ladder",
            "value": ", ".join(outside),
            "flag": "info",
            "note": "none of these is a catch. A suite that cannot import has "
                    "not detected anything, a hang is changed behaviour "
                    "nothing asserted, and a hook that refuses every edit to "
                    "a file has discriminated nothing"})
    return rows


# -- 3 -----------------------------------------------------------------------

def reliable_delivery(root, log, check_dirs=(), gate=None):
    """When a change is called done, what is the evidence?"""
    rows = []
    verdicts = [name for f, name in VERDICT_FILES
                if os.path.exists(os.path.join(root, f))]
    if os.path.isdir(os.path.join(root, ".github", "workflows")):
        verdicts.append("github-actions")
    pkg = os.path.join(root, "package.json")
    if os.path.exists(pkg):
        try:
            with open(pkg, encoding="utf-8", errors="replace") as fh:
                if "test" in (json.load(fh).get("scripts") or {}):
                    verdicts.append("npm test")
        except (OSError, ValueError):
            pass

    rows.append({
        "label": "a verdict someone can run",
        "value": ", ".join(verdicts) if verdicts else "none found",
        "flag": "ok" if verdicts else "bad",
        "note": "" if verdicts else
                "with no runnable verdict, whether a change is accepted "
                "depends on who happened to be looking"})

    homes = _test_homes(root, check_dirs)
    total = sum(n for _d, n in homes)
    rows.append({
        "label": "where the verdict is written",
        "value": (", ".join(f"{d}/ ({n})" for d, n in homes[:4])
                  + (f" … {len(homes)} places" if len(homes) > 4 else ""))
                 if homes else "nothing that verifies, anywhere in the tree",
        "flag": "ok" if homes else "bad",
        "note": (f"{total} file(s) — this is where the percentage below comes "
                 f"from, so if a suite of yours is missing from this list the "
                 f"percentage is wrong and not merely low")
        if homes else
        "no test, spec or check file was found under any name this instrument "
        "knows — if that is wrong, nothing else in this dimension is right"})

    ci_files, ci_runs = _ci_verdict(root, check_dirs)
    if ci_files:
        rows.append({
            "label": "CI runs the suite",
            "value": (", ".join(f"{f} → {cmd}" for f, cmd in ci_runs[:2])
                      + (" …" if len(ci_runs) > 2 else "")) if ci_runs else
                     "no — it is defined, but names no test runner",
            "flag": "ok" if ci_runs else "bad",
            "note": "" if ci_runs else
                    f"{len(ci_files)} pipeline file(s) — {', '.join(ci_files[:3])}"
                    + (" …" if len(ci_files) > 3 else "")
                    + " — a tick from a pipeline that lints, builds and "
                      "deploys without running a suite is a green light that "
                      "means the build compiled"})
    else:
        rows.append({
            "label": "CI runs the suite",
            "value": "no pipeline found",
            "flag": "warn",
            "note": "whatever verdict exists is caught only when somebody "
                    "chooses to run it on their own machine"})

    stranded = _stranded_checks(root, check_dirs)
    if stranded:
        rows.append({
            "label": "checks only one machine can run",
            "value": str(len(stranded)),
            "flag": "bad",
            "note": "; ".join(f"{f} hardcodes {p}" for f, p in stranded[:2])
                    + " — absent here, so the check is inert for everyone but "
                      "whoever set that machine up, while still looking from "
                      "outside like coverage"})

    if log is None:
        rows.append({"label": "changes that verified nothing", "value": "—",
                     "flag": "info", "note": "the history cannot be read"})
        state, headline = "abstained", "the history cannot be read"
    else:
        touched = [c for c in log[:60] if any(
            _is_source(p, check_dirs) for p in c[2])]
        # Renames, reformatting and dependency bumps all touch source and
        # none of them owe a test, so the denominator is narrowed to the
        # changes that add behaviour or repair it. A subject that is not
        # typed cannot be narrowed and is counted: the alternative is a
        # denominator that quietly shrinks and a number that quietly improves
        # -> 0039
        typed = [c for c in touched
                 if history_mod.owes_a_test(c[1]) is not None]
        recent = [c for c in touched if history_mod.owes_a_test(c[1]) is not
                  False]
        bare = [c for c in recent
                if not any(_verifies(p, check_dirs) for p in c[2])]
        pct = round(100 * len(bare) / len(recent)) if recent else 0
        state = "measured"
        headline = (f"{len(bare)} of the last {len(recent)} changes that owe "
                    f"a test touched nothing that verifies them")
        if len(typed) >= max(4, len(touched) // 2):
            how = (f"{len(touched) - len(recent)} of {len(touched)} change(s) "
                   f"to source are excluded as owing no test — renames, "
                   f"formatting, dependency bumps, docs and chores, read off "
                   f"the commit type")
        else:
            how = ("the denominator is every change to source, because these "
                   "subjects are not typed — nothing here can tell a rename "
                   "from a new function, and guessing would shrink the "
                   "denominator without changing the repository")
        rows.append({
            "label": "changes that verified nothing",
            "value": f"{len(bare)}/{len(recent)}  ({pct}%)",
            "flag": "bad" if pct >= 80 else ("warn" if pct >= 40 else "ok"),
            "note": "the green light can be real and still have nothing to "
                    "do with what was changed. " + how})

        # Most unverified changes are not worth anyone's attention -- in a
        # repository that writes tests, the ones without are usually small.
        # Changes to the machinery that does the verifying are the exception:
        # rare, and when one of them breaks, the thing that would have caught
        # it is the thing that changed.
        # Deliberately drawn from every change to source, not from the
        # narrowed set above. `ci:` and `build:` owe no unit test and are
        # excluded from the percentage for that reason -- but a change to the
        # machinery that does the verifying owes evidence whatever its commit
        # type, and narrowing here would hide exactly the commits this row
        # exists to find.
        unverified = [c for c in touched
                      if not any(_verifies(p, check_dirs) for p in c[2])]
        critical = [c for c in unverified if any(CRITICAL_PATH.search(p)
                                                 for p in c[2])]
        if critical:
            rows.append({
                "label": "unverified changes to the machinery itself",
                "value": str(len(critical)),
                "flag": "warn",
                "note": "CI, build or dependency files changed with nothing "
                        "verifying the change: "
                        + "; ".join(c[1][:44] for c in critical[:2])})

    # The repair log is gone. It counted places repaired more than once and
    # read that as churn, and the reading does not hold: plenty of code is
    # revised repeatedly on purpose, and a counter cannot tell that from a
    # place nobody can get right. A number nobody can act on is worse than no
    # number, because it occupies the space where an actionable one would go.

    # Whether anything is *obliged* to look before a change lands. Not whether
    # the checks work -- dimension 2 injects defects and measures that. This
    # is the failure a repository can have while every check passes.
    if gate:
        p = gate["protection"]
        if p.get("readable"):
            required = p.get("required_checks") or []
            rows.append({
                "label": "can the verification be skipped",
                "value": gate["state"],
                "flag": "ok" if required else "bad",
                "note": ("required to merge: " + ", ".join(required))
                        if required else
                        ("nothing is required on `%s`, so a red run can be "
                         "merged past. Running on pull requests and being "
                         "required to pass are different settings, and every "
                         "surface a person normally sees — the green tick, the "
                         "badge, the workflow file — shows only the first"
                         % p.get("branch", "the default branch"))})
        else:
            rows.append({
                "label": "can the verification be skipped",
                "value": "not readable",
                "flag": "info",
                "note": p.get("why", "") + " — this is not the same as "
                        "`nothing is required`, and reporting it that way "
                        "would be a confident claim about a repository "
                        "nobody read"})
        if gate["swallow_candidates"]:
            unexplained = [c for c in gate["swallow_candidates"]
                           if not c["reason_given"]]
            rows.append({
                "label": "steps that could turn a red run green",
                "value": "%d candidate(s), %d with no reason given"
                         % (len(gate["swallow_candidates"]), len(unexplained)),
                "flag": "warn" if unexplained else "info",
                "note": "`continue-on-error: true` and `|| true`. Not counted "
                        "as findings: legitimate uses exist and every one this "
                        "project has seen carried a comment saying why, which "
                        "is a signal an agent can use and a counter cannot"
                        + ("; unexplained: " + ", ".join(
                            "%s:%d" % (c["file"], c["line"])
                            for c in unexplained[:3]) if unexplained else "")})

    return {"n": 3, "name": "Reliable Delivery",
            "question": "When a change is called done, what is the evidence?",
            "state": state, "headline": headline, "rows": rows}


def _test_homes(root, check_dirs):
    """Name the directories the verdict actually comes from.

    Test trees sit wherever a repository put them -- `tests/`, but just as
    often `frontend/src/__tests__`, `backend/spec`, `packages/*/test`. A
    percentage computed over matches that are never named makes a wrong answer
    invisible: the number looks the same whether the instrument found every
    suite or missed the subtree they all live in.

    So this row exists to be contradicted. It says where it looked and what it
    found there, and the agent reading the page can open the repository and say
    "you missed `apps/api/tests`" -- which is a correction somebody can act on,
    where "the coverage number seems low" is not."""
    homes = {}
    for here, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs
                   if not d.startswith(".") and d not in NOT_OURS]
        for f in files:
            rel = os.path.relpath(os.path.join(here, f), root)
            rel = rel.replace(os.sep, "/")
            if not _verifies(rel, check_dirs):
                continue
            d = os.path.dirname(rel) or "."
            homes[d] = homes.get(d, 0) + 1
    return sorted(homes.items(), key=lambda kv: (-kv[1], kv[0]))


def _ci_verdict(root, check_dirs=()):
    """Does the pipeline run a suite, or only exist?

    Returns (where CI is defined, which of those name a runner). Existing and
    running the tests are different facts, and only the first one is what
    "has CI" usually means when somebody says it.

    Two matchers, for the reason `VERIFIES` has two. `RUNNER` knows the common
    tools; a repository whose verdict is a script it wrote itself uses none of
    them, and scoring that as "no suite" would mark a repository down for not
    being shaped like the ones we had in mind. So the second matcher looks for
    the repository's OWN check directories appearing in the pipeline -- this
    project's CI would otherwise read as running nothing, since it invokes
    `selftest.py` files and never says pytest."""
    ours = [d.rstrip("/") for d in check_dirs if d.strip("/")]
    found, runs = [], []
    for rel in CI_FILES:
        full = os.path.join(root, rel.replace("/", os.sep))
        paths = []
        if os.path.isdir(full):
            for here, dirs, files in os.walk(full):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                paths += [os.path.join(here, f) for f in sorted(files)]
        elif os.path.isfile(full):
            paths = [full]
        for pth in paths:
            found.append(os.path.relpath(pth, root).replace(os.sep, "/"))
            try:
                with open(pth, encoding="utf-8", errors="replace") as fh:
                    body = fh.read(200000)
            except OSError:
                continue
            m = RUNNER.search(body)
            if m:
                runs.append((found[-1], m.group(0).strip()))
                continue
            hit = next((d for d in ours if d in body), None)
            if hit is None:
                hit = next((tok for tok in PATH_TOKEN.findall(body)
                            if _verifies(tok, ours)), None)
            if hit:
                runs.append((found[-1], hit))
    return found, runs


def _stranded_checks(root, check_dirs):
    """Checks that hardcode a path only one machine has.

    Only reported when the path is absent here: on the author's own machine it
    resolves, and calling their working setup broken would be the instrument
    inventing a defect."""
    out = []
    roots = list(check_dirs) + ["scripts", "tools", "bin", "ci"]
    for rel in roots:
        base = os.path.join(root, rel)
        if not os.path.isdir(base):
            continue
        for here, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if not f.endswith(RUNNABLE_EXT):
                    continue
                full = os.path.join(here, f)
                try:
                    with open(full, encoding="utf-8", errors="replace") as fh:
                        body = fh.read(200000)
                except OSError:
                    continue
                for m in PINNED_PATH.finditer(body):
                    hit = m.group(1).replace("\\\\", "\\")
                    if not os.path.exists(hit):
                        out.append((os.path.relpath(full, root), hit))
                        break
    return sorted(out)[:8]


def _verifies(path, check_dirs=()):
    """Does touching this path constitute verifying something?"""
    if VERIFIES.search(path):
        return True
    return any(path == d or path.startswith(d.rstrip("/") + "/")
               for d in check_dirs)


def _is_source(path, check_dirs=()):
    if _verifies(path, check_dirs):
        return False
    return path.rsplit(".", 1)[-1].lower() in (
        "py", "ts", "tsx", "js", "jsx", "go", "rs", "rb", "java", "kt", "c",
        "cc", "cpp", "h", "hpp", "cs", "php", "swift", "scala", "sh", "vue")


# -- 4 -----------------------------------------------------------------------

def repository_memory(root, log, check_dirs=(), truth=None,
                      conflict=None, conflict_judged=None,
                      promises=None, truth_judged=None):
    """Is what this repository writes down still true, and worth keeping?

    `truth` is `truth.assess()`'s output, and it asks not how much the
    repository writes down but **how much of it is still true**. Thickness
    appears as a denominator and never as a score: counting what a repository
    keeps would grade it on whether it adopted our conventions, would reward
    this plugin's own presence, and would call 0024 -- which cut the standing
    cost by 81% -- a regression while dimension 5 called it an improvement.
    A denominator has none of those properties -> 0025, 0027

    There used to be a second half here, and it was the answer to a better
    question: two agents, one on this tree and one on a copy with the standing
    context removed, with the difference between them as the measurement. It
    was removed because the difference could not be told from the noise --
    two runs of the same pair disagreed by more than the thing being measured
    -> 0042"""
    rows = []

    if truth is not None:
        t = truth["thickness"]
        rows.append({
            "label": "what it writes down",
            "value": "  ".join(f"{k}:{v}" for k, v in t.items() if v),
            "flag": "info",
            "note": "the denominator every row below is read against: "
                    "adding files cannot "
                    "raise anything on this page, because a repository is not "
                    "better for having adopted somebody else's conventions"})

        proven = truth["proven"]
        rows.append({
            "label": "references that do not resolve",
            "value": (f"{len(proven)} across {truth['checked']} document(s)"
                      if proven else
                      f"none across {truth['checked']} document(s)"),
            "flag": "bad" if len(proven) > 2 else ("warn" if proven else "ok"),
            "note": ("; ".join(f"{r['file']} → {r['claim']}"
                               for r in proven[:3])[:220]
                     if proven else
                     "every link in the non-historical documents points at "
                     "something that is there. Historical records — decisions, "
                     "changelogs, postmortems — are excluded: describing a "
                     "state that has changed is their job")})

        cands = truth["candidates"]
        if cands:
            by = {}
            for c in cands:
                by[c["tier"]] = by.get(c["tier"], 0) + 1
            judged = truth_judged
            spread = "  ".join(f"T{k}:{v}" for k, v in sorted(by.items()))
            if judged:
                # A reading that happened and was written down. Without this
                # the same 24 candidates came back on every run forever, and
                # each reader paid again to rediscover that most of them
                # describe a repository this one scaffolds rather than this
                # one -> conflict.py, which had the same hole.
                rows.append({
                    "label": "candidates for a second reading",
                    "value": "%d real of %d candidate(s)%s" % (
                        len(judged["real"]), judged["judged"],
                        ", %d unread" % judged["pending"]
                        if judged["pending"] else ""),
                    "flag": "bad" if judged["real"] else "ok",
                    "note": ("read, not counted: " + spread + ". "
                             + (judged["real"][0].get("why", "")[:160]
                                if judged["real"]
                                else "every candidate was dismissed on "
                                     "reading, and the reasons are in the "
                                     "answers file"))})
            else:
                rows.append({
                    "label": "candidates for a second reading",
                    "value": spread,
                    "flag": "info",
                    "note": "NOT findings. A machine can say where to look and "
                            "cannot say what is wrong: T1 a count the tree "
                            "disagrees with, T2 a path resolving nowhere, T3 a "
                            "document the code moved out from under, T4 two "
                            "documents giving one number two values. An agent "
                            "reads these and keeps what is real — "
                            "`truth.py --brief <run.json>`, then "
                            "`--truth-answers`"})

    records = _mistake_records(root)
    if records:
        readers = _readers_of(root, records)
        rows.append({
            "label": "somewhere mistakes are written",
            "value": ", ".join(os.path.relpath(p, root) for p in records[:3])
                     + (" …" if len(records) > 3 else ""),
            "flag": "ok" if readers else "warn",
            "note": ("referenced from " + ", ".join(readers)) if readers else
                    "nothing references it — a write-only record of mistakes "
                    "is the failure that looks healthiest from outside"})
    else:
        rows.append({"label": "somewhere mistakes are written",
                     "value": "none found", "flag": "warn",
                     "note": "no postmortem, decision record, known-issues or "
                             "changelog anywhere in the tree"})

    # Everything above asks what the repository writes down. This asks what
    # shape the sentences are in, which is a separate question with its own
    # evidence: reframing an instruction without changing what it asks moves
    # how reliably it is followed -> reframe.py. Candidates only; which are
    # worth rewriting is a reading, and a repository may mean its prose.
    # It costs nothing -- no agent, no network, one walk of the tracked `.md`
    # files -- so it runs every time, the way `truth` does. A measurement
    # nobody has to opt into is a measurement that gets looked at.
    rows.extend(reframe_mod.render(reframe_mod.measure(root)))

    # Does the repository contradict itself? Stage one is lexical and narrows
    # hard -- 1711 possible pairs to one candidate here -- because a filter
    # that hands an agent hundreds of pairs has moved the reading problem
    # rather than solved it.
    if conflict:
        total = conflict["candidates_total"]
        if not total:
            rows.append({
                "label": "documents that contradict each other",
                "value": "no candidate among %d pair(s)"
                         % conflict["possible_pairs"],
                "flag": "ok",
                "note": "no two documents name the same flag, path or "
                        "identifier and attach different values to it. This "
                        "is a lexical filter: a contradiction phrased without "
                        "a shared token is invisible to it"})
        elif conflict_judged:
            real = conflict_judged["real"]
            rows.append({
                "label": "documents that contradict each other",
                "value": "%d real of %d candidate(s)" % (len(real), total),
                "flag": "bad" if real else "ok",
                "note": ("; ".join("`%s`: %s vs %s"
                                   % (p.get("subject", "?"), p.get("a", "?"),
                                      p.get("b", "?")) for p in real[:3])
                         or "every candidate was dismissed on reading")})
        else:
            rows.append({
                "label": "documents that contradict each other",
                "value": "%d candidate(s) of %d pair(s), not yet judged"
                         % (total, conflict["possible_pairs"]),
                "flag": "info",
                "note": "a candidate is not a conflict — two documents naming "
                        "the same thing with different values are as often an "
                        "example beside a default. Judge them with "
                        "`assess/conflict.py --brief`"
                        + (". %d pair(s) excluded as supersession, which is "
                           "contradiction on purpose"
                           % conflict["excluded_by_supersession"]
                           if conflict["excluded_by_supersession"] else "")})

    # Does the code do what the documents promise? Only printed once it has
    # actually been run: "21 testable claims, not checked" is a fact about
    # this session, not about the repository, and a row with an empty verdict
    # reads as a failing grade.
    if promises and any(c.get("verdict", "not run") != "not run"
                        for c in promises):
        counts = {}
        for c in promises:
            key = c.get("verdict", "not run")
            counts[key] = counts.get(key, 0) + 1
        bad = counts.get("inconsistent", 0)
        # A claim the real code *failed* is not a claim the real code passed.
        # It is waiting for the round that decides whether the document or the
        # test was wrong, and reporting it under an `ok` alongside "the code
        # passed it" is wrong in the one direction this page cannot afford.
        pending = counts.get("pending", 0)
        untested = counts.get("not tested", 0) + counts.get("not run", 0)
        if bad:
            note = "; ".join(c["doc"] + ": " + c["says"][:70]
                             for c in promises
                             if c.get("verdict") == "inconsistent")
        elif pending:
            note = ("%d claim(s) undecided: the real code failed a test and "
                    "round two — which decides whether the document or the "
                    "test was wrong — has not run. Pass --promise-impls"
                    % pending)
        elif untested:
            note = ("no claim was contradicted, but %d got no runnable test "
                    "at all, so they were not asked" % untested)
        else:
            note = ("each one had a test written from the document alone, and "
                    "the code passed it")
        rows.append({
            "label": "promises the code does not keep",
            "value": "%d of %d testable claim(s)" % (bad, len(promises)),
            "flag": "bad" if bad else "info" if (pending or untested) else "ok",
            "note": note
                    + ". Recall is low by construction — CASCADE reports 0.21 "
                      "on method-level documentation, and this reads prose "
                      "across a whole repository, so nothing found here is a "
                      "long way from nothing there"})

    # The navigation half used to live here: two probe agents, one on this
    # tree and one on a copy with the standing context removed, and the
    # difference between them scored. It was removed -- the variance between
    # two runs of the same pair was wider than anything it could measure, so a
    # repository could be told it had improved by rerunning
    # -> docs/decisions/0042
    proven = len(truth["proven"]) if truth is not None else 0
    head = (f"{proven} reference(s) in its documentation point at nothing"
            if proven else
            f"every reference in {truth['checked']} document(s) resolves"
            if truth is not None else "nothing could be read")
    return {"n": 4, "name": "Repository Memory",
            "question": "Is what this repository writes down still true, and "
                        "is it worth what it costs to keep?",
            "state": "measured" if truth is not None else "abstained",
            "headline": head, "rows": rows}


def _mistake_records(root):
    out = []
    for here, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs
                   if not d.startswith(".") and d not in
                   ("node_modules", "vendor", "venv", "dist", "build")]
        if here.count(os.sep) - root.count(os.sep) > 3:
            dirs[:] = []
        for f in files:
            low = f.lower()
            if not low.endswith((".md", ".rst", ".txt")):
                continue
            if any(h in low for h in RECORD_HINTS):
                out.append(os.path.join(here, f))
        for d in list(dirs):
            if d.lower() in ("decisions", "adr", "postmortems", "incidents"):
                out.append(os.path.join(here, d))
                dirs.remove(d)
    return sorted(out)[:12]


def _readers_of(root, records):
    """Anything that points at the record -- prose that links it, or a hook."""
    names = {os.path.basename(p).lower() for p in records}
    names |= {os.path.relpath(p, root).lower() for p in records}
    readers = []
    for cand in ("CLAUDE.md", "AGENTS.md", "README.md",
                 os.path.join(".claude", "CLAUDE.md")):
        p = os.path.join(root, cand)
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                body = fh.read().lower()
        except OSError:
            continue
        if any(n in body for n in names):
            readers.append(cand)
    for event, cmd in _hook_commands(root):
        if any(n in cmd.lower() for n in names):
            readers.append(f"{event} hook")
    return readers


# -- 5 -----------------------------------------------------------------------

def context_economy(root, probe, blast=None, value=None, units=None):
    """What does the harness cost per turn, what at worst -- and on what?

    A token count is a bill with no itemisation. Two repositories with the same
    thousand-token floor are not in the same position: one spends it on four
    constraints an agent could not have guessed, the other on forty
    prohibitions against things nobody was going to do.

    `value` is `value.assess()`'s reading of the floor, and `blast` is
    dimension 1's, which is what makes the sharpest row here possible: a
    prohibition against something the repository's hooks **already refuse and
    were measured refusing** is paying rent on every turn to restate what the
    machine says better -> 0029"""
    always = probe["always_on_skill_tokens"]
    by_origin = probe.get("skill_tokens_by_origin") or {}
    from_plugins = by_origin.get("plugin", 0)

    entry = 0
    for cand in ("CLAUDE.md", os.path.join(".claude", "CLAUDE.md"),
                 "AGENTS.md"):
        entry += tokens(chars(os.path.join(root, cand)))

    rules = _rule_files(root)
    uncond = sum(tokens(chars(p)) for p in rules if not _scoped(p))
    scoped = [tokens(chars(p)) for p in rules if _scoped(p)]

    nested = []
    for here, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")
                   and d not in ("node_modules", "vendor", "venv")]
        if here == root:
            continue
        if "CLAUDE.md" in files:
            nested.append(tokens(chars(os.path.join(here, "CLAUDE.md"))))

    floor = entry + uncond + always
    worst_extra = max(scoped or [0]) + max(nested or [0])
    ceiling = floor + worst_extra
    parked = sum(scoped) + sum(nested)

    # The part this repository can do anything about. Skill descriptions from
    # installed plugins are real tokens and are charged, but they are charged
    # to the machine: judging a repository on them would score it for what
    # somebody else installed.
    theirs = floor - from_plugins
    rows = [
        {"label": "floor — paid on every turn", "value": f"~{floor} tokens",
         "flag": "ok" if theirs < 2000 else ("warn" if theirs < 6000 else "bad"),
         "note": f"~{theirs} from this repository "
                 f"(~{entry} in entry files, ~{uncond} in unconditional rules)"
                 + (f", ~{from_plugins} from plugins installed on this machine, "
                    f"which this repository cannot fix" if from_plugins else "")},
        {"label": "ceiling — the worst a single turn reaches",
         "value": f"~{ceiling} tokens",
         "flag": "info",
         "note": "floor plus the largest scoped rule and the largest nested "
                 "CLAUDE.md that a single turn could pull in"},
        {"label": "parked — installed, arrives only when asked",
         "value": f"~{parked} tokens",
         "flag": "info",
         "note": f"{len(scoped)} scoped rule(s), {len(nested)} nested "
                 f"CLAUDE.md — this is the escape hatch, not the bill"},
    ]
    if value:
        pro, req = value["prohibitions"], value["requirements"]
        rows.append({
            "label": "what the floor is spent on",
            "value": f"{pro} prohibition(s) · {req} requirement(s) · "
                     f"{value['kinds'].get('statement', 0)} statement(s)",
            # Not a threshold on prohibitions as such -- some repositories are
            # dangerous and should be full of them. A floor that is almost
            # entirely `don't` is usually a list of one-off incidents nobody
            # deleted, which is worth a look and is not a failure.
            "flag": "warn" if pro > 3 * req and pro > 8 else "info",
            "note": "a prohibition earns its place against a mistake somebody "
                    "actually makes; a requirement is working every time the "
                    "thing it requires comes up"})

        enforced = value["already_enforced"]
        if enforced:
            rows.append({
                "label": "prohibitions a guard already enforces",
                "value": f"{len(enforced)} of {pro}",
                "flag": "warn",
                "note": "these restate something dimension 1 measured this "
                        "repository actually refusing — the guard is not "
                        "optional, does not depend on the agent having read "
                        "anything, and costs nothing until it fires: "
                        + "; ".join(f"{h['file']}: {h['text'][:60]}"
                                    for h in enforced[:2])})

        loaded = value["path_scoped_but_loaded"]
        if loaded:
            rows.append({
                "label": "sentences about one path, paid for on every turn",
                "value": str(len(loaded)),
                "flag": "info",
                "note": "not wrong, misfiled — the same words under a "
                        "path-scoped rule cost nothing until somebody touches "
                        "that path: "
                        + "; ".join(f"{h['about']}" for h in loaded[:4])})

    if not entry and not uncond:
        # Zero standing cost and no harness at all are the same measurement.
        # Printed alone, the number reads as praise for the repository that
        # has done the least.
        rows[0]["note"] = ("nothing this repository ships is loaded on every "
                           "turn, because there is no CLAUDE.md and no "
                           "unconditional rule — a floor of zero here is the "
                           "absence of a harness, not a lean one"
                           + (f". ~{from_plugins} comes from plugins installed "
                              f"on this machine, which this repository cannot "
                              f"fix" if from_plugins else ""))

    # The same measurement per file instead of as a sum. A repository paying
    # 1200 tokens a turn across twenty lean files is in a different position
    # from one paying 1200 across nineteen lean files and one bloated one,
    # and the total is identical. Nobody can act on a total.
    if units and units.get("outliers"):
        first = units["outliers"][0]
        rows.append({
            "label": "files unlike their neighbours",
            "value": "%d of %d unit(s)" % (len(units["outliers"]),
                                           len(units["units"])),
            "flag": "warn",
            "note": "%s (~%d tokens): %s"
                    % (first["path"], first["tokens"], "; ".join(first["why"]))
                    + (". %d sentence(s) appear in more than one loaded file, "
                       "paid for twice on every turn and free to drift apart"
                       % units["duplicated_sentences"]
                       if units["duplicated_sentences"] else "")
                    + ". Each is compared to the median of its own kind, not "
                      "to a threshold chosen for a repository nobody has seen"})
    elif units:
        rows.append({
            "label": "files unlike their neighbours",
            "value": "none of %d unit(s)" % len(units["units"]),
            "flag": "ok",
            "note": "no rule, document, skill or CLAUDE.md is far from the "
                    "median of its own kind, prohibition-heavy, mostly fenced, "
                    "or repeating another file's paragraphs"})

    return {"n": 5, "name": "Context Economy",
            "question": "What does the harness cost per turn, and at worst?",
            "state": "measured",
            "headline": (f"~{theirs} tokens on every turn from this "
                         f"repository, ~{ceiling - from_plugins} at worst"),
            "rows": rows}


# ---------------------------------------------------------------------------

def assess(root, probe, blast, catch, catch_why, defects, log, ladder,
           truth=None, value=None, mutants=None, mutants_why="",
           judged=None, cover=None, cover_why="", observe=None,
           observe_judged=None, gate=None, conflict=None,
           conflict_judged=None, promises=None, units=None,
           permitted=None, truth_judged=None):
    """`probe` is what `probe_repo.py` found; `truth` is what `truth.assess()`
    read out of the documents, which costs nothing and runs every time; and
    `mutants` is the second injection into dimension 2, which is None unless
    somebody passed `--mutate` and paid for it."""
    check_dirs = tuple((probe.get("discipline") or {}).get("check_dirs") or ())
    return [
        controlled_execution(root, probe, blast, observe,
                             observe_judged, permitted),
        change_validation(defects, catch, catch_why, ladder, mutants,
                          mutants_why, judged, cover, cover_why, probe, value),
        reliable_delivery(root, log, check_dirs, gate),
        repository_memory(root, log, check_dirs, truth,
                          conflict, conflict_judged, promises, truth_judged),
        context_economy(root, probe, blast, value, units),
    ]


def main():
    import argparse
    sys.path.insert(0, HERE)
    from history import commits                          # noqa: PLC0415
    import blast as blast_mod                            # noqa: PLC0415
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "probe_repo", os.path.join(PARENT, "probe_repo.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    probe = mod.probe(root)
    if probe is None:
        print("cannot judge: not a git repository", file=sys.stderr)
        return 2

    from history import mine                               # noqa: PLC0415
    found = mine(root)
    defects = None if found is None else {
        "replayable": len([x for x in found["revert"] + found["fix_test"]
                           if x["small"]]),
        "fix_no_test": len(found["fix_no_test"]),
        "has_test_files": found["has_test_files"],
        "shallow": found["shallow"]}
    blast = (blast_mod.assess(root, "", "")
             if os.path.isdir(os.path.join(root, ".claude")) else None)
    dims = assess(root, probe, blast, None, "", defects, commits(root),
                  ["before-write", "same-turn", "local-suite", "ci", "never"])
    if a.json:
        print(json.dumps(dims, indent=2, ensure_ascii=False))
    else:
        for d in dims:
            print(f"\n{d['n']}. {d['name']} — {d['headline']}")
            for row in d["rows"]:
                print(f"   {row['flag']:5} {row['label']}: {row['value']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
