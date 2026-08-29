#!/usr/bin/env python3
"""Clone the corpus at its pinned commits, into a directory git ignores.

    python3 eval/fetch.py [--only <substring>] [--jobs 8]

    0 = every repository is at its pinned commit
    1 = at least one could not be fetched
    2 = cannot judge (no corpus.json, or no git)

The corpus is **pinned and never vendored**, and that is not tidiness. Nine of
the twenty repositories carry no licence at all, which makes redistributing
them not ours to do; two are GPL-3.0. And a copy committed here would stop
being an unseen repository within a few months, which is the entire property
the corpus exists to provide. So this file fetches, and `eval/.work/` is
ignored.

Shallow, single-commit fetches: the corpus is about 30 MB of trees and nobody
needs the history. Re-running is cheap and idempotent -- a repository already
sitting at its pinned SHA *with a clean tree* is left alone.

Both halves of that matter. `run_corpus.py` scaffolds these repositories in
place, which writes seventeen files and edits two tracked ones and never makes
a commit, so the SHA alone reported an untouched repository that was nothing of
the kind. A dirty tree is re-cloned, and the summary calls it `restored` so that
a run which quietly undid somebody else's work in progress says so.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, ".work")


def sh(args, cwd=None, timeout=300):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout)


def head_of(path):
    out = sh(["git", "rev-parse", "HEAD"], cwd=path)
    return out.stdout.strip() if out.returncode == 0 else None


def is_clean(path):
    """Whether the working tree matches the commit, untracked files included.

    A pinned SHA is not the same claim as an untouched repository, and the
    difference is not academic: `run_corpus.py` scaffolds these trees in place,
    which writes seventeen files and edits two tracked ones without producing a
    commit. HEAD still matched, so the old check called them cached and skipped
    them, and the next thing to read one read our own scaffold back as if it
    were the repository's. Anything that measures an untouched repository has to
    be able to say the repository is untouched."""
    out = sh(["git", "status", "--porcelain"], cwd=path)
    return out.returncode == 0 and not out.stdout.strip()


def fetch_one(entry):
    """(name, status, detail). Status is one of ok / cached / failed."""
    name, sha = entry["full_name"], entry["sha"]
    dest = os.path.join(WORK, name.replace("/", "__"))

    if os.path.isdir(os.path.join(dest, ".git")) and head_of(dest) == sha:
        if is_clean(dest):
            return (name, "cached", sha[:10])
        # Re-clone rather than `git clean -xfd`: the tree may hold an installed
        # dependency directory that took ten minutes to build, and deciding
        # which dirt is precious is not a decision a fetch should be making.
        dirty = True
    else:
        dirty = False

    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    url = f"https://github.com/{name}.git"
    steps = (
        ["git", "init", "-q", "."],
        ["git", "remote", "add", "origin", url],
        # A single commit, no history, no tags. `--depth 1` on a SHA needs
        # uploadpack.allowReachableSHA1InWant, which github.com has.
        ["git", "fetch", "-q", "--depth", "1", "origin", sha],
        ["git", "checkout", "-q", "FETCH_HEAD"],
    )
    for step in steps:
        out = sh(step, cwd=dest)
        if out.returncode != 0:
            return (name, "failed",
                    f"{' '.join(step[:3])}: {(out.stderr or out.stdout).strip()[:160]}")
    got = head_of(dest)
    if got != sha:
        return (name, "failed", f"landed on {got} not {sha}")
    return (name, "restored" if dirty else "ok", sha[:10])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="",
                    help="fetch only repositories whose name contains this")
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()

    manifest = os.path.join(HERE, "corpus.json")
    if not os.path.exists(manifest):
        print("cannot judge: no eval/corpus.json", file=sys.stderr)
        return 2
    if shutil.which("git") is None:
        print("cannot judge: git is not on PATH", file=sys.stderr)
        return 2

    with open(manifest, encoding="utf-8") as fh:
        repos = json.load(fh)["repos"]
    if a.only:
        repos = [r for r in repos if a.only in r["full_name"]]
    if not repos:
        print("cannot judge: --only matched no repository", file=sys.stderr)
        return 2

    os.makedirs(WORK, exist_ok=True)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:
        for row in pool.map(fetch_one, repos):
            results.append(row)

    width = max(len(n) for n, _, _ in results)
    for name, status, detail in sorted(results):
        print(f"  {status:<7} {name:<{width}}  {detail}")

    failed = [r for r in results if r[1] == "failed"]
    print(f"\n{len(results) - len(failed)}/{len(results)} at their pinned "
          f"commit, in {os.path.relpath(WORK, os.getcwd())}/")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
