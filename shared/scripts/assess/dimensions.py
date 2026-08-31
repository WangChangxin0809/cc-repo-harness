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

    return {"n": 3, "name": "Reliable Delivery",
            "question": "When a change is called done, what is the evidence?",
            "state": state, "headline": headline, "rows": rows}


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

def learning_capture(root, log, check_dirs=()):
    """Has a mistake made here ever turned into something that acts next time?"""
    rows = []
    state = "measured"

    if log is None:
        return {"n": 4, "name": "Learning Capture",
                "question": "Has a mistake made here ever turned into "
                            "something that acts next time?",
                "state": "abstained", "headline": "the history cannot be read",
                "rows": []}

    fixed = {}
    for sha, subject, paths in log:
        if not (FIX_SUBJECT.search(subject) or REVERT_SUBJECT.search(subject)):
            continue
        for p in paths:
            if _is_source(p, check_dirs):
                fixed.setdefault(p, []).append(sha)
    repeats = sorted(((p, len(s)) for p, s in fixed.items() if len(s) >= 2),
                     key=lambda x: -x[1])
    rows.append({
        "label": "places fixed more than once",
        "value": str(len(repeats)),
        "flag": "warn" if repeats else "ok",
        "note": (", ".join(f"{p} ×{n}" for p, n in repeats[:4])
                 + (" …" if len(repeats) > 4 else ""))
        if repeats else "no file in this history was repaired twice"})

    # A check that arrived because of an incident, rather than because somebody
    # thought it was a good idea: a commit that introduces something verifying
    # AND touches a path an earlier commit had already fixed.
    fixed_before = set()
    grown = []
    for sha, subject, paths in reversed(log):
        verifying = [p for p in paths if _verifies(p, check_dirs)]
        if verifying and any(p in fixed_before for p in paths):
            grown.append((sha, subject))
        if FIX_SUBJECT.search(subject) or REVERT_SUBJECT.search(subject):
            fixed_before.update(p for p in paths
                                if _is_source(p, check_dirs))
    rows.append({
        "label": "checks with an incident behind them",
        "value": str(len(grown)),
        "flag": "ok" if grown else "warn",
        "note": ((grown[-1][1][:64].rstrip() + "…"
                  if len(grown[-1][1]) > 64 else grown[-1][1]) if grown else
                 "no check in this history arrived right after a repair to "
                 "the same ground")})

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

    headline = ("nothing here remembers a mistake"
                if not grown and not records else
                f"{len(grown)} check(s) grew out of a repair"
                + (f"; {len(repeats)} place(s) repaired twice" if repeats else ""))
    return {"n": 4, "name": "Learning Capture",
            "question": "Has a mistake made here ever turned into something "
                        "that acts next time?",
            "state": state, "headline": headline, "rows": rows}


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

def assess(root, probe, blast, catch, catch_why, defects, log, ladder):
    check_dirs = tuple((probe.get("discipline") or {}).get("check_dirs") or ())
    return [
        controlled_execution(root, probe, blast),
        change_validation(defects, catch, catch_why, ladder),
        reliable_delivery(root, log, check_dirs),
        learning_capture(root, log, check_dirs),
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
