#!/usr/bin/env python3
"""Rung 0: what does this harness cost, before asking whether it helps.

    python3 scripts/measure_cost.py [--root .]

    0 = measured    2 = cannot judge

Ours, not payload: it reaches into `claude plugin details` and this repository's
own wiring.

The cost side of an eval is free and deterministic, and it is the half everyone
skips. A benefit does not have to be positive, it has to beat this number -- so
measuring it first is the cheapest thing in the whole ladder and it sets the bar
every later rung is judged against.

The split that matters is not big versus small. It is **where the cost is paid**:

  * Standing, per session, in *this* repository -- CLAUDE.md and the SessionStart
    brief. Paid only where the harness applies, by someone it applies to.
  * Standing, per session, in *every* repository -- the plugin's skill and agent
    descriptions. An installed plugin is global, so this is paid in repositories
    the harness has never touched and can do nothing for.

The second is the one that compounds badly, and it is invisible from inside the
repository that benefits.

Token counts: no tokenizer ships with the standard library, so this calibrates
chars-per-token against a number Claude Code reports itself -- the plugin's
always-on cost against the bytes of frontmatter that produce it. That ratio is
measured on this repository's own prose rather than assumed, and it is slightly
conservative: per-component structural overhead is attributed to characters, so
prose is charged a little more than it costs.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys

FALLBACK_RATIO = 3.5


def frontmatter_chars(root):
    total = 0
    for p in (sorted(glob.glob(os.path.join(root, "skills/*/SKILL.md")))
              + sorted(glob.glob(os.path.join(root, "agents/*.md")))):
        with open(p, encoding="utf-8") as fh:
            m = re.match(r"^---\n(.*?)\n---\n", fh.read(), re.S)
        if m:
            total += len(m.group(1))
    return total


def plugin_always_on(root):
    """The number Claude Code reports for itself. None if it cannot be had."""
    try:
        with open(os.path.join(root, ".claude-plugin/plugin.json"),
                  encoding="utf-8") as fh:
            name = json.load(fh)["name"]
    except (OSError, KeyError, ValueError):
        return None, None
    try:
        p = subprocess.run(["claude", "plugin", "details", name],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return name, None
    m = re.search(r"Always-on:\s*~?([\d,]+)\s*tok", p.stdout)
    return name, int(m.group(1).replace(",", "")) if m else None


def chars(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return len(fh.read())
    except OSError:
        return 0


def session_start_chars(root):
    script = os.path.join(root, "scripts/context/session_brief.py")
    if not os.path.exists(script):
        return 0
    payload = {"hook_event_name": "SessionStart", "source": "startup",
               "cwd": root}
    try:
        p = subprocess.run([sys.executable, script], input=json.dumps(payload),
                           capture_output=True, text=True, cwd=root, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return 0
    return len((p.stdout + p.stderr).strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    name, always_on = plugin_always_on(root)
    fm = frontmatter_chars(root)
    if always_on and fm:
        ratio = fm / always_on
        basis = (f"calibrated: {fm} chars of skill/agent frontmatter produce "
                 f"the ~{always_on} tok Claude Code reports")
    else:
        ratio = FALLBACK_RATIO
        basis = (f"assumed {FALLBACK_RATIO} chars/token -- `claude plugin "
                 f"details` gave no number to calibrate against")

    def tok(n):
        return round(n / ratio)

    root_md = chars(os.path.join(root, "CLAUDE.md"))
    brief = session_start_chars(root)

    subtree = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d != "node_modules"]
        if "CLAUDE.md" in filenames and os.path.abspath(dirpath) != root:
            rel = os.path.relpath(os.path.join(dirpath, "CLAUDE.md"), root)
            subtree.append((rel, chars(os.path.join(dirpath, "CLAUDE.md"))))

    docs = sum(chars(p) for p in
               glob.glob(os.path.join(root, "docs/**/*.md"), recursive=True))

    print(f"chars/token: {ratio:.2f}\n  {basis}\n")

    here = tok(root_md) + tok(brief)
    print("Standing, every session, in THIS repository")
    print(f"  {'CLAUDE.md':<34} ~{tok(root_md):5d} tok  ({root_md} chars)")
    print(f"  {'SessionStart brief':<34} ~{tok(brief):5d} tok  ({brief} chars)")
    print(f"  {'':<34} ~{here:5d} tok\n")

    print("Standing, every session, in EVERY repository")
    if always_on:
        print(f"  {'plugin skills + agents':<34} ~{always_on:5d} tok"
              f"  (paid where the harness does nothing)")
    else:
        print(f"  {'plugin skills + agents':<34}      ?  "
              f"(run `claude plugin details {name or '<name>'}`)")
    print()

    total = here + (always_on or 0)
    print(f"  {'TOTAL standing, harnessed repo':<34} ~{total:5d} tok")
    if always_on and total:
        print(f"  {'':<34}  {always_on * 100 // total}% of it is the plugin, "
              f"and that share is paid everywhere")
    print()

    print("On demand -- paid only when the trigger fires")
    for rel, n in sorted(subtree):
        print(f"  {rel:<34} ~{tok(n):5d} tok  (whoever opens that directory)")
    print(f"  {'docs/ in full':<34} ~{tok(docs):5d} tok  "
          f"(nobody reads it in full; routed one file at a time)")
    print("\n  Hook output per fire: see scripts/probe_moments.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
