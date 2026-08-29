#!/usr/bin/env python3
"""Gate: the repository's public face is present and its links resolve.

    python3 scripts/gates/check_community_health.py [--root .] [--strict]

    0 = present and intact    1 = something missing or broken    2 = cannot judge

Three failures, all of which look like nothing from the inside:

  * A missing community health file. GitHub publishes the gap on the community
    profile page, so the first person to notice is an outsider.
  * A README section that was never written. The reader who needed it leaves
    rather than asking.
  * A link that points at nothing. This is the one that rots: the file was
    correct when written and the target moved later, and nobody re-reads a
    README once it exists.

What this cannot judge, and does not pretend to: whether the prose is any good,
and whether the quick start actually works. The second has no substitute for
running it in a fresh clone -- put that in CONTRIBUTING.md as a release step.

`--strict` also requires the optional files (CODE_OF_CONDUCT, issue and PR
templates). Off by default, because a repository that is not taking outside
contributions yet does not need them, and a gate that is red for a reason the
author has deliberately chosen is a gate the author learns to skip.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

# name -> (candidate paths, required by default)
FILES = {
    "README.md":          (["README.md", "README.rst", "docs/README.md"], True),
    "LICENSE":            (["LICENSE", "LICENSE.md", "LICENCE", "COPYING"], True),
    "CONTRIBUTING.md":    (["CONTRIBUTING.md", ".github/CONTRIBUTING.md"], True),
    "SECURITY.md":        (["SECURITY.md", ".github/SECURITY.md"], True),
    "CODE_OF_CONDUCT.md": (["CODE_OF_CONDUCT.md",
                            ".github/CODE_OF_CONDUCT.md"], False),
    "issue templates":    ([".github/ISSUE_TEMPLATE"], False),
    "PR template":        ([".github/PULL_REQUEST_TEMPLATE.md",
                            ".github/pull_request_template.md"], False),
}

# section -> a pattern that, appearing anywhere in the README, satisfies it.
# Deliberately loose: this gate judges presence, not wording, and a gate that
# insists on a heading spelling is a gate people satisfy by renaming headings.
#
# Keys carry no article, because the message is built from them and the first
# version of it read "the README has no a pointer to contributing".
README_SECTIONS = {
    "quick start": r"(?im)^#{1,4}\s*(quick\s*start|getting\s*started|installation|install|usage)\b",
    "requirements section": r"(?im)^#{1,4}\s*(requirements|prerequisites|dependencies)\b|^\s*[-*]\s*(python|node|go|rust|godot|java)\s*[\d>=]",
    "licence statement": r"(?im)^#{1,4}\s*licen[cs]e\b|\blicen[cs]ed under\b",
    "pointer to CONTRIBUTING": r"(?i)contributing",
}

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")

# GitHub resolves `../../issues`, `../../security/advisories/new` and friends
# against the repository on github.com; they are a documented feature and they
# never exist on disk. Named individually rather than exempting "relative links
# with no file extension", which would also swallow a genuinely broken
# `docs/handbook`. A narrow list is the cost of not opening an exemption channel.
GITHUB_RELATIVE = re.compile(
    r"^(?:\.\./)+(?:issues|pulls|security|discussions|releases|wiki|actions"
    r"|labels|milestones|projects|blob|tree|commits|compare|graphs|network"
    r"|settings|community)(?:/|$)")
PUBLIC_FACE = ("README.md", "CONTRIBUTING.md", "SECURITY.md",
               "CODE_OF_CONDUCT.md", ".github/CONTRIBUTING.md",
               ".github/SECURITY.md", ".github/CODE_OF_CONDUCT.md")


def find(root, candidates):
    for rel in candidates:
        if os.path.exists(os.path.join(root, rel)):
            return rel
    return None


def broken_links(root, rel):
    """Relative links only. Remote URLs are not checked: reaching the network
    from a gate makes it fail for reasons that have nothing to do with the
    repository, and a gate that is red for external reasons stops being read."""
    out = []
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return out
    base = os.path.dirname(path)
    for target in LINK.findall(text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        if GITHUB_RELATIVE.match(target):
            continue
        clean = target.split("#", 1)[0]
        if not clean:
            continue
        if not os.path.exists(os.path.normpath(os.path.join(base, clean))):
            out.append((rel, target))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    if subprocess.run(["git", "rev-parse", "--git-dir"], cwd=root,
                      capture_output=True).returncode != 0:
        print("cannot judge: not a git repository", file=sys.stderr)
        return 2

    missing, present = [], {}
    for name, (candidates, required) in FILES.items():
        hit = find(root, candidates)
        if hit:
            present[name] = hit
        elif required or a.strict:
            missing.append((name, candidates[0]))

    readme = present.get("README.md")
    thin = []
    if readme:
        with open(os.path.join(root, readme), encoding="utf-8",
                  errors="replace") as fh:
            body = fh.read()
        # A README that exists but says nothing passes every "does it contain"
        # check ever written unless one of them is positive.
        if len(body.split()) < 40:
            thin.append("the README is under 40 words — a placeholder reads as "
                        "though the project was documented")
        else:
            for what, pat in README_SECTIONS.items():
                if not re.search(pat, body):
                    thin.append(f"the README has no {what}")

    broken = []
    for rel in PUBLIC_FACE:
        if os.path.exists(os.path.join(root, rel)):
            broken.extend(broken_links(root, rel))

    if not (missing or thin or broken):
        return 0

    if missing:
        print("Missing from the repository's public face:", file=sys.stderr)
        for name, where in missing:
            print(f"  {name:<20} expected at {where}", file=sys.stderr)
        print("  GitHub publishes these gaps on the community profile page, so\n"
              "  the first person to notice will be someone outside the project.",
              file=sys.stderr)
    if thin:
        print(("\n" if missing else "") + "README:", file=sys.stderr)
        for t in thin:
            print(f"  {t}", file=sys.stderr)
        print("  Take each section from a document that already exists here. A\n"
              "  section you have to invent is a document the repo is missing —\n"
              "  record that in docs/exec-plans/tech-debt-tracker.md instead of\n"
              "  writing plausible text.", file=sys.stderr)
    if broken:
        print(("\n" if (missing or thin) else "")
              + f"{len(broken)} link(s) in the public-facing files resolve to nothing:",
              file=sys.stderr)
        for rel, target in broken:
            print(f"  {rel} -> {target}", file=sys.stderr)
        print("  git cat-file -e HEAD:<path>\n"
              "  exit 0 means the file was deleted from the worktree — restore it.\n"
              "  Non-zero means it never existed — fix the link.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
