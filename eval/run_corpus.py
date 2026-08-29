#!/usr/bin/env python3
"""Run the harness against every repository in the corpus and record what happened.

    python3 eval/run_corpus.py [--tier B] [--only <substring>] [--out <path>]

    0 = nothing crashed    1 = something crashed    2 = cannot judge

This is not an eval. Nothing here judges whether the harness *helps*; it judges
whether the harness *survives contact* with repositories nobody here has seen.
Those are different questions and the second one has to be answered first,
because measuring the effect of a tool that crashes on a third of its inputs
measures the two thirds that are left.

## Why it exists

`shared/scripts/CLAUDE.md` opens with a rule: "Write for a repository you have
never seen. No path, name, or convention from this repository may be assumed."
Every acceptance case builds its own fixture, which means every one of them was
written by someone who knew what the harness expected. That rule has been an
assertion, not a finding.

The corpus is the counterexample generator. Twenty repositories built mainly by
coding agents, eleven languages, 22 KB to 4.8 MB, none of them ours.

## What is recorded, and why each column

Per repository, in order:

  - **has**: what was already there. Every one of these repositories already has
    a `CLAUDE.md` somebody else wrote, and `scaffold.py` skips files that exist,
    so the most important file in the harness is one it will not write. Whatever
    the gates then say, they are saying it about someone else's prose.
  - **probe**: the tier it reports. A tier is a claim about what a repository
    can carry; a wrong one installs machinery that rots.
  - **dry-run vs real**: the preview exists to be approved before the thing
    happens. One that describes a different run is worse than none.
  - **ci**: what the generated entry point does on a real tree. Red is expected
    -- a fresh scaffold is full of placeholders. Red *for something other than
    placeholders*, or an exit 2, is the finding.

A crash is any non-zero exit that is not 1, plus any traceback on stderr. Exit 2
is not a crash and not a pass: it is the harness saying it could not judge, and
on a real repository that is a result worth reading rather than an error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.join(HERE, ".work")
SCRIPTS = os.path.join(ROOT, "shared", "scripts")

TRACEBACK = re.compile(r"^Traceback \(most recent call last\)", re.M)
MARKERS = ("CLAUDE.md", "AGENTS.md", ".claude", "docs", "scripts", "ci.sh",
           "README.md", "LICENSE")


def sh(args, cwd, timeout=180):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", f"timed out after {timeout}s")
    except OSError as exc:
        return subprocess.CompletedProcess(args, 127, "", str(exc))


def crashed(proc):
    """Non-zero that is not a judged failure, or a traceback either way.

    Exit 1 is a judgement and exit 2 is an abstention; both are the harness
    working. Anything else, and any traceback, is the harness breaking."""
    return proc.returncode not in (0, 1, 2) or bool(TRACEBACK.search(proc.stderr))


def already_has(path):
    return sorted(m for m in MARKERS if os.path.exists(os.path.join(path, m)))


def run_one(name, tier):
    path = os.path.join(WORK, name.replace("/", "__"))
    row = {"repo": name, "has": [], "probe": None, "moments": None,
           "dry_run": None, "scaffold": None, "gates": {}, "crashes": [],
           "abstained": [], "judged_the_repo": [], "notes": []}
    if not os.path.isdir(path):
        row["notes"].append("not fetched; run eval/fetch.py")
        return row

    row["has"] = already_has(path)

    probe = sh([sys.executable, os.path.join(SCRIPTS, "probe_repo.py"),
                "--root", path], cwd=path)
    row["probe"] = probe.returncode
    row["moments"] = len(re.findall(r"^\s*\[x\]", probe.stdout, re.M))
    if crashed(probe):
        row["crashes"].append(("probe_repo.py", (probe.stderr or probe.stdout).strip()[:400]))

    dry = sh([sys.executable, os.path.join(SCRIPTS, "scaffold.py"),
              "--root", path, "--tier", tier, "--dry-run"], cwd=path)
    row["dry_run"] = dry.returncode
    if crashed(dry):
        row["crashes"].append(("scaffold.py --dry-run", (dry.stderr or dry.stdout).strip()[:400]))

    real = sh([sys.executable, os.path.join(SCRIPTS, "scaffold.py"),
               "--root", path, "--tier", tier], cwd=path)
    row["scaffold"] = real.returncode
    if crashed(real):
        row["crashes"].append(("scaffold.py", (real.stderr or real.stdout).strip()[:400]))

    # The preview promised these; the run either wrote them or did not.
    promised = set(re.findall(r"^\s+NEW\s+(\S+)", dry.stdout, re.M))
    missing = sorted(p for p in promised
                     if not os.path.exists(os.path.join(path, p)))
    if missing:
        row["notes"].append("preview promised files the run did not write: "
                            + ", ".join(missing[:5]))

    # Each gate on its own, rather than reading ci.sh's combined output. That
    # was the first shape and it hid the only interesting result: ci.sh prints
    # placeholder failures *and* failures about the repository's own content in
    # one stream, so a substring test for "unfilled placeholder" matched every
    # run and reported nothing. Per-gate exit codes cannot blur like that.
    gates = os.path.join(path, "scripts", "gates")
    if os.path.isdir(gates):
        for gate in sorted(f for f in os.listdir(gates)
                           if f.startswith("check_") and f.endswith(".py")):
            out = sh([sys.executable, os.path.join(gates, gate),
                      "--root", path], cwd=path, timeout=120)
            row["gates"][gate] = out.returncode
            body = (out.stderr or out.stdout).strip()
            if crashed(out):
                row["crashes"].append((gate, body[:400]))
            elif out.returncode == 2:
                row["abstained"].append((gate, body.splitlines()[0][:200]
                                         if body else ""))
            elif out.returncode == 1 and "placeholder" not in body:
                # Red about the repository rather than about our templates.
                # This is the column the corpus exists to produce.
                row["judged_the_repo"].append((gate, body.splitlines()[0][:200]
                                               if body else ""))
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=["A", "B", "C"], default="B")
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default=os.path.join(HERE, "results", "latest.json"))
    a = ap.parse_args()

    manifest = os.path.join(HERE, "corpus.json")
    if not os.path.exists(manifest):
        print("cannot judge: no eval/corpus.json", file=sys.stderr)
        return 2
    with open(manifest, encoding="utf-8") as fh:
        repos = [r["full_name"] for r in json.load(fh)["repos"]]
    if a.only:
        repos = [r for r in repos if a.only in r]
    if not repos:
        print("cannot judge: --only matched no repository", file=sys.stderr)
        return 2

    started = time.time()
    rows = [run_one(name, a.tier) for name in repos]

    width = max(len(r["repo"]) for r in rows)
    print(f"{'repo':<{width}}  {'mom':>3} {'sca':>3} {'crash':>5} "
          f"{'exit2':>5} {'judged-the-repo':>15}")
    for r in rows:
        print(f"{r['repo']:<{width}}  {r['moments'] or 0:>3} "
              f"{'-' if r['scaffold'] is None else r['scaffold']:>3} "
              f"{len(r['crashes']):>5} {len(r['abstained']):>5} "
              f"{len(r['judged_the_repo']):>15}")

    crashes = [(r["repo"], w, d) for r in rows for w, d in r["crashes"]]
    notes = [(r["repo"], n) for r in rows for n in r["notes"]]

    import collections
    judged = collections.Counter(g for r in rows for g, _ in r["judged_the_repo"])
    abstained = collections.Counter(g for r in rows for g, _ in r["abstained"])
    if judged:
        print("\ngates that failed on the repository's own content, not on our "
              "templates:")
        for gate, n in judged.most_common():
            example = next(d for r in rows for g, d in r["judged_the_repo"]
                           if g == gate)
            print(f"  {gate:<30} {n:>2}/{len(rows)}   e.g. {example}")
    if abstained:
        print("\ngates that could not judge (exit 2):")
        for gate, n in abstained.most_common():
            example = next(d for r in rows for g, d in r["abstained"]
                           if g == gate)
            print(f"  {gate:<30} {n:>2}/{len(rows)}   e.g. {example}")

    if crashes:
        print(f"\n{len(crashes)} crash(es):")
        for repo, where, detail in crashes:
            print(f"\n  --- {repo} · {where} ---\n    "
                  + detail.replace("\n", "\n    "))
    if notes:
        print(f"\n{len(notes)} note(s):")
        for repo, note in notes:
            print(f"  {repo}: {note}")

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump({"tier": a.tier, "repos": len(rows),
                   "crashes": len(crashes), "notes": len(notes),
                   "seconds": round(time.time() - started), "rows": rows},
                  fh, indent=2)
    print(f"\n{len(rows)} repositories, {len(crashes)} crash(es), "
          f"{len(notes)} note(s) -> {os.path.relpath(a.out, os.getcwd())}")
    return 1 if crashes else 0


if __name__ == "__main__":
    sys.exit(main())
