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

def controlled_execution(root, probe, blast):
    """Can an agent working here in good faith destroy something?"""
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

    return {"n": 1, "name": "Controlled Execution",
            "question": "Can an agent working here in good faith destroy "
                        "something, and does anything stop it?",
            "state": state, "headline": headline, "rows": rows}


# -- 2 -----------------------------------------------------------------------

def change_validation(defects, catch, catch_why, ladder):
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
            headline = (f"{late} of {placed} defects survive past the end of "
                        f"a session")
            rows.append({"label": "where each was first caught",
                         "value": "  ".join(f"{k}:{counts[k]}" for k in ladder),
                         "flag": "bad" if late else "ok",
                         "note": "the cliff sits between local-suite and ci: "
                                 "the session ends, the context is gone, and "
                                 "everything after it is paid for twice"})
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
        headline = "not replayed — rerun with --full"
        rows.append({"label": "replay", "value": "not run", "flag": "info",
                     "note": "add --full to put each defect back and record "
                             "where it is first caught"})

    return {"n": 2, "name": "Change Validation",
            "question": "When a defect is introduced, how late is it caught?",
            "state": state, "headline": headline, "rows": rows}


# -- 3 -----------------------------------------------------------------------

def reliable_delivery(root, log, check_dirs=()):
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
        recent = [c for c in log[:60] if any(
            _is_source(p, check_dirs) for p in c[2])]
        bare = [c for c in recent
                if not any(_verifies(p, check_dirs) for p in c[2])]
        pct = round(100 * len(bare) / len(recent)) if recent else 0
        state = "measured"
        headline = (f"{len(bare)} of the last {len(recent)} code changes "
                    f"touched nothing that verifies them")
        rows.append({
            "label": "changes that verified nothing",
            "value": f"{len(bare)}/{len(recent)}  ({pct}%)",
            "flag": "bad" if pct >= 80 else ("warn" if pct >= 40 else "ok"),
            "note": "the green light can be real and still have nothing to "
                    "do with what was changed"})

        # Most unverified changes are not worth anyone's attention -- in a
        # repository that writes tests, the ones without are usually small.
        # Changes to the machinery that does the verifying are the exception:
        # rare, and when one of them breaks, the thing that would have caught
        # it is the thing that changed.
        critical = [c for c in bare if any(CRITICAL_PATH.search(p)
                                           for p in c[2])]
        if critical:
            rows.append({
                "label": "unverified changes to the machinery itself",
                "value": str(len(critical)),
                "flag": "warn",
                "note": "CI, build or dependency files changed with nothing "
                        "verifying the change: "
                        + "; ".join(c[1][:44] for c in critical[:2])})

    if log is not None:
        repair, repeats, grown = _repair_rows(log, check_dirs)
        rows += repair
        if repeats:
            headline += f"; {repeats} place(s) said done twice"

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

def _repair_rows(log, check_dirs=()):
    """Two readings of the history that belong to dimension 3.

    Both are about whether a verdict held. A place repaired twice on purpose is
    a place where somebody said "done" and was wrong; a check that appears
    right after a repair is the verdict getting stronger because of one. They
    lived in dimension 4 while it was called Learning Capture, and moved when
    that dimension stopped reading history and started watching an agent
    -> docs/decisions/0025"""
    rows = []
    fixed, touched = {}, {}
    for sha, subject, paths in log:
        src = [p for p in paths if _is_source(p, check_dirs)]
        for p in src:
            touched[p] = touched.get(p, 0) + 1
        if not (FIX_SUBJECT.search(subject) or REVERT_SUBJECT.search(subject)):
            continue
        # The same attribution rule dimension 2 uses: above a few files, a
        # commit that says "fix" is a commit that also did four other things,
        # and nothing in it can be pinned on any one file. Without this, the
        # row just ranks files by size -- the biggest router in the tree is
        # touched by everything, so it tops the list in every repository
        # regardless of how much rework it actually took.
        if len(src) > FOCUSED:
            continue
        for p in src:
            fixed.setdefault(p, []).append(sha)

    repeats = sorted(((p, len(v)) for p, v in fixed.items() if len(v) >= 2),
                     key=lambda x: -x[1])
    rows.append({
        "label": "places repaired more than once, on purpose",
        "value": str(len(repeats)),
        "flag": "warn" if repeats else "ok",
        "note": (", ".join(f"{p} ×{n} of {touched.get(p, n)} touches"
                           for p, n in repeats[:3])
                 + (" …" if len(repeats) > 3 else "")
                 + " — counting only focused repairs, so this is rework "
                   "rather than a busy file")
        if repeats else
        f"no file was the subject of two separate small repairs "
        f"(commits of at most {FOCUSED} source files)"})

    # A check that arrived because of an incident, rather than because somebody
    # thought it was a good idea: a commit that introduces something verifying
    # AND touches a path an earlier commit had already fixed.
    fixed_before = set()
    grown = []
    for sha, subject, paths in reversed(log):
        src = [p for p in paths if _is_source(p, check_dirs)]
        verifying = [p for p in paths if _verifies(p, check_dirs)]
        # Same rule again. A commit touching thirty files will touch something
        # repaired earlier and something that verifies, every time, so without
        # the size limit this counts most of the history and means nothing.
        if (verifying and len(src) <= FOCUSED
                and any(p in fixed_before for p in src)):
            grown.append((sha, subject))
        if ((FIX_SUBJECT.search(subject) or REVERT_SUBJECT.search(subject))
                and len(src) <= FOCUSED):
            fixed_before.update(src)
    rows.append({
        "label": "checks that grew out of a repair",
        "value": str(len(grown)),
        "flag": "ok" if grown else "warn",
        "note": ((grown[-1][1][:64].rstrip() + "…"
                  if len(grown[-1][1]) > 64 else grown[-1][1]) if grown else
                 "no check in this history arrived right after a repair to "
                 "the same ground")})

    return rows, len(repeats), len(grown)


def repository_memory(root, log, check_dirs=(), probe=None):
    """Can an agent that has never seen this repository find its way, and is
    that because of something the repository keeps?

    The measurement is a **difference**: the same questions asked of the tree
    as it is, and of the tree with everything it keeps in order to explain
    itself removed. Counting what it keeps instead would grade a repository on
    whether it adopted our conventions, would reward this plugin's own
    presence, and would call 0024 -- which cut the standing cost by 81% -- a
    regression while dimension 5 called it an improvement -> 0025

    `probe` is the output of `memory.compare()`, and there is no way to obtain
    it without spending two agents. Without it this dimension **abstains**. It
    does not report zero: a repository nobody has probed is not a repository an
    agent cannot navigate, and scoring it as one would throw away exactly the
    repositories that read well."""
    rows = []

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

    if not probe:
        rows.append({
            "label": "an agent finding its way",
            "value": "not probed",
            "flag": "info",
            "note": "two agents, one on this tree and one on a copy with "
                    "CLAUDE.md and .claude/ removed — the difference between "
                    "them is the memory. Run /assess with --memory"})
        return {"n": 4, "name": "Repository Memory",
                "question": "Can an agent that has never seen this repository "
                            "find its way, and is that because of something "
                            "the repository keeps?",
                "state": "abstained",
                "headline": "not probed — the difference was never measured",
                "rows": rows}

    for r in probe.get("rows", []):
        w, o = r["with"], r["without"]
        subject = r["subject"]
        if len(subject) > 56:
            subject = subject[:56].rsplit(" ", 1)[0] + "…"
        rows.append({
            "label": subject,
            "value": f"{w['found']}/{w['of']} with  ·  "
                     f"{o.get('found', '—')}/{o.get('of', w['of'])} without",
            # About the question, not about the difference: a question both
            # runs answered is not a warning. What the standing context adds
            # is one row, below, and conflating the two made three correct
            # answers render as three warnings.
            "flag": "ok" if (w["found"] or 0) >= (w["of"] or 1) else
                    ("warn" if w["found"] else "bad"),
            "note": f"{w.get('tool_calls', '?')} tool call(s) with the "
                    f"repository's own context, {o.get('tool_calls', '?')} "
                    f"without; {w.get('named', '?')} file(s) named against "
                    f"{o.get('named', '?')}"})

    # Two questions, and conflating them was a real bug: the first live run of
    # this dimension came back with a difference of zero on a repository an
    # agent navigated easily, because what carried it was `docs/decisions/` --
    # discovered by reading, not loaded automatically. Scoring that as a
    # failure would mark a repository down for keeping its memory somewhere an
    # agent has to open rather than somewhere Claude Code loads for it.
    found = sum(r["with"]["found"] or 0 for r in probe.get("rows", []))
    want = sum(r["with"]["of"] or 0 for r in probe.get("rows", [])) or 1
    calls = sum(r["with"].get("tool_calls") or 0 for r in probe.get("rows", []))
    rows.append({
        "label": "an agent finding its way",
        "value": f"{found}/{want} file(s), {calls} tool call(s)",
        "flag": "ok" if found * 2 >= want else ("warn" if found else "bad"),
        "note": "across the questions above, each asked with only a commit's "
                "subject line on a copy with no history — this is whether the "
                "repository can be navigated at all, before asking what makes "
                "it navigable"})

    removed = probe.get("removed") or []
    lift = probe.get("lift", 0)
    legible = found * 2 >= want
    if not removed:
        note = ("nothing was removed, because there is nothing to remove — "
                "this repository keeps no standing context, so the two runs "
                "were one run")
        flag, headline = "info", "there is no standing context to measure"
    elif lift > 0:
        note = (f"removed for the second run: {', '.join(removed)} — without "
                f"them the same agent found {lift} fewer file(s)")
        flag = "ok"
        headline = (f"what this repository loads on every turn found {lift} "
                    f"more file(s) than the code alone")
    elif legible:
        note = (f"removed for the second run: {', '.join(removed)} — and it "
                f"made no difference. The repository is navigable without "
                f"them, so whatever is carrying an agent is being read rather "
                f"than loaded. Dimension 5 is where to ask whether the loaded "
                f"part is still worth its tokens")
        flag = "info"
        headline = ("an agent finds its way here, but not because of what is "
                    "loaded every turn")
    else:
        note = (f"removed for the second run: {', '.join(removed)} — an agent "
                f"could not find its way either way, so what is loaded on "
                f"every turn is being paid for and is not helping")
        flag = "bad"
        headline = "hard to navigate, and the standing context does not help"

    rows.append({"label": "what the standing context adds",
                 "value": f"{lift:+d} file(s)", "flag": flag, "note": note})

    return {"n": 4, "name": "Repository Memory",
            "question": "Can an agent that has never seen this repository find "
                        "its way, and is that because of something the "
                        "repository keeps?",
            "state": "measured", "headline": headline, "rows": rows}


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

def context_economy(root, probe):
    """What does the harness cost per turn, and what can it cost at worst?"""
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

    return {"n": 5, "name": "Context Economy",
            "question": "What does the harness cost per turn, and at worst?",
            "state": "measured",
            "headline": (f"~{theirs} tokens on every turn from this "
                         f"repository, ~{ceiling - from_plugins} at worst"),
            "rows": rows}


# ---------------------------------------------------------------------------

def assess(root, probe, blast, catch, catch_why, defects, log, ladder,
           memory=None):
    """`probe` is what `probe_repo.py` found; `memory` is what the two
    navigation agents came back with, or None when nobody spent them."""
    check_dirs = tuple((probe.get("discipline") or {}).get("check_dirs") or ())
    return [
        controlled_execution(root, probe, blast),
        change_validation(defects, catch, catch_why, ladder),
        reliable_delivery(root, log, check_dirs),
        repository_memory(root, log, check_dirs, memory),
        context_economy(root, probe),
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
