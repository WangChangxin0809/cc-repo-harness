#!/usr/bin/env python3
"""One page about this repository, with nothing in it that needed an opinion.

    python3 assess/factsheet.py [--root .] [--full] [--json OUT]

    (default)  probe + blast + drift   -- seconds, no toolchain, no network
    --full     also replays defects    -- minutes, needs the repo's test tools

Exit codes:
    0 = the page was produced    2 = cannot judge (not a git repository)

## Two readers, one page

A person reads this to decide whether the machine is worth trusting. An agent
reads it as the input to the only step of the assessment that costs anything --
and an agent that is handed counts does not have to produce them, which matters
because a model counting is expensive, unrepeatable, and cannot count tokens.

So everything here is measured. The page ends by naming, explicitly, the
questions it could not answer; that list is the brief for the step that follows,
and it is short on purpose.

## Why this is also the unit of before-and-after

Whatever the harness changes has to show up here, in these numbers, measured
the same way afterwards as before. "We added three gates" is a claim about what
we did. "Two of six irreversible actions were refused, now five are, and no
legitimate action became blocked" is a claim about the repository -- and it is
the only kind this page will carry.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import blast as blast_mod  # noqa: E402
import catch as catch_mod  # noqa: E402
from history import mine  # noqa: E402


def load(name, path):
    """Import a sibling script by path.

    `probe_repo.py` and `drift.py` sit one directory up and are not a package;
    importing them by name would depend on how this was invoked."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:                                    # noqa: BLE001
        return None
    return mod


def drift_pairs(root):
    """(documents claiming authority over code, how many are behind it)."""
    path = os.path.join(PARENT, "drift.py")
    if not os.path.exists(path):
        return None
    out = subprocess.run([sys.executable, path, "pairs", "--root", root,
                          "--json"], capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        return None
    try:
        pairs = json.loads(out.stdout)
    except ValueError:
        return None
    return len(pairs), sum(1 for p in pairs if p.get("newer"))


def a_source_file(root):
    out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True,
                         text=True, timeout=120)
    for f in out.stdout.split():
        if f.endswith((".py", ".ts", ".js", ".go", ".rs", ".rb", ".java")):
            return f
    return ""


def a_check_file(probe, root):
    for d in probe["discipline"].get("check_dirs") or []:
        full = os.path.join(root, d)
        if os.path.isdir(full):
            for f in sorted(os.listdir(full)):
                if f.endswith(".py"):
                    return os.path.join(d, f)
    return ""


def gather(root, full, instances, work):
    probe_mod = load("probe_repo", os.path.join(PARENT, "probe_repo.py"))
    probe = probe_mod.probe(root) if probe_mod else None
    if probe is None:
        return None

    r = {"probe": probe, "blast": None, "catch": None, "catch_why": "",
         "drift": drift_pairs(root), "defects": None}

    if os.path.isdir(os.path.join(root, ".claude")):
        r["blast"] = blast_mod.assess(root, a_source_file(root),
                                      a_check_file(probe, root))

    found = mine(root)
    if found is not None:
        r["defects"] = {"replayable": len(
            [x for x in found["revert"] + found["fix_test"] if x["small"]]),
            "fix_no_test": len(found["fix_no_test"]),
            "has_test_files": found["has_test_files"],
            "shallow": found["shallow"]}

    if full:
        r["catch"], r["catch_why"] = catch_mod.assess(root, instances, work)
    return r


# --------------------------------------------------------------------------

def render(r):
    p, d = r["probe"], r["probe"]["discipline"]
    by = r["probe"]["skill_tokens_by_origin"]
    entry = p["moments"]["1_always"]
    moments = sorted(k for k in p["moments"] if k[0].isdigit())
    filled = [k.split("_")[0] for k in moments if filled_moment(p, k)]
    empty = [k.split("_")[0] for k in moments if not filled_moment(p, k)]

    out = ["",
           f"REPO   {p['root']}",
           f"       {p['tracked_files']} tracked · {p['source_files']} source · "
           f"tier {p['tier']}",
           ""]

    out.append(f"STANDING COST   ~{p['always_on_skill_tokens']} tokens/turn "
               f"({by['repo']} this repo, {by['plugin']} installed plugins)")
    out.append("                " + (", ".join(
        f"{e['file']} {e['lines']} lines" for e in entry) or
        "no CLAUDE.md — nothing is loaded every turn"))
    out.append(f"MOMENTS         filled {','.join(filled) or '-'}   "
               f"empty {','.join(empty) or 'none'}")
    out.append(f"CHECKS          gates {d['gates']}  guards {d['guards']}  "
               f"selftests {d['selftests']}"
               + (f"   in {', '.join(d['check_dirs'])}" if d["check_dirs"] else "")
               )
    out.append(f"                CI: {', '.join(d['ci_entry']) or 'none found'}")

    if r["drift"]:
        pairs, behind = r["drift"]
        out.append(f"DOC AUTHORITY   {pairs} document(s) claim code; "
                   f"{behind} are older than the code they claim")

    if r["blast"]:
        b = r["blast"]
        stopped = [x for x in b["rows"] if x["stopped"] and not x["false_block"]]
        wrong = [x for x in b["rows"] if x["false_block"]]
        loose = [x["probe"] for x in b["rows"]
                 if not x["stopped"] and not x["deny_rules"]]
        out.append(f"BLAST RADIUS    {len(stopped)}/{len(b['rows'])} irreversible "
                   f"actions refused before they happen"
                   + (f"; {len(wrong)} FALSE BLOCK(S)" if wrong else
                      "; no legitimate action blocked"))
        if loose:
            out.append(f"                open: {', '.join(loose)}")
    else:
        out.append("BLAST RADIUS    no .claude/ — nothing is wired to ask")

    dfx = r["defects"]
    if dfx:
        if dfx["shallow"]:
            out.append("DEFECT SUPPLY   shallow clone — no history to replay")
        else:
            out.append(f"DEFECT SUPPLY   {dfx['replayable']} replayable from this "
                       f"repo's own history; {dfx['fix_no_test']} fixes nothing "
                       f"verifies")
    if r["catch"]:
        c = r["catch"]
        counts = {k: 0 for k in catch_mod.LADDER}
        for row in c["rows"]:
            if row["rung"]:
                counts[row["rung"]] += 1
        late = counts["ci"] + counts["never"]
        out.append("CATCH LADDER    " + "  ".join(
            f"{k}:{counts[k]}" for k in catch_mod.LADDER))
        out.append(f"                {late} of {len(c['rows'])} survive past the "
                   f"end of a session")
    elif r["catch_why"]:
        out.append(f"CATCH LADDER    {r['catch_why'].replace('cannot judge: ', '')}")

    out += ["",
            "WHAT THIS PAGE CANNOT SAY — the brief for the step that costs money",
            "  1. Is the standing cost earning its tokens, or restating the code?",
            "  2. Which sentences in the docs are waffle? Quote them.",
            "  3. Does each wired hook address a mistake THIS repository makes?",
            ""]
    return "\n".join(out)


def filled_moment(p, key):
    """Does this delivery moment carry anything?

    Public because `hooks/first_look.py` asks the same question in its
    once-per-repository notice. Two implementations of it would let the
    notice and the assessment disagree about one repository, and the
    notice is the one nobody would check."""
    v = p["moments"][key]
    if key == "5_before_action":
        return v["PreToolUse"] > 0 or v["permissions_deny"] > 0
    return bool(v) if isinstance(v, (list, dict)) else v > 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--full", action="store_true",
                    help="also replay defects (minutes, needs the test toolchain)")
    ap.add_argument("--instances", type=int, default=3)
    ap.add_argument("--work", default="")
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    root = os.path.abspath(a.root)
    work = a.work or os.path.join(root, ".assess")
    r = gather(root, a.full, a.instances, work)
    if r is None:
        print("cannot judge: not a git repository, or git is unavailable",
              file=sys.stderr)
        return 2
    print(render(r))
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(r, fh, indent=2, ensure_ascii=False)
        print(f"  written to {a.json}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
