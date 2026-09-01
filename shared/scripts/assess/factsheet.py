#!/usr/bin/env python3
"""One page about this repository, with nothing in it that needed an opinion.

    python3 assess/factsheet.py [--root .] [--no-full] [--json OUT]

    (default)  probe + blast + drift   -- seconds, no toolchain, no network
    --no-full  skip the defect replay -- the replay is on by default and
               costs minutes and the repo's test toolchain; without it
               dimension 2 abstains
    --mutate N change N covered lines and see whether the tests notice --
               OFF by default, because it runs the suite once per mutant
    --html P   a self-contained page for a person to read once and act on

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
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import blast as blast_mod  # noqa: E402
import catch as catch_mod  # noqa: E402
import cover as cover_mod  # noqa: E402
import dimensions as dim_mod  # noqa: E402
import judge as judge_mod  # noqa: E402
import run_mutants as mutants_mod  # noqa: E402
import report as report_mod  # noqa: E402
import truth as truth_mod  # noqa: E402
import value as value_mod  # noqa: E402
from history import commits, mine  # noqa: E402


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
    out = subprocess.run(["git", "-c", "core.quotePath=false", "ls-files"],
                         cwd=root, capture_output=True,
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


def gather(root, full, instances, work, command=None, mutate=0):
    probe_mod = load("probe_repo", os.path.join(PARENT, "probe_repo.py"))
    probe = probe_mod.probe(root) if probe_mod else None
    if probe is None:
        return None

    r = {"probe": probe, "blast": None, "catch": None, "catch_why": "",
         "drift": drift_pairs(root), "defects": None,
         "mutants": None, "mutants_why": "", "mutant_brief": None,
         "cover": None, "cover_why": ""}

    if os.path.isdir(os.path.join(root, ".claude")):
        r["blast"] = blast_mod.assess(root, a_source_file(root),
                                      a_check_file(probe, root))

    r["log"] = commits(root)
    r["truth"] = truth_mod.assess(root)
    r["value"] = value_mod.assess(
        root, value_mod.guards_from_blast(r.get("blast")))
    found = mine(root)
    if found is not None:
        r["defects"] = {"replayable": len(
            [x for x in found["revert"] + found["fix_test"] if x["small"]]),
            "fix_no_test": len(found["fix_no_test"]),
            "has_test_files": found["has_test_files"],
            "shallow": found["shallow"]}

    if full:
        r["catch"], r["catch_why"] = catch_mod.assess(
            root, instances, work, command)

        # What the ladder below cannot speak about. A line no test executes
        # cannot be caught at the suite rung, ever, for any defect -- that is
        # a guarantee rather than a correlation, and it is the only direction
        # in which coverage means anything at all.
        cwork = os.path.join(work, "cover")
        cbench = catch_mod.bench(root, cwork)
        catch_mod.park(cbench, "HEAD")
        r["cover"], r["cover_why"] = cover_mod.assess(cbench, command, cwork)

    # Second injection, and the only one that is opt-in. The replay asks how
    # late a defect that actually happened here is caught; mutation asks
    # whether a change to a line the tests *already execute* is noticed at
    # all. They can disagree, and when they do the disagreement is the
    # finding: a repository can catch its own history early and still have a
    # suite that runs code without asserting anything about it.
    if mutate:
        r["mutants"], r["mutants_why"] = mutants_mod.assess(
            root, mutate, work=os.path.join(work, "mutate"), command=command)
        if r["mutants"]:
            got, _why = judge_mod.brief(r["mutants"], root)
            r["mutant_brief"] = got
    return r


# --------------------------------------------------------------------------

CANNOT_SAY = [
    "Open the repository and list where its tests actually live, including "
    "any under frontend/, backend/ or packages/. Does that match the row "
    "'where the verdict is written'? If it missed a suite, say so — the "
    "percentage under it is then wrong, not merely low.",
    "Is the standing cost earning its tokens, or restating the code?",
    "Which sentences in the docs are waffle? Quote them.",
    "Does each wired hook address a mistake THIS repository makes?",
    "Reading the hooks and settings: is anything you would normally need "
    "refused? Quote the refusal.",
]


def repo_name(root):
    """What this repository is called, not what the directory it was cloned
    into is called. A page headed `target` names the reader's scratch folder."""
    out = subprocess.run(["git", "remote", "get-url", "origin"], cwd=root,
                         capture_output=True, text=True, timeout=30)
    url = out.stdout.strip()
    if out.returncode == 0 and url:
        name = url.rstrip("/").rsplit("/", 1)[-1]
        if name.endswith(".git"):
            name = name[:-4]
        if name:
            return name
    return os.path.basename(root.rstrip("/")) or root


def head_of(r):
    p = r["probe"]
    return {"name": repo_name(p["root"]),
            "root": p["root"],
            "tracked": p["tracked_files"], "source": p["source_files"],
            "tier": p["tier"]}


def dimensions_of(r, memory=None, judged=None):
    """`memory` is `memory.compare()`'s output, when somebody spent the two
    agents dimension 4's navigation half needs. Without it that half abstains;
    the truth half in `r["truth"]` costs nothing and is always there."""
    return dim_mod.assess(r["root"], r["probe"], r["blast"], r["catch"],
                          r["catch_why"], r["defects"], r.get("log"),
                          catch_mod.LADDER, memory, r.get("truth"),
                          r.get("value"), r.get("mutants"),
                          r.get("mutants_why", ""), judged,
                          r.get("cover"), r.get("cover_why", ""))


def render_flat(r):
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
    # Default on. The assessment's most-used row -- when a defect is first
    # caught -- is the one this pays for, and a flag nobody remembers to pass
    # meant the page's headline dimension abstained almost every time it was
    # run. The cost is announced before it is spent instead.
    ap.add_argument("--no-full", dest="full", action="store_false",
                    default=True,
                    help="skip the defect replay (dimension 2 then abstains)")
    ap.add_argument("--instances", type=int, default=3)
    ap.add_argument("--test-command", default="",
                    help="how this repository's tests run. The built-in table "
                         "recognises a handful of conventions and misses most "
                         "repositories that do not follow one — including this "
                         "one. An agent that has read the repo can say.")
    # Off by default, and the asymmetry with --full is deliberate. The replay
    # runs the suite once per defect over three defects; mutation runs it once
    # per mutant, and the number of mutants is chosen by the caller. It is the
    # one thing on this page whose cost the page cannot bound on its own, so it
    # is the one thing the caller has to ask for.
    ap.add_argument("--mutate", nargs="?", type=int, const=30, default=0,
                    metavar="N",
                    help="change N covered lines and see whether the tests "
                         "notice (default 30 when given without a number). "
                         "Runs the suite once per mutant — minutes to hours.")
    ap.add_argument("--mutant-answers", default="",
                    help="JSON from the agent that read `mutant_brief` and "
                         "said which uncaught changes were worth catching. "
                         "Without it those mutants are reported pending, not "
                         "parked at `never`")
    ap.add_argument("--work", default="")
    ap.add_argument("--json", default="")
    ap.add_argument("--html", default="",
                    help="also write a self-contained page for a person")
    ap.add_argument("--memory", default="",
                    help="JSON from `memory.py --score`; without it "
                         "dimension 4 abstains rather than scoring zero")
    ap.add_argument("--flat", action="store_true",
                    help="the ungrouped page: the same numbers, unsorted")
    a = ap.parse_args()

    root = os.path.abspath(a.root)
    # Outside the subject repository, and removed afterwards. `catch.py` gets
    # this right in its own `main`; defaulting to `<root>/.assess` here undid
    # it, and left 2.6 MB of bench clone untracked in a repository this tool
    # promises only to read. An instrument that litters its subject has changed
    # the thing it was measuring.
    work = a.work or tempfile.mkdtemp(prefix="assess-")
    try:
        return _run(a, root, work)
    finally:
        if not a.work:
            shutil.rmtree(work, ignore_errors=True)


def preflight(root, a, work):
    """What is about to be run, printed before it runs.

    The replay executes a stranger's test suite and their CI entry point on this
    machine. That is a reasonable thing to do to a repository you asked to be
    assessed, and an unreasonable thing to do without saying so first -- so it
    is said first, with the command named, rather than explained afterwards in
    a footnote nobody reads."""
    eco, cmd = catch_mod.find(root)
    if a.test_command:
        cmd = a.test_command.split()
    ci = catch_mod.ci_command(root)
    lines = [f"  assessing {root}",
             f"  replaying up to {a.instances} of this repository's own "
             f"defects, in a clone under {work}"]
    lines.append("  and once more, instrumented, to record which lines, "
                 "branches and conditions it exercises at all")
    lines.append("  it will run: " + (" ".join(cmd) if cmd else
                                      "nothing — no runnable test command "
                                      "found. Pass --test-command, or "
                                      "dimension 2 will abstain"))
    if ci:
        lines.append("  and its CI entry point: " + " ".join(ci))
    if a.mutate:
        lines.append(f"  then changing up to {a.mutate} line(s) the tests "
                     f"already execute, one at a time, and running that "
                     f"command again for each — so up to {a.mutate + 3} more "
                     f"runs of it")
    lines.append("  --no-full skips all of it"
                 + ("" if a.mutate else "; --mutate adds the second injection"))
    print("\n".join(lines) + "\n", file=sys.stderr)


def _run(a, root, work):
    if a.full or a.mutate:
        preflight(root, a, work)
    r = gather(root, a.full, a.instances, work,
               a.test_command or None, a.mutate)
    if r is None:
        print("cannot judge: not a git repository, or git is unavailable",
              file=sys.stderr)
        return 2
    r["root"] = root

    if a.flat:
        print(render_flat(r))
    else:
        memory = None
        if a.memory:
            with open(a.memory, encoding="utf-8") as fh:
                memory = json.load(fh)
        judged = None
        if a.mutant_answers and r.get("mutants"):
            with open(a.mutant_answers, encoding="utf-8") as fh:
                judged = judge_mod.grade(r["mutants"], json.load(fh))
            r["mutants_judged"] = judged
        head, dims = head_of(r), dimensions_of(r, memory, judged)
        print(report_mod.text(head, dims, CANNOT_SAY))
        if a.html:
            where = report_mod.write_html(a.html, head, dims, CANNOT_SAY)
            print(f"  page written to {where}\n")
        r["dimensions"] = dims
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(r, fh, indent=2, ensure_ascii=False)
        print(f"  written to {a.json}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
