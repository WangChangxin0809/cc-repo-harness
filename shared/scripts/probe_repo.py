#!/usr/bin/env python3
"""Survey a repository: which of the seven delivery moments are filled, what
discipline already exists, and which tier the repo is at.

    python3 probe_repo.py [--root PATH] [--json]

Exit codes:
    0 = probe completed (a repo with nothing installed is a successful probe)
    2 = cannot judge (not a git repository, git unavailable)

Run this before writing a single file. A harness installed against an imagined
repo fits nothing, and the most common way to imagine a repo wrong is to assume
it is emptier than it is -- half-built conventions are everywhere and silently
conflict with anything you add.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter

SOURCE_EXT = {
    "py", "js", "ts", "tsx", "jsx", "go", "rs", "java", "kt", "rb", "php",
    "c", "h", "cc", "cpp", "hpp", "cs", "swift", "m", "mm", "scala", "ex",
    "exs", "gd", "lua", "sh", "bash", "sql", "vue", "svelte",
}
# Trees that carry somebody else's checks and somebody else's skills. Counting
# them would report a dependency's discipline as the repository's.
SKIP_DIRS = {
    ".git", "node_modules", "vendor", "third_party", "addons", ".venv", "venv",
    "target", "dist", "build", "out", "__pycache__", ".tox", ".mypy_cache",
    ".next", ".gradle", "Pods", "bower_components",
}
CHECK_DIRNAMES = {"gates", "guards", "selftests"}
# Files that live in a check directory and are not checks. Counting these is
# how a repository with three guards reports five, forever and consistently.
MACHINERY = {"dispatch.py", "__init__.py", "conftest.py", "run.py"}
WALK_CAP = 6000

HOOK_EVENTS = [
    "SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
    "Stop", "SubagentStop", "PreCompact", "SessionEnd", "Notification",
]


def sh(args, root):
    try:
        out = subprocess.run(
            args, cwd=root, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def _walk(root):
    """os.walk with vendored and hidden trees pruned, and a cap."""
    seen = 0
    for here, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        seen += 1
        if seen > WALK_CAP:
            return
        yield here, dirs, files


def find_check_dirs(root):
    """Where this repository keeps its checks, by shape rather than by path.

    Not `scripts/gates`. That is where *this* harness would put them, and a
    probe that only looks where it would have put things reports zero for every
    repository that had its own idea -- including, for a while, this one, whose
    gates are payload under `shared/scripts/` and were reported as absent by
    the tool whose job is to find them.

    Returns {dirname: [relative paths]}, capped so a large tree cannot turn a
    survey into a filesystem crawl."""
    found = {n: [] for n in CHECK_DIRNAMES}
    for here, _dirs, files in _walk(root):
        name = os.path.basename(here)
        if name in CHECK_DIRNAMES and any(f.endswith(".py") for f in files):
            found[name].append(os.path.relpath(here, root))
    return found


def skill_dirs(root):
    """Every skill whose description is loaded on every turn, and where from.

    Two sources, and the second is the one that was missing: skills the
    repository ships under `.claude/skills/`, and skills an *installed plugin*
    ships. Both are standing per-turn cost; only the first is the repository's
    to fix. Reporting one and not the other made this tool blind to the cost it
    exists to report -- it said ~0 tokens/turn while the installed plugin was
    spending about thirteen hundred."""
    out = []
    for base, origin in ((os.path.join(root, ".claude", "skills"), "repo"),
                         (os.path.join(root, ".agents", "skills"), "repo")):
        out.append((base, origin))
    plug = os.environ.get("CLAUDE_PLUGIN_ROOT")
    roots = [os.path.join(plug, "skills")] if plug else []
    home = os.path.expanduser("~/.claude/plugins")
    if os.path.isdir(home):
        for n in sorted(os.listdir(home)):
            if n in ("cache", "data", "marketplace", "marketplaces"):
                continue
            roots.append(os.path.join(home, n, "skills"))
    for base in roots:
        out.append((base, "plugin"))
    return out


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def load_json(path):
    raw = read(path)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return "MALFORMED"


def probe(root):
    tracked = sh(["git", "ls-files"], root)
    if tracked is None:
        return None
    files = [f for f in tracked.splitlines() if f]
    ext = Counter(f.rsplit(".", 1)[-1].lower() for f in files if "." in f)
    source = sum(n for e, n in ext.items() if e in SOURCE_EXT)
    md = [f for f in files if f.lower().endswith(".md")]

    r = {
        "root": os.path.abspath(root),
        "tracked_files": len(files),
        "source_files": source,
        "markdown_files": len(md),
        "top_extensions": ext.most_common(8),
        "moments": {},
        "discipline": {},
    }

    # --- moment 1: always-loaded entry file -------------------------------
    entry = []
    for name in ("CLAUDE.md", "AGENTS.md"):
        body = read(os.path.join(root, name))
        if body is not None:
            entry.append({"file": name, "lines": len(body.splitlines())})
    r["moments"]["1_always"] = entry

    # --- moment 4: nested entry files -------------------------------------
    # Vendored dependency trees carry their own; they are not the repo's own.
    vendor = re.compile(r"(^|/)(node_modules|vendor|third_party|addons|\.venv)(/|$)")
    nested = [
        f for f in files
        if re.search(r"(^|/)(CLAUDE|AGENTS)\.md$", f)
        and "/" in f
        and not vendor.search(f)
    ]
    r["moments"]["4_subtree"] = nested
    r["discipline"]["vendored_entry_files"] = [
        f for f in files
        if re.search(r"(^|/)(CLAUDE|AGENTS)\.md$", f) and vendor.search(f)
    ]

    # --- moments 2/3/5/6: hooks and permissions ---------------------------
    hooks_by_event, deny, settings_state = {}, [], "absent"
    for name in ("settings.json", "settings.local.json"):
        cfg = load_json(os.path.join(root, ".claude", name))
        if cfg is None:
            continue
        if cfg == "MALFORMED":
            settings_state = "MALFORMED"
            continue
        settings_state = "present"
        for event, entries in (cfg.get("hooks") or {}).items():
            hooks_by_event.setdefault(event, 0)
            for entry_group in entries if isinstance(entries, list) else []:
                hooks_by_event[event] += len(entry_group.get("hooks") or [])
        deny += ((cfg.get("permissions") or {}).get("deny") or [])

    r["discipline"]["settings"] = settings_state
    r["moments"]["2_session_start"] = hooks_by_event.get("SessionStart", 0)
    r["moments"]["3_prompt"] = hooks_by_event.get("UserPromptSubmit", 0)
    r["moments"]["5_before_action"] = {
        "PreToolUse": hooks_by_event.get("PreToolUse", 0),
        "permissions_deny": len(deny),
    }
    r["moments"]["6_after_action"] = hooks_by_event.get("PostToolUse", 0)
    r["discipline"]["other_hooks"] = {
        e: n for e, n in hooks_by_event.items()
        if e not in ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse")
    }

    # --- moment 7: skills, and what their descriptions cost ---------------
    skills, seen_dirs = [], set()
    for base, origin in skill_dirs(root):
        if not os.path.isdir(base) or base in seen_dirs:
            continue
        seen_dirs.add(base)
        for name in sorted(os.listdir(base)):
            body = read(os.path.join(base, name, "SKILL.md"))
            if body is None:
                continue
            m = re.search(r"^description:\s*(.+?)(?=^\w+:|^---)", body,
                          re.M | re.S)
            desc = " ".join(m.group(1).split()) if m else ""
            skills.append({
                "dir": os.path.join(base, name) if origin == "plugin"
                else os.path.relpath(os.path.join(base, name), root),
                "origin": origin,
                "desc_words": len(desc.split()),
                "body_lines": len(body.splitlines()),
            })
    r["moments"]["7_on_request"] = skills
    # ~1.35 tokens/word is a serviceable English estimate; this is a budget
    # signal, not an accounting figure.
    def cost(origin=None):
        return int(sum(s["desc_words"] for s in skills
                       if origin is None or s["origin"] == origin) * 1.35)
    r["always_on_skill_tokens"] = cost()
    r["skill_tokens_by_origin"] = {"repo": cost("repo"), "plugin": cost("plugin")}

    # --- existing discipline ----------------------------------------------
    def has(*parts):
        return os.path.isdir(os.path.join(root, *parts))

    check_dirs = find_check_dirs(root)
    retrieval_at = next(
        (os.path.relpath(os.path.join(h, "build.py"), root)
         for h, _d, f in _walk(root)
         if os.path.basename(h) == "index" and "build.py" in f), "")

    def tally(*parts):
        """(checks, selftests) in one check directory.

        Three things this has to get right, each of which it got wrong:

        A selftest is a *file*, not a directory. `find_check_dirs` looks for a
        directory called `selftests/`, which is where this harness would put
        them; almost everyone -- including this repository -- writes
        `guards/selftest.py` instead, and was reported as having none.

        `dispatch.py` and `selftest.py` are machinery, not checks. Counting
        them inflated this repository's own guard count from three to five,
        and would inflate every scaffolded repository's by exactly the same
        two, which is the kind of error that survives because it is consistent.

        Only `.py` files. A README sitting in `guards/` is not a guard.
        """
        d = os.path.join(root, *parts)
        if not os.path.isdir(d):
            return 0, 0
        checks = selftests = 0
        for f in os.listdir(d):
            if f.startswith((".", "_")) or not f.endswith(".py"):
                continue
            if f.startswith("selftest"):
                selftests += 1
            elif f not in MACHINERY:
                checks += 1
        return checks, selftests

    def total(kind, index):
        return sum(tally(d)[index] for d in check_dirs[kind])

    r["discipline"].update({
        "docs_dir": has("docs"),
        "docs_subdirs": sorted(
            d for d in os.listdir(os.path.join(root, "docs"))
            if os.path.isdir(os.path.join(root, "docs", d))
        ) if has("docs") else [],
        "gates": total("gates", 0),
        "guards": total("guards", 0),
        # Both spellings: a `selftests/` directory, and the `selftest.py` that
        # sits beside the checks it proves. Most repositories write the second.
        "selftests": (total("selftests", 0) + total("selftests", 1)
                      + total("gates", 1) + total("guards", 1)),
        "check_dirs": sorted(d for v in check_dirs.values() for d in v),
        "git_hooks": has(".githooks") or os.path.isdir(
            os.path.join(root, ".git", "hooks")),
        "ci_entry": [
            f for f in ("ci.sh", "scripts/ci.sh", "Makefile", "justfile",
                        "noxfile.py")
            if os.path.exists(os.path.join(root, f))
        ] + (["github-actions"] if has(".github", "workflows") else []),
        # By shape, for the reason `find_check_dirs` gives: a retrieval layer
        # under `tools/index/` is a retrieval layer.
        "retrieval": bool(retrieval_at),
        "retrieval_at": retrieval_at,
    })

    src = r["source_files"]
    r["tier"] = "A" if src < 50 else ("B" if src < 800 else "C")
    return r


FILLED = {
    "1_always": lambda v: bool(v),
    "2_session_start": lambda v: v > 0,
    "3_prompt": lambda v: v > 0,
    "4_subtree": lambda v: bool(v),
    "5_before_action": lambda v: v["PreToolUse"] > 0 or v["permissions_deny"] > 0,
    "6_after_action": lambda v: v > 0,
    "7_on_request": lambda v: bool(v),
}
LABEL = {
    "1_always": "1 · every turn        CLAUDE.md",
    "2_session_start": "2 · session start     SessionStart hook",
    "3_prompt": "3 · each prompt       UserPromptSubmit hook",
    "4_subtree": "4 · reading subtree   nested CLAUDE.md",
    "5_before_action": "5 · before an action  PreToolUse / deny",
    "6_after_action": "6 · after an action   PostToolUse hook",
    "7_on_request": "7 · on request        skills",
}


def describe(key, v):
    if key == "1_always":
        return ", ".join(f"{e['file']} ({e['lines']} lines)" for e in v) or "-"
    if key == "4_subtree":
        return f"{len(v)} file(s)" if v else "-"
    if key == "5_before_action":
        return (f"{v['PreToolUse']} hook(s), {v['permissions_deny']} deny rule(s)"
                if FILLED[key](v) else "-")
    if key == "7_on_request":
        return f"{len(v)} skill(s)" if v else "-"
    return f"{v} hook(s)" if v else "-"


def render(r):
    out = [
        "",
        f"REPO   {r['root']}",
        f"       {r['tracked_files']} tracked files · {r['source_files']} source "
        f"· {r['markdown_files']} markdown",
        f"       {'  '.join(f'.{e}:{n}' for e, n in r['top_extensions'][:6])}",
        "",
        "SEVEN MOMENTS",
    ]
    empty = []
    for key, label in LABEL.items():
        v = r["moments"][key]
        filled = FILLED[key](v)
        if not filled:
            empty.append(label.split("·")[0].strip())
        out.append(f"  [{'x' if filled else ' '}] {label:<38} {describe(key, v)}")

    d = r["discipline"]
    by = r["skill_tokens_by_origin"]
    out += [
        "",
        "EXISTING DISCIPLINE",
        f"  .claude/settings.json  {d['settings']}",
        f"  docs/                  {'yes: ' + ', '.join(d['docs_subdirs']) if d['docs_subdirs'] else ('yes (flat)' if d['docs_dir'] else 'no')}",
        f"  gates / guards         {d['gates']} / {d['guards']}   selftests: "
        f"{d['selftests']}"
        + (f"   in {', '.join(d['check_dirs'])}" if d["check_dirs"] else ""),
        f"  CI entry               {', '.join(d['ci_entry']) or 'none found'}",
        "  retrieval layer        "
        + (d["retrieval_at"] if d["retrieval"] else "absent"),
        f"  always-on skill cost   ~{r['always_on_skill_tokens']} tokens/turn"
        + (f"   ({by['repo']} this repo, {by['plugin']} installed plugins)"
           if by["plugin"] else ""),
        "",
        f"TIER  {r['tier']}   " + {
            "A": "small — install steps 1-3 only; retrieval and dream are dead weight here",
            "B": "real project — steps 1-5",
            "C": "large — all steps, including a gold set for the harness itself",
        }[r["tier"]],
        "",
        f"EMPTY MOMENTS: {', '.join(empty) if empty else 'none'}",
    ]

    if d["settings"] == "MALFORMED":
        out.append("  !! settings.json did not parse — no hook in it is running")
    if d["vendored_entry_files"]:
        out.append(f"  note: {len(d['vendored_entry_files'])} CLAUDE.md/AGENTS.md "
                   "in vendored trees, not counted as this repo's")
    if r["always_on_skill_tokens"] > 2000:
        out.append("  note: skill descriptions are a standing per-turn cost — "
                   "see references/layering.md on merging by trigger overlap")
    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    r = probe(a.root)
    if r is None:
        print("cannot judge: not a git repository, or git is unavailable",
              file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2, ensure_ascii=False) if a.json else render(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
