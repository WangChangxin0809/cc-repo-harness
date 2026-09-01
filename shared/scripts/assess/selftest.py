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
import ast
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
import memory as memory_mod        # noqa: E402
import truth as truth_mod          # noqa: E402
import value as value_mod          # noqa: E402
import arid as arid_mod            # noqa: E402
import judge as judge_mod          # noqa: E402
import mutate as mutate_mod        # noqa: E402
import run_mutants as run_mod      # noqa: E402
import factsheet as fact_mod       # noqa: E402
import cover as cover_mod          # noqa: E402


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


def case_source_files_named_in_another_language_are_not_invisible(t):
    """git C-quotes non-ASCII paths unless `core.quotePath=false`.

    `git ls-files` returns `"docs/\\344\\270\\255..."`, quotes included, and
    `git log --name-only` does the same. Every extension test then fails, so a
    repository whose source files are named in its own language goes missing
    from the file counts and from dimensions 2, 3 and 4 -- silently, and worst
    for exactly the repositories this instrument is least likely to have been
    tried on."""
    repo(t)
    put(t, "后端/服务.py", "x = 1\n")
    put(t, "tests/test_服务.py", "def test_x():\n    assert True\n")
    commit(t, "init")
    put(t, "后端/服务.py", "x = 2\n")
    put(t, "tests/test_服务.py", "def test_x():\n    assert 1\n")
    commit(t, "fix: 服务算错了")

    log = history_mod.commits(t)
    if log is None:
        return "the history could not be read at all"
    paths = [p for _sha, _subj, ps in log for p in ps]
    if any(p.startswith('"') for p in paths):
        return f"paths came back C-quoted: {[p for p in paths if p[0] == chr(34)][:2]}"
    if "后端/服务.py" not in paths:
        return f"the Chinese-named source file is missing from the log: {paths}"

    probe = load_probe().probe(t)
    if probe["source_files"] < 1:
        return (f"a repository whose only source file is named in Chinese "
                f"counted {probe['source_files']} source files")

    d3 = dims_of(t, with_blast=False)[3]
    bare = [r for r in d3["rows"] if "verified nothing" in r["label"]][0]
    if not bare["value"].startswith("0/"):
        return (f"a Chinese-named change with a test beside it counted as "
                f"unverified: {bare['value']}")
    return None


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


def case_a_check_only_its_author_can_run_is_not_coverage(t):
    """A check that hardcodes a path into one person's home directory is inert
    for everybody else, while still looking from outside like coverage.

    Found in the wild by reading, not by measuring: a screenshot check whose
    Chrome path was `/home/<author>/.cache/ms-playwright/...`. It had an
    incident behind it and was counted as a point in the repository's favour.
    Nothing could run it."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    put(t, "scripts/viewcheck.mjs",
        "const CHROME = '/home/nobody-at-all-xyz/.cache/chrome'\n")
    # The second shape, and the one a home-directory matcher misses. Both were
    # in one real repository: a Linux script and a Windows script, so no single
    # machine could run both, while from outside it looked like coverage.
    put(t, "scripts/shot.mjs",
        "const EDGE = 'C:\\\\Program Files (x86)\\\\Edge\\\\msedge.exe'\n")
    commit(t, "init")
    rows = dims_of(t, with_blast=False)[3]["rows"]
    hit = [r for r in rows if "one machine" in r["label"]]
    if not hit:
        return "a check hardcoding a path only one machine has passed"
    if hit[0]["flag"] != "bad":
        return f"flagged {hit[0]['flag']!r}, not 'bad'"
    if hit[0]["value"] != "2":
        return (f"found {hit[0]['value']} of the two pinned paths — a home "
                f"directory and an install root are the same defect")

    # An absolute path that is an argument, not an installed binary, is fine.
    put(t, "scripts/out.sh", "OUT='/tmp/shot.png'\n")
    commit(t, "chore: an output path")
    rows = dims_of(t, with_blast=False)[3]["rows"]
    again = [r for r in rows if "one machine" in r["label"]]
    if again and again[0]["value"] != "2":
        return f"an ordinary /tmp output path was counted: {again[0]['value']}"

    # A path that DOES resolve here is somebody's working setup, not a defect.
    # It has to match the same shape -- a directory INSIDE a home directory --
    # or this half passes because nothing matched, not because the check held.
    real = os.path.expanduser("~/.claude")
    if not os.path.isdir(real):
        real = os.path.join(os.path.expanduser("~"), os.listdir(
            os.path.expanduser("~"))[0])
    put(t, "scripts/viewcheck.mjs", f"const CHROME = {real!r}\n")
    commit(t, "chore: point it somewhere real")
    os.remove(os.path.join(t, "scripts", "shot.mjs"))
    commit(t, "chore: drop the windows one")
    rows = dims_of(t, with_blast=False)[3]["rows"]
    if [r for r in rows if "one machine" in r["label"]]:
        return "a pinned path that exists on this machine was called dead"
    return None


def case_an_unverified_change_to_the_machinery_is_singled_out(t):
    """Most unverified changes are not worth anyone's attention. A change to
    the thing that does the verifying is, because when it breaks, what would
    have caught the mistake is what changed."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    put(t, "tests/test_app.py", "def test_x():\n    assert True\n")
    commit(t, "init")
    put(t, "app.py", "x = 2\n")
    put(t, ".github/workflows/ci.yml", "on: push\n")
    commit(t, "ci: change the workflow and nothing else")
    rows = dims_of(t, with_blast=False)[3]["rows"]
    hit = [r for r in rows if "machinery" in r["label"]]
    if not hit:
        return "an unverified CI change was not singled out"

    # An ordinary unverified change must not land in that row.
    repo2 = t + "-plain"
    os.makedirs(repo2, exist_ok=True)
    repo(repo2)
    put(repo2, "app.py", "x = 1\n")
    put(repo2, "tests/test_app.py", "def test_x():\n    assert True\n")
    commit(repo2, "init")
    put(repo2, "app.py", "x = 2\n")
    commit(repo2, "feat: a small change with no test")
    rows = dims_of(repo2, with_blast=False)[3]["rows"]
    if [r for r in rows if "machinery" in r["label"]]:
        return "an ordinary unverified change was reported as machinery"
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


def case_the_instrument_leaves_nothing_in_the_repository(t):
    """Assessing must not change the thing being assessed.

    `factsheet.py --full` defaulted its bench directory to `<root>/.assess`
    and left 2.6 MB of clone untracked in a repository whose own page says
    nothing in it was executed. Found by pointing the assessor at somebody
    else's repository and reading what it complained about afterwards."""
    repo(t)
    put(t, "app.py", "def double(n):\n    return n + n\n")
    put(t, "tests/test_app.py",
        "from app import double\n\n\ndef test_double():\n"
        "    assert double(2) == 4\n")
    commit(t, "feat: double")
    # A replayable defect, or the replay abstains before it ever builds the
    # bench directory this case exists to look for.
    put(t, "app.py", "def double(n):\n    return n * 2\n")
    put(t, "tests/test_app.py",
        "from app import double\n\n\ndef test_double():\n"
        "    assert double(3) == 6\n")
    commit(t, "fix: double was addition, which is only right for 2")
    before = sorted(os.listdir(t))

    out = subprocess.run(
        [sys.executable, os.path.join(HERE, "factsheet.py"), "--root", t,
         "--full"], capture_output=True, text=True, timeout=900)
    if out.returncode not in (0, 2):
        return f"factsheet exited {out.returncode}: {out.stderr[-200:]}"

    left = [n for n in sorted(os.listdir(t)) if n not in before]
    if left:
        return (f"the assessment left {left} behind in the repository it was "
                f"only supposed to read")

    dirty = git(["status", "--porcelain"], t).stdout.strip()
    if dirty:
        return f"the assessment left the working tree dirty: {dirty[:120]}"
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


def case_a_rung_says_when_and_also_how_long(t):
    """A rung name says the order. Only seconds say the size of the step.

    The ladder's whole claim is that the gap between `local-suite` and `ci` is a
    cliff and not a slope, and a list of rung names cannot support that claim --
    `local-suite:1 ci:1` reads as two adjacent things. The seconds row is what
    makes the gap arguable, so it has to be on the page whenever any instance
    carries a time."""
    probe = load_probe().probe(dim_repo(t))
    supply = {"replayable": 2, "fix_no_test": 0, "has_test_files": True,
              "shallow": False}
    caught = {"ci_seconds": 512.0, "rows": [
        {"sha": "aaaa", "subject": "x", "rung": "local-suite", "detail": "",
         "seconds": 3.2},
        {"sha": "bbbb", "subject": "y", "rung": "ci", "detail": "",
         "seconds": 512.0},
    ]}
    d2 = dim_mod.assess(t, probe, None, caught, "", supply, None,
                        catch_mod.LADDER)[1]
    timed = [r for r in d2["rows"] if "how long" in r["label"]]
    if not timed:
        return ("two instances carried times and the page shows no seconds -- "
                "the cliff is then a claim with no number under it")
    value = timed[0]["value"]
    if "local-suite:3s" not in value or "ci:9m" not in value:
        return f"the seconds row reads {value!r}, which is not what was measured"
    return None


def case_ci_seconds_that_cannot_be_read_are_not_zero(t):
    """No CI history is an abstention, not a fast CI.

    The tempting shortcut is to time the CI command on this machine. That
    number is real and it is a measurement of the wrong thing: what a person
    waits for at rung 3 includes a queue and a runner that do not exist here,
    so a local timing makes the cliff look like a step. When the repository's
    own history cannot be read, the row must say so."""
    probe = load_probe().probe(dim_repo(t))
    supply = {"replayable": 1, "fix_no_test": 0, "has_test_files": True,
              "shallow": False}
    blind = {"ci_seconds": None, "rows": [
        {"sha": "aaaa", "subject": "x", "rung": "ci", "detail": "",
         "seconds": None}]}
    d2 = dim_mod.assess(t, probe, None, blind, "", supply, None,
                        catch_mod.LADDER)[1]
    timed = [r for r in d2["rows"] if "how long" in r["label"]]
    if timed:
        return (f"with no readable CI history the page still printed a time: "
                f"{timed[0]['value']!r}")

    # And `ci_seconds` itself must abstain rather than invent a number when the
    # subject has no runs to read -- a plain git repository with no remote.
    if catch_mod.ci_seconds(repo(t)) is not None:
        return "ci_seconds returned a number for a repository with no CI runs"
    return None


def case_the_page_says_there_is_only_one_way_in(t):
    """One injection is a finding about the instrument, and must be printed.

    Dimension 2 replays defects this repository actually shipped, which makes
    every instance real -- and means the page is silent about every failure mode
    that never became a commit here. A reader who is not told that reads a good
    ladder as "this repository catches defects", when what it says is "this
    repository catches the kind of defect it has already caught once"."""
    probe = load_probe().probe(dim_repo(t))
    supply = {"replayable": 3, "fix_no_test": 0, "has_test_files": True,
              "shallow": False}
    d2 = dim_mod.assess(t, probe, None, None, "", supply, None,
                        catch_mod.LADDER)[1]
    said = [r for r in d2["rows"] if "how the defect got in" in r["label"]]
    if not said:
        return "the page does not say how the defect was introduced at all"
    note = said[0]["value"] + " " + said[0]["note"]
    if "1 way" not in said[0]["value"]:
        return f"the count of injection routes is not stated: {said[0]['value']!r}"
    if "mutated" not in note:
        return ("the row does not say what is NOT done -- a reader cannot tell "
                "which failure modes this page never looked for")
    return None


def case_the_replay_runs_unless_it_is_refused(t):
    """`--full` was opt-in, and dimension 2 therefore abstained almost always.

    A flag guarding the page's headline measurement, which nobody remembers to
    pass, is a measurement that does not happen. It is on by default now, and
    the cost is announced before it is spent rather than explained afterwards.
    This case holds both halves: the default, and the pre-flight line."""
    src = os.path.join(PARENT, "assess", "factsheet.py")
    out = subprocess.run([sys.executable, src, "--help"],
                         capture_output=True, text=True, timeout=120)
    if "--no-full" not in out.stdout:
        return "there is no --no-full: the replay cannot be refused"
    if "--full " in out.stdout.replace("--no-full", ""):
        return ("--full is still a flag, so the replay is still opt-in and "
                "dimension 2 will keep abstaining by default")
    return None


# --------------------------------------------------------------------------
# truth: is what the repository writes down still true?
# --------------------------------------------------------------------------

def truth_repo(t):
    repo(t)
    put(t, "src/pay/charge.py", "def charge():\n    return 1\n")
    put(t, "docs/guide.md", "See [charge](../src/pay/charge.py).\n")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "feat: charging"], t)
    return t


def case_a_link_to_nothing_is_proven_wrong(t):
    """The one tier that needs no judgement, and it has to actually fire.

    Everything else this module does is a candidate handed to a reader. If the
    proven tier cannot catch a link typed at a file that is not there, the
    module has no floor and every row on it is a guess."""
    truth_repo(t)
    put(t, "docs/broken.md", "See [the plan](../docs/nowhere.md) for details.\n")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "docs: a link to nothing"], t)
    r = truth_mod.assess(t)
    hits = [x for x in r["proven"] if "nowhere.md" in x["claim"]]
    if not hits:
        return ("a markdown link to a file that does not exist was not "
                f"reported: proven={r['proven']}")
    if hits[0]["tier"] != 0:
        return f"the broken link came back as tier {hits[0]['tier']}, not 0"
    return None


def case_a_link_inside_a_fence_is_being_shown_not_followed(t):
    """A link inside ``` is an illustration, and checking it is noise.

    Live, on this repository: a skill showing an example plan linked
    `steps/01-shadow-verify.md`, a file that has never existed and is not meant
    to, and a template wrote `<... see [ARCHITECTURE.md](ARCHITECTURE.md).>`.
    Both were reported as broken references. Three of three proven findings
    were false, which is a proven tier that has proven nothing."""
    truth_repo(t)
    put(t, "docs/example.md",
        "Here is what a plan looks like:\n\n"
        "```markdown\n"
        "- [x] done [Shadow-verify](steps/01-shadow-verify.md)\n"
        "```\n\n"
        "And a template line:\n\n"
        "<Three lines. Then: see [ARCHITECTURE.md](ARCHITECTURE.md).>\n")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "docs: an example"], t)
    r = truth_mod.assess(t)
    false = [x for x in r["proven"]
             if "01-shadow-verify" in x["claim"] or "ARCHITECTURE" in x["claim"]]
    if false:
        return (f"links inside a fence or a <placeholder> were reported as "
                f"broken: {[x['claim'] for x in false]}")

    # And the stripping must not hide a real one on an ordinary line.
    put(t, "docs/example.md",
        open(os.path.join(t, "docs/example.md")).read()
        + "\nAnd really: [gone](../docs/gone.md).\n")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "docs: and a real one"], t)
    r = truth_mod.assess(t)
    if not any("gone.md" in x["claim"] for x in r["proven"]):
        return ("stripping fences also swallowed a broken link on an ordinary "
                "line — the filter is now hiding findings")
    return None


def case_a_historical_document_is_not_stale(t):
    """A decision record describing what used to be true is doing its job.

    The same sentence in a `CLAUDE.md` is a lie and in `docs/decisions/0004-...`
    is a record. A checker that cannot tell them apart reports every ADR a
    repository has ever written, which is the fastest way to be switched off."""
    truth_repo(t)
    put(t, "docs/decisions/0004-we-used-to-do-it-differently.md",
        "We used to keep it in [the old place](../../src/old/thing.py).\n")
    put(t, "CHANGELOG.md", "## 1.0\n- moved [it](src/old/thing.py)\n")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "docs: a record"], t)
    r = truth_mod.assess(t)
    leaked = [x for x in r["proven"] + r["candidates"]
              if "decisions/" in x["file"] or "CHANGELOG" in x["file"]]
    if leaked:
        return (f"historical documents were checked for staleness: "
                f"{[x['file'] for x in leaked]}")
    if not truth_mod.historical("docs/decisions/0004-a.md"):
        return "a numbered record under decisions/ is not read as historical"
    if truth_mod.historical("guide/1-assess.md"):
        return "an ordinary guide page is being excluded as historical"
    return None


def case_two_documents_disagreeing_is_a_candidate(t):
    """The contradiction tier has to be able to fire at all.

    A tier that returns nothing on every repository is indistinguishable from
    a tier that is broken, and this one returned nothing on the repository it
    was written in. So a disagreement is planted and it has to come back --
    as a candidate, never as a finding, because two documents giving a number
    two values may be two different numbers."""
    truth_repo(t)
    put(t, "docs/a.md",
        "The standing context budget for this repository is 800 tokens per "
        "turn, measured across every session on the machine.\n")
    put(t, "docs/b.md",
        "The standing context budget for this repository is 173 tokens per "
        "turn, measured across every session on the machine.\n")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "docs: two budgets"], t)
    r = truth_mod.assess(t)
    hits = [x for x in r["candidates"] if x["tier"] == 4]
    if not hits:
        return ("two documents stating the same budget as 800 and 173 tokens "
                "produced no contradiction candidate")
    if any(x["tier"] == 4 for x in r["proven"]):
        return "a contradiction candidate was reported as proven"
    return None


def case_thickness_is_a_denominator_and_never_a_score(t):
    """Counting what a repository keeps cannot raise anything here.

    0025 rejected thickness scoring for three reasons that all still hold: it
    grades a repository on adopting our conventions, it rewards this plugin's
    own presence, and it calls 0024 -- which cut the standing cost by 81% -- a
    regression while dimension 5 calls it an improvement. Thickness is kept as
    a denominator, and a denominator must not appear in the numerator."""
    truth_repo(t)
    thin = truth_mod.assess(t)
    for i in range(6):
        put(t, f"docs/extra{i}.md", "Some more prose about nothing.\n" * 20)
    put(t, "CLAUDE.md", "Rules.\n")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "docs: more of it"], t)
    thick = truth_mod.assess(t)
    if thick["thickness"]["documents"] <= thin["thickness"]["documents"]:
        return "the denominator did not move when documents were added"
    if len(thick["proven"]) < len(thin["proven"]):
        return ("adding documents that say nothing reduced the proven "
                "findings — thickness is leaking into the score")
    return None


def case_the_candidate_budget_is_shared_between_tiers(t):
    """A budget one tier can eat is not a budget.

    Live: the cap was applied to the tiers concatenated in order, T1 and T2
    filled all 24 slots, and T3 and T4 -- staleness and contradiction, the two
    tiers the module was asked for -- returned rows that were then silently
    discarded. Nothing failed; the page was simply missing two tiers."""
    got = truth_mod._share(5, [["a1", "a2", "a3", "a4", "a5", "a6"],
                               ["b1", "b2"], [], ["d1", "d2", "d3"]])
    if len(got) != 5:
        return f"the cap was not honoured: {got}"
    if "b1" not in got or "d1" not in got:
        return (f"a later tier was starved by an earlier one: {got}")
    # A tier with nothing to say gives its share back rather than holding it.
    if truth_mod._share(4, [["a1", "a2", "a3", "a4", "a5"], [], []]) != [
            "a1", "a2", "a3", "a4"]:
        return "an empty tier's share was not given back"
    return None


# --------------------------------------------------------------------------
# mutation: the operators, the suppression, and the ways it lies
# --------------------------------------------------------------------------

def case_every_operator_offers_every_alternative(t):
    """Mothra replaces an operator with each other operator of its class.

    Getting this wrong is invisible: the tool still produces mutants, still
    runs them, still reports a number. It only shows up against the paper --
    a one-partner AOR gave a 2x reduction in the RQ1 study where the paper
    reports 117x, because a strategy that generates few mutants has little
    left to suppress. The control arm has to be the real control arm."""
    src = "def f(a, b):\n    return a + b\n"
    ops = [m for m in mutate_mod.candidates("f.py", src) if m.op == "AOR"]
    if len(ops) != len(mutate_mod.ARITH) - 1:
        return (f"`a + b` produced {len(ops)} AOR mutant(s); Mothra's AOR "
                f"offers each of the other {len(mutate_mod.ARITH) - 1} "
                f"arithmetic operators")
    src = "def f(a, b):\n    return a < b\n"
    ror = [m for m in mutate_mod.candidates("f.py", src) if m.op == "ROR"]
    if len(ror) != len(mutate_mod.RELATE) - 1:
        return f"`a < b` produced {len(ror)} ROR mutant(s), not 5"
    return None


def case_abs_is_not_an_operator_here(t):
    """The paper excludes ABS, and adding it back would be inventing.

    Their Table 1 lists five operators and says of ABS that it "predominantly
    creates unproductive mutants". A reimplementation that quietly adds a sixth
    because it seemed useful is no longer a reimplementation."""
    src = ("def f(a, b):\n    x = a + b\n    if a < b and a:\n"
           "        return -a\n    return x\n")
    ops = {m.op for m in mutate_mod.candidates("f.py", src)}
    if not ops:
        return "nothing was generated at all"
    if not ops <= {"AOR", "LCR", "ROR", "UOI", "SBR"}:
        return f"an operator outside the paper's five appeared: {ops}"
    return None


def case_the_three_rules_that_paid_for_everything_fire(t):
    """LOG, TIME and FLAG carry the paper's 15% -> 80%, so each must work.

    Not a formality. The LOG rule is two clauses -- a name starting with `log`,
    or a receiver called `logger` -- and it is the one rule the paper validated
    by sampling, at 99 of 100. If it silently matched nothing, everything below
    it in the report would still look plausible."""
    for src, want in (
            # The receiver clause: an object called `logger`.
            ('logger.info("x %s", a + b)\n', "LOG"),
            ('log.debug("x")\n', "LOG"),
            ('logging.warning("x")\n', "LOG"),
            # The **name-prefix** clause, which is the half of the rule the
            # paper validated by sampling. Without a case that reaches it, the
            # prefix regex can be broken outright and every log case still
            # passes through the receiver clause -- which is exactly what
            # happened when this was planted.
            ('log_request(a + b)\n', "LOG"),
            ('logAudit(a + b)\n', "LOG"),
            ('time.sleep(5 * 2)\n', "TIME"),
            ('parser.add_argument("--n", default=1000 * 1000)\n', "FLAG"),
    ):
        hit = arid_mod.arid_line(src, 1)
        if not hit:
            return f"nothing fired on {src.strip()!r}; expected {want}"
        if hit[0] != want:
            return f"{src.strip()!r} fired {hit[0]}, not {want}"
    # And a plain arithmetic line must NOT be arid, or everything is suppressed
    # and the tool reports a clean sheet on every repository.
    if arid_mod.arid_line("total = price * quantity\n", 1):
        return ("an ordinary arithmetic line was marked arid — a rule that "
                "fires on everything suppresses everything")
    return None


def case_a_suppressed_mutant_is_counted_not_discarded(t):
    """The paper never measures what its unsound rules cost. We must.

    Their own words: "Sound heuristics are demonstrably correct, but we have
    had much more important improvements ... from unsound heuristics." An
    unsound rule can suppress a productive mutant, and there is no figure
    anywhere in the paper for how often. Copying the rules is right; copying
    the silence is not, so suppressions are returned with their soundness."""
    src = 'def f(a):\n    logger.info("x %s", a + 1)\n    return a + 1\n'
    mutants = mutate_mod.candidates("f.py", src)
    kept, dropped = mutate_mod.suppress(mutants, {"f.py": src})
    if not dropped:
        return "a mutation inside a logging call was not suppressed at all"
    if not kept:
        return "everything was suppressed, including the line outside the log"
    for _m, hit in dropped:
        if not isinstance(hit, tuple) or len(hit) != 2:
            return f"a suppression came back without its soundness: {hit!r}"
    ids = {h[0] for _m, h in dropped}
    if "LOG" not in ids:
        return f"the logging line was suppressed by {ids}, not LOG"
    return None


def case_only_covered_lines_are_mutated(t):
    """A file the suite never entered is outside the measurement, not inside it.

    This was live and it inverted the policy. When coverage was supplied but a
    file had no entry, `generate` fell through to `lines = None` and mutated
    the file **entirely**. Measured on `tenacity`: every single survivor was in
    `doc/source/conf.py`, a Sphinx config no test executes and none should."""
    repo(t)
    put(t, "app/covered.py", "def f(a, b):\n    return a + b\n")
    put(t, "app/never.py", "def g(a, b):\n    return a * b\n")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "feat: two files"], t)
    covered = {"app/covered.py": {2}}
    mutants, _d, _s = mutate_mod.generate(
        t, ["app/covered.py", "app/never.py"], covered, "arid")
    touched = {m.path for m in mutants}
    if "app/never.py" in touched:
        return ("a file with no coverage entry was mutated — the covered-line "
                "restriction is inverted, which is the bug that put every "
                "survivor in a Sphinx config")
    if "app/covered.py" not in touched:
        return "the covered file was not mutated either"
    return None


def case_a_broken_suite_is_not_a_killed_mutant(t):
    """A mutant that stops the suite loading has tested nothing.

    From outside, a suite that will not import looks exactly like a suite that
    caught something: both are a non-zero exit. Counting the first as a kill
    inflates the score with mutants nothing examined. The paper's own Go
    heuristic A.5.2 exists for this: "the mutant appears killed because the
    test fails (to build)".

    A suite that *hangs* is a third thing again, and it is not hypothetical:
    measured on `tenacity`, a retry library, flipping one comparison in a
    backoff loop ran for 166 seconds against a 2.8 second baseline. Behaviour
    changed observably, and no test asserted anything, so it is neither."""
    put(t, "src.py", "x = 1\n")
    put(t, "suite.py", "import nosuchmodule_xyz\n")
    verdict, _d = run_mod.run_one(t, "src.py", "x = 2\n",
                                  [sys.executable, "suite.py"], "x = 1\n")
    if verdict != "broken":
        return (f"a suite that could not import came back {verdict!r}; a "
                f"mutant that stops the suite loading tested nothing")

    put(t, "slow.py", "import time\ntime.sleep(30)\n")
    verdict, _d = run_mod.run_one(t, "src.py", "x = 2\n",
                                  [sys.executable, "slow.py"], "x = 1\n",
                                  budget=2)
    if verdict != "timeout":
        return (f"a suite that hung came back {verdict!r}, not 'timeout' — a "
                f"hang credits the suite with a catch it did not make")

    # And the original file must be back on disk either way.
    with open(os.path.join(t, "src.py"), encoding="utf-8") as fh:
        if fh.read() != "x = 1\n":
            return "the mutated file was not restored after the run"
    return None


def case_module_level_statements_are_not_deleted(t):
    """A.1.12 excludes declaration statements, and in Python that is module
    scope.

    Measured on `tenacity`: 15 of 40 mutants came back `broken`, and all
    fifteen were module-level deletions or insertions in `__init__.py` --
    deleting `WrappedFn = t.TypeVar("WrappedFn")` does not test anything, it
    stops the module importing, and every test then reports a failure."""
    src = ('import typing as t\n'
           'WrappedFn = t.TypeVar("WrappedFn")\n'
           '_unset = object()\n\n'
           'def f(a, b):\n'
           '    x = a + b\n'
           '    return x\n')
    mutants = mutate_mod.candidates("m.py", src)
    bad = [m for m in mutants if m.line in (2, 3)]
    if bad:
        return (f"module-level declarations were offered for mutation: "
                f"{[(m.line, m.op) for m in bad]}")
    inside = [m for m in mutants if m.line in (6, 7)]
    if not inside:
        return "nothing inside the function body was offered either"
    return None


def case_a_mutant_is_applied_on_the_tree_not_the_text(t):
    """A textual replacement hits the operator inside a string on the same line.

    `return a + b  # use + not -` has three `+` in it and only one of them is
    the operator. Replacing text produces a mutant that compiles, runs, and
    tests something other than what the report says it tested."""
    src = 'def f(a, b):\n    return a + b  # always + here, never -\n'
    ms = [m for m in mutate_mod.candidates("f.py", src)
          if m.op == "AOR" and m.after == "-"]
    if not ms:
        return "no AOR mutant was generated to apply"
    got = run_mod.apply(src, ms[0])
    if got is None:
        return "the mutation could not be applied at all"
    if "a - b" not in got:
        return f"the operator was not the thing that changed: {got!r}"
    return None


def case_an_unplaceable_mutant_is_counted_as_neither(t):
    """A mutation that could not be applied did not happen.

    Scoring it killed inflates the result and scoring it survived deflates it.
    It has to come back as its own thing so the denominator stays honest."""
    src = "def f(a, b):\n    return a + b\n"
    ms = mutate_mod.candidates("f.py", src)
    if not ms:
        return "nothing generated"
    ghost = mutate_mod.Mutant("f.py", 999, 0, "AOR", "+", "-")
    if run_mod.apply(src, ghost) is not None:
        return "a mutation at a line that does not exist was applied anyway"
    return None


def case_a_redundant_short_circuit_guard_is_suppressed(t):
    """The one rule here that came from our own feedback, not the appendix.

    A second pass over 13 surviving mutants in `tenacity` judged 7
    unproductive, and 4 of those 7 were one pattern written twice: an
    `if acc: break` under `acc = acc or f(x)`. The `or` has already stopped
    evaluating, so neither the guard nor the break can change what is
    returned; every mutant on those lines is equivalent.

    That is the paper's own process -- "if we decide a certain mutation is not
    productive ... the rule is added to the expert function" -- and it is the
    only rule in `arid.py` not transcribed from Appendix A, which is why it
    needs a case of its own.

    The second half is what keeps it from becoming a rule that suppresses
    every loop: a guard whose condition is computed *inside* the loop decides
    something, and must survive."""
    redundant = ("def f(rs):\n"
                 "    result = False\n"
                 "    for r in rs:\n"
                 "        result = result or check(r)\n"
                 "        if result:\n"
                 "            break\n"
                 "    return result\n")
    hit = arid_mod.arid_lines(redundant)
    if hit.get(5) is None or hit[5][0] != "SHORTCIRCUIT":
        return (f"the redundant `if result: break` was not suppressed: "
                f"{hit.get(5)}")

    mirror = redundant.replace("result = False", "result = True").replace(
        "result or check(r)", "result and check(r)").replace(
        "if result:", "if not result:")
    if (arid_mod.arid_lines(mirror).get(5) or ("", ""))[0] != "SHORTCIRCUIT":
        return "the `and`/`not` mirror of the same pattern was not suppressed"

    # A guard that decides something must survive, or this rule has silently
    # turned off mutation of every loop in every repository.
    load_bearing = ("def f(items):\n"
                    "    found = False\n"
                    "    for i in items:\n"
                    "        found = check(i)\n"
                    "        if found:\n"
                    "            break\n"
                    "    return found\n")
    if arid_mod.arid_lines(load_bearing).get(5) is not None:
        return ("a guard whose condition is computed inside the loop was "
                "suppressed — that guard decides when the loop stops")

    # And the rule must declare itself unsound, because the loop body could
    # have a side effect the early exit skips.
    if arid_mod.RULES["SHORTCIRCUIT"]["sound"]:
        return "SHORTCIRCUIT claims to be sound; it cannot see side effects"
    return None


def case_productivity_is_reported_with_its_judge_named(t):
    """The paper's 82% comes from the developers who wrote the lines. Ours
    does not, and the page has to say so.

    A number that looks like theirs, computed from a different judge, and
    printed without that difference attached, is the most misleading thing this
    whole module could produce."""
    run = {"rows": [
        {"path": "a.py", "line": 2, "operator": "AOR", "before": "+",
         "after": "-", "verdict": "survived", "detail": ""},
        {"path": "a.py", "line": 5, "operator": "ROR", "before": "<",
         "after": "<=", "verdict": "survived", "detail": ""},
        {"path": "a.py", "line": 9, "operator": "SBR", "before": "x = 1",
         "after": "(deleted)", "verdict": "killed", "detail": ""},
    ]}
    g = judge_mod.grade(run, {"verdicts": [
        {"id": 0, "verdict": "productive", "why": "the boundary is a promise"},
        {"id": 1, "verdict": "unproductive", "why": "off by one epsilon"}]})
    if g["survivors"] != 2:
        return f"killed mutants leaked into the judged set: {g['survivors']}"
    if abs(g["productivity"] - 0.5) > 1e-9:
        return f"productivity computed as {g['productivity']}, not 0.5"
    if "agent" not in g["judge"] or "wrote" not in g["judge"]:
        return "the judge is not named in the output"
    text = judge_mod.render(g)
    if "70" not in text or "MISSED" not in text:
        return "the bar and whether it was met are not both printed"
    return None


# --------------------------------------------------------------------------
# the second injection, on the page
# --------------------------------------------------------------------------

_DFX = {"replayable": 0, "fix_no_test": 0, "has_test_files": True,
        "shallow": False}


def _mutable_repo(t):
    """A repository with one covered line the tests assert about, and one they
    only execute. The second is what a mutant survives on."""
    repo(t)
    put(t, "app.py",
        "def add(a, b):\n"
        "    return a + b\n\n"
        "def describe(n):\n"
        "    width = n * 2\n"
        "    return 'n'\n")
    put(t, "suite.py",
        "import sys, os\n"
        "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
        "from app import add, describe\n"
        "assert add(2, 3) == 5\n"
        "describe(4)\n"
        "sys.exit(0)\n")
    commit(t, "feat: an app and a suite")
    return [sys.executable, "suite.py"]


# --------------------------------------------------------------------------
# coverage: what the ladder cannot speak about
# --------------------------------------------------------------------------

def _covered_repo(t, calls):
    """One decision with two conditions, one function nothing calls, and a
    suite that makes exactly `calls`."""
    repo(t)
    put(t, "app.py",
        "def gate(a, b):\n"
        "    if a and b:\n"
        "        return 'both'\n"
        "    return 'no'\n"
        "\n"
        "\n"
        "def nobody_calls_this(x):\n"
        "    if x > 0:\n"
        "        return 1\n"
        "    return 2\n")
    put(t, "suite.py",
        "import sys, os\n"
        "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
        "from app import gate\n"
        + "".join(f"gate({a}, {b})\n" for a, b in calls)
        + "sys.exit(0)\n")
    commit(t, "feat: a gate")
    return [sys.executable, "suite.py"]


def case_a_short_circuited_condition_is_absent_not_false(t):
    """The one detail the whole MC/DC measurement rests on.

    `a and b` does not evaluate `b` when `a` is false. If the recorder writes
    False for the condition that never ran, the two observations then differ in
    *two* places instead of one, no independence pair is found, and `a` is
    reported as untested when it was tested perfectly well. The failure is
    silent and it makes the measurement pessimistic in exactly the cases that
    short-circuit most.

    So: call with a=False (b never evaluated) and a=True,b=True. `a` must come
    out independent -- and it only can if the skipped `b` was recorded as
    absent rather than as false."""
    cmd = _covered_repo(t, [("False", "True"), ("True", "True")])
    work = os.path.join(t, "..", "cw-" + os.path.basename(t))
    r, why = cover_mod.assess(t, cmd, work)
    if r is None:
        return f"coverage could not be measured at all: {why}"
    gate = [x for x in r["not_independent"] if x["line"] == 2]
    if not gate:
        return "the two-condition decision was not reported at all"
    if gate[0]["independent"] != 1:
        return (f"`a` was not shown independent ({gate[0]['independent']} of "
                f"{gate[0]['conditions']}) — a condition that short-circuited "
                f"away is being recorded as false rather than as absent")
    return None


def case_mcdc_finds_a_condition_branch_coverage_calls_covered(t):
    """Why the third criterion is worth its instrumentation.

    With calls (False,True) and (True,True) the decision `a and b` goes both
    ways, so branch coverage is satisfied and says the line is fine. But `b` is
    true every single time it is reached: you could delete it and no test would
    notice, which is precisely a mutant we would generate. MC/DC is the
    criterion that can say so, and it says it without running the suite once
    per mutant."""
    cmd = _covered_repo(t, [("False", "True"), ("True", "True")])
    work = os.path.join(t, "..", "cw-" + os.path.basename(t))
    r, why = cover_mod.assess(t, cmd, work)
    if r is None:
        return f"coverage could not be measured at all: {why}"
    gate = [x for x in r["not_independent"] if x["line"] == 2]
    if not gate:
        return "MC/DC did not flag the decision at all"
    if not gate[0]["both_ways"]:
        return ("the fixture was supposed to satisfy branch coverage on this "
                "decision and did not, so the case proves nothing")
    if gate[0]["missing"] != 1:
        return (f"branch coverage is satisfied and MC/DC reports "
                f"{gate[0]['missing']} untested condition(s), expected 1")
    return None


def case_a_decision_no_test_reaches_is_not_the_same_as_one_way(t):
    """Two findings with two different fixes, and one number would hide both.

    A decision nothing reaches needs a test that gets there at all. A decision
    reached that only ever went one way needs a test that gets there with the
    other answer. Reporting them as a single branch percentage leaves the
    reader with neither."""
    cmd = _covered_repo(t, [("False", "True"), ("True", "True")])
    work = os.path.join(t, "..", "cw-" + os.path.basename(t))
    r, why = cover_mod.assess(t, cmd, work)
    if r is None:
        return f"coverage could not be measured at all: {why}"
    cold = [x for x in r["unreached"] if x["line"] == 8]
    if not cold:
        return ("the decision inside the function nothing calls was not "
                "reported as unreached")
    if [x for x in r["one_way"] if x["line"] == 8]:
        return "a decision nothing reaches was also counted as one-way"
    st = r.get("statements")
    if not st or not st["files_with_none_total"] == 0:
        pass          # app.py IS partly executed; only the function is dark
    return None


def case_an_assertion_is_not_a_decision(t):
    """A green suite makes every assertion in the repository one-way.

    An assertion that has gone both ways is a test run that failed. Counting
    assertions as decisions would therefore report every correct assertion as
    an uncovered branch -- a denominator made entirely of noise, and one that
    gets worse the more carefully a repository asserts."""
    src = ("def f(x):\n"
           "    assert x is not None\n"
           "    if x > 0:\n"
           "        return 1\n"
           "    return 0\n")
    got = cover_mod.decisions(ast.parse(src))
    if len(got) != 1:
        return (f"{len(got)} decision(s) found in a function with one `if` "
                f"and one `assert` — the assertion is being counted")
    return None


def case_the_instrument_leaves_the_tree_as_it_found_it(t):
    """It rewrites every source file and drops a recorder module in the root.

    Both have to be gone afterwards, on the failure path as well as the happy
    one. An instrument that leaves its own scaffolding behind has changed the
    repository it was pointed at, and the next thing to read that tree -- the
    mutation pass, the replay, a person -- sees the instrument instead of the
    subject."""
    cmd = _covered_repo(t, [("True", "True")])
    before = git(["status", "--porcelain"], t).stdout
    work = os.path.join(t, "..", "cw-" + os.path.basename(t))
    r, _why = cover_mod.assess(t, cmd, work)
    if r is None:
        return "coverage could not be measured, so nothing was proven"
    after = git(["status", "--porcelain"], t).stdout
    if after != before:
        return f"the tree was left modified: {after.strip()[:200]!r}"
    if os.path.exists(os.path.join(t, cover_mod.RECORDER + ".py")):
        return "the recorder module was left in the repository root"
    with open(os.path.join(t, "app.py"), encoding="utf-8") as fh:
        if "_ASSESS_C" in fh.read():
            return "an instrumented source file was left in place"
    return None


def case_mutation_reaches_the_page_only_when_asked(t):
    """`--mutate` is off by default, and off has to mean the page says so.

    The replay's cost is bounded by the page -- three defects, three suite
    runs. Mutation's is chosen by the caller, so it is the one thing here that
    must be asked for. What must NOT happen is the page quietly reading the
    same either way: a dimension that shows the same rows whether or not the
    expensive half ran is a dimension nobody can tell has abstained."""
    cmd = _mutable_repo(t)
    off = dim_mod.change_validation(_DFX, None, "", catch_mod.LADDER)
    how = [r for r in off["rows"] if r["label"] == "how the defect got in"]
    if not how or not how[0]["value"].startswith("1 way"):
        return f"without --mutate the page does not say one injection ran: {how}"

    run, why = run_mod.assess(t, 6, work=os.path.join(t, "..", "w-" +
                                                      os.path.basename(t)),
                              command=cmd)
    if run is None:
        return f"the fixture could not be mutated at all: {why}"
    on = dim_mod.change_validation(_DFX, None, "", catch_mod.LADDER, run)
    how = [r for r in on["rows"] if r["label"] == "how the defect got in"]
    if not how or not how[0]["value"].startswith("2 ways"):
        return f"with mutation the page still reports one injection: {how}"

    # The replay abstained in both calls. Mutation walked the ladder, so the
    # dimension WAS measured -- reporting it as unmeasured would throw away
    # something somebody paid for.
    if on["state"] != "measured":
        return (f"mutation walked the ladder and the dimension still reports "
                f"{on['state']!r}")
    if off["state"] == "measured":
        return "the dimension claims a measurement with neither injection run"

    # And off by default has to be the CLI's answer too, not only this
    # function's. The test command has to be supplied here or the check is
    # vacuous: the ecosystem table does not recognise this fixture, mutation
    # would abstain for that reason instead of for being switched off, and a
    # planted `default=8` sailed straight through this case.
    out = subprocess.run(
        [sys.executable, os.path.join(HERE, "factsheet.py"), "--root", t,
         "--no-full", "--test-command", " ".join(cmd)],
        capture_output=True, text=True, timeout=600)
    if "2 ways" in out.stdout:
        return "the default run mutated the repository without being asked"
    if "1 way" not in out.stdout:
        return "the default run says nothing about how a defect got in"
    return None


def case_a_mutant_walks_the_same_ladder_as_a_real_defect(t):
    """The whole point of the second injection, and what it got wrong first.

    A mutant was scored `killed` or `survived` -- did the test suite notice --
    which is a narrower question than this dimension's and answers it at one
    rung out of five. But a mutant is a change to a file, so every moment that
    can see a change can see it: a PreToolUse hook that refuses the write is a
    defect that never reached the disk, not a defect the suite missed.

    So the mutant walks the same five rungs a defect from the repository's own
    history walks, and both are counted in one ladder."""
    cmd = _mutable_repo(t)
    work = os.path.join(t, "..", "w-" + os.path.basename(t))

    # No hooks: the suite is the first thing that can catch anything.
    plain, why = run_mod.assess(t, 6, work=work + "-a", command=cmd)
    if plain is None:
        return f"the fixture could not be mutated at all: {why}"
    if not plain["ladder"].get("local-suite"):
        return (f"nothing reached the suite rung on a fixture whose tests do "
                f"assert: {plain['ladder']}")
    if plain["ladder"].get("before-write"):
        return "a rung fired with no hooks wired at all"

    # Now wire a hook that refuses every write. The same mutants must now be
    # caught at the TOP of the ladder, not at the suite.
    hook_script(t, ".claude/block.py", BLOCKER)
    commit(t, "chore: a hook that refuses writes")
    hooked, why = run_mod.assess(t, 6, work=work + "-b", command=cmd)
    if hooked is None:
        return f"the fixture stopped being mutable once a hook existed: {why}"
    if not hooked["ladder"].get("before-write") and not hooked["false_block"]:
        return (f"a hook that refuses every write caught nothing: "
                f"{hooked['ladder']}")
    return None


def case_a_hook_that_refuses_everything_gets_no_rung(t):
    """A guard that says no to the fix as well has discriminated nothing.

    `catch.false_block` asks this of a replayed defect, and it has to be asked
    of a mutant too. Otherwise the best rung on the ladder goes to the least
    discriminating check in the repository, and a repository could top the
    measurement by refusing all edits."""
    cmd = _mutable_repo(t)
    hook_script(t, ".claude/block.py", BLOCKER)
    commit(t, "chore: a hook that refuses writes")
    r, why = run_mod.assess(t, 6, work=os.path.join(t, "..", "w-" +
                                                    os.path.basename(t)),
                            command=cmd)
    if r is None:
        return f"nothing could be mutated: {why}"
    if not r["false_block"]:
        return ("a hook that refuses the original line too was not recorded "
                "as a false block")
    if r["ladder"].get("before-write"):
        return ("a hook that refuses everything was still given the top rung "
                "of the ladder")
    return None


def case_an_uncaught_mutant_is_pending_until_it_is_judged(t):
    """`never` is only a failure if the thing never caught was worth catching.

    A mutant nothing catches is not yet a defect: the paper's own figure says
    roughly three survivors in ten are lines nothing should assert about. So
    an unjudged one is reported `pending` and is NOT parked at `never` --
    counting it there would make a repository look worse for having bought a
    measurement nobody has finished reading. The agent's verdict is what turns
    it into a defect, or removes it from the count entirely."""
    cmd = _mutable_repo(t)
    run, why = run_mod.assess(t, 6, work=os.path.join(t, "..", "w-" +
                                                      os.path.basename(t)),
                              command=cmd)
    if run is None:
        return f"nothing could be mutated: {why}"
    if not run["survived"]:
        return ("nothing reached `never` on a fixture built to have a line "
                "the tests execute without asserting about")

    counts, pending, real, dropped = dim_mod.mutant_ladder(run, None)
    if counts.get("never"):
        return (f"{counts['never']} unjudged mutant(s) were parked at `never` "
                f"before anybody said they were defects")
    if pending != run["survived"]:
        return f"{run['survived']} uncaught, but {pending} reported pending"

    ids = [i for i in range(run["survived"])]
    yes = {"verdicts": [{"id": i, "verdict": "productive", "why": "real"}
                        for i in ids]}
    counts, pending, real, dropped = dim_mod.mutant_ladder(
        run, judge_mod.grade(run, yes))
    if counts.get("never") != run["survived"] or pending:
        return (f"judged real, they did not land at `never`: "
                f"{counts.get('never')} never, {pending} pending")

    no = {"verdicts": [{"id": i, "verdict": "unproductive", "why": "no test"}
                       for i in ids]}
    counts, pending, real, dropped = dim_mod.mutant_ladder(
        run, judge_mod.grade(run, no))
    if counts.get("never") or pending:
        return ("a change judged not worth a test still counts against the "
                "repository")
    if len(dropped) != run["survived"]:
        return f"{len(dropped)} dropped, expected {run['survived']}"
    return None


def case_a_caveat_outranks_the_figure_it_qualifies(t):
    """A ladder taken over a flaky suite is not a ladder.

    Both caveats are about the same failure: the mutation numbers look like
    the paper's and are not comparable to them. Printing them below the rows
    they disqualify invites exactly the comparison they exist to refuse."""
    run = {"killed": 8, "survived": 2, "generated": 10, "suppressed": 3,
           "broken": 0, "timeout": 0, "unplaceable": 0, "survivability": 0.2,
           "seconds": 4.0, "command": "pytest", "flaky": True,
           "false_block": 0,
           "ladder": {"before-write": 0, "same-turn": 0, "local-suite": 8,
                      "ci": 0, "never": 2},
           "coverage": "NOT available — the covered-line restriction was "
                       "dropped",
           "rows": [{"verdict": "survived", "path": "a.py", "line": 3,
                     "operator": "AOR", "before": "a + b", "after": "a - b"}]}
    rows = dim_mod.mutation_rows(run, catch_mod.LADDER, None)
    labels = [r["label"] for r in rows]
    body = labels.index("mutants nothing caught, awaiting judgement")
    for caveat in ("!! the suite is flaky", "!! coverage was not available"):
        if caveat not in labels:
            return f"the page does not carry the caveat {caveat!r} at all"
        if labels.index(caveat) > body:
            return f"{caveat!r} is printed below the rows it disqualifies"
        if [r for r in rows if r["label"] == caveat][0]["flag"] != "warn":
            return f"{caveat!r} is not flagged, so it reads as a footnote"

    clean = dict(run, flaky=False, coverage="measured — 40 line(s) executed")
    labels = [x["label"] for x in
              dim_mod.mutation_rows(clean, catch_mod.LADDER, None)]
    if [x for x in labels if x.startswith("!!")]:
        return f"a clean run still prints a caveat: {labels}"
    return None


def case_the_brief_asks_about_the_whole_ladder(t):
    """What the agent is judging changed, so what it is told had to change.

    It used to be handed changes "the suite did not notice". It is now handed
    changes NOTHING caught -- no hook before the write, no hook after, not the
    suite, not CI -- and told that its verdict decides whether each one counts
    as a defect at all. An agent judging the narrower question would be
    answering about a measurement that no longer exists."""
    cmd = _mutable_repo(t)
    run, why = run_mod.assess(t, 6, work=os.path.join(t, "..", "w-" +
                                                      os.path.basename(t)),
                              command=cmd)
    if run is None:
        return f"nothing could be mutated: {why}"
    got, _why = judge_mod.brief(run, t)
    if got is None or not got["index"]:
        return "no brief was produced for the uncaught changes"
    if "def " not in got["prompt"]:
        return ("the brief does not carry the enclosing code, so the judging "
                "pass would be guessing from a diff line")
    low = got["prompt"].lower()
    if "nothing in this repository caught" not in low:
        return "the brief still describes the narrower suite-only question"
    if "leaves the measurement" not in low:
        return ("the brief does not tell the judge that its verdict decides "
                "whether the change is a defect at all")
    return None


def case_an_unanswered_mutant_moves_the_score_neither_way(t):
    """Silence must not be scoreable.

    If unanswered counted as unproductive, a judge could raise productivity by
    answering less; if it counted as productive, by answering less still. Both
    make the number a property of the judge's diligence rather than of the
    mutants."""
    run = {"rows": [{"path": "a.py", "line": i, "operator": "AOR",
                     "before": "+", "after": "-", "verdict": "survived",
                     "detail": ""} for i in range(4)]}
    g = judge_mod.grade(run, {"verdicts": [
        {"id": 0, "verdict": "productive", "why": "x"}]})
    if g["judged"] != 1 or g["unanswered"] != 3:
        return f"judged={g['judged']} unanswered={g['unanswered']}, want 1 and 3"
    if g["productivity"] != 1.0:
        return (f"productivity {g['productivity']} — the three unanswered "
                f"mutants moved a score they should not touch")
    return None


# --------------------------------------------------------------------------
# value: what the standing context is spent ON
# --------------------------------------------------------------------------

def case_a_supplied_test_command_is_used(t):
    """The ecosystem table is a fast path, not the only path.

    It knows a handful of conventions -- a `tests/` directory plus a packaging
    marker, a `package.json`, a `Cargo.toml`. Measured: of five real Python
    repositories cloned to test the mutation work, it produced a green suite
    for **one**. This repository is another miss; its suites are `selftest.py`
    scripts, so dimension 2 abstained on its own author while a perfectly good
    suite sat in the tree.

    Unit tests may also simply not exist, and reporting that is correct. What
    must not happen is abstaining because a table did not recognise a
    convention, when an agent could have read the CI file and said."""
    repo(t)
    put(t, "app/calc.py", "def add(a, b):\n    return a - b\n")
    # Named test-shaped so the history miner recognises the fix as one that
    # touched a test; kept OUT of a `tests/` directory so the ecosystem table
    # still cannot guess how to run it. The fixture has to defeat exactly one
    # of the two, or it is not testing what it says.
    put(t, "test_calc.py",
        "import sys, os\n"
        "sys.path.insert(0, os.path.dirname(__file__))\n"
        "from app.calc import add\n"
        "sys.exit(0 if add(2, 3) == 5 else 1)\n")
    put(t, "app/__init__.py", "")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "feat: a calculator"], t)
    put(t, "app/calc.py", "def add(a, b):\n    return a + b\n")
    put(t, "test_calc.py",
        open(os.path.join(t, "test_calc.py")).read()
        + "sys.exit(0 if add(1, 1) == 2 else 1)\n")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "fix: add was subtracting"], t)

    # The table cannot see this suite: no tests/ directory, no packaging marker.
    _eco, guessed = catch_mod.find(t)
    if guessed is not None:
        return (f"the fixture was supposed to defeat the ecosystem table and "
                f"did not: it guessed {guessed}")

    work = os.path.join(t, "..", "work-" + os.path.basename(t))
    r, why = catch_mod.assess(t, 1, work)
    if r is not None:
        return "the table found a command it should not have"
    if "--test-command" not in why:
        return (f"the abstention does not mention how to supply a command: "
                f"{why!r}")

    r, why = catch_mod.assess(t, 1, work + "-2",
                              command=[sys.executable, "test_calc.py"])
    if r is None:
        return f"a supplied test command was not used: {why}"
    if not r["rows"]:
        return "the command was accepted and nothing was replayed"
    return None


def case_a_prohibition_a_guard_enforces_is_named(t):
    """The sharpest row on dimension 5, and it needs dimension 1 to exist.

    A rule saying *never force-push to main* in a repository whose hooks were
    **measured refusing** force-pushes to main is paying tokens on every turn
    to restate a thing that cannot happen. The guard is strictly better: not
    optional, does not depend on the agent having read anything, costs nothing
    until it fires.

    The cross-reference is to what dimension 1 *measured*, not to what the
    settings claim. A prohibition restating a guard that does not fire is the
    one sentence on the floor that is definitely earning its place."""
    repo(t)
    put(t, "CLAUDE.md",
        "# Rules\n\n"
        "Never force-push to main. It overwrites other people's commits.\n\n"
        "Always run the tests before you open a pull request.\n\n"
        "The billing service talks to the ledger over gRPC.\n")
    stopped = {"rows": [{"probe": "force-push the default branch",
                         "stopped": True, "false_block": False}]}
    guards = value_mod.guards_from_blast(stopped)
    if "force push" not in guards:
        return f"dimension 1's refusal did not map to a rule topic: {guards}"
    r = value_mod.assess(t, guards)
    if not r["already_enforced"]:
        return ("a prohibition against the exact thing the hooks were measured "
                "refusing was not reported")

    # And a guard that does NOT fire must leave the sentence alone.
    open_ = {"rows": [{"probe": "force-push the default branch",
                       "stopped": False, "false_block": False}]}
    r2 = value_mod.assess(t, value_mod.guards_from_blast(open_))
    if r2["already_enforced"]:
        return ("a prohibition was called redundant while the guard it "
                "restates does not actually refuse anything")

    # A guard that refuses the legitimate action too has discriminated nothing
    # and must not count as enforcement either.
    false = {"rows": [{"probe": "force-push the default branch",
                       "stopped": True, "false_block": True}]}
    if value_mod.guards_from_blast(false):
        return "a guard that refuses everything was counted as enforcement"
    return None


def case_prohibitions_and_requirements_are_counted_apart(t):
    """Both are legitimate; they are not doing the same work.

    A prohibition earns its place against a mistake somebody actually makes. A
    requirement is working every time the thing it requires comes up. A floor
    that is nine-tenths `don't` is usually a list of one-off incidents nobody
    deleted, and a single token count cannot see the difference."""
    repo(t)
    put(t, "CLAUDE.md",
        "Never commit generated files.\n\n"
        "Do not edit the vendored code.\n\n"
        "Always regenerate the client after changing the schema.\n\n"
        "The parser lives in src/parse and is generated from grammar.ebnf.\n")
    r = value_mod.assess(t, ())
    if r is None:
        return "nothing was read from a CLAUDE.md that is plainly there"
    if r["prohibitions"] < 2:
        return f"two prohibitions were not counted: {r['kinds']}"
    if r["requirements"] < 1:
        return f"the requirement was not counted: {r['kinds']}"
    if r["kinds"].get("statement", 0) < 1:
        return ("the plain statement of fact was classified as an "
                "instruction — most of a good CLAUDE.md is neither")
    return None


def case_a_command_in_a_fence_is_not_a_prohibition(t):
    """A fenced block shows what to do; it does not instruct.

    A document demonstrating `git push --force` inside a code block would
    otherwise be classified as being made of prohibitions, which turns every
    well-written guide into a warning."""
    repo(t)
    put(t, "CLAUDE.md",
        "# How to release\n\n"
        "```bash\n"
        "# never do this by hand, and do not skip the checks\n"
        "git push --force origin main\n"
        "```\n\n"
        "Run the release script.\n")
    r = value_mod.assess(t, ())
    if r is None:
        return "nothing was read"
    for row in value_mod.classify(open(os.path.join(t, "CLAUDE.md")).read()):
        if "--force" in row["text"] or "never do this by hand" in row["text"]:
            return f"a fenced line was classified as prose: {row['text']!r}"
    return None


def case_a_path_scoped_sentence_on_the_floor_is_flagged(t):
    """Not wrong — misfiled, and the distinction is the whole row.

    A paragraph about the frontend build, paid for on every turn including the
    ones that never leave the database layer. The same words under a
    path-scoped rule cost nothing until somebody touches that path."""
    repo(t)
    put(t, "CLAUDE.md",
        "In `frontend/src/` the components must be function components.\n\n"
        "Write commit messages in the imperative mood.\n")
    r = value_mod.assess(t, ())
    if not r["path_scoped_but_loaded"]:
        return "a sentence about one directory was not flagged as misfiled"
    hit = r["path_scoped_but_loaded"][0]
    if "frontend" not in hit["about"]:
        return f"the wrong path was named: {hit['about']!r}"
    if len(r["path_scoped_but_loaded"]) > 1:
        return ("the general rule about commit messages was also flagged — "
                "a row that fires on everything says nothing")
    return None


def case_a_scoped_rule_file_is_not_on_the_floor(t):
    """A rule with a path glob is parked, and parked is not the bill.

    This is 0024's whole point measured from the other side: text that arrives
    only when asked for is not what dimension 5 is about, and counting it would
    make moving something off the floor look like no change at all."""
    repo(t)
    put(t, "CLAUDE.md", "Always write a test.\n")
    put(t, ".claude/rules/frontend.md",
        "---\npaths: [\"frontend/**\"]\n---\n"
        "Never use class components. Do not import from src/legacy.\n")
    r = value_mod.assess(t, ())
    if any("frontend.md" in f for f in r["files"]):
        return ("a path-scoped rule was charged to the floor — it arrives "
                "only when somebody touches that path")
    put(t, ".claude/rules/always.md", "Never commit secrets.\n")
    r2 = value_mod.assess(t, ())
    if not any("always.md" in f for f in r2["files"]):
        return "an unconditional rule was NOT charged to the floor"
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


def _memwork(t):
    w = os.path.join(t, "..", "memwork")
    w = os.path.abspath(w)
    shutil.rmtree(w, ignore_errors=True)
    os.makedirs(w)
    return w


def case_the_probe_cannot_reach_the_history(t):
    """The one cheat that would look like a brilliant result.

    Every micro question is "given this commit subject, which files would you
    change" -- and one `git log --grep` answers all of them perfectly. A rule
    saying not to look could be broken silently, and the run would come back
    with a flawless score that meant nothing. So the history is not forbidden,
    it is absent: both copies are made without `.git`, and the probe agent is
    given no Bash to reach one with."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    commit(t, "feat: thing")
    put(t, "app.py", "x = 2\n")
    commit(t, "fix: thing was wrong")

    w = _memwork(t)
    brief = memory_mod.prepare(t, w)
    if brief is None:
        return "the history could not be read in a repository that has one"
    for name in ("with", "without"):
        tree = os.path.join(w, name)
        if not os.path.isdir(tree):
            return f"the {name!r} copy was not made"
        for here, dirs, _files in os.walk(tree):
            if ".git" in dirs or os.path.basename(here) == ".git":
                return (f"the {name!r} copy carries a .git directory — one "
                        f"`git log --grep` answers every question in it")
    if not brief["micro"]:
        return "no question was asked of a repository with a focused commit"
    return None


def case_the_second_copy_has_no_memory(t):
    """The measurement is a difference, so the second copy must really differ.

    Everything the repository keeps in order to explain itself comes out --
    including a CLAUDE.md nested three directories down, which is memory
    wherever it sits. If the strip misses one, the two runs are the same run
    and the difference is zero for the wrong reason."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    put(t, "CLAUDE.md", "# the repo\n")
    put(t, "src/deep/CLAUDE.md", "# a nested one\n")
    put(t, ".claude/rules/style.md", "always do the thing\n")
    put(t, "README.md", "# readme\n")
    put(t, ".gitignore", "build/\n")
    commit(t, "feat: thing")
    # Untracked and ignored: neither is this repository.
    put(t, "node_modules/dep/x.js", "// somebody else's code\n")
    put(t, "build/out.js", "// generated\n")
    # Not in any skip list, and not in the repository either. Only asking git
    # what it tracks keeps this out, so this is the file that tells the two
    # mechanisms apart.
    put(t, "scratch/notes.md", "my own working notes\n")

    w = _memwork(t)
    memory_mod.prepare(t, w)
    kept, stripped = os.path.join(w, "with"), os.path.join(w, "without")
    for rel in ("CLAUDE.md", "src/deep/CLAUDE.md", ".claude/rules/style.md"):
        if not os.path.exists(os.path.join(kept, rel)):
            return f"{rel} is missing from the copy that should keep it"
        if os.path.exists(os.path.join(stripped, rel)):
            return (f"{rel} survived into the copy with no memory — the two "
                    f"runs would be the same run")
    if not os.path.exists(os.path.join(stripped, "README.md")):
        return "the README was stripped; only what explains the repo comes out"
    if not os.path.exists(os.path.join(stripped, "app.py")):
        return "the code was stripped; there would be nothing left to find"

    # Only what git tracks. Walking the tree instead copies build output,
    # dependencies, and — on this project — 25 cloned repositories under
    # `eval/.work/` that are somebody else's code entirely. A probe reading
    # those answers questions about the wrong repository, and both live probe
    # runs reported having to exclude them from every search.
    for tree in (kept, stripped):
        if os.path.exists(os.path.join(tree, "node_modules", "dep", "x.js")):
            return ("an untracked dependency was copied into the probe's "
                    "tree — it would be answering about somebody else's code")
        if os.path.exists(os.path.join(tree, "build", "out.js")):
            return "ignored build output was copied into the probe's tree"
        if os.path.exists(os.path.join(tree, "scratch", "notes.md")):
            return ("an untracked file with no give-away name was copied — "
                    "the copy is being walked rather than asked of git")
    return None


def case_only_a_focused_commit_becomes_a_question(t):
    """"Did you find the right files?" needs there to be right files.

    A commit touching thirty files is answered correctly by naming almost any
    of them, so it is not a question. Dimensions 2 and 3 draw this line
    already; dimension 4 not drawing it is the bug that made every
    repository's biggest router look like its most reworked file."""
    repo(t)
    names = [f"m{i}.py" for i in range(8)]
    for n in names:
        put(t, n, "x = 1\n")
    commit(t, "feat: everything at once")
    put(t, "m0.py", "x = 2\n")
    commit(t, "fix: just this one")

    picked = memory_mod.pick_commits(t, k=5)
    subjects = [c["subject"] for c in picked]
    if "feat: everything at once" in subjects:
        return ("an eight-file commit became a question; naming almost any "
                "file would answer it")
    if "fix: just this one" not in subjects:
        return f"the focused commit was not asked about: {subjects}"
    return None


def case_a_pull_request_number_is_not_part_of_the_question(t):
    """`(#123)` is a handle, not a description.

    A squash merge leaves it on the subject, and a probe that cannot reach the
    history cannot look it up — so it is either dead weight or, worse, a way to
    tell two commits apart without understanding either. A live probe run
    reported doing exactly that."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    commit(t, "feat: thing")
    put(t, "app.py", "x = 2\n")
    commit(t, "fix: the thing was wrong (#412)")
    picked = memory_mod.pick_commits(t, k=1)
    if not picked:
        return "no question was asked at all"
    if "#412" in picked[0]["subject"]:
        return f"the pull request number is still in the question: " \
               f"{picked[0]['subject']!r}"
    if picked[0]["subject"] != "fix: the thing was wrong":
        return f"the subject came out {picked[0]['subject']!r}"
    return None


def case_a_question_whose_answer_was_deleted_is_not_asked(t):
    """The probe reads the tree as it is. A commit whose files are gone has no
    answer in that tree, so grading against it would mark a correct reading
    wrong for not naming a file that does not exist."""
    repo(t)
    put(t, "gone.py", "x = 1\n")
    put(t, "here.py", "y = 1\n")
    commit(t, "feat: two files")
    put(t, "gone.py", "x = 2\n")
    commit(t, "fix: only the doomed one")
    os.remove(os.path.join(t, "gone.py"))
    commit(t, "chore: delete it")

    picked = memory_mod.pick_commits(t, k=5)
    for c in picked:
        if "gone.py" in c["files"]:
            return ("a commit was asked about whose only file no longer "
                    "exists — no answer to it can be right")
    return None


def case_the_difference_is_reported_as_rows_not_a_rate(t):
    """Three questions do not support a percentage.

    A sample of three reporting 66% is a number invented to look like a
    measurement. The rows say what happened, and can be argued with. The row
    also carries how many files the answer named, because recall alone is
    gameable: an answer listing two hundred files finds everything."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    put(t, "CLAUDE.md", "app.py is where the thing lives\n")
    commit(t, "feat: thing")
    put(t, "app.py", "x = 2\n")
    commit(t, "fix: the thing was wrong")

    w = _memwork(t)
    brief = memory_mod.prepare(t, w)
    qid = brief["micro"][0]["id"]
    got = memory_mod.compare(
        brief,
        {"answers": {qid: "I would change app.py"}, "tool_calls": {qid: 4}},
        {"answers": {qid: "maybe README.md or setup.py or main.py"},
         "tool_calls": {qid: 19}})

    if "rate" in got or "percent" in json.dumps(got):
        return "the comparison reported a rate from a sample of three"
    row = got["rows"][0]
    if row["with"]["found"] != 1:
        return f"naming the right file scored {row['with']['found']}, not 1"
    if row["without"]["found"] != 0:
        return (f"naming three wrong files scored "
                f"{row['without']['found']}, not 0")
    if row["without"]["named"] != 3:
        return (f"the row says {row['without']['named']} files were named, "
                f"not 3 — recall without that is gameable by listing the tree")
    if got["lift"] != 1:
        return f"the difference between the runs came out {got['lift']}, not 1"
    if not got["removed"]:
        return "the comparison does not say what was taken away"
    return None


def case_a_pipeline_that_runs_nothing_is_not_a_verdict(t):
    """Having CI and running the tests are different facts.

    A pipeline that installs, lints, builds and deploys goes green on every
    push while never invoking a suite, and from outside -- from the tick on the
    pull request -- it is indistinguishable from one that runs everything. This
    is the failure the dimension is named after, so it may not be scored by the
    existence of `.github/workflows/`."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    put(t, "tests/test_app.py", "def test_app():\n    assert True\n")
    put(t, ".github/workflows/ci.yml",
        "name: ci\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - uses: actions/checkout@v4\n"
        "      - run: pip install -r requirements.txt\n"
        "      - run: ruff check .\n"
        "      - run: python -m build\n")
    commit(t, "feat: ship it")

    ci = [r for r in dims_of(t, with_blast=False)[3]["rows"]
          if r["label"] == "CI runs the suite"][0]
    if ci["flag"] != "bad":
        return (f"a pipeline that lints and builds without running the suite "
                f"was flagged {ci['flag']!r}, not 'bad'")
    if "ci.yml" not in ci["note"]:
        return "the row does not name the pipeline file it read"

    # Now let it run something. A repository whose verdict is a script it
    # wrote itself says none of the tool names, and must still count -- the
    # alternative is scoring a repository down for not being shaped like ours.
    put(t, ".github/workflows/ci.yml",
        "name: ci\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: python3 tests/run_everything.py\n")
    put(t, "tests/run_everything.py", "print('ok')\n")
    commit(t, "ci: actually run the checks")
    ci = [r for r in dims_of(t, with_blast=False)[3]["rows"]
          if r["label"] == "CI runs the suite"][0]
    if ci["flag"] != "ok":
        return (f"a pipeline invoking the repository's own suite was flagged "
                f"{ci['flag']!r}: {ci['value']!r}")
    return None


def case_the_page_names_where_it_looked_for_tests(t):
    """A percentage over matches nobody named cannot be contradicted.

    Every repository puts its tests somewhere different -- `frontend/`,
    `backend/`, `packages/*/`. When the instrument reports only "17% of changes
    verified nothing", a reader has no way to tell a repository with poor
    coverage from one where the suite lives in a subtree the matcher missed:
    the two produce the same number. Naming the directories turns an invisible
    miss into a correction somebody can make."""
    repo(t)
    put(t, "backend/app.py", "x = 1\n")
    put(t, "backend/tests/test_app.py", "def test_app():\n    assert 1\n")
    put(t, "frontend/src/__tests__/App.spec.js", "it('works', () => {})\n")
    put(t, "node_modules/left-pad/test/index.test.js", "// not ours\n")
    commit(t, "feat: two halves")

    row = [r for r in dims_of(t, with_blast=False)[3]["rows"]
           if r["label"] == "where the verdict is written"][0]
    if "backend/tests" not in row["value"]:
        return f"a suite under backend/ was not named: {row['value']!r}"
    if "frontend/src/__tests__" not in row["value"]:
        return f"a suite under frontend/ was not named: {row['value']!r}"
    if "node_modules" in row["value"]:
        return "a dependency's own tests were counted as this repository's"
    if row["flag"] != "ok":
        return f"two real suites were flagged {row['flag']!r}"
    return None


def case_a_busy_file_is_not_mistaken_for_a_reworked_one(t):
    """Touching a file often is not the same as reworking it.

    A commit that says "fix" and changes thirty files also did four other
    things, and nothing in it can be attributed to any one of them. Without a
    size limit the row just ranks files by how busy they are -- the biggest
    router in the tree is touched by everything, so it tops the list in every
    repository, which is a fact about file size and not about rework. Measured
    on a real repository: 13 places "repaired twice" became 2, and 38 "checks
    with an incident behind them" became 4.

    Dimension 2 has drawn this line since the beginning. Dimension 4 read the
    same history without it."""
    repo(t)
    names = [f"m{i}.py" for i in range(8)]
    for n in names:
        put(t, n, "x = 1\n")
    commit(t, "init")
    for round_ in (2, 3):
        for n in names:
            put(t, n, f"x = {round_}\n")
        # A test file in the sweep too: a commit this broad touches something
        # that verifies AND something repaired earlier every single time, so
        # the "grew out of a repair" count is worthless without the same limit.
        put(t, "tests/test_m.py", f"def test_{round_}():\n    assert True\n")
        commit(t, f"fix: a sweep touching everything, round {round_}")

    rows = dims_of(t, with_blast=False)[3]["rows"]
    repeat = [r for r in rows if "repaired more than once" in r["label"]][0]
    if repeat["value"] != "0":
        return (f"two eight-file sweeps counted {repeat['value']} reworked "
                f"places; a commit that broad cannot be pinned on any one file")
    grew = [r for r in rows if "grew out of a repair" in r["label"]][0]
    if grew["value"] != "0":
        return (f"a sweep that happened to touch a test counted "
                f"{grew['value']} check(s) as growing out of a repair")

    # A focused repair to the same file twice IS rework, and must still count.
    put(t, "m0.py", "x = 9\n")
    commit(t, "fix: m0 specifically")
    put(t, "m0.py", "x = 10\n")
    commit(t, "fix: m0 again, properly this time")
    rows = dims_of(t, with_blast=False)[3]["rows"]
    repeat = [r for r in rows if "repaired more than once" in r["label"]][0]
    if repeat["value"] != "1":
        return (f"two focused repairs to one file counted "
                f"{repeat['value']}, not 1")

    # Now that m0.py is known-repaired, a sweep that happens to touch it and
    # a test must still not count. This is the half the earlier sweeps cannot
    # test: back there nothing had been repaired yet, so the count was zero
    # for the wrong reason.
    for n in names:
        put(t, n, "x = 20\n")
    put(t, "tests/test_broad.py", "def test_broad():\n    assert True\n")
    commit(t, "feat: a sweep that happens to touch m0 and a test")
    rows = dims_of(t, with_blast=False)[3]["rows"]
    grew = [r for r in rows if "grew out of a repair" in r["label"]][0]
    if grew["value"] != "0":
        return (f"an eight-file sweep touching one repaired file and one test "
                f"counted {grew['value']} check(s) as growing out of a repair")

    # A focused commit that adds a check beside ground repaired earlier is the
    # thing this dimension exists to find, and must still be found.
    put(t, "m0.py", "x = 11\n")
    put(t, "tests/test_m0.py", "def test_m0():\n    assert True\n")
    commit(t, "test: pin down what kept breaking in m0")
    rows = dims_of(t, with_blast=False)[3]["rows"]
    grew = [r for r in rows if "grew out of a repair" in r["label"]][0]
    if grew["value"] == "0":
        return ("a focused check added beside ground repaired twice was not "
                "counted as growing out of a repair")
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
    rows = dims_of(t, with_blast=False)[3]["rows"]
    repeat = [r for r in rows if "more than once" in r["label"]][0]
    if repeat["value"] != "1":
        return f"two repairs to one file counted as {repeat['value']!r}"
    return None


def case_an_unprobed_repository_abstains_rather_than_scoring_zero(t):
    """Nobody has spent the two agents, so nothing is known.

    A repository nobody has probed is not a repository an agent cannot
    navigate. Reporting it as zero would throw away exactly the repositories
    that read well, which is the same mistake as scoring a missing toolchain
    as a failing test suite."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    put(t, "CLAUDE.md", "# the repo\n")
    commit(t, "init")
    d4 = dims_of(t, with_blast=False)[4]
    if d4["name"] != "Repository Memory":
        return f"dimension 4 is called {d4['name']!r}"
    if d4["state"] != "abstained":
        return f"an unprobed repository was {d4['state']!r}, not 'abstained'"
    row = [r for r in d4["rows"] if "finding its way" in r["label"]]
    if not row:
        return "nothing says the probe was never run"
    if row[0]["flag"] in ("ok", "bad"):
        return (f"a measurement nobody made was flagged {row[0]['flag']!r} — "
                f"an abstention is not a verdict in either direction")
    return None


def case_the_memory_is_the_difference_not_the_thickness(t):
    """A repository is not graded on what it keeps, but on what removing it
    costs.

    Counting skills, hooks and rules would grade a repository on whether it
    adopted our conventions and would score installing this plugin as an
    improvement to the repository being measured. So a thick CLAUDE.md that
    changes nothing must come out bad, and a thin one that halves the search
    must come out ok."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    put(t, "CLAUDE.md", "# pages and pages that help nobody\n" * 200)
    commit(t, "init")
    probe_repo = load_probe().probe(t)
    log = history_mod.commits(t)

    def dim(with_found, without_found):
        got = {"rows": [{"subject": "fix: the thing",
                         "with": {"found": with_found, "of": 1, "named": 2,
                                  "tool_calls": 5},
                         "without": {"found": without_found, "of": 1,
                                     "named": 9, "tool_calls": 21}}],
               "lift": with_found - without_found,
               "removed": ["CLAUDE.md"]}
        return dim_mod.repository_memory(t, log, (), got)

    # Three outcomes, and the first live run of this dimension produced the
    # middle one -- which the first implementation called 'bad'. It is not:
    # the repository was navigable, and what carried the agent was
    # `docs/decisions/`, read rather than loaded. Marking that a failure would
    # penalise a repository for keeping its memory somewhere an agent has to
    # open.
    lifted = dim(1, 0)
    if lifted["rows"][-1]["flag"] != "ok":
        return "a CLAUDE.md that found a file reading alone missed scored badly"

    legible = dim(1, 1)
    if legible["rows"][-1]["flag"] == "ok":
        return ("a CLAUDE.md that changed nothing was credited as memory — "
                "thickness is not the measurement")
    if legible["rows"][-1]["flag"] == "bad":
        return ("a navigable repository was failed for keeping its memory "
                "somewhere read rather than loaded")

    lost = dim(0, 0)
    if lost["rows"][-1]["flag"] != "bad":
        return (f"a repository an agent could not navigate either way was "
                f"flagged {lost['rows'][-1]['flag']!r}, not 'bad'")
    nav = [r for r in lost["rows"] if "finding its way" in r["label"]][0]
    if nav["flag"] != "bad":
        return "nothing reported that the agent found no files at all"

    if "%" in json.dumps(lifted):
        return "a percentage was reported from a single question"
    if probe_repo is None:
        return "the probe could not read the repository"
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
    ("source files named in another language are not invisible",
     case_source_files_named_in_another_language_are_not_invisible),
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
    ("a check only one machine can run is not counted as coverage",
     case_a_check_only_its_author_can_run_is_not_coverage),
    ("an unverified change to the machinery itself is singled out",
     case_an_unverified_change_to_the_machinery_is_singled_out),
    ("a test suite is recognised by its name, wherever it lives",
     case_a_test_suite_is_recognised_by_its_name),
    ("the instrument leaves nothing behind in the repository it read",
     case_the_instrument_leaves_nothing_in_the_repository),
    ("a replay that could not run is not scored as a clean sheet",
     case_a_replay_that_could_not_run_is_not_a_clean_sheet),
    ("a rung says when a defect was caught, and also how long that took",
     case_a_rung_says_when_and_also_how_long),
    ("a CI time that cannot be read abstains rather than reading as fast",
     case_ci_seconds_that_cannot_be_read_are_not_zero),
    ("the page says there is only one way a defect is introduced",
     case_the_page_says_there_is_only_one_way_in),
    ("the defect replay runs unless it is explicitly refused",
     case_the_replay_runs_unless_it_is_refused),
    ("a markdown link to a file that is not there is proven wrong",
     case_a_link_to_nothing_is_proven_wrong),
    ("a link inside a fence is being shown, not followed",
     case_a_link_inside_a_fence_is_being_shown_not_followed),
    ("a historical document is not checked for staleness",
     case_a_historical_document_is_not_stale),
    ("two documents disagreeing is a candidate, never a finding",
     case_two_documents_disagreeing_is_a_candidate),
    ("thickness is a denominator and never a score",
     case_thickness_is_a_denominator_and_never_a_score),
    ("the candidate budget is shared, so no tier starves another",
     case_the_candidate_budget_is_shared_between_tiers),
    ("every operator offers every alternative, as Mothra does",
     case_every_operator_offers_every_alternative),
    ("ABS is not an operator here, because the paper excludes it",
     case_abs_is_not_an_operator_here),
    ("the three heuristics that carried 15% -> 80% all fire",
     case_the_three_rules_that_paid_for_everything_fire),
    ("a suppressed mutant is counted with its soundness, not discarded",
     case_a_suppressed_mutant_is_counted_not_discarded),
    ("only covered lines are mutated, and an uncovered file is skipped",
     case_only_covered_lines_are_mutated),
    ("a suite that could not load is not a killed mutant",
     case_a_broken_suite_is_not_a_killed_mutant),
    ("module-level declarations are not deleted",
     case_module_level_statements_are_not_deleted),
    ("a mutant is applied on the tree, not on the text",
     case_a_mutant_is_applied_on_the_tree_not_the_text),
    ("a mutation that could not be placed is counted as neither",
     case_an_unplaceable_mutant_is_counted_as_neither),
    ("a redundant short-circuit guard is suppressed, a real one is not",
     case_a_redundant_short_circuit_guard_is_suppressed),
    ("productivity is reported with its judge named",
     case_productivity_is_reported_with_its_judge_named),
    ("a short-circuited condition is absent, not false",
     case_a_short_circuited_condition_is_absent_not_false),
    ("MC/DC finds a condition branch coverage calls covered",
     case_mcdc_finds_a_condition_branch_coverage_calls_covered),
    ("a decision nothing reaches is not the same as a one-way decision",
     case_a_decision_no_test_reaches_is_not_the_same_as_one_way),
    ("an assertion is not a decision",
     case_an_assertion_is_not_a_decision),
    ("the instrument leaves the tree as it found it",
     case_the_instrument_leaves_the_tree_as_it_found_it),
    ("mutation reaches the page only when it is asked for",
     case_mutation_reaches_the_page_only_when_asked),
    ("a mutant walks the same ladder as a real defect",
     case_a_mutant_walks_the_same_ladder_as_a_real_defect),
    ("a hook that refuses everything gets no rung",
     case_a_hook_that_refuses_everything_gets_no_rung),
    ("an uncaught mutant is pending until it is judged",
     case_an_uncaught_mutant_is_pending_until_it_is_judged),
    ("the brief asks about the whole ladder, not just the suite",
     case_the_brief_asks_about_the_whole_ladder),
    ("a caveat is printed above the figure it disqualifies",
     case_a_caveat_outranks_the_figure_it_qualifies),
    ("an unanswered mutant moves the score neither way",
     case_an_unanswered_mutant_moves_the_score_neither_way),
    ("a supplied test command is used when the table cannot guess",
     case_a_supplied_test_command_is_used),
    ("a prohibition a guard already enforces is named",
     case_a_prohibition_a_guard_enforces_is_named),
    ("prohibitions and requirements are counted apart",
     case_prohibitions_and_requirements_are_counted_apart),
    ("a command in a fence is not a prohibition",
     case_a_command_in_a_fence_is_not_a_prohibition),
    ("a path-scoped sentence on the floor is flagged as misfiled",
     case_a_path_scoped_sentence_on_the_floor_is_flagged),
    ("a scoped rule file is parked, not on the floor",
     case_a_scoped_rule_file_is_not_on_the_floor),
    ("an installed plugin's tokens are not charged to the repository",
     case_plugin_tokens_are_not_charged_to_the_repository),
    ("the probe cannot reach the history it is being tested on",
     case_the_probe_cannot_reach_the_history),
    ("the copy with no memory really has none, nested ones included",
     case_the_second_copy_has_no_memory),
    ("only a focused commit becomes a question",
     case_only_a_focused_commit_becomes_a_question),
    ("a pull request number is not part of the question",
     case_a_pull_request_number_is_not_part_of_the_question),
    ("a question whose answer was deleted is not asked",
     case_a_question_whose_answer_was_deleted_is_not_asked),
    ("the difference is reported as rows, not as a rate",
     case_the_difference_is_reported_as_rows_not_a_rate),
    ("a pipeline that runs nothing is not counted as a verdict",
     case_a_pipeline_that_runs_nothing_is_not_a_verdict),
    ("the page names the directories it took the verdict from",
     case_the_page_names_where_it_looked_for_tests),
    ("a busy file is not mistaken for a reworked one",
     case_a_busy_file_is_not_mistaken_for_a_reworked_one),
    ("a place repaired twice is counted, from committed history",
     case_a_place_repaired_twice_is_counted),
    ("an unprobed repository abstains rather than scoring zero",
     case_an_unprobed_repository_abstains_rather_than_scoring_zero),
    ("the memory is the difference removing it makes, not the thickness",
     case_the_memory_is_the_difference_not_the_thickness),
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
