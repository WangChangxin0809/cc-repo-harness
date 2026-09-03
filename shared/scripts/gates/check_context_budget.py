#!/usr/bin/env python3
"""Gate: the always-on context budget.

    python3 scripts/gates/check_context_budget.py [--root .] [--cap 100]

    0 = within budget    1 = over    2 = cannot judge

Instructions loaded at launch are paid on every turn of every session, forever.
Nothing about that cost is visible while writing them -- each addition is one
plausible line -- so it only ever grows. This gate is the feedback the writing
does not otherwise have.

## What counts, and why each one does

Claude Code loads **four** things unconditionally, and the cap is over their sum
rather than over one file. It used to be over one file, and that made the other
three free:

  1. `CLAUDE.md` at the repository root.
  2. `.claude/CLAUDE.md`. Both are first-party project locations -- the docs say
     "`./CLAUDE.md` **or** `./.claude/CLAUDE.md`" -- and both load. Looking only
     at the root one meant a repository following the documented layout returned
     "cannot judge" while carrying hundreds of always-on lines.
  3. `.claude/rules/**/*.md` **without** `paths:` frontmatter. Such a rule is
     "loaded at launch with the same priority as `.claude/CLAUDE.md`". Not
     counting them made `.claude/rules/` a complete bypass: move a hundred lines
     there and the cost is identical while the cap goes quiet.
  4. Every installed skill's `description`, summed. They load whether the skill
     triggers or not; twenty skills at eighty tokens each is 1,600 tokens gone
     before anyone types.

## What deliberately does not count

- **Nested `CLAUDE.md` in subdirectories.** They are the escape hatch this gate
  exists to push work toward, and charging for them would push it back.
- **Rules that declare `paths:`.** Same argument: they load only when Claude
  works with matching files, which is the move this gate wants to reward. They
  are reported, not charged.

## The two escape hatches have a ceiling of their own

Neither is charged against the shared cap, and neither is unbounded. An escape
hatch with no bound is where everything ends up: the cost does not disappear
when a rule moves out of `CLAUDE.md`, it moves from *every turn* to *every
matching read*, and at three hundred lines that is the worse of the two.

So the ceiling is **per file, never summed**. Summing would be a charge by
another name and would undo the incentive to move work out at all. Ten scoped
rules of thirty lines is exactly the shape this gate wants; one of three
hundred is not.

- A rule with `paths:` --- `--rule-tok-cap`, 50 tokens, and `--scoped-cap`,
  40 lines. It arrives in full at the moment it matches, competing with the
  work already in front of the model. Fifty tokens is one sentence and a
  pointer: the test, and where the reasoning lives. A rule that needs more is
  a document with a rule's file extension.
- A nested `CLAUDE.md` --- `--nested-cap`, 50 lines. Past that it has stopped
  being "what is true in this directory" and become a second root file.
- One skill's `description` --- `--skill-desc-cap`, 100 tokens. The sum is
  capped too, but a sum lets one description eat the budget of five. What
  triggers a skill is a sentence; a description that lists every symptom has
  become the skill's body in the wrong place.

Only tracked files are read, via `git ls-files`, so vendored trees and fixture
repositories are out of scope --- somebody else's `CLAUDE.md`, checked in under
`eval/` or `vendor/`, is not this repository's context cost.
- **HTML comment lines.** Claude Code strips block-level comments before the
  content enters context, so they cost nothing. The cap charged for them, which
  meant a file could fail on maintainer notes that were never delivered -- two
  different definitions of "line" inside one function.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys

TOKENS_PER_WORD = 1.35   # measured against tokenized English prose; identifiers
                         # and punctuation push it higher, so this under-reports

FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
# `[^\S\n]*` and not `\s*`, which would match the newline and read a list on the
# following lines as an empty inline value.
PATHS_KEY = re.compile(r"^paths:[^\S\n]*(.*)$", re.M)
BLOCK_COMMENT = re.compile(r"<!--.*?-->", re.S)


def frontmatter_description(path):
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return ""
    m = FRONTMATTER.match(text)
    if not m:
        return ""
    d = re.search(r"^description:\s*(.+?)(?=\n\w+:|\Z)", m.group(1), re.S | re.M)
    return " ".join(d.group(1).split()) if d else ""


def charged_lines(text):
    """Lines that actually reach the context window.

    Block-level HTML comments are stripped before injection, so they are free
    and must not be charged. Removing them can leave a blank line behind where
    the comment stood; those go too, because a comment did not cost a blank
    line either."""
    return [l for l in BLOCK_COMMENT.sub("", text).splitlines() if l.strip()]


def is_unconditional(path):
    """A rule with no `paths:` loads at launch. One with `paths:` does not.

    A file with no frontmatter at all has no `paths:` either, so it is
    unconditional -- which is the common shape of a hand-written rule and
    exactly the one that must not slip through."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False, ""
    m = FRONTMATTER.match(text)
    if not m:
        return True, text
    return PATHS_KEY.search(m.group(1)) is None, text


def always_on_instructions(root):
    """(charged, conditional) — (rel, line count) for each file, in load order."""
    charged, conditional = [], []
    for rel in ("CLAUDE.md", os.path.join(".claude", "CLAUDE.md")):
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                charged.append((rel.replace(os.sep, "/"),
                                len(charged_lines(fh.read()))))
        except OSError:
            continue

    rules_dir = os.path.join(root, ".claude", "rules")
    for dirpath, _, names in os.walk(rules_dir):
        for name in sorted(names):
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            unconditional, text = is_unconditional(path)
            n = len(charged_lines(text))
            (charged if unconditional else conditional).append((rel, n))
    return charged, conditional


def rule_tokens(path):
    """Tokens a scoped rule delivers when it matches: the body, not the
    frontmatter, and not block comments. Same estimate as the descriptions
    use, so the two caps are in one unit."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return 0
    m = FRONTMATTER.match(text)
    body = text[m.end():] if m else text
    return int(len(" ".join(charged_lines(body)).split()) * TOKENS_PER_WORD)


def nested_claude_files(root):
    """(rel, lines) for every tracked CLAUDE.md that is not one of the two
    always-on locations. `git ls-files` and not a walk: it already excludes
    what .gitignore excludes, which is where fixture repositories live."""
    out = subprocess.run(["git", "ls-files", "-z", "*CLAUDE.md"],
                         cwd=root, capture_output=True, text=True)
    if out.returncode != 0:
        return None
    found = []
    for rel in out.stdout.split("\0"):
        rel = rel.strip()
        if not rel or rel in ("CLAUDE.md", ".claude/CLAUDE.md"):
            continue
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                found.append((rel, len(charged_lines(fh.read()))))
        except OSError:
            continue
    return sorted(found)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--cap", type=int, default=100,
                    help="max lines of always-on instructions, summed")
    ap.add_argument("--skill-cap", type=int, default=2000,
                    help="max total tokens of always-on skill descriptions")
    ap.add_argument("--scoped-cap", type=int, default=40,
                    help="max lines in one .claude/rules/ file with paths:")
    ap.add_argument("--nested-cap", type=int, default=50,
                    help="max lines in one nested CLAUDE.md")
    ap.add_argument("--rule-tok-cap", type=int, default=50,
                    help="max tokens one .claude/rules/ file with paths: delivers")
    ap.add_argument("--skill-desc-cap", type=int, default=100,
                    help="max tokens in one skill's description")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    failures = []
    charged, conditional = always_on_instructions(root)

    if not any(rel.endswith("CLAUDE.md") for rel, _ in charged):
        print("cannot judge: no CLAUDE.md at the repository root or in "
              ".claude/ — both are first-party project locations and neither "
              "is present", file=sys.stderr)
        return 2

    total_lines = sum(n for _, n in charged)
    if total_lines > a.cap:
        listing = "\n".join(f"    {rel:<40} {n:>4} lines"
                            for rel, n in sorted(charged, key=lambda t: -t[1]))
        extra = ""
        if conditional:
            extra = ("\n  Already scoped, and not charged here:\n"
                     + "\n".join(f"    {rel:<40} {n:>4} lines"
                                 for rel, n in conditional))
        failures.append(
            f"Always-on instructions total {total_lines} lines, cap is "
            f"{a.cap}.\n{listing}\n"
            f"  Every one of these loads at launch, on every turn, forever.\n"
            f"  Move rules out, do not compress them:\n"
            f"    - an action a script can block   -> scripts/guards/\n"
            f"    - a state a script can detect    -> scripts/gates/\n"
            f"    - true only under one path       -> .claude/rules/ with\n"
            f"                                        paths:, or that\n"
            f"                                        directory's CLAUDE.md\n"
            f"    - a procedure with a trigger     -> a skill\n"
            f"  See docs/decisions/{extra}")

    # An empty CLAUDE.md passes every length check ever written. One positive
    # assertion is what catches it.
    #
    # This catches empty and nothing else -- a scaffolded CLAUDE.md that is
    # twenty lines of `<placeholder>` has plenty of "content" and sails past.
    # That case is check_templates_filled.py's, and it is deliberately a
    # separate gate: this one judges cost, that one judges truthfulness, and a
    # check that judges two things reports the wrong one half the time.
    if total_lines < 5:
        failures.append("The always-on instructions have almost no content — a "
                        "template left unfilled is worse than no file, because "
                        "it reads as though the conventions were written down.")

    over = [(rel, n) for rel, n in conditional if n > a.scoped_cap]
    if over:
        failures.append(
            "A scoped rule is longer than one file's worth of context:\n"
            + "\n".join(f"    {rel:<40} {n:>4} lines  (cap {a.scoped_cap})"
                        for rel, n in over)
            + "\n  It is not charged on every turn, but it arrives whole the\n"
              "  moment it matches, next to the work already in front of the\n"
              "  model. Split it by path, or move what a script can enforce\n"
              "  into scripts/guards/ or scripts/gates/.")

    heavy = []
    for rel, _ in conditional:
        cost = rule_tokens(os.path.join(root, rel))
        if cost > a.rule_tok_cap:
            heavy.append((rel, cost))
    if heavy:
        failures.append(
            "A scoped rule costs more than one sentence and a pointer:\n"
            + "\n".join(f"    {rel:<40} ~{c:>4} tok  (cap {a.rule_tok_cap})"
                        for rel, c in heavy)
            + "\n  Keep the test and where the reasoning lives; move the\n"
              "  reasoning itself to docs/decisions/ or the directory's own\n"
              "  CLAUDE.md, and what a script could enforce to scripts/.")

    nested = nested_claude_files(root)
    if nested is None:
        print("cannot judge: `git ls-files` failed, so the nested CLAUDE.md "
              "files cannot be enumerated", file=sys.stderr)
        return 2
    over = [(rel, n) for rel, n in nested if n > a.nested_cap]
    if over:
        failures.append(
            "A nested CLAUDE.md has become a second root file:\n"
            + "\n".join(f"    {rel:<40} {n:>4} lines  (cap {a.nested_cap})"
                        for rel, n in over)
            + "\n  Everything in it is delivered whenever Claude reads a file\n"
              "  in that directory. Past this length it is no longer \"what is\n"
              "  true here\" — route the rest to docs/ and link it.")

    total = 0
    per_skill = []
    for path in sorted(glob.glob(os.path.join(root, ".claude", "skills",
                                              "*", "SKILL.md"))):
        desc = frontmatter_description(path)
        cost = int(len(desc.split()) * TOKENS_PER_WORD)
        total += cost
        per_skill.append((os.path.basename(os.path.dirname(path)), cost))
    big = [(n, c) for n, c in per_skill if c > a.skill_desc_cap]
    if big:
        failures.append(
            "A skill description costs more than a trigger should:\n"
            + "\n".join(f"    {n:<32} ~{c:>4} tok  (cap {a.skill_desc_cap})"
                        for n, c in big)
            + "\n  Say what it does and when it fires. The symptoms, the\n"
              "  steps and the caveats are the body, which is free until\n"
              "  the skill triggers.")
    if total > a.skill_cap:
        listing = "\n".join(f"    {n:<32} ~{c} tok"
                            for n, c in sorted(per_skill, key=lambda t: -t[1]))
        failures.append(
            f"Skill descriptions cost ~{total} tokens on every turn, cap is "
            f"{a.skill_cap}.\n{listing}\n"
            f"  Merge skills that compete for the same trigger; split only what\n"
            f"  is re-entered independently. See the writing-docs skill.")

    if not failures:
        return 0
    for f in failures:
        print(f, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
