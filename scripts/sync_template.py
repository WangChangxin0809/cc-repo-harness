#!/usr/bin/env python3
"""Push this repository's machinery into the template repository.

    python3 scripts/sync_template.py --to <path> [--check]

    0 = in sync (or synced)   1 = --check and it had drifted   2 = cannot judge

Decision 0057 splits the two repositories by *who authors what*: machinery is
authored here and pushed there, prose is authored there and never comes back.
This is the push, and the reason it is a script rather than a paragraph is that
the first manual sync copied four files individually and left `gates/selftest.py`
behind -- so the template shipped a gate with a ceiling and a selftest that did
not know about it. Two of its own cases failed. Nothing about that was visible
until the template's `ci.sh` was run end to end.

Whole directories, never single files, for exactly that reason: a check and the
selftest that proves it can fail are one unit, and copying half of one is how
you get a suite that disagrees with the thing it is testing.

`session_brief.py` is deliberately not pushed. It is *generated per repository*
rather than copied -- the target's copy is its own, and overwriting it would
replace whatever that repository had learned to say at session start.
"""

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAYLOAD = os.path.join(HERE, "shared")

# Generated per repository, so the target's copy is authoritative.
KEEP = {"session_brief.py"}

# Where a leftover file is looked for. Split by *who owns the directory*, and
# the split is the safety property: the three script directories hold nothing
# but payload, so a file there that we no longer ship is ours to remove. A
# repository's `.claude/skills/` and `.claude/agents/` also hold whatever that
# repository wrote for itself, and deleting somebody's own skill because a
# rename happened here would be the worst kind of helpful.
OWNED = ("scripts/guards", "scripts/gates", "scripts/context")
WATCHED = (".claude/skills", ".claude/agents")


def plan_for(tier):
    """What a repository at this tier gets, read out of scaffold.py's own tables.

    Imported rather than restated. A second list of what a tier installs is a
    list that drifts, and the drift would be invisible in exactly the direction
    that matters: the template would quietly stop matching what the scaffolder
    hands everybody else.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "scaffold", os.path.join(PAYLOAD, "scripts", "scaffold.py"))
    sc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sc)

    dirs, files = [], []
    for src, dst, floor in sc.COPY:
        if sc.at_least(tier, floor):
            dirs.append((os.path.join("scripts", src), dst))
    dirs.append(("scripts/context", "scripts/context"))
    for name, floor in sc.SKILLS:
        if sc.at_least(tier, floor):
            dirs.append((os.path.join("skills", name),
                         os.path.join(".claude", "skills", name)))
    for name, floor in sc.AGENTS:
        if sc.at_least(tier, floor):
            files.append((os.path.join("agents", name),
                          os.path.join(".claude", "agents", name)))
    for src, dst, floor in sc.SCRIPTS:
        if sc.at_least(tier, floor):
            files.append((os.path.join("scripts", src), dst))
    return dirs, files


def wanted(src_dir):
    """Files worth copying: .py and .md, no caches, no generated-per-repo."""
    out = []
    for cur, dirs, names in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for n in sorted(names):
            if n in KEEP or not n.endswith((".py", ".md")):
                continue
            out.append(os.path.relpath(os.path.join(cur, n), src_dir))
    return out


def selftest(verbose):
    """Three cases, each a defect this has already had or would not survive.

    The partial sync is not hypothetical: the first manual push copied four
    gate files and left `gates/selftest.py` behind, so the template shipped a
    ceiling its own suite did not know about.
    """
    import subprocess
    import tempfile

    def build(missing=(), extra=(), modified=()):
        root = tempfile.mkdtemp(prefix="sync-selftest-")
        subprocess.run(["git", "init", "-q", "."], cwd=root, check=False)
        dirs, files = plan_for("B")
        for src_rel, dst_rel in dirs:
            for rel in wanted(os.path.join(PAYLOAD, src_rel)):
                if os.path.join(dst_rel, rel) in missing:
                    continue
                dst = os.path.join(root, dst_rel, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(os.path.join(PAYLOAD, src_rel, rel), dst)
        for src_rel, dst_rel in files:
            dst = os.path.join(root, dst_rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(PAYLOAD, src_rel), dst)
        for rel in extra:
            p2 = os.path.join(root, rel)
            os.makedirs(os.path.dirname(p2), exist_ok=True)
            open(p2, "w").write("# left behind by a rename\n")
        for rel in modified:
            p2 = os.path.join(root, rel)
            with open(p2, "a") as fh:
                fh.write("\n# an edit made on the far side\n")
        return root

    me = os.path.abspath(__file__)

    def run(root):
        return subprocess.run([sys.executable, me, "--to", root, "--check"],
                              capture_output=True, text=True)

    cases = []
    root = build()
    cases.append(("a faithful copy is in sync", run(root), 0, "in sync"))
    shutil.rmtree(root, ignore_errors=True)

    root = build(missing=("scripts/gates/selftest.py",))
    cases.append(("a half-copied directory is drift", run(root), 1,
                  "drifted   scripts/gates/selftest.py"))
    shutil.rmtree(root, ignore_errors=True)

    # Present, same name, different bytes. Without this the whole comparison
    # could be `os.path.exists` and every case above would still pass -- which
    # is the shape of a check that has stopped checking.
    root = build(modified=("scripts/gates/check_docs_index.py",))
    cases.append(("a file edited on the far side is drift", run(root), 1,
                  "drifted   scripts/gates/check_docs_index.py"))
    shutil.rmtree(root, ignore_errors=True)

    root = build(extra=(".claude/skills/writing-github-docs/SKILL.md",))
    cases.append(("a renamed skill is reported, not deleted", run(root), 1,
                  "orphaned  .claude/skills/writing-github-docs/SKILL.md"))
    shutil.rmtree(root, ignore_errors=True)

    root = build(extra=("scripts/gates/check_that_was_removed.py",))
    cases.append(("a gate we no longer ship is ours to remove", run(root), 1,
                  "stale     scripts/gates/check_that_was_removed.py"))
    shutil.rmtree(root, ignore_errors=True)

    empty = tempfile.mkdtemp(prefix="sync-selftest-nogit-")
    cases.append(("a destination that is not a repository cannot be judged",
                  run(empty), 2, "cannot judge"))
    shutil.rmtree(empty, ignore_errors=True)

    bad = []
    for label, out, want_rc, needle in cases:
        body = out.stdout + out.stderr
        if out.returncode != want_rc:
            bad.append(f"{label}: exit {out.returncode}, wanted {want_rc}")
        elif needle not in body:
            bad.append(f"{label}: said nothing about {needle!r}")
        elif verbose:
            print(f"  ok  {label}")
    for line in bad:
        print(f"  FAIL  {line}", file=sys.stderr)
    print(f"{len(cases)} sync case(s), {len(bad)} failed")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", help="the template repository")
    ap.add_argument("--selftest", action="store_true",
                    help="prove this can still see a partial copy")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="report drift and change nothing")
    ap.add_argument("--tier", choices=["A", "B", "C"], default="B",
                    help="what the template ships (0057: B, without index/)")
    a = ap.parse_args()

    if a.selftest:
        return selftest(a.verbose)
    if not a.to:
        print("cannot judge: --to is required", file=sys.stderr)
        return 2

    dest_root = os.path.abspath(a.to)
    if not os.path.isdir(os.path.join(dest_root, ".git")):
        print(f"cannot judge: {dest_root} is not a git repository",
              file=sys.stderr)
        return 2

    try:
        DIRS, FILES = plan_for(a.tier)
    except Exception as exc:
        print(f"cannot judge: scaffold.py's tables did not load: {exc}",
              file=sys.stderr)
        return 2

    plan = []
    for src_rel, dst_rel in DIRS:
        src = os.path.join(PAYLOAD, src_rel)
        if not os.path.isdir(src):
            print(f"cannot judge: no {src_rel} under shared/", file=sys.stderr)
            return 2
        for rel in wanted(src):
            plan.append((os.path.join(src, rel),
                         os.path.join(dest_root, dst_rel, rel)))
    for src_rel, dst_rel in FILES:
        plan.append((os.path.join(PAYLOAD, src_rel),
                     os.path.join(dest_root, dst_rel)))

    # Anything the template holds under a synced directory that this repository
    # no longer ships. A renamed skill leaves its old copy behind otherwise, and
    # the template then carries two skills competing for one trigger.
    stale, orphaned = [], []
    keeping = {os.path.abspath(d) for _, d in plan}
    for scan, bucket in [(r, stale) for r in OWNED] + \
                        [(r, orphaned) for r in WATCHED]:
        d = os.path.join(dest_root, scan)
        if not os.path.isdir(d):
            continue
        for cur, dirs, names in os.walk(d):
            dirs[:] = [x for x in dirs if x != "__pycache__"]
            for n in names:
                q = os.path.join(cur, n)
                if n not in KEEP and os.path.abspath(q) not in keeping:
                    bucket.append(os.path.relpath(q, dest_root))

    changed = [(s, d) for s, d in plan
               if not os.path.exists(d) or not filecmp.cmp(s, d, shallow=False)]

    if a.check:
        if not changed and not stale and not orphaned:
            print(f"in sync: {len(plan)} file(s)")
            return 0
        for _, d in changed:
            print(f"  drifted   {os.path.relpath(d, dest_root)}")
        for rel in sorted(stale):
            print(f"  stale     {rel}")
        for rel in sorted(orphaned):
            print(f"  orphaned  {rel}   (not ours to delete — decide by hand)")
        print(f"\n{len(changed)} drifted, {len(stale)} stale, "
              f"{len(orphaned)} orphaned. Run without --check to push.",
              file=sys.stderr)
        return 1

    for src, dst in changed:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        if src.endswith(".py"):
            os.chmod(dst, 0o755)
    for rel in stale:
        os.remove(os.path.join(dest_root, rel))

    print(f"pushed {len(changed)} file(s), removed {len(stale)} stale; "
          f"{len(plan)} in sync")
    for rel in sorted(orphaned):
        print(f"  orphaned  {rel}   (left alone: this directory is not ours)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
