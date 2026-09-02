#!/usr/bin/env python3
"""Which of the ways of reaching an agent this repository actually uses.

    python3 assess/surface.py [--root .] [--json]

## The distinction this rests on, and it is the whole module

Decision 0025 refused to score a repository on **what it keeps**, and that
refusal stands. Counting files grades a repository on whether it adopted
somebody else's conventions, goes *up* when this plugin is installed, and
called 0024 -- which cut the standing cost by 81% -- a regression.

This is a different question, and the difference is not a matter of degree.
`scripts/gates/` is **our** convention: a repository that keeps its checks in
`tools/` keeps its checks, and marking it down would be marking it down for
disagreeing with us. A `PreToolUse` hook is **not** a convention. It is the
only place a tool call can be refused before it happens. A repository without
one has not chosen a different way of refusing actions; it has no way of
refusing actions.

So what is read here is Claude Code's own surface -- the places the product
offers for a repository to reach an agent working in it -- and what is
reported is, for each place with nothing at it, **what therefore cannot
happen here**.

## Two rules keep this from becoming the thing 0025 rejected

**Coverage, never a count.** Each mechanism is present or absent, and nothing
else. Two `PreToolUse` hooks are the same coverage as one, six skills the same
as one. This is the test 0025 used and it is the test that matters: 0024
deleted five skills that all sat at the same moment, and this row does not
move.

**The repository's own, never the machine's.** A skill a plugin provides is
installed on somebody's laptop, not kept in the tree -- a teammate who has not
installed it gets nothing. `probe_repo.py` already separates the two by
origin, and only `repo` counts here. The instrument cannot reward its own
presence.

## And it hands over, rather than deciding

An absent mechanism is a **candidate**, exactly like 4.2's. A repository can
be right to have no MCP server, no subagents, no `UserPromptSubmit` hook. What
a machine can say is which places are empty and what each empty place costs;
which of those absences is fine here is a reading -> conflict.py, truth.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# (key, what it is, where it lives, what nothing there means)
#
# Every entry is a mechanism Claude Code offers, not a layout this project
# likes. The test for admission: is there another way to get this effect? If
# yes, it is a convention and does not belong here.
SURFACE = (
    ("always", "entry file", "CLAUDE.md",
     "nothing reaches an agent unless somebody types it into the prompt"),
    ("subtree", "nested entry file", "*/CLAUDE.md",
     "a rule true of one directory is either paid for on every turn or not "
     "written down"),
    ("scoped", "path-scoped rule", ".claude/rules/*.md with `paths:`",
     "the same, for a rule that does not follow a directory boundary"),
    ("session", "SessionStart hook", ".claude/settings.json",
     "a fact that should open every session has nowhere to live"),
    ("prompt", "UserPromptSubmit hook", ".claude/settings.json",
     "nothing can act on what was just asked, before the work starts"),
    ("before", "PreToolUse hook or deny rule", ".claude/settings.json",
     "no action can be refused before it happens, and a destructive one is "
     "complete the moment it runs"),
    ("after", "PostToolUse hook", ".claude/settings.json",
     "nothing checks what was just written while the turn that wrote it is "
     "still open"),
    ("end", "Stop or SubagentStop hook", ".claude/settings.json",
     "nothing runs when the work stops, so anything owed at the end is owed "
     "to whoever remembers"),
    ("skills", "skill of its own", ".claude/skills/",
     "knowledge that should arrive when it is needed is either loaded on "
     "every turn or not at all"),
    ("agents", "subagent", ".claude/agents/",
     "work that wants its own context window shares this one"),
    ("commands", "slash command", ".claude/commands/",
     "a procedure people repeat is retyped, differently each time"),
    ("mcp", "MCP server", ".mcp.json",
     "a tool this project needs stays outside the session"),
)

_PATHS_FRONTMATTER = re.compile(r"^---\s*$.*?^\s*paths\s*:", re.M | re.S)


def _dir_has(root, rel, suffix=".md"):
    where = os.path.join(root, *rel.split("/"))
    if not os.path.isdir(where):
        return False
    for name in os.listdir(where):
        if name.endswith(suffix):
            return True
        if os.path.isdir(os.path.join(where, name)):
            # skills/ holds one directory per skill
            if os.path.exists(os.path.join(where, name, "SKILL.md")):
                return True
    return False


def _scoped_rules(root):
    """A rule under `.claude/rules/` carrying `paths:` frontmatter.

    Without the frontmatter it loads at launch and is a slower entry file, not
    a scoped rule -- which is why `check_context_budget.py` counts those on
    the floor. Absent frontmatter is therefore absent coverage."""
    where = os.path.join(root, ".claude", "rules")
    if not os.path.isdir(where):
        return False
    for here, _dirs, files in os.walk(where):
        for name in files:
            if not name.endswith(".md"):
                continue
            try:
                with open(os.path.join(here, name), encoding="utf-8",
                          errors="replace") as fh:
                    head = fh.read(2000)
            except OSError:
                continue
            if _PATHS_FRONTMATTER.search(head):
                return True
    return False


def used(root, probe):
    """Which mechanisms this repository reaches, as a flat present/absent map.

    `probe` is `probe_repo.probe()`'s output, which has already read the
    settings and the entry files; re-reading them here would be a second
    parser to keep in step with the first."""
    m = probe.get("moments") or {}
    d = probe.get("discipline") or {}
    other = d.get("other_hooks") or {}
    before = m.get("5_before_action") or {}
    # A skill a plugin installed is on this machine, not in this tree.
    own_skills = [s for s in (m.get("7_on_request") or [])
                  if s.get("origin") == "repo"]
    return {
        "always": bool(m.get("1_always")),
        "subtree": bool(m.get("4_subtree")),
        "scoped": _scoped_rules(root),
        "session": bool(m.get("2_session_start")),
        "prompt": bool(m.get("3_prompt")),
        "before": bool(before.get("PreToolUse") or
                       before.get("permissions_deny")),
        "after": bool(m.get("6_after_action")),
        "end": bool(other.get("Stop") or other.get("SubagentStop")),
        "skills": bool(own_skills),
        "agents": _dir_has(root, ".claude/agents"),
        "commands": _dir_has(root, ".claude/commands"),
        "mcp": os.path.exists(os.path.join(root, ".mcp.json")),
    }


def assess(root, probe):
    if not probe:
        return {"could_not_judge": "nothing probed the repository's wiring"}
    have = used(root, probe)
    absent = [{"key": k, "what": what, "where": where, "costs": costs}
              for k, what, where, costs in SURFACE if not have[k]]
    return {"of": len(SURFACE), "reached": len(SURFACE) - len(absent),
            "absent": absent, "have": have}


def render(r):
    if "could_not_judge" in r:
        return [{"label": "the surface it uses", "value": "could not judge",
                 "flag": "info", "note": r["could_not_judge"]}]
    absent, of, reached = r["absent"], r["of"], r["reached"]
    if not absent:
        return [{"label": "the surface it uses", "value": f"{of} of {of}",
                 "flag": "ok",
                 "note": "every place Claude Code offers for a repository to "
                         "reach an agent has something at it"}]
    names = ", ".join(a["what"] for a in absent[:3])
    if len(absent) > 3:
        names += f", and {len(absent) - 3} more"
    rows = [{
        "label": "the surface it uses",
        "value": f"{reached} of {of} — no {names}",
        # Below half is a repository using Claude Code as a text box with a
        # CLAUDE.md. It is a real finding and it is still not a verdict: the
        # rows under it say what each absence costs, and some of them will be
        # fine here.
        "flag": "bad" if reached * 2 < of else "warn" if len(absent) > 3
                else "ok",
        "note": "these are the places the product offers, not conventions "
                "this project likes — a repository that keeps its checks in "
                "`tools/` keeps its checks, but one with no `PreToolUse` hook "
                "has no way to refuse an action. Which of these absences is "
                "right here is a reading -> 0043"}]
    for a in absent:
        rows.append({"label": "  no " + a["what"], "value": a["where"],
                     "flag": "info", "note": a["costs"]})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    sys.path.insert(0, os.path.dirname(HERE))
    import probe_repo  # noqa: E402
    r = assess(root, probe_repo.probe(root))
    if a.json:
        print(json.dumps(r, indent=2))
        return 0
    for row in render(r):
        print("{0:44} {1}".format(row["label"], row.get("value", "")))
        if row.get("note"):
            print("    {0}".format(row["note"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
