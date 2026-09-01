#!/usr/bin/env python3
"""Put a defect back into this repository and record when it is first caught.

    python3 assess/catch.py [--root .] [--instances 3] [--json OUT]

Exit codes:
    0 = every instance reached a verdict
    2 = cannot judge (no history, no runnable tests, no clone possible)

## The ladder

The same defect caught at different moments costs different amounts, and for an
agent the curve is not smooth -- there is a cliff:

    L0 before-write   a wired PreToolUse hook refuses the edit. The mistake
                      never exists. This is the only rung that costs nothing.
    L1 same-turn      a wired PostToolUse hook complains. The agent still holds
                      the context that produced it and fixes it for free.
    L2 local-suite    the tests the change touched go red. A few turns, and the
                      session is still warm.
    ------------------ the cliff: the session ends, and the context that
                       produced the defect is gone with it ------------------
    L3 ci             something goes red after the fact. A person has to be
                      recruited and has to re-derive what happened.
    L4 never          nothing went red. The worst case, and the one a count of
                      "does it have tests" cannot see at all.

## Early is only better if it is right

A hook that refuses every edit scores L0 on every defect and is the worst thing
in a repository: it blocks real work, and people learn to switch it off. So
each instance is run twice -- once with the defect, once with the repository's
own fix, which is a change that must be allowed. A rung that fires on both
discriminates nothing, and is reported as a false block rather than a catch.

## What this does not do

It does not judge the *mechanism*. Whatever is wired at each moment is run,
whether that is one of ours, a `permissions.deny` rule, a pre-commit script or
something nobody here has seen. A repository that catches things early by means
we would not have chosen scores exactly as well as one that copied us, which is
the only way this measurement can be honest about repositories it has never
seen.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from ecosystems import find, run, sh  # noqa: E402
from history import candidates, mine  # noqa: E402

LADDER = ("before-write", "same-turn", "local-suite", "ci", "never")
CI_ENTRIES = ("ci.sh", "scripts/ci.sh", "./ci.sh")
HOOK_TIMEOUT = 120
CI_TIMEOUT = 900


# --------------------------------------------------------------------------
# the repository's own hooks, run the way Claude Code runs them
# --------------------------------------------------------------------------

def wired(root, event):
    """Every command wired at `event`, from settings the repository ships.

    `settings.local.json` is read too: it is not committed, so a hook that only
    exists there is not protecting anybody but the person who wrote it -- which
    is worth knowing, and worth reporting separately rather than silently
    counting as the repository's."""
    out = []
    for name in ("settings.json", "settings.local.json"):
        path = os.path.join(root, ".claude", name)
        try:
            with open(path, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except (OSError, ValueError):
            continue
        for group in (cfg.get("hooks") or {}).get(event, []) or []:
            for hook in group.get("hooks") or []:
                if hook.get("type") == "command" and hook.get("command"):
                    out.append({"command": hook["command"],
                                "matcher": group.get("matcher", ""),
                                "local": name.endswith("local.json")})
    return out


def matches(matcher, tool_name):
    """Would Claude Code run this hook for this tool?

    An empty matcher or `*` means every tool. Otherwise it is a regular
    expression, and in practice almost always an alternation of tool names.

    This is not a detail. Firing an `Edit` payload at a hook wired
    `matcher: "Bash"` asks a guard a question it will never be asked in
    reality: it counts a layer as wired that cannot see this kind of defect at
    all, and if such a hook ever *did* block, the ladder would record a catch
    that could not happen. Measured on this repository, whose destructive-
    command guards are Bash-only: the inventory reported `before-write: 2
    hook(s), 0 of 16 caught` when only one of the two could ever have run."""
    if not matcher or matcher in ("*", ".*"):
        return True
    try:
        return re.fullmatch(matcher, tool_name) is not None
    except re.error:
        return tool_name in [p.strip() for p in matcher.split("|")]


def applicable(hooks, tool_name):
    return [h for h in hooks if matches(h.get("matcher", ""), tool_name)]


def fire_ex(root, hooks, payload):
    """(blocked, which command, what it said, [hooks that ran and broke]).

    A hook blocks by exiting 2, or by saying so in JSON on stdout. Both
    spellings are honoured because both are in use, and a probe that knew only
    one would report a working guard as absent.

    The fourth value is the state this probe used to lose. Claude Code treats
    any other non-zero exit as a non-blocking error: the action proceeds. So a
    guard with a syntax error, a missing import, or a bad path is indis-
    tinguishable here from a guard that considered the action and allowed it --
    and from no guard at all. That is the worst of the three, because everybody
    believes they are covered. It is returned separately so the report can say
    which one happened."""
    broke = []
    for h in hooks:
        proc = subprocess.run(
            h["command"], shell=True, cwd=root, input=json.dumps(payload),
            capture_output=True, text=True, timeout=HOOK_TIMEOUT,
            env={**os.environ, "CLAUDE_PROJECT_DIR": root},
        )
        said = (proc.stderr or proc.stdout or "").strip().replace("\n", " ")
        if proc.returncode == 2:
            return True, h, said[:160], broke
        try:
            spoken = json.loads(proc.stdout or "{}")
        except ValueError:
            spoken = {}
        decision = (spoken.get("permissionDecision")
                    or spoken.get("decision") or "")
        if decision in ("deny", "block"):
            return True, h, str(spoken.get("permissionDecisionReason")
                                or spoken.get("reason") or said)[:160], broke
        if proc.returncode not in (0, 2):
            broke.append((h, f"exit {proc.returncode}: {said[:120]}"))
    return False, None, "", broke


def fire(root, hooks, payload):
    """(blocked, which command, what it said) -- see `fire_ex`."""
    blocked, hook, said, _ = fire_ex(root, hooks, payload)
    return blocked, hook, said


def edit_payload(root, event, path, before, after):
    return {
        "session_id": "assess", "transcript_path": "", "cwd": root,
        "hook_event_name": event, "tool_name": "Edit",
        "tool_input": {"file_path": os.path.join(root, path),
                       "old_string": before[:4000], "new_string": after[:4000]},
        "tool_response": {"filePath": os.path.join(root, path),
                          "success": True} if event == "PostToolUse" else None,
    }


# --------------------------------------------------------------------------
# the bench
# --------------------------------------------------------------------------

def git(args, cwd, check=True):
    out = subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                         text=True, timeout=600)
    if check and out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])}: {out.stderr.strip()[:200]}")
    return out


def bench(root, work):
    """A clone, so the repository being assessed is never moved off its HEAD."""
    dst = os.path.join(work, "bench")
    if os.path.isdir(os.path.join(dst, ".git")):
        return dst
    os.makedirs(work, exist_ok=True)
    git(["clone", "-q", "--no-hardlinks", os.path.abspath(root), dst], work)
    return dst


def park(repo, sha):
    # --force, because parking is also how an instance is undone: the tree
    # carries the injected defect at that point.
    git(["checkout", "-q", "--force", "--detach", sha], repo)
    git(["clean", "-qfd"], repo)


def blob(repo, sha, path):
    out = git(["show", f"{sha}:{path}"], repo, check=False)
    return out.stdout if out.returncode == 0 else ""


def inject(repo, row):
    """Put the source half back to its pre-fix state; leave the tests fixed."""
    at_parent = set(git(["ls-tree", "-r", "--name-only", row["sha"] + "^"],
                        repo).stdout.split())
    for p in row["source"]:
        if p in at_parent:
            git(["checkout", row["sha"] + "^", "--", p], repo)
        else:
            # Added by the fix: reverting it means removing it. Missing this
            # case leaves the fix in place, and the instance then scores as
            # `never` when the bug in question is in this function.
            full = os.path.join(repo, p)
            if os.path.exists(full):
                os.remove(full)


def ci_command(repo):
    for entry in CI_ENTRIES:
        if os.path.exists(os.path.join(repo, entry.lstrip("./"))):
            return ["bash", entry.lstrip("./")]
    mk = os.path.join(repo, "Makefile")
    if os.path.exists(mk):
        try:
            with open(mk, encoding="utf-8", errors="replace") as fh:
                if "\nci:" in "\n" + fh.read():
                    return ["make", "ci"]
        except OSError:
            pass
    return None


def ci_seconds(root):
    """Median seconds this repository's own CI takes, from its own run history.

    Deliberately *not* the wall clock of running its CI command on this machine.
    The number the ladder is about is how long a person waits before they are
    told, and that includes the queue and the runner -- neither of which exists
    here. Our machine's timing would be a smaller number measuring a different
    thing, which is worse than no number.

    So when `gh` is absent, unauthenticated, or the repository has no runs, this
    returns None and the row says the rung was reached without saying how long
    it took. An abstention is a result."""
    out = sh(["gh", "run", "list", "--limit", "20", "--json",
              "status,conclusion,startedAt,updatedAt"], root, 60)
    if out.returncode != 0:
        return None
    try:
        runs = json.loads(out.stdout or "[]")
    except ValueError:
        return None
    secs = []
    for r in runs:
        if r.get("status") != "completed" or r.get("conclusion") not in (
                "success", "failure"):
            continue
        try:
            a = datetime.datetime.fromisoformat(
                (r.get("startedAt") or "").replace("Z", "+00:00"))
            b = datetime.datetime.fromisoformat(
                (r.get("updatedAt") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        d = (b - a).total_seconds()
        if d > 0:
            secs.append(d)
    if not secs:
        return None
    secs.sort()
    return secs[len(secs) // 2]


# --------------------------------------------------------------------------
# one instance, down the ladder
# --------------------------------------------------------------------------

def rung(repo, row, pre, post, cmd, ci, ci_secs=None):
    """(rung, detail, hook, seconds) for the first rung that fires.

    Rungs are asked cheapest first and the walk stops at the first red, because
    the measurement is *when it is first caught* -- a defect that a PreToolUse
    hook refuses is not also a CI failure, it is a mistake that never happened.

    The fourth value is how long that moment costs, and it is measured
    differently at each rung because the thing being waited on is different:

    * L0/L1 -- the wall clock of the hooks that ran, which is what an agent
      actually waits mid-turn.
    * L2 -- the wall clock of the scoped suite on this machine, which is where
      it would also run for the person who wrote the defect.
    * L3 -- **not** the wall clock of running CI here. See `ci_seconds`: the
      number is taken from the repository's own run history, and is None when
      that history cannot be read. A local timing would be a smaller number
      measuring a different thing.
    * L4 -- there is no number, because nothing ever happens.

    The seconds are what make the cliff between L2 and L3 legible. A rung name
    says the order; only the seconds say that the order spans four orders of
    magnitude."""
    t0 = time.monotonic()
    for p in row["source"]:
        before, after = blob(repo, row["sha"] + "^", p), blob(repo, row["sha"], p)
        blocked, h, said = fire(repo, pre,
                                edit_payload(repo, "PreToolUse", p, after, before))
        if blocked:
            return ("before-write", f"{h['command'][:60]} — {said}", h,
                    time.monotonic() - t0)

    inject(repo, row)

    t1 = time.monotonic()
    for p in row["source"]:
        blocked, h, said = fire(repo, post, edit_payload(
            repo, "PostToolUse", p, "", blob(repo, row["sha"] + "^", p)))
        if blocked:
            return ("same-turn", f"{h['command'][:60]} — {said}", h,
                    time.monotonic() - t1)

    t2 = time.monotonic()
    verdict, detail = run(repo, cmd)
    suite = time.monotonic() - t2
    if verdict == "red":
        return "local-suite", detail, None, suite
    if verdict == "could-not-run":
        return None, f"the tests could not run: {detail}", None, None

    if ci:
        out = sh(ci, repo, CI_TIMEOUT)
        if out.returncode not in (0,):
            tail = (out.stdout or out.stderr).strip().splitlines()
            return ("ci", (tail[-1][:140] if tail else f"exit {out.returncode}"),
                    None, ci_secs)

    return "never", "nothing went red", None, None


def false_block(repo, row, pre, post):
    """Do the same rungs fire on the repository's *own fix*?

    They must not. A rung that refuses the defect and the fix alike has not
    discriminated anything, and reporting it as a catch would reward a hook
    that only ever says no."""
    for p in row["source"]:
        before, after = blob(repo, row["sha"] + "^", p), blob(repo, row["sha"], p)
        blocked, h, said = fire(repo, pre,
                                edit_payload(repo, "PreToolUse", p, before, after))
        if blocked:
            return f"before-write: {h['command'][:60]} — {said}"
        blocked, h, said = fire(repo, post,
                                edit_payload(repo, "PostToolUse", p, before, after))
        if blocked:
            return f"same-turn: {h['command'][:60]} — {said}"
    return ""


def assess(root, instances, work, command=None):
    """`command` is how this repository's tests run, when somebody has read it.

    The ecosystem table is a fast path that knows a handful of conventions --
    a `tests/` directory plus a packaging marker, a `package.json`, a
    `Cargo.toml`. A repository it has never seen will often match none of
    them, and the honest measurement of how often is: of five real Python
    repositories cloned to test the mutation work, the table produced a green
    suite for **one**. This repository is another miss; its suites are
    `selftest.py` scripts, so dimension 2 abstained on its own author.

    Unit tests may also simply not exist, and that is a finding rather than a
    failure. What must not happen is abstaining because a table did not
    recognise a convention, while the repository has a perfectly good suite an
    agent could have found by reading its CI file in one call."""
    found = mine(root)
    if found is None or found["shallow"]:
        return None, ("cannot judge: no history to mine — a shallow clone has "
                      "no defects in it")
    rows = candidates(found, instances)
    if not rows:
        return None, ("cannot judge: this repository's history offers no small "
                      "fix-with-test commit to replay")

    repo = bench(root, work)
    eco, cmd = find(repo)
    if command:
        cmd = command if isinstance(command, list) else command.split()
        eco = eco or type("Given", (), {
            "name": "given", "tool": None,
            "install": staticmethod(lambda p: []),
            "scope": staticmethod(lambda c, t: None)})()
    if cmd is None:
        return None, ("cannot judge: no runnable test command"
                      + (f" ({eco.name} needs {eco.tool}, which is not on "
                         f"PATH)" if eco and eco.tool else "")
                      + " — pass --test-command if this repository has a "
                        "suite the table does not recognise")
    for step in eco.install(repo):
        sh(step, repo, 900)
    # Only the hooks that would actually run for the payload the ladder
    # sends. The ladder edits files, so a Bash-only guard is not a layer that
    # failed to catch this -- it is a layer that was never asked.
    pre = applicable(wired(root, "PreToolUse"), "Edit")
    post = applicable(wired(root, "PostToolUse"), "Edit")
    ci = ci_command(repo)
    # Asked of the subject, not the clone: the clone has no remote history.
    ci_secs = ci_seconds(root)

    out = []
    for row in rows:
        park(repo, row["sha"])
        tests = [p for p in row["tests"] if os.path.exists(os.path.join(repo, p))]
        scoped = eco.scope(cmd, tests) or cmd
        base, detail = run(repo, scoped)
        if base != "green":
            out.append({"sha": row["sha"][:10], "subject": row["subject"],
                        "rung": None, "detail": f"unusable — at the fix the "
                        f"tests are {base}: {detail}"})
            continue
        wrong = false_block(repo, row, pre, post)
        park(repo, row["sha"])
        got, detail, _h, secs = rung(repo, row, pre, post, scoped, ci,
                                     ci_secs)
        park(repo, row["sha"])
        out.append({"sha": row["sha"][:10], "subject": row["subject"],
                    "rung": got, "detail": detail, "false_block": wrong,
                    "seconds": secs, "tests": tests,
                    "source": row["source"]})
    return {"ecosystem": eco.name, "command": " ".join(cmd),
            "ci": " ".join(ci) if ci else "", "ci_seconds": ci_secs,
            "hooks": {
                "PreToolUse": len(pre), "PostToolUse": len(post)},
            "rows": out}, ""


def render(r):
    counts = {k: 0 for k in LADDER}
    unusable = 0
    lines = [""]
    for row in r["rows"]:
        if row["rung"] is None:
            unusable += 1
            lines.append(f"  --  {row['sha']}  {row['subject'][:56]}")
            lines.append(f"      {row['detail'][:110]}")
            continue
        counts[row["rung"]] += 1
        mark = "!!" if row["rung"] in ("ci", "never") else "OK"
        lines.append(f"  {mark}  {row['sha']}  {row['rung']:<13} "
                     f"{row['subject'][:48]}")
        if row["rung"] in ("before-write", "same-turn"):
            lines.append(f"      {row['detail'][:110]}")
        if row.get("false_block"):
            lines.append(f"      !! FALSE BLOCK — it refuses the fix too: "
                         f"{row['false_block'][:80]}")
    lines += [
        "",
        "  ladder   " + "  ".join(f"{k}:{counts[k]}" for k in LADDER)
        + (f"  unusable:{unusable}" if unusable else ""),
        f"  suite    {r['command']}   ci: {r['ci'] or 'none found'}",
        f"  hooks    PreToolUse:{r['hooks']['PreToolUse']}  "
        f"PostToolUse:{r['hooks']['PostToolUse']}",
        "",
    ]
    late = counts["ci"] + counts["never"]
    if late:
        lines.append(f"  {late} of {len(r['rows'])} defects survive past the "
                     f"end of a session, where the context that produced them "
                     f"is gone.")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--instances", type=int, default=3)
    ap.add_argument("--work", default="")
    ap.add_argument("--test-command", default="",
                    help="how to run this repository's tests, when the "
                         "ecosystem table does not recognise it. The table is "
                         "a fast path, not the only one.")
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    work = a.work or tempfile.mkdtemp(prefix="assess-catch-")
    try:
        r, why = assess(os.path.abspath(a.root), a.instances, work,
                        a.test_command or None)
        if r is None:
            print(why, file=sys.stderr)
            return 2
        print(render(r))
        if a.json:
            with open(a.json, "w") as fh:
                json.dump(r, fh, indent=2, ensure_ascii=False)
        return 0
    finally:
        if not a.work:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
