#!/usr/bin/env python3
"""Run a repository's guards, and any candidate, over every tool call its
transcripts ever made.

    python3 wiki/replay.py --root REPO [--transcripts DIR]
                           [--candidate GUARD.py ...] [--expect commands.json]
                           [--json OUT]
    python3 wiki/replay.py --selftest

    0 = a table was produced    2 = cannot judge (no guards, no transcripts)

## The held-out set a single repository does have

A skill changes what an agent does, and proving that better needs a held-out
set of like tasks a repository cannot supply. A guard changes what can
*happen*, and its held-out set is free: every tool call the transcripts
recorded, thousands of them, which a candidate guard must refuse where the
pattern occurred and nowhere else.

So for each guard, this prints how many historical calls it fires on, how
many of those were already refused at the time, and -- the column that
matters for a candidate -- the ones it would refuse *now* that nobody
refused *then*, listed. The candidate is right when that list is the
pattern's own instances and nothing else. Whether it is, is a reading, and
this script does not make it: it prints the list.

`--expect` takes a JSON list of command substrings, one per recorded
instance of the pattern, and reports which the candidate missed. That is the
red half; the listed new fires are the green half's near misses.

## Redaction

Every listed call goes through the same `redact` as extract.py. The table is
meant to be pasted into a pull request.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _common import (JUDGED_TOOLS, calls, is_refusal,  # noqa: E402
                     summarise_input, transcript_dir, transcripts_in)


def load_guard(path):
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location("guard_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not callable(getattr(mod, "check", None)):
        raise ValueError(f"{path} has no check()")
    return name, mod


def load_guards(root, candidates, guards_dir=None):
    guards = []
    gdir = guards_dir or os.path.join(root, "scripts", "guards")
    if os.path.isdir(gdir):
        sys.path.insert(0, gdir)   # guards import their `_shell` sibling
        for n in sorted(os.listdir(gdir)):
            if n.endswith(".py") and not n.startswith("_") and n not in (
                    "dispatch.py", "selftest.py"):
                guards.append(load_guard(os.path.join(gdir, n)))
    for c in candidates:
        name, mod = load_guard(c)
        guards.append((name + " (candidate)", mod))
    return guards


def replay(root, files, guards, expect=None):
    rows = {name: {"fired": 0, "refused_then": 0, "new": []} for name, _ in guards}
    seen = 0
    hits = {e: 0 for e in (expect or [])}
    for f in files:
        for rec in calls(f):
            if rec["kind"] != "call":
                continue
            use = rec["use"]
            name, inp = use.get("name"), use.get("input") or {}
            if name not in JUDGED_TOOLS:
                continue
            seen += 1
            was_refused = bool(rec["result"] and is_refusal(rec["result"]))
            for gname, mod in guards:
                try:
                    reason = mod.check(name, inp)
                except Exception as exc:  # a crashing guard fails open at runtime
                    reason = None
                    rows[gname].setdefault("crashed", 0)
                    rows[gname]["crashed"] += 1
                    rows[gname].setdefault("crash", str(exc)[:120])
                if not reason:
                    continue
                r = rows[gname]
                r["fired"] += 1
                if was_refused:
                    r["refused_then"] += 1
                else:
                    if len(r["new"]) < 40:
                        r["new"].append({
                            "session": os.path.basename(f),
                            "at": rec["entry"].get("timestamp"),
                            "tool": name,
                            "input": summarise_input(name, inp, root)})
                    r.setdefault("new_total", 0)
                    r["new_total"] += 1
                for e in hits:
                    if name == "Bash" and e in inp.get("command", ""):
                        hits[e] += 1
    return {"root": os.path.abspath(root), "calls": seen, "guards": rows,
            "expect": ({"hit": {e: n for e, n in hits.items() if n},
                        "missed": [e for e, n in hits.items() if not n]}
                       if expect else None)}


def table(rep):
    out = [f"{rep['calls']} judged tool calls replayed",
           f"{'guard':<36} {'fired':>6} {'refused then':>13} {'new':>6}"]
    for g, r in rep["guards"].items():
        new = r.get("new_total", len(r["new"]))
        out.append(f"{g:<36} {r['fired']:>6} {r['refused_then']:>13} {new:>6}"
                   + (f"   crashed {r['crashed']}x: {r['crash']}" if r.get("crashed") else ""))
        for n in r["new"]:
            what = n["input"].get("command") or n["input"].get("file_path") or ""
            out.append(f"    {n['at'] or '':<22} {n['tool']:<6} {what[:100]}")
    if rep["expect"] is not None:
        out.append("")
        for e, n in rep["expect"]["hit"].items():
            out.append(f"expected, refused {n}x: {e}")
        for e in rep["expect"]["missed"]:
            out.append(f"expected, MISSED:     {e}")
    return "\n".join(out)


# --- selftest ----------------------------------------------------------------

GOOD_GUARD = '''
def check(tool_name, tool_input):
    if tool_name != "Bash":
        return None
    c = tool_input.get("command", "")
    if "git push" in c and "|" in c:
        return "Blocked: push piped."
    return None
CASES = []
'''
WRONG_GUARD = '''
def check(tool_name, tool_input):
    if tool_name == "Bash" and "status" in tool_input.get("command", ""):
        return "Blocked: status."
    return None
CASES = []
'''


def selftest(verbose=False):
    failures = []

    def expect(cond, what):
        (failures if not cond else []).append(what)
        if verbose:
            print(("ok   " if cond else "FAIL ") + what)

    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "repo")
        os.makedirs(os.path.join(root, "scripts", "guards"))
        with open(os.path.join(root, "scripts", "guards", "no_piped_push.py"), "w") as fh:
            fh.write(GOOD_GUARD)
        cand = os.path.join(tmp, "no_status.py")
        with open(cand, "w") as fh:
            fh.write(WRONG_GUARD)
        d = os.path.join(tmp, "t")
        os.makedirs(d)

        def use(i, cmd):
            return {"type": "assistant", "timestamp": f"2026-09-01T10:0{i}:00Z",
                    "message": {"role": "assistant", "content": [
                        {"type": "tool_use", "id": f"t{i}", "name": "Bash",
                         "input": {"command": cmd}}]}}

        def result(i, text, err=False):
            return {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": f"t{i}",
                 "content": text, "is_error": err}]}}
        lines = [use(1, "git push origin main | tail -1"),
                 result(1, "<tool_use_error>Blocked: push piped.", err=True),
                 use(2, "git status"), result(2, "clean"),
                 use(3, "git push origin main | cat"), result(3, "ok"),
                 use(4, "rm -rf build"), result(4, "")]
        with open(os.path.join(d, "s.jsonl"), "w") as fh:
            for o in lines:
                fh.write(json.dumps(o) + "\n")

        guards = load_guards(root, [cand])
        rep = replay(root, transcripts_in(d), guards,
                     expect=["git push origin main | tail"])
        g = rep["guards"]["no_piped_push"]
        c = rep["guards"]["no_status (candidate)"]
        expect(rep["calls"] == 4, "every Bash call was replayed")
        expect(g["fired"] == 2 and g["refused_then"] == 1 and len(g["new"]) == 1
               and "| cat" in g["new"][0]["input"]["command"],
               "the shipped guard's one new fire is the piped push nobody refused")
        expect(c["fired"] == 1 and c["new"][0]["input"]["command"] == "git status",
               "the wrong candidate's new fire is the legitimate command it would break")
        expect(rep["expect"]["hit"] == {"git push origin main | tail": 1}
               and rep["expect"]["missed"] == [],
               "the expected instance is reported refused")
        rep2 = replay(root, transcripts_in(d), guards, expect=["git stash"])
        expect(rep2["expect"]["missed"] == ["git stash"],
               "an expected instance nothing refuses is reported missed")
        t = table(rep)
        expect("git status" in t and "MISSED" not in t, "the table says it")
    for f in failures:
        print("FAIL " + f, file=sys.stderr)
    return 1 if failures else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--transcripts")
    ap.add_argument("--guards", help="the guards directory, when it is not "
                    "scripts/guards (this plugin keeps its own under shared/)")
    ap.add_argument("--candidate", action="append", default=[],
                    help="a guard file not yet in the tree; may repeat")
    ap.add_argument("--expect", help="JSON list of command substrings that "
                    "must be refused")
    ap.add_argument("--json", help="write the full report here")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest(a.verbose)

    root = os.path.abspath(a.root)
    try:
        guards = load_guards(root, a.candidate, a.guards)
    except Exception as exc:
        print(f"cannot judge: a guard did not load: {exc}", file=sys.stderr)
        return 2
    if not guards:
        print(f"cannot judge: no guards under {root}/scripts/guards and no "
              "--candidate", file=sys.stderr)
        return 2
    d = a.transcripts or transcript_dir(root)
    files = transcripts_in(d) if d else []
    if not files:
        print(f"cannot judge: no transcripts for {root}", file=sys.stderr)
        return 2
    expect = None
    if a.expect:
        with open(a.expect, encoding="utf-8") as fh:
            expect = json.load(fh)
    rep = replay(root, files, guards, expect)
    print(table(rep))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
