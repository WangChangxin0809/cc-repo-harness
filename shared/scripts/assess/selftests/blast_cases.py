#!/usr/bin/env python3
"""Assessment selftest cases: blast: the false block.

Split out of ``assess/selftest.py`` to keep every file under this
repository's line-count ceiling; see that file for the CLI, exit codes, and
why this selftest exists. Every case here is unchanged from the original --
same name, body, docstring, comments -- and this module's own ``CASES`` list
keeps them in the same order relative to each other that the original single
list held. ``selftest.py`` concatenates every case module's list, so all 192
cases still run, each exactly once.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _support import (
    BLOCKER,
    HERE,
    QUIET,
    _factsheet,
    blast_mod,
    commit,
    git,
    hook_script,
    permitted_mod,
    put,
    repo,
)



# --------------------------------------------------------------------------
# blast: and the false block, which is the whole reason early is not free
# --------------------------------------------------------------------------

def case_nothing_wired_stops_nothing(t):
    repo(t)
    put(t, ".claude/settings.json", "{}")
    r = blast_mod.assess(t, "src/a.py", "scripts/gates/c.py")
    if any(row["stopped"] for row in r["rows"]):
        return "a repository with no hooks was reported as stopping something"
    return ""


def case_a_blanket_refusal_is_a_false_block_not_a_score(t):
    """A hook that says no to everything scores perfectly on every destructive
    probe. It is the worst thing in a repository, and the column that says so
    is the only thing keeping `stopped` honest."""
    repo(t)
    hook_script(t, "hooks/no.py", BLOCKER)
    r = blast_mod.assess(t, "src/a.py", "scripts/gates/c.py")
    if not all(row["stopped"] for row in r["rows"]):
        return "the blanket refusal did not even register as stopping things"
    if not all(row["false_block"] for row in r["rows"]):
        return ("a hook that also refuses every legitimate action was scored as "
                "a clean catch — `stopped` can be gamed by refusing everything")
    return ""


def case_a_targeted_refusal_is_not_a_false_block(t):
    """The other half: a hook that refuses only the destructive thing must not
    be smeared with the same brush."""
    repo(t)
    hook_script(t, "hooks/selective.py",
                "import sys, json\n"
                "d = json.loads(sys.stdin.read() or '{}')\n"
                "cmd = (d.get('tool_input') or {}).get('command', '')\n"
                "if 'push --force origin main' in cmd:\n"
                "    print('no', file=sys.stderr); sys.exit(2)\n"
                "sys.exit(0)\n")
    r = blast_mod.assess(t, "src/a.py", "scripts/gates/c.py")
    push = [row for row in r["rows"] if "force-push" in row["probe"]][0]
    if not push["stopped"]:
        return "a hook refusing exactly the force-push did not register"
    if push["false_block"]:
        return ("a hook that allows `git push origin feature/x` was reported as "
                "a false block")
    return ""


def case_the_second_pass_writes_the_run_back(t):
    """`--from RUN --html PAGE` wrote the page and left RUN as it was.

    So the record said less than the page: the first pass's JSON had three
    rows in dimension 1 and the page five, and anyone holding the two read a
    mismatch. The run is the record. The pass that changes what the page says
    writes it back, and says what it applied."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    commit(t, "feat: x")
    work = tempfile.mkdtemp(prefix="assess-second-pass-")
    try:
        run = os.path.join(work, "run.json")
        out = _factsheet(["--root", t, "--no-full", "--json", run])
        if out.returncode not in (0, 2) or not os.path.exists(run):
            return f"the first pass did not produce a run: {out.stderr[-200:]}"
        page = os.path.join(work, "page.html")
        out = _factsheet(["--from", run, "--html", page])
        if out.returncode not in (0, 2):
            return f"the second pass failed: {out.stderr[-200:]}"
        with open(run, encoding="utf-8") as fh:
            r = json.load(fh)
        if "applied" not in r:
            return ("the second pass wrote the page and left the run as it "
                    "was, so the record says less than the page")
        if r["applied"] != []:
            return f"nothing was applied, but the run says {r['applied']!r}"
        if "dimensions" not in r:
            return "the run written back carries no dimensions"
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return ""


def case_a_page_with_questions_unanswered_says_so_in_its_header(t):
    """The instrument's half of the page can pass for the whole of it.

    A fact sheet taken with nobody answering its briefs is honest row by row
    -- an unanswered brief is an absent row, not a zero -- and dishonest as a
    page, because nothing at the top says the readers never came. The header
    names every question left for a reader, and every dimension that could
    not be judged, so a partial page cannot be handed over as a full one."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    hook_script(t, ".claude/quiet.py", QUIET)
    commit(t, "feat: x, with a hook wired")
    work = tempfile.mkdtemp(prefix="assess-partial-")
    try:
        run = os.path.join(work, "run.json")
        out = _factsheet(["--root", t, "--no-full", "--json", run])
        if out.returncode not in (0, 2):
            return f"the run failed: {out.stderr[-200:]}"
        with open(run, encoding="utf-8") as fh:
            r = json.load(fh)
        if not r.get("permitted"):
            return "fixture: no permitted brief was left, nothing to leave unanswered"
        spec = importlib.util.spec_from_file_location(
            "factsheet_partial", os.path.join(HERE, "factsheet.py"))
        fs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fs)
        head = fs.head_of(r)
        if "permitted" not in (head.get("unanswered") or []):
            return ("the header does not name the permitted brief as "
                    f"unanswered: {head.get('unanswered')!r}")
        text = out.stdout
        if "unanswered" not in text or "permitted" not in text:
            return "the text page's header does not say a question is unanswered"
        page = os.path.join(work, "page.html")
        out = _factsheet(["--from", run, "--html", page])
        with open(page, encoding="utf-8") as fh:
            html_text = fh.read()
        if "unanswered" not in html_text.split("<section>")[0]:
            return "the HTML page's header does not say a question is unanswered"
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return ""


def case_the_silence_probe_is_aimed_at_a_check_that_can_fail(t):
    """`__init__.py` sorts before `test_a.py`, and cannot be silenced.

    The silence probe replaces one check with a body that returns success,
    and `no_silenced_check` refuses that only when the file could fail
    before. So the file the probe is aimed at has to be one that can: an
    empty `__init__.py`, or a `conftest.py`, taken because it sorted first,
    is a probe the guard correctly allows -- and the page reads `nothing
    stops it` about a repository that stops exactly this. Found by the agent
    that rewrote the guard, before it shipped."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "factsheet_target", os.path.join(HERE, "factsheet.py"))
    fs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fs)
    repo(t)
    put(t, "tests/__init__.py", "")
    put(t, "tests/conftest.py", "import pytest\n")
    put(t, "tests/test_a.py", "def test_a():\n    assert 1 == 1\n")
    got = fs.a_check_file({"discipline": {"check_dirs": ["tests"]}}, t)
    if got != os.path.join("tests", "test_a.py"):
        return f"the silence probe was aimed at {got!r}, which cannot fail"
    put(t, "gates/_shared.py", "def helper():\n    return 1\n")
    put(t, "gates/check_b.py", "import sys\nsys.exit(1)\n")
    got = fs.a_check_file({"discipline": {"check_dirs": ["gates"]}}, t)
    if got != os.path.join("gates", "check_b.py"):
        return f"a helper that sorted first was chosen over the gate: {got!r}"
    return ""


def case_a_bash_only_hook_is_not_asked_about_a_write(t):
    """The instrument asks a hook only what Claude Code would ask it.

    blast.py and permitted.py fired every probe at every PreToolUse hook,
    matcher or no matcher. On this repository, whose dispatcher was wired
    `matcher: "Bash"`, that credited it with refusing the credential Write and
    the gate Edit -- 6 of 6 -- when Claude Code would never have run the
    dispatcher for either. catch.py had honoured the matcher since 0032; its
    two siblings had not, and the headline of dimension 1 was the instrument
    talking to itself. The reading for 1.1 on 2026-09-02 caught it, and the
    honest number was 4 of 6.

    The legitimate half is the same firing on purpose, so it gets the same
    rule: a Bash-only blocker cannot be counted as refusing a Write."""
    repo(t)
    put(t, "src/a.py", "x = 1\n")
    put(t, "scripts/gates/c.py", "import sys\nsys.exit(1)\n")
    put(t, ".claude/block.py", BLOCKER)
    put(t, ".claude/settings.json", json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [
            {"type": "command",
             "command": f'python3 "{os.path.join(t, ".claude/block.py")}"'}]}]}}))
    r = blast_mod.assess(t, "src/a.py", "scripts/gates/c.py")
    tool_of = {"commit a credential": "Write", "silence a failing check": "Edit"}
    for row in r["rows"]:
        tool = tool_of.get(row["probe"], "Bash")
        if tool != "Bash" and row["stopped"]:
            return (f"a Bash-only hook was credited with stopping the {tool} "
                    f"probe {row['probe']!r}, which Claude Code never sends it")
        if tool == "Bash" and not row["stopped"]:
            return f"the Bash-only blocker did not stop {row['probe']!r}"
    got, why = permitted_mod.fire(t, {"actions": [
        {"what": "write a note", "tool": "Write", "path": "tmp/n.md",
         "content": "x\n"},
        {"what": "list the tree", "tool": "Bash", "command": "ls"}]})
    if why:
        return why
    blocked = {a["what"]: a["blocked"] for a in got["fired"]}
    if blocked["write a note"]:
        return "a Bash-only hook was counted as refusing a legitimate Write"
    if not blocked["list the tree"]:
        return "the Bash-only blocker was not counted as refusing the Bash action"
    return ""


def case_a_verdict_does_not_move_with_the_checkout(t):
    """The same repository must score the same from any branch.

    It did not. The history-rewrite probe named no branch, so it pushed
    whatever happened to be checked out: the guard fired on `main` and stayed
    quiet on a feature branch, and the difference was briefly read as this
    repository being a rung behind its own scaffold. A verdict that moves with
    the working tree is not a measurement of the repository."""
    repo(t)
    # Faithful to the real guard, and that is the whole case: it falls back to
    # the *current* branch when the command names none, which is exactly how a
    # branch-less probe borrows the checkout's state.
    hook_script(t, "hooks/protect.py",
                "import sys, json, subprocess\n"
                "d = json.loads(sys.stdin.read() or '{}')\n"
                "cmd = (d.get('tool_input') or {}).get('command', '')\n"
                "if 'push' in cmd:\n"
                "    words = cmd.split()\n"
                "    named = words[-1] if words and not words[-1].startswith('-') else ''\n"
                "    cur = subprocess.run(['git', 'branch', '--show-current'],\n"
                "                         capture_output=True, text=True).stdout.strip()\n"
                "    if (named or cur) == 'main':\n"
                "        print('protected', file=sys.stderr); sys.exit(2)\n"
                "sys.exit(0)\n")
    put(t, "README.md", "# x\n")
    commit(t, "init")
    on_default = blast_mod.assess(t, "src/a.py", "scripts/gates/c.py")
    git(["switch", "-q", "-c", "feature/x"], t)
    on_feature = blast_mod.assess(t, "src/a.py", "scripts/gates/c.py")
    for a, b in zip(on_default["rows"], on_feature["rows"]):
        if a["stopped"] != b["stopped"]:
            return (f"{a['probe']!r} scored stopped={a['stopped']} on the "
                    f"default branch and stopped={b['stopped']} on a feature "
                    f"branch — the probe is reading the checkout, not the repo")
    return ""


CASES = [
    ('the second pass writes the run back',
     case_the_second_pass_writes_the_run_back),
    ('a page with questions unanswered says so in its header',
     case_a_page_with_questions_unanswered_says_so_in_its_header),
    ('the silence probe is aimed at a check that can fail',
     case_the_silence_probe_is_aimed_at_a_check_that_can_fail),
    ('a Bash-only hook is not asked about a write',
     case_a_bash_only_hook_is_not_asked_about_a_write),
    ('nothing wired stops nothing',
     case_nothing_wired_stops_nothing),
    ('a blanket refusal is reported as a false block',
     case_a_blanket_refusal_is_a_false_block_not_a_score),
    ('a targeted refusal is not reported as a false block',
     case_a_targeted_refusal_is_not_a_false_block),
    ('the same repository scores the same from any branch',
     case_a_verdict_does_not_move_with_the_checkout),
]
