#!/usr/bin/env python3
"""Prove the assessment can still tell a good repository from a bad one.

    python3 assess/selftest.py [--verbose]

    0 = every case held    1 = a case failed    2 = cannot run

## Why an assessment needs this more than a gate does

A gate that stops working is loud: the thing it guarded breaks. An assessment
that stops working is silent and worse than silent, because it keeps printing
numbers. A probe that has quietly gone blind reports a repository as safe, and
the report is indistinguishable from the report on a repository that is safe.

So every case here builds a repository with a known answer and insists the
probe finds it. Half of them build a repository that must score *badly*: a
measurement that cannot go down has not measured anything, and two of the
defects below were live in this tree when these cases were written --
`probe_repo.py` reported this repository's own gates as absent, and reported an
always-on skill cost of zero while an installed plugin was spending about eight
hundred tokens a turn. Both are cases here now.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import blast as blast_mod          # noqa: E402
import catch as catch_mod          # noqa: E402
import dimensions as dim_mod       # noqa: E402
import history as history_mod      # noqa: E402


def git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                          text=True, timeout=120)


def repo(root):
    """A git repository with an identity, so committing works anywhere."""
    git(["init", "-q", "-b", "main"], root)
    git(["config", "user.email", "selftest@example.invalid"], root)
    git(["config", "user.name", "assess selftest"], root)
    return root


def put(root, rel, body):
    full = os.path.join(root, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(body)
    return full


def commit(root, message):
    git(["add", "-A"], root)
    git(["commit", "-q", "-m", message], root)
    return git(["rev-parse", "HEAD"], root).stdout.strip()


def hook_script(root, rel, body):
    """A PreToolUse hook, and the settings that wire it."""
    put(root, rel, body)
    put(root, ".claude/settings.json", json.dumps({
        "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
            {"type": "command",
             "command": f'python3 "{os.path.join(root, rel)}"'}]}]}}))


BLOCKER = ("import sys, json\n"
           "sys.stdin.read()\n"
           "print('no', file=sys.stderr)\n"
           "sys.exit(2)\n")
QUIET = "import sys\nsys.stdin.read()\nsys.exit(0)\n"


# --------------------------------------------------------------------------
# probe_repo: the two defects it shipped with
# --------------------------------------------------------------------------

def load_probe():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "probe_repo", os.path.join(PARENT, "probe_repo.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def case_checks_are_found_outside_scripts(t):
    """Gates live wherever the repository decided, not where we would have put
    them. This tree keeps its own under `shared/scripts/`, and the probe whose
    job is to find them reported zero."""
    repo(t)
    put(t, "tools/gates/check_thing.py", "def main():\n    return 0\n")
    put(t, "tools/guards/no_thing.py", "def main():\n    return 0\n")
    put(t, "README.md", "# x\n")
    commit(t, "init")
    r = load_probe().probe(t)
    if r["discipline"]["gates"] != 1 or r["discipline"]["guards"] != 1:
        return (f"gates/guards under tools/ were reported as "
                f"{r['discipline']['gates']}/{r['discipline']['guards']}, "
                f"not 1/1 — the probe is looking in one hard-coded place")
    return ""


def case_machinery_is_not_counted_as_checks(t):
    """Three guards plus a dispatcher plus a selftest is three guards.

    The two files that run the checks are not checks, and counting them added
    exactly two to every repository this scaffolder has ever touched -- an
    error that survives precisely because it is consistent, and that shows up
    in the one number `first_look.py` prints unasked.

    And a selftest is a file. `find_check_dirs` looks for a directory called
    `selftests/`, which is where this harness would put them and where almost
    nobody does; every repository writing `guards/selftest.py` -- this one
    included -- was reported as having none at all.
    """
    repo(t)
    for name in ("no_a.py", "no_b.py", "no_c.py"):
        put(t, f"scripts/guards/{name}", "def check(n, i):\n    return None\n")
    put(t, "scripts/guards/dispatch.py", "x = 1\n")
    put(t, "scripts/guards/selftest.py", "x = 1\n")
    put(t, "scripts/guards/_helper.py", "x = 1\n")
    put(t, "scripts/guards/README.md", "# not a guard\n")
    put(t, "README.md", "# x\n")
    commit(t, "init")
    d = load_probe().probe(t)["discipline"]
    if d["guards"] != 3:
        return (f"three guards, a dispatcher, a selftest, a private helper and "
                f"a README were counted as {d['guards']} guards")
    if d["selftests"] != 1:
        return (f"scripts/guards/selftest.py was counted as {d['selftests']} "
                f"selftest(s) — a selftest is a file, not a directory")
    return ""


def case_vendored_checks_are_not_this_repos(t):
    """A dependency's discipline is not the repository's."""
    repo(t)
    put(t, "node_modules/somelib/gates/check_theirs.py", "x = 1\n")
    put(t, "README.md", "# x\n")
    commit(t, "init")
    r = load_probe().probe(t)
    if r["discipline"]["gates"]:
        return (f"counted {r['discipline']['gates']} gate(s) from node_modules "
                f"as this repository's")
    return ""


def case_plugin_skill_cost_is_counted(t):
    """The standing per-turn cost includes skills an installed plugin ships.

    Counting only `.claude/skills/` reported ~0 tokens a turn for a repository
    paying about eight hundred, which is the one number this probe exists for."""
    repo(t)
    put(t, "README.md", "# x\n")
    commit(t, "init")
    plug = os.path.join(t, "fake-plugin")
    put(plug, "skills/a-skill/SKILL.md",
        "---\nname: a-skill\ndescription: " + ("word " * 100) + "\n---\n\nbody\n")
    old = os.environ.get("CLAUDE_PLUGIN_ROOT")
    os.environ["CLAUDE_PLUGIN_ROOT"] = plug
    try:
        r = load_probe().probe(t)
    finally:
        if old is None:
            os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
        else:
            os.environ["CLAUDE_PLUGIN_ROOT"] = old
    if r["skill_tokens_by_origin"]["plugin"] < 100:
        return (f"an installed plugin's 100-word skill description scored "
                f"{r['skill_tokens_by_origin']['plugin']} tokens — the probe is "
                f"blind to the plugin's own standing cost")
    return ""


# --------------------------------------------------------------------------
# history: what counts as a defect
# --------------------------------------------------------------------------

def case_a_fix_with_a_test_is_an_instance(t):
    repo(t)
    put(t, "src/a.py", "def f():\n    return 1\n")
    put(t, "tests/test_a.py", "from src.a import f\n\n\ndef test_f():\n    assert f() == 1\n")
    commit(t, "feat: a")
    put(t, "src/a.py", "def f():\n    return 2\n")
    put(t, "tests/test_a.py", "from src.a import f\n\n\ndef test_f():\n    assert f() == 2\n")
    commit(t, "fix: f returned the wrong number")
    found = history_mod.mine(t)
    if len(found["fix_test"]) != 1:
        return f"found {len(found['fix_test'])} fix+test commits, expected 1"
    if not history_mod.candidates(found):
        return "the instance was found but not offered as replayable"
    return ""


def case_a_repair_is_found_when_the_subject_is_not_english(t):
    """A defect miner that only reads English reports a repository with years
    of history as having nothing to replay.

    That is indistinguishable, on the page, from a repository that genuinely
    repairs nothing -- and it is the instrument's fault, not the repository's.
    Found on a real subject repository whose 53 commit messages are almost all
    Chinese: the English-only matcher classified one of them."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    put(t, "tests/test_app.py", "def test_x():\n    assert True\n")
    commit(t, "初始版本")
    put(t, "app.py", "x = 2\n")
    put(t, "tests/test_app.py", "def test_x():\n    assert 1\n")
    commit(t, "修签到提醒里没被替换的占位符")

    found = history_mod.mine(t)
    if len(found["fix_test"]) != 1:
        return (f"a Chinese repair subject was classified as "
                f"{len(found['fix_test'])} fix-with-test commits, not 1")

    # And the word for "modify" must not be read as a repair, or every commit
    # in such a repository becomes a defect.
    put(t, "app.py", "x = 3\n")
    commit(t, "修改配色")
    if len(history_mod.mine(t)["fix_no_test"]) != 0:
        return "修改 ('modify') was read as a repair"
    return None


def case_a_docs_only_fix_is_not_a_defect(t):
    """`fix: typo in the README` is not a bug that happened to the code."""
    repo(t)
    put(t, "README.md", "# x\n")
    commit(t, "init")
    put(t, "README.md", "# x, spelled right\n")
    commit(t, "fix: typo in the README")
    found = history_mod.mine(t)
    if found["fix_test"] or found["fix_no_test"]:
        return "a documentation-only commit was counted as a code defect"
    return ""


def case_a_large_commit_is_not_one_defect(t):
    """Above the size cap a revert is a refactor with a bug inside it, and
    nothing that goes red afterwards can be attributed to one change."""
    repo(t)
    put(t, "tests/test_a.py", "def test_x():\n    assert True\n")
    for i in range(6):
        put(t, f"src/m{i}.py", "x = 1\n")
    commit(t, "init")
    for i in range(6):
        put(t, f"src/m{i}.py", "x = 2\n")
    put(t, "tests/test_a.py", "def test_x():\n    assert True  # touched\n")
    commit(t, "fix: everything at once")
    found = history_mod.mine(t)
    if history_mod.candidates(found):
        return "a six-file commit was offered as a single replayable defect"
    return ""


def case_a_shallow_clone_cannot_judge(t):
    """No history is not the same as no defects, and must not read as zero."""
    src = os.path.join(t, "src")
    os.makedirs(src, exist_ok=True)
    repo(src)
    put(src, "a.py", "x = 1\n")
    commit(src, "one")
    put(src, "a.py", "x = 2\n")
    commit(src, "two")
    dst = os.path.join(t, "shallow")
    git(["clone", "-q", "--depth", "1", "file://" + src, dst], t)
    if not os.path.exists(os.path.join(dst, ".git", "shallow")):
        return ""                       # git refused to make it shallow; skip
    out = subprocess.run([sys.executable, os.path.join(HERE, "history.py"),
                          "--root", dst], capture_output=True, text=True,
                         timeout=120)
    if out.returncode != 2:
        return (f"a shallow clone exited {out.returncode}, not 2 — no history "
                f"was reported as no defects")
    return ""


# --------------------------------------------------------------------------
# catch: the ladder, and the rung that must not fire
# --------------------------------------------------------------------------

def case_a_hook_that_refuses_is_read_as_before_write(t):
    repo(t)
    hook_script(t, "hooks/no.py", BLOCKER)
    pre = catch_mod.wired(t, "PreToolUse")
    if len(pre) != 1:
        return f"read {len(pre)} PreToolUse hook(s) from settings.json, expected 1"
    blocked, _h, _said = catch_mod.fire(t, pre, {"tool_name": "Edit",
                                                 "tool_input": {}})
    if not blocked:
        return "a hook exiting 2 was not read as a block"
    return ""


def case_a_hook_that_denies_in_json_is_also_a_block(t):
    """Two spellings are in use. A probe that knew one would report a working
    guard as absent."""
    repo(t)
    hook_script(t, "hooks/no.py",
                "import sys, json\n"
                "sys.stdin.read()\n"
                "print(json.dumps({'permissionDecision': 'deny',\n"
                "                  'permissionDecisionReason': 'nope'}))\n")
    blocked, _h, said = catch_mod.fire(t, catch_mod.wired(t, "PreToolUse"),
                                       {"tool_name": "Edit", "tool_input": {}})
    if not blocked:
        return "a hook denying in JSON on stdout was not read as a block"
    if "nope" not in said:
        return f"the reason was lost: {said!r}"
    return ""


def case_a_quiet_hook_is_not_a_block(t):
    """The inverse, and the one that turns the whole ladder into a lie if it
    breaks: a hook that allows must not be scored as a catch."""
    repo(t)
    hook_script(t, "hooks/ok.py", QUIET)
    blocked, _h, _s = catch_mod.fire(t, catch_mod.wired(t, "PreToolUse"),
                                     {"tool_name": "Edit", "tool_input": {}})
    if blocked:
        return "a hook that exited 0 was scored as refusing the action"
    return ""


def case_settings_local_is_read_and_marked(t):
    """A hook only in `settings.local.json` protects its author and nobody
    else, which is worth reporting rather than silently counting."""
    repo(t)
    put(t, ".claude/settings.local.json", json.dumps({
        "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
            {"type": "command", "command": "true"}]}]}}))
    pre = catch_mod.wired(t, "PreToolUse")
    if len(pre) != 1 or not pre[0]["local"]:
        return "a hook wired only in settings.local.json was missed or unmarked"
    return ""


def case_no_hooks_and_a_real_defect_lands_on_the_suite(t):
    """The end-to-end shape, with the answer known in advance: a repository
    with tests and no hooks catches its defects at `local-suite`.

    The fixture runs its test through a `Makefile` and the standard library,
    not through pytest. The first version needed pytest, which is not on a
    fresh runner's ambient interpreter, so the one case that exercises the
    whole ladder was the one case CI could not run -- and the failure looked
    like a broken ladder rather than a missing package. A selftest for an
    assessment may not depend on anything the assessment does not."""
    if shutil.which("make") is None:
        return ""                       # no runner; not a verdict about anything
    repo(t)
    check = ("test:\n"
             "\t@python3 -c \"import sys; sys.path.insert(0,'.'); "
             "from src.a import f; sys.exit(0 if f() == {want} else 1)\"\n")
    put(t, "src/__init__.py", "")
    put(t, "src/a.py", "def f():\n    return 2\n")
    put(t, "tests/.keep", "")
    put(t, "Makefile", check.format(want=2))
    commit(t, "feat: a")
    put(t, "src/a.py", "def f():\n    return 3\n")
    put(t, "Makefile", check.format(want=3))
    put(t, "tests/case_f.py", "# the test moved with the fix\n")
    commit(t, "fix: f returned the wrong number")

    work = os.path.join(t, ".work")
    r, why = catch_mod.assess(t, 1, work)
    if r is None:
        return f"could not run the ladder at all: {why}"
    rungs = [row["rung"] for row in r["rows"]]
    if rungs != ["local-suite"]:
        return (f"a repository with tests and no hooks put its defect on "
                f"{rungs}, not ['local-suite'] — detail: "
                f"{[str(row['detail'])[:70] for row in r['rows']]}")
    return ""


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



# --------------------------------------------------------------------------
# dimensions: the five groups, and the states each of them can lose
# --------------------------------------------------------------------------

CRASHES = "import nonexistent_module_xyz\n"


def dim_repo(t, files=(), hook=None):
    """A committed repository, optionally with one PreToolUse hook wired."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    for rel, body in files:
        put(t, rel, body)
    if hook is not None:
        hook_script(t, ".claude/guard.py", hook)
    commit(t, "init")
    return t


def dims_of(t, with_blast=True):
    probe = load_probe().probe(t)
    blast = blast_mod.assess(t, "app.py", "") if with_blast and os.path.isdir(
        os.path.join(t, ".claude")) else None
    return {d["n"]: d for d in dim_mod.assess(
        t, probe, blast, None, "", None, history_mod.commits(t),
        catch_mod.LADDER)}


def case_a_guard_that_crashes_is_not_read_as_allowed(t):
    """A hook that exits 1 with a traceback decided nothing.

    Claude Code treats any non-zero exit other than 2 as a non-blocking error:
    the action proceeds. Before this, such a hook was folded into `allowed`,
    so a guard with a missing import and no guard at all produced the same
    page -- and the first of those is worse, because everybody believes they
    are covered."""
    dim_repo(t, hook=CRASHES)
    rows = dims_of(t)[1]["rows"]
    broke = [r for r in rows if "broke" in r["label"]]
    if not broke:
        return "a guard that crashed was not reported as broken"
    if broke[0]["flag"] != "bad":
        return f"a broken guard was flagged {broke[0]['flag']!r}, not 'bad'"
    return None


def case_a_guard_that_allows_is_not_reported_as_broken(t):
    """The twin. Without it the case above passes on a probe that shouts
    'broken' at every repository."""
    dim_repo(t, hook=QUIET)
    rows = dims_of(t)[1]["rows"]
    if [r for r in rows if "broke" in r["label"]]:
        return "a working guard that allowed the action was reported broken"
    return None


def case_a_scoped_rule_with_nothing_delivering_it_is_reported(t):
    """A rule carrying `paths:` loads when Claude READS a matching file -- not
    when it creates one, and not when it writes through the shell. If nothing
    fills that gap, the rule is silent at the two moments it is worth most."""
    dim_repo(t, files=[(".claude/rules/api.md",
                        "---\npaths:\n  - \"src/**/*.py\"\n---\n\nrule\n")],
             hook=QUIET)
    rows = dims_of(t)[1]["rows"]
    scoped = [r for r in rows if "scoped" in r["label"]]
    if not scoped:
        return "a path-scoped rule with no delivery was not reported"
    if scoped[0]["flag"] != "warn":
        return f"flagged {scoped[0]['flag']!r}, not 'warn'"
    return None


def case_an_unconditional_rule_is_not_reported_as_undelivered(t):
    """A rule with no `paths:` loads at launch, every session. Its problem is
    cost, not delivery, and reporting it here would be an invented finding."""
    dim_repo(t, files=[(".claude/rules/all.md", "always do the thing\n")],
             hook=QUIET)
    rows = dims_of(t)[1]["rows"]
    if [r for r in rows if "scoped" in r["label"]]:
        return "an unconditional rule was reported as undelivered"
    return None


def case_verification_is_found_where_the_repository_put_it(t):
    """`tests/` is not the only shape verification takes.

    This defect was live: a matcher that knew only test-file names read this
    project's own history -- whose checks are called `selftest.py` and live in
    `gates/` -- as 33 code changes out of 33 with nothing behind them."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    # Named so that ONLY its directory makes it verification -- no `test_`,
    # no `check_`, no `selftest`. A matcher that reads file names alone will
    # miss it, which is the defect this case exists for.
    put(t, "tools/gates/thing.py", "def main():\n    return 0\n")
    commit(t, "feat: a change, with a check beside it")
    d3 = dims_of(t, with_blast=False)[3]
    bare = [r for r in d3["rows"] if "verified nothing" in r["label"]]
    if not bare:
        return "the coverage row is missing"
    if not bare[0]["value"].startswith("0/"):
        return (f"a change accompanied by a check in tools/gates/ counted as "
                f"unverified: {bare[0]['value']}")
    return None


def case_a_test_suite_is_recognised_by_its_name(t):
    """The other half of the mechanism above: a directory nobody would call a
    check directory, recognised because test suites are named from a small and
    stable vocabulary."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    put(t, "spec/thing.rb", "describe 'x'\n")
    commit(t, "feat: a change, with a spec beside it")
    d3 = dims_of(t, with_blast=False)[3]
    bare = [r for r in d3["rows"] if "verified nothing" in r["label"]]
    if not bare[0]["value"].startswith("0/"):
        return (f"a change accompanied by spec/ counted as unverified: "
                f"{bare[0]['value']}")
    return None


def case_a_replay_that_could_not_run_is_not_a_clean_sheet(t):
    """A ladder of zeros is not a perfect score.

    This was live: a repository whose two replayable defects both failed for
    want of an installed dependency came out as "0 of 2 defects survive past
    the end of a session", flagged green. `catch.py` had reported both rows as
    unusable, with the missing module named; the dimension counted rungs and
    threw the reason away. Exit 2 means COULD NOT JUDGE, and so does this."""
    probe = load_probe().probe(dim_repo(t))
    unusable = {"rows": [
        {"sha": "aaaa", "subject": "x", "rung": None,
         "detail": "unusable — at the fix the tests are could-not-run: "
                   "No module named 'sqlalchemy'"},
        {"sha": "bbbb", "subject": "y", "rung": None, "detail": "unusable — x"},
    ]}
    supply = {"replayable": 2, "fix_no_test": 0, "has_test_files": True,
              "shallow": False}
    d2 = dim_mod.assess(t, probe, None, unusable, "", supply, None,
                        catch_mod.LADDER)[1]
    if d2["state"] != "abstained":
        return (f"two unusable replays produced state {d2['state']!r} and "
                f"headline {d2['headline']!r}, not an abstention")
    if not any("sqlalchemy" in r["note"] for r in d2["rows"]):
        return "the abstention does not say what stopped the replay"

    # And one usable row among unusable ones must still be measured, with the
    # unusable ones outside the count rather than inside it as successes.
    mixed = {"rows": [dict(unusable["rows"][0]),
                      {"sha": "cccc", "subject": "z", "rung": "never",
                       "detail": ""}]}
    d2 = dim_mod.assess(t, probe, None, mixed, "", supply, None,
                        catch_mod.LADDER)[1]
    if d2["state"] != "measured" or "1 of 1" not in d2["headline"]:
        return (f"a mix of one usable and one unusable replay gave "
                f"{d2['state']!r}: {d2['headline']!r}")
    return None


def case_plugin_tokens_are_not_charged_to_the_repository(t):
    """Skill descriptions installed on this machine are real tokens and are
    reported -- but a repository judged on them is being scored for what
    somebody else installed."""
    dim_repo(t, files=[("CLAUDE.md", "x\n" * 400)])
    d5 = dims_of(t, with_blast=False)[5]
    floor = [r for r in d5["rows"] if r["label"].startswith("floor")][0]
    if "from this repository" not in floor["note"]:
        return "the floor does not say how much of it this repository owns"
    if "from this repository" not in d5["headline"]:
        return f"the headline does not scope the number: {d5['headline']!r}"
    return None


def case_a_place_repaired_twice_is_counted(t):
    """The offline, shared version of noticing a recurrence: it is in the
    history, so it is the same for everyone who clones."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    commit(t, "feat: thing")
    put(t, "app.py", "x = 2\n")
    commit(t, "fix: the thing was wrong")
    put(t, "app.py", "x = 3\n")
    commit(t, "fix: the thing was still wrong")
    rows = dims_of(t, with_blast=False)[4]["rows"]
    repeat = [r for r in rows if "more than once" in r["label"]][0]
    if repeat["value"] != "1":
        return f"two repairs to one file counted as {repeat['value']!r}"
    return None


def case_a_record_nobody_reads_is_not_scored_as_learning(t):
    """A write-only record of mistakes is the failure that looks healthiest
    from outside: the file exists, it is long, and nothing has ever read it."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    put(t, "docs/postmortem-outage.md", "we broke it\n")
    commit(t, "init")
    rows = dims_of(t, with_blast=False)[4]["rows"]
    rec = [r for r in rows if "mistakes are written" in r["label"]][0]
    if rec["flag"] != "warn":
        return f"an unreferenced record was flagged {rec['flag']!r}, not 'warn'"

    put(t, "README.md", "see docs/postmortem-outage.md\n")
    commit(t, "docs: point at it")
    rows = dims_of(t, with_blast=False)[4]["rows"]
    rec = [r for r in rows if "mistakes are written" in r["label"]][0]
    if rec["flag"] != "ok":
        return "a record that README points at was still flagged as unread"
    return None


CASES = [
    ("checks are found where the repository put them, not where we would",
     case_checks_are_found_outside_scripts),
    ("a dispatcher and a selftest are not themselves checks",
     case_machinery_is_not_counted_as_checks),
    ("a dependency's gates are not counted as this repository's",
     case_vendored_checks_are_not_this_repos),
    ("an installed plugin's standing skill cost is counted",
     case_plugin_skill_cost_is_counted),
    ("a fix with a test is a replayable instance",
     case_a_fix_with_a_test_is_an_instance),
    ("a repair is found when the commit subject is not English",
     case_a_repair_is_found_when_the_subject_is_not_english),
    ("a documentation-only fix is not a code defect",
     case_a_docs_only_fix_is_not_a_defect),
    ("a commit too large to attribute is not one defect",
     case_a_large_commit_is_not_one_defect),
    ("a shallow clone cannot judge, and does not report zero",
     case_a_shallow_clone_cannot_judge),
    ("a hook exiting 2 reads as a refusal",
     case_a_hook_that_refuses_is_read_as_before_write),
    ("a hook denying in JSON reads as a refusal, with its reason",
     case_a_hook_that_denies_in_json_is_also_a_block),
    ("a hook that allows is not scored as a catch",
     case_a_quiet_hook_is_not_a_block),
    ("a hook wired only in settings.local.json is read, and marked",
     case_settings_local_is_read_and_marked),
    ("tests and no hooks put a real defect on the local suite",
     case_no_hooks_and_a_real_defect_lands_on_the_suite),
    ("nothing wired stops nothing",
     case_nothing_wired_stops_nothing),
    ("a blanket refusal is reported as a false block",
     case_a_blanket_refusal_is_a_false_block_not_a_score),
    ("a targeted refusal is not reported as a false block",
     case_a_targeted_refusal_is_not_a_false_block),
    ("the same repository scores the same from any branch",
     case_a_verdict_does_not_move_with_the_checkout),
    ("a guard that crashes is not read as having allowed the action",
     case_a_guard_that_crashes_is_not_read_as_allowed),
    ("a guard that allows is not reported as broken",
     case_a_guard_that_allows_is_not_reported_as_broken),
    ("a path-scoped rule with nothing delivering it is reported",
     case_a_scoped_rule_with_nothing_delivering_it_is_reported),
    ("an unconditional rule is not reported as undelivered",
     case_an_unconditional_rule_is_not_reported_as_undelivered),
    ("verification is found where the repository put it",
     case_verification_is_found_where_the_repository_put_it),
    ("a test suite is recognised by its name, wherever it lives",
     case_a_test_suite_is_recognised_by_its_name),
    ("a replay that could not run is not scored as a clean sheet",
     case_a_replay_that_could_not_run_is_not_a_clean_sheet),
    ("an installed plugin's tokens are not charged to the repository",
     case_plugin_tokens_are_not_charged_to_the_repository),
    ("a place repaired twice is counted, from committed history",
     case_a_place_repaired_twice_is_counted),
    ("a record of mistakes nobody reads is not scored as learning",
     case_a_record_nobody_reads_is_not_scored_as_learning),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    if shutil.which("git") is None:
        print("cannot run: git not on PATH", file=sys.stderr)
        return 2
    for name in ("probe_repo.py",):
        if not os.path.exists(os.path.join(PARENT, name)):
            print(f"cannot run: {name} is missing", file=sys.stderr)
            return 2

    failures = []
    for label, fn in CASES:
        tmp = tempfile.mkdtemp(prefix="assess-selftest-")
        try:
            problem = fn(tmp)
        except Exception as exc:                          # noqa: BLE001
            problem = f"{type(exc).__name__}: {exc}"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if problem:
            failures.append(f"{label}\n    {problem}")
        elif a.verbose:
            print(f"  ok  {label}")

    if failures:
        print(f"{len(failures)} of {len(CASES)} assessment case(s) failed:\n",
              file=sys.stderr)
        for f in failures:
            print(f"  {f}\n", file=sys.stderr)
        return 1
    print(f"PASS  {len(CASES)} assessment case(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
