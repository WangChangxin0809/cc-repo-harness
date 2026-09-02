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
import reframe as reframe_mod
import surface as surface_mod  # noqa: E402
# Coverage and mutation row builders -- split into their own file by
# decision 0053, re-exported here so `dim_mod.mutant_ladder` and friends
# keep resolving for every existing caller, `assess/selftest.py` included.
from mutation_tables import (  # noqa: E402
    coverage_rows, mutant_ladder, mutation_rows, suite_rows,
)

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

# The username slot filled with the shape rather than a person. A check
# reading `/home/you/.cache/chrome` is a fixture or a line of documentation,
# not a check that runs on one machine only, and `check_no_machine_paths.py`
# already decided this for the whole tree -- it lets a placeholder through and
# stops a real name. This list is that one, kept in step by a selftest case
# that fails when the two drift apart.
PLACEHOLDER_USER = {
    "you", "user", "username", "your-name", "yourname", "me", "name",
    "someone", "somebody", "example", "alice", "bob", "carol", "dev",
    "developer", "test", "tester", "foo", "bar", "myuser", "my-user",
    "runner", "root", "ubuntu", "vagrant", "docker", "circleci", "travis",
    "jenkins", "builder", "codespace", "vscode", "node", "app",
}

_USER_SLOT = re.compile(r"^(?:/(?:home|Users)/|[A-Za-z]:\\Users\\)([^/\\]+)")


def _only_the_shape(path):
    """Is the username slot filled with a placeholder rather than a person?

    A path with no username slot at all -- `C:\\Program Files\\...` -- is not a
    placeholder; it is an install root that exists on one kind of machine, and
    that is the finding."""
    m = _USER_SLOT.match(path)
    return bool(m) and m.group(1).lower() in PLACEHOLDER_USER


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
        # Not an abstention. With no .claude/ there is nothing to ask, and
        # the answer to "is anything refused" is therefore known: no. The
        # first version said `not asked` under a label no sub-item claimed,
        # so the worst possible reading left the brief and the radar drew
        # it exactly like a dimension nobody measured.
        rows.append({"label": "refused before they happen",
                     "value": "0/6 — nothing is wired",
                     "flag": "bad",
                     "note": "no .claude/, so no hook and no deny rule: every "
                             "destructive action goes through, and that is a "
                             "measurement, not a gap in one"})
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

    rows += suite_rows(catch)
    rows += coverage_rows(cover, cover_why)

    # Both injections feed ONE ladder. A mutant is a change to a file, so
    # every moment that can see a change can see it, and the question is the
    # same for both: where is this first caught? Only the mutants need a
    # second opinion about whether they are defects at all.
    mut_counts, pending, real, dropped = (
        mutant_ladder(mutants, judged) if mutants else ({}, 0, [], []))

    if catch:
        unreached = _unreached(catch, cover)
        counts = {k: 0 for k in ladder}
        unusable = [r for r in catch["rows"] if not r["rung"]]
        for row in catch["rows"]:
            if row["rung"] and row["sha"] not in unreached:
                counts[row["rung"]] += 1
        placed = sum(counts.values())
        late = counts.get("ci", 0) + counts.get("never", 0)
        if unreached:
            rows.append({
                "label": "defects outside the suite's reach",
                "value": str(len(unreached)),
                "flag": "info",
                "note": "nothing went red, and the suite never executed the "
                        "file the defect is in — so this is not a miss, it "
                        "is a region the command you gave does not cover: "
                        + "; ".join(f"{sha} ({', '.join(files[:2])})"
                                    for sha, files in
                                    list(unreached.items())[:3])
                        + ". Not counted as surviving. Pass a command that "
                          "reaches it, or read this as the finding"})

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
            # The control: the suite as it was before the fix. Kept beside
            # the ladder because the ladder alone is close to a tautology --
            # the replay keeps the fix's own regression test, which was
            # written to fail on exactly this.
            judged_prior = [r for r in catch["rows"]
                            if r.get("prior_suite") in ("caught", "missed")]
            if judged_prior:
                caught = [r for r in judged_prior
                          if r["prior_suite"] == "caught"]
                rows.append({
                    "label": "caught by a test that already existed",
                    "value": f"{len(caught)} of {len(judged_prior)} replayed",
                    "flag": "info",
                    "note": "source and tests both put back to before the "
                            "fix, then the whole suite. The rest were caught "
                            "only by the test the fix itself brought, which "
                            "is the ordinary case: a suite that sees a "
                            "defect before its regression test exists is "
                            "the exception worth knowing about"
                            + (": " + ", ".join(r["sha"] for r in caught[:3])
                               if caught else "")})
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
    elif not defects["shallow"] and not defects["has_test_files"]:
        # Absent in the repository, not on this machine. `no runnable test
        # command` covers two situations that must never share a row: a
        # toolchain this machine lacks, which is an abstention, and a
        # repository with no test file anywhere in it, which is the finding.
        # The history has already been read for this and it cost nothing, so
        # it is measured even under --no-full -> 0047
        state = "measured"
        headline = ("no suite: nothing here can catch a defect before the "
                    "session ends")
        rows.append({
            "label": "a suite in the repository",
            "value": "none — no test file anywhere in the tree",
            "flag": "bad",
            "note": "the local-suite rung does not exist, so every defect "
                    "an agent writes is caught by a hook before it is "
                    "written, by CI after the session is gone, or never. "
                    "This is a fact about the repository, not about this "
                    "machine: nothing was skipped for want of a toolchain"})
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

    # The counts above are what HEAD wires. Each replayed row was fired at
    # what its *own* commit wired, and a hook committed after the defect was
    # not there to catch it: that is "absent at the defect", not "0 of N
    # caught", and it must not be flagged as a layer that failed.
    scored = [r for r in (catch or {}).get("rows") or []
              if r.get("rung") and r.get("hooks") is not None]
    absent = {ev: sum(1 for r in scored if not (r["hooks"] or {}).get(ev, 0))
              for ev in ("PreToolUse", "PostToolUse")}

    def state(exists, rung, what, event=None):
        if not exists:
            return f"{rung}: none wired"
        got = counts.get(rung, 0)
        if got:
            return f"{rung}: {what}, {got} caught"
        if not reached.get(rung, 0):
            return f"{rung}: {what}, nothing reached it"
        gone = absent.get(event, 0) if event else 0
        if gone and gone >= reached[rung]:
            return (f"{rung}: {what} at HEAD, wired at none of the "
                    f"{reached[rung]} replayed commits")
        if gone:
            return (f"{rung}: {what} ({gone} replayed before it was wired), "
                    f"0 of {reached[rung] - gone} caught")
        return f"{rung}: {what}, 0 of {reached[rung]} caught"

    bits = [
        state(pre, "before-write",
              f"{pre} hook(s)" + (f" incl. {deny} deny rule(s)"
                                  if deny else ""), "PreToolUse"),
        state(post, "same-turn", f"{post} hook(s)", "PostToolUse"),
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


# -- 3 -----------------------------------------------------------------------

def reliable_delivery(root, log, check_dirs=(), gate=None, pipeline=None):
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
        if len(typed) >= max(4, len(touched) // 2):  # kept in step with typed_mode
            how = (f"{len(touched) - len(recent)} of {len(touched)} change(s) "
                   f"to source are excluded as owing no test — renames, "
                   f"formatting, dependency bumps, docs and chores, read off "
                   f"the commit type")
        else:
            how = ("the denominator is every change to source, because these "
                   "subjects are not typed — nothing here can tell a rename "
                   "from a new function, and guessing would shrink the "
                   "denominator without changing the repository")
        # Both denominators travel with the row. Which one the percentage
        # uses depends on whether the subjects are typed, and a branch that
        # types its commits against one that does not would otherwise
        # produce two percentages that cannot be compared -- while the guide
        # asks people to keep the JSON precisely in order to compare.
        bare_all = [c for c in touched
                    if not any(_verifies(p, check_dirs) for p in c[2])]
        typed_mode = len(typed) >= max(4, len(touched) // 2)
        rows.append({
            "label": "changes that verified nothing",
            "value": f"{len(bare)}/{len(recent)}  ({pct}%)",
            "flag": "bad" if pct >= 80 else ("warn" if pct >= 40 else "ok"),
            "denominator": "typed" if typed_mode else "all source",
            "all_source": f"{len(bare_all)}/{len(touched)}",
            "note": "the green light can be real and still have nothing to "
                    "do with what was changed. " + how
                    + f". Against every change to source, typed or not: "
                      f"{len(bare_all)}/{len(touched)} — compare that one "
                      f"across branches whose commits are typed differently"})

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

    # What the pipeline runs on, whether it is itself checked, whether its
    # verdict survives a rerun, and what leaves through it. Read by
    # pipeline.py; every row here is a candidate with its evidence attached,
    # and the conventions -- matrix, cache, job count -- are not read -> 0044
    if pipeline:
        rows += _pipeline_rows(pipeline)
    elif not ci_files:
        # No pipeline of any host. `pipeline.py` reads one host and abstains
        # on the others, which is right when there is a Jenkinsfile it cannot
        # read; it is wrong when there is nothing, because nothing is a
        # measurement. One row, under 3.3: every change runs no check -> 0047
        rows.append({
            "label": "changes that run no check",
            "value": "all of them — no pipeline",
            "flag": "bad",
            "note": "no workflow, Jenkinsfile or pipeline file of any host "
                    "is in the tree, so no change to this repository is "
                    "checked by anything but whoever runs it by hand. "
                    "Absent in the repository, not unread"})

    return {"n": 3, "name": "Reliable Delivery",
            "question": "When a change is called done, what is the evidence?",
            "state": state, "headline": headline, "rows": rows}


def _pipeline_rows(p):
    """Rows 3.3 to 3.6, from what pipeline.py read."""
    rows = []
    s = p["scope"]
    if s["on_pull_request"]:
        if s["unconditional"]:
            rows.append({
                "label": "changes that run no check",
                "value": "none — %d workflow(s) run on every pull request"
                         % len(s["unconditional"]),
                "flag": "ok",
                "note": ", ".join(s["unconditional"][:3])})
        else:
            gaps = []
            for f in s["filtered"]:
                if f["paths"]:
                    gaps.append("outside " + ", ".join(f["paths"][:3])
                                + (" …" if len(f["paths"]) > 3 else ""))
                if f["paths-ignore"]:
                    gaps.append("touching only "
                                + ", ".join(f["paths-ignore"][:3])
                                + (" …" if len(f["paths-ignore"]) > 3 else ""))
            rows.append({
                "label": "changes that run no check",
                "value": "a pull request %s runs nothing" % (gaps[0] if gaps
                                                             else "?"),
                "flag": "warn",
                "note": "every workflow on pull requests carries a path "
                        "filter. A filter is usually deliberate; the reading "
                        "is whether what it skips can break anything — a "
                        "docs-only change is exactly the one that breaks a "
                        "routing table"
                        + ("; also " + "; ".join(gaps[1:3]) if len(gaps) > 1
                           else "")})
        if s["self_blind"]:
            rows.append({
                "label": "a workflow that does not run when it changes itself",
                "value": ", ".join(s["self_blind"][:3]),
                "flag": "warn",
                "note": "its `paths:` filter does not include "
                        ".github/workflows, so an edit to the pipeline is "
                        "the one change the pipeline never checks"})
        if s["job_filters"]:
            rows.append({
                "label": "a job-level filter decides at run time",
                "value": ", ".join(s["job_filters"][:3]),
                "flag": "info",
                "note": "paths-filter or similar: which checks a change runs "
                        "is computed inside the run and cannot be read from "
                        "the file"})

    c = p["checked"]
    present = sorted(c["present"])
    rows.append({
        "label": "the pipeline is itself checked",
        "value": ", ".join(present) if present else "by nothing",
        "flag": "ok" if present else "warn",
        "note": ", ".join(sorted(set(c["present"].values())))
                if present else
                "a workflow file is code nobody runs locally. Its first test "
                "is the next push, and a mistake in it turns every verdict "
                "after it into a guess"})
    if c["refusing"]:
        rows.append({
            "label": "rules a step refuses",
            "value": "%d step(s)" % len(c["refusing"]),
            "flag": "info",
            "note": "search-and-fail steps, the CI-side twin of a guard, "
                    "paid on every run instead of every turn: "
                    + "; ".join("%s:%d %s" % (r["file"], r["line"], r["name"])
                                for r in c["refusing"][:3])})

    a = p.get("audit")
    if a:
        by = a["by_severity"]
        high = by.get("high", 0) + by.get("critical", 0)
        rows.append({
            "label": "workflow audit findings",
            "value": "%d finding(s)" % a["total"]
                     + (": " + ", ".join("%d %s" % (n, k) for k, n in
                                         sorted(by.items())) if by else ""),
            "flag": "bad" if high else ("warn" if a["total"] else "ok"),
            "note": "by zizmor" + (": " + ", ".join(a["idents"])
                                   if a["idents"] else "")})
    else:
        rows.append({
            "label": "workflow audit findings",
            "value": "not run — " + p.get("audit_why", ""),
            "flag": "info",
            "note": "the audit is the ecosystem's tool, never reimplemented "
                    "here; absent, this row abstains"})

    v = p.get("verdicts")
    if v:
        rows.append({
            "label": "reruns that changed the verdict",
            "value": "%d of %d rerun(s), across %d run(s)"
                     % (len(v["flipped"]), v["reruns"], v["runs"]),
            "flag": "warn" if v["flipped"] else "ok",
            "note": ("median %ds to a verdict" % v["median_seconds"]
                     if v["median_seconds"] else "")
                    + ("; a verdict that changed with no change to the code "
                       "depended on something other than the code: "
                       + ", ".join("%s %s→%s" % (f["sha"], f["first"],
                                                f["last"])
                                   for f in v["flipped"][:3])
                       if v["flipped"] else "")})
    else:
        rows.append({
            "label": "reruns that changed the verdict",
            "value": "not readable",
            "flag": "info",
            "note": p.get("verdicts_why", "")})

    sh_ = p["shipping"]
    makers = "; ".join("%s (%s)" % (m["file"], ", ".join(m["what"] + m["trigger"]))
                       for m in sh_["makers"][:3])
    if not sh_["tags"] and not sh_["makers"]:
        rows.append({
            "label": "what ships from here",
            "value": "nothing found — no tag, no release or publish step",
            "flag": "info",
            "note": "fine for a repository nobody installs; for one somebody "
                    "does, every install is of an untagged commit"})
    else:
        rows.append({
            "label": "what ships from here",
            "value": "%d tag(s)%s" % (sh_["tags"], ", latest " + sh_["latest"]
                                       if sh_["latest"] else ""),
            "flag": "info",
            "note": ("made by " + makers) if makers else
                    "no workflow makes a tag or publishes anything: every "
                    "release is a person's hands, and the trace is whatever "
                    "they wrote down"})
    if sh_["latest"]:
        ok = bool(sh_["latest_reachable"])
        base = sh_.get("base") or "HEAD"
        rows.append({
            "label": "the latest tag is on this branch",
            "value": ("yes, on %s" % base) if ok else
                     "no — %s at %s is not reachable from %s"
                     % (sh_["latest"], sh_["latest_sha"], base),
            "flag": "ok" if ok else "bad",
            "note": "" if ok else
                    "what shipped is not what the default branch says shipped, "
                    "and nothing reading the branch can tell"})
    if sh_["manifest_version"] and sh_["tag_version"]:
        same = sh_["manifest_version"] == sh_["tag_version"]
        rows.append({
            "label": "the manifest agrees with the latest tag",
            "value": "%s on %s says %s, latest tag %s" % (
                sh_["manifest"], sh_.get("base") or "HEAD",
                sh_["manifest_version"], sh_["latest"]),
            "flag": "ok" if same else "warn",
            "note": "" if same else
                    "ahead: a version nobody can install yet, or a release "
                    "somebody forgot; behind: a tag pointing at a version the "
                    "manifest no longer claims"})
    return rows


def _suite_root(command):
    """The directory a `cd X && ...` command runs in, or None."""
    m = re.match(r"\s*cd\s+('?)([^\s'&]+)\1\s*&&", command or "")
    return m.group(2).rstrip("/") if m else None


def _unreached(catch, cover):
    """{sha: [files]} for replayed defects the suite never got in front of.

    Two ways to know. The command itself runs from a subdirectory, so a
    defect in a file outside it is out of reach by construction. Or the
    coverage run executed nothing in the file. Either way the defect is
    reclassified rather than counted as surviving: `1 defect survives past
    the end of a session` is a sentence about the repository, and the
    honest sentence here is about the command."""
    # One root per suite that ran. A file is out of reach by construction
    # only when every suite runs from a subdirectory and the file is under
    # none of them; a suite running at the top reaches everything.
    ran = [s for s in catch.get("suites") or [] if s.get("ran")]
    if ran:
        subs = [_suite_root(s.get("command")) for s in ran]
        subs = [] if any(s is None for s in subs) else subs
    else:
        one = _suite_root(catch.get("command"))
        subs = [one] if one else []
    reached = (cover or {}).get("reached") or {}
    out = {}
    for row in catch.get("rows") or []:
        if row.get("rung") not in ("ci", "never") or not row.get("source"):
            continue
        outside = []
        for p in row["source"]:
            rel = p.lstrip("./")
            if subs and not any(rel.startswith(s + "/") for s in subs):
                outside.append(rel)
            elif rel in reached and not reached[rel]:
                outside.append(rel)
        if outside and len(outside) == len(row["source"]):
            out[row["sha"]] = outside
    return out


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
                    if _only_the_shape(hit):
                        continue
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
                      promises=None, truth_judged=None, probe=None):
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

    if probe is not None:
        rows.extend(surface_mod.render(surface_mod.assess(root, probe)))

    if truth is not None:
        t = truth["thickness"]
        kinds = "  ".join(f"{k}:{v}" for k, v in t.items() if v)
        rows.append({
            "label": "what it writes down",
            "value": kinds or "nothing — no entry file, no document of any "
                              "kind an agent is pointed at",
            # An empty value was dropped as an abstention, so a repository
            # with nothing written down was the one repository this row
            # never scored. Nothing is a measurement here -> 0047
            "flag": "info" if kinds else "bad",
            "note": ("the denominator every row below is read against: "
                     "adding files cannot "
                     "raise anything on this page, because a repository is "
                     "not better for having adopted somebody else's "
                     "conventions") if kinds else
                    ("a newcomer, human or agent, starts from the code alone "
                     "and repeats whatever the last one learned. Absent in "
                     "the repository, not unread")})

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
                    "value": "%d real of %d candidate(s)%s%s" % (
                        len(judged["real"]), judged["judged"],
                        ", %d unread" % judged["pending"]
                        if judged["pending"] else "",
                        # An answer this run has no candidate for. Usually the
                        # shared cap moved and it will be back; occasionally
                        # the document changed under it. Either way, printing
                        # it beats a file that quietly loses entries.
                        ", %d answer(s) matched nothing"
                        % len(judged.get("stale") or [])
                        if judged.get("stale") else ""),
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
           permitted=None, truth_judged=None, pipeline=None):
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
        reliable_delivery(root, log, check_dirs, gate, pipeline),
        repository_memory(root, log, check_dirs, truth,
                          conflict, conflict_judged, promises, truth_judged,
                          probe),
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
