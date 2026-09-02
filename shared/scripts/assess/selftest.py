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
import truth as truth_mod          # noqa: E402
import value as value_mod          # noqa: E402
import arid as arid_mod            # noqa: E402
import judge as judge_mod          # noqa: E402
import mutate as mutate_mod        # noqa: E402
import run_mutants as run_mod      # noqa: E402
import coverage_tools as cover_mod  # noqa: E402
import observe as observe_mod      # noqa: E402
import merge as merge_mod          # noqa: E402
import conflict as conflict_mod    # noqa: E402
import promises as promises_mod    # noqa: E402
import units as units_mod          # noqa: E402
import review as review_mod        # noqa: E402
import permitted as permitted_mod  # noqa: E402
import reframe as reframe_mod      # noqa: E402
import surface as surface_mod      # noqa: E402
import ecosystems as eco_mod       # noqa: E402
import pipeline as pipeline_mod    # noqa: E402


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
        # A placeholder name on purpose. The dimension-1 check reads the
        # *shape* of the path, so `you` exercises it exactly as a real
        # username would -- and a real-looking one in a committed fixture is
        # the thing check_no_machine_paths.py exists to stop.
        "const CHROME = '/home/you/.cache/chrome'\n")
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

def _layer_row(hooks, counts, value=None, ci=""):
    probe = {"moments": {"5_before_action": {"PreToolUse": hooks.get(
        "PreToolUse", 0), "permissions_deny": 0}},
        "discipline": {"check_dirs": ["tests"], "ci_entry": ["github-actions"]}}
    catch = {"hooks": hooks, "command": "pytest", "ci": ci}
    return dim_mod.interception_layers(probe, catch, None, value,
                                       catch_mod.LADDER, counts)


def case_a_wired_layer_that_caught_nothing_is_not_an_absent_one(t):
    """`before-write: 0` meant two different things and printed one character.

    Either nothing is wired at that moment, or several hooks are wired and not
    one of them caught anything. The second is much the worse finding and it
    was indistinguishable from the first, because a rung cannot be read without
    knowing what stands behind it. Measured on this repository the day the row
    was added: two PreToolUse hooks wired, zero of 26 injected defects caught
    by either."""
    # `same-turn` rather than `before-write`, deliberately. A PostToolUse hook
    # runs the repository's checks, so one that catches nothing while defects
    # walk past it is exactly the finding this row exists for. `before-write`
    # cannot be read that way and has a case of its own below.
    silent = _layer_row({"PreToolUse": 0, "PostToolUse": 2},
                        {"local-suite": 14})
    if "2 hook(s), 0 of 14 caught" not in silent["value"]:
        return (f"a wired hook that caught nothing is not reported as wired: "
                f"{silent['value']!r}")
    if "before-write: none wired" not in silent["value"]:
        return "a moment with no hooks is not reported as unwired"
    if silent["flag"] != "bad":
        return ("a layer that is wired and silent is not flagged — that is "
                "the worse of the two readings and it has to outrank the "
                "layer that simply does not exist")

    absent = _layer_row({"PreToolUse": 0, "PostToolUse": 0},
                        {"local-suite": 14})
    if "same-turn: none wired" not in absent["value"]:
        return f"an absent layer is reported as present: {absent['value']!r}"
    if absent["flag"] == "bad":
        return ("a repository with nothing wired is flagged as harshly as one "
                "whose wiring does not work")

    # And a third state the first version of this row got wrong. The walk
    # stops at the first red, so when the top rungs catch everything the ones
    # below them show 0 because nothing ever reached them. Flagging that would
    # report a repository that catches defects early as one whose suite is
    # broken -- the exact opposite of the truth.
    early = _layer_row({"PreToolUse": 2, "PostToolUse": 1},
                       {"before-write": 3, "same-turn": 1}, ci="ci.sh")
    if "local-suite" not in early["value"] or "nothing reached it" not in \
            early["value"]:
        return (f"a rung nothing reached is reported as a rung that failed: "
                f"{early['value']!r}")
    if early["flag"] == "bad":
        return ("a repository that caught every defect before it was written "
                "is flagged for the rungs those defects never reached")
    return None


def case_a_rule_is_a_layer_with_no_rung(t):
    """A sentence saying *never do X* is trying to stop the same defect.

    It cannot be measured by injection -- firing a payload at a document does
    nothing -- so it is counted and marked, and given no rung. Testing it
    honestly would mean handing an agent the rule and the task and seeing
    whether it writes the defect anyway: stochastic, expensive, unrepeatable.
    Counting it as a rung would credit the repository for a layer nobody can
    show working."""
    value = {"prohibitions": 5, "already_enforced": [{"text": "x"}]}
    row = _layer_row({"PreToolUse": 1, "PostToolUse": 0},
                     {"before-write": 1}, value)
    if "rule: 4 unenforced" not in row["value"]:
        return (f"the 4 prohibitions no guard backs were not counted: "
                f"{row['value']!r}")
    if "no rung" not in row["value"]:
        return "a rule was listed without saying it has no rung"
    for k in catch_mod.LADDER:
        if f"rule: 4 unenforced, {k}" in row["value"]:
            return "a rule was given a rung on the ladder"

    covered = {"prohibitions": 2,
               "already_enforced": [{"text": "x"}, {"text": "y"}]}
    row2 = _layer_row({"PreToolUse": 1, "PostToolUse": 0},
                      {"before-write": 1}, covered)
    if "rule:" in row2["value"]:
        return ("prohibitions a guard already enforces were counted as an "
                "unenforced layer as well — they are the guard, twice")
    return None


def case_a_hook_that_could_not_run_is_not_a_layer_that_failed(t):
    """A `matcher: "Bash"` guard is never asked about an edit.

    The ladder introduces defects by editing files, so it fires Edit payloads.
    Claude Code would never send one to a hook wired for Bash. Firing it anyway
    does two wrong things at once: it counts a layer as wired that cannot see
    this class of defect at all, and if such a hook ever did block, the ladder
    would record a `before-write` catch that could not happen in reality.

    Measured on this repository, whose destructive-command guards are Bash-only
    by design: the inventory row read `before-write: 2 hook(s), 0 of 16 caught`
    when only one of the two could ever have run. That is an accusation against
    a guard for not doing a job it was never given."""
    if catch_mod.matches("Bash", "Edit"):
        return "a Bash-only hook is treated as applying to an edit"
    if not catch_mod.matches("Bash|Write|Edit|MultiEdit", "Edit"):
        return "an alternation naming Edit is not treated as applying to it"
    for wide in ("", "*", ".*"):
        if not catch_mod.matches(wide, "Edit"):
            return f"the catch-all matcher {wide!r} excluded a tool"

    repo(t)
    put(t, "app.py", "def add(a, b):\n    return a + b\n")
    put(t, ".claude/block.py", BLOCKER)
    put(t, ".claude/settings.json", json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [
            {"type": "command",
             "command": f'python3 "{os.path.join(t, ".claude/block.py")}"'}]}]}}))
    commit(t, "chore: a Bash-only guard")
    pre = catch_mod.applicable(catch_mod.wired(t, "PreToolUse"), "Edit")
    if pre:
        return (f"{len(pre)} Bash-only hook(s) were selected for an Edit "
                f"payload — the ladder would ask them a question Claude Code "
                f"never asks")
    if not catch_mod.applicable(catch_mod.wired(t, "PreToolUse"), "Bash"):
        return "the Bash-only hook was excluded from Bash payloads too"
    return None


def case_the_default_branch_is_not_the_one_that_happens_to_be_out(t):
    """A clone inherits the source's checkout as its `origin/HEAD`.

    Cloning from a local path copies the source repository's *checked-out
    branch* into `origin/HEAD`, not its default. So a clone taken while
    somebody was on a feature branch reports that feature branch as the
    default, the force-push probe is aimed at a branch nothing protects, the
    guard correctly allows it, and the page says `force-push the default
    branch: nothing stops it` about a repository that refuses exactly that.

    Found by assessing a clone of this repository: dimension 1 read 1 of 6
    with three working guards in the tree. A wrong headline produced by a
    correct guard is the worst kind, because nothing looks broken."""
    src = os.path.join(t, "src")
    os.makedirs(src)
    repo(src)
    put(src, "a.txt", "x\n")
    commit(src, "feat: first")
    git(["branch", "feature/work"], src)
    git(["checkout", "-q", "feature/work"], src)
    put(src, "b.txt", "y\n")
    commit(src, "feat: second")

    dst = os.path.join(t, "clone")
    git(["clone", "-q", src, dst], t)
    head = git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
               dst).stdout.strip()
    if not head.endswith("feature/work"):
        return (f"the fixture was supposed to produce a clone whose "
                f"origin/HEAD is the feature branch and gave {head!r}")

    got = blast_mod.default_branch(dst)
    if got != "main":
        return (f"the probe would be aimed at {got!r} — a branch nothing "
                f"protects — so a repository that refuses force-pushes to "
                f"main would be reported as refusing nothing")

    git(["checkout", "-q", "main"], dst)
    if blast_mod.default_branch(dst) != "main":
        return "standing on the default branch changed what the default is"

    # And where `origin` is a real remote, `origin/HEAD` must still be
    # trusted: a repository whose default is genuinely `develop` or
    # `release` must not be dragged to `main` because the name exists.
    git(["remote", "set-url", "origin", "https://example.invalid/x.git"], dst)
    if blast_mod.default_branch(dst) != "feature/work":
        return ("with a real remote, origin/HEAD was overruled — a repository "
                "whose default is not conventionally named would be measured "
                "on the wrong branch")
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



def _observable_repo(t, **files):
    """A tree with whatever pieces the case is about, and nothing else."""
    for rel, body in files.items():
        full = os.path.join(t, rel.replace("|", os.sep))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(body)
    return t


def case_the_instrument_does_not_find_its_own_vocabulary(t):
    """Every collector is a list of the names it looks for.

    So an instrument that reads its own source finds `grafana`, `jaeger` and
    `playwright` in a repository that has none of them, and reports a tree's
    observability as excellent on the strength of its own keyword table. This
    was live when the module was written: assessing this repository reported
    twenty logging findings, all of them the detector's own list.

    This one is measured the way it happens: the subject *contains* the
    instrument, which is the ordinary case when the assessment is run against
    the repository it ships from. The module's own directory is what gets
    excluded, so the case points that directory at a copy inside the fixture
    and insists every angle comes back empty."""
    inside = os.path.join(t, "shared", "scripts", "assess")
    shutil.copytree(HERE, inside)
    _observable_repo(t, **{"README.md": "a repository with no application in it"})
    was = observe_mod.HERE
    observe_mod.HERE = inside
    try:
        ev, why = observe_mod.assess(t)
    finally:
        observe_mod.HERE = was
    if ev is None:
        return f"nothing was collected at all: {why}"
    found = {a: len(ev[a]) for a in observe_mod.ANGLES if ev[a]}
    if found:
        return ("the instrument found itself: " + repr(found) +
                " -- its own keyword lists are not evidence about the subject")
    return None


def case_prose_about_a_logging_stack_is_not_a_logging_stack(t):
    """A design document naming Loki is not a repository that emits to Loki.

    The distinction is the whole difference between what a team wrote down and
    what the application does, and counting the first as the second puts a
    repository's ambitions on the page as its capabilities. Markdown is
    deliberately not scanned for this reason."""
    _observable_repo(t, **{
        "docs|observability.md": (
            "# Plan\n\nWe will ship logs to Loki via Vector, add "
            "opentelemetry tracing, and read them in Grafana. structlog is the "
            "library we picked.\n"),
    })
    ev, _ = observe_mod.assess(t)
    if ev is None:
        return "nothing was collected"
    if ev["logs"]:
        return ("a document describing a logging stack was counted as one: " +
                repr([i["detail"] for i in ev["logs"]]))
    return None


def case_a_test_target_is_not_a_way_to_run_the_thing(t):
    """This dimension is about the rung the test suite is not on.

    `make test` is dimension 2's business and is measured there. Counting it
    here would report every repository with a test target as one an agent can
    watch run, which is the opposite of what the row is for."""
    _observable_repo(t, **{"Makefile": "test:\n\tpytest\n\ncheck:\n\truff\n"})
    ev, _ = observe_mod.assess(t)
    if ev is None:
        return "nothing was collected"
    if ev["run"]:
        return ("a test target was counted as a way to run the application: " +
                repr([i["detail"] for i in ev["run"]]))
    return None


def case_a_literal_port_and_a_port_from_the_environment_differ(t):
    """The two shapes that decide whether a second agent can work at all.

    A hard-coded host port means the second concurrent instance collides, and
    the second agent gets a crash that looks like a bug in its own change --
    worse than no observability, because it is observability that lies. Both
    shapes must be reported, and reported as different things."""
    _observable_repo(t, **{
        "docker-compose.yml": ('services:\n  web:\n    container_name: fixed_web\n'
                               '    ports:\n      - "8080:8080"\n'),
        "app.py": 'import os\nPORT = os.environ.get("PORT", 8080)\n',
    })
    ev, _ = observe_mod.assess(t)
    if ev is None:
        return "nothing was collected"
    kinds = {i["kind"] for i in ev["isolation"]}
    for want in ("fixed-port", "fixed-name", "port-from-env"):
        if want not in kinds:
            return f"{want} was not reported; found {sorted(kinds)}"
    return None


def case_collecting_the_evidence_starts_nothing(t):
    """The promise the module's docstring makes, held by a case.

    Starting a stranger's application is a far larger promise than this
    assessment makes anywhere else, and 0026's pre-flight contract exists so
    that nothing executes without having been named first. The way this breaks
    is not malice -- it is somebody adding `run the dev target and read its
    output` because it would be better evidence."""
    proof = os.path.join(t, "it-ran")
    _observable_repo(t, **{
        "Makefile": "dev:\n\ttouch %s\n" % proof,
        "run.sh": "#!/bin/sh\ntouch %s\n" % proof,
    })
    observe_mod.assess(t)
    if os.path.exists(proof):
        return "collecting the evidence executed the repository's run target"
    return None


def case_an_unjudged_scan_carries_no_verdict(t):
    """A verdict nobody gave must not appear, in either direction.

    The page prints this row's prose verbatim, so a default here would put
    words on the page that no judge said. Absent, malformed and unsupported
    answers must all fail to produce one."""
    _observable_repo(t, **{"Makefile": "dev:\n\tpython3 app.py\n"})
    ev, _ = observe_mod.assess(t)
    if "not yet judged" not in observe_mod.render(ev):
        return "an unjudged scan rendered something other than 'not yet judged'"
    for bad in ({}, {"verdict": "excellent", "prose": "x"},
                {"verdict": "yes"}, {"verdict": "yes", "prose": "   "}, "yes"):
        judged, why = observe_mod.grade(bad)
        if judged is not None:
            return f"grade() accepted {bad!r} and returned {judged!r}"
    judged, why = observe_mod.grade(
        {"verdict": "partly", "prose": "the logs are unreachable"})
    if judged is None:
        return f"a well-formed answer was rejected: {why}"
    if "the logs are unreachable" not in observe_mod.render(ev, judged):
        return "the judge's prose did not reach the rendered row"
    return None


def case_the_brief_asks_about_every_angle(t):
    """A brief that has quietly lost an angle still reads as a full question.

    The agent answers what it was asked, so an angle missing from the brief is
    an angle nobody judges, and the row still prints a verdict as though the
    whole question had been put."""
    _observable_repo(t, **{"Makefile": "dev:\n\tpython3 app.py\n"})
    ev, _ = observe_mod.assess(t)
    text = observe_mod.brief(ev)
    # Not `a in text`: the brief's opening prose names all six angles, so a
    # membership test passes while the evidence section is missing one. What
    # the judge actually reads is the per-angle heading.
    missing = [a for a in observe_mod.ANGLES if ("### " + a) not in text]
    if missing:
        return "the brief carries no evidence section for: " + ", ".join(missing)
    if "nothing was started" not in text:
        return ("the brief does not tell the judge that nothing was run -- so "
                "an absent `logs` reads as an application that emits none, "
                "rather than as one nobody started")
    return None



def case_a_repository_of_scripts_is_runnable(t):
    """The collector's first version only knew application shapes.

    A Makefile, a compose file, a top-level app.py -- so it read `run: 0` on
    this repository, whose every file is executable from a shell, and the row
    would have said an agent could not watch its change run when running it is
    a single command. A tool, a library with a CLI and a directory of scripts
    are the common case, not the exception.

    Both directions: a module that says it can be run counts, and a library
    module that says nothing of the kind does not."""
    _observable_repo(t, **{
        "tool|cli.py": ('import sys\n\n\ndef main():\n    return 0\n\n\n'
                        'if __name__ == "__main__":\n    sys.exit(main())\n'),
        "tool|helpers.py": "def add(a, b):\n    return a + b\n",
        "pyproject.toml": ('[project]\nname = "tool"\n\n'
                           '[project.scripts]\nmytool = "tool.cli:main"\n'),
    })
    ev, _ = observe_mod.assess(t)
    if ev is None:
        return "nothing was collected"
    details = {i["detail"] for i in ev["run"]}
    if "python3 tool/cli.py" not in details:
        return ("a module with a __main__ guard was not counted as a way to "
                "run the thing: " + repr(sorted(details)))
    if "mytool" not in details:
        return "a console script in pyproject.toml was not counted"
    if any("helpers" in d for d in details):
        return "a library module with no entry point was counted as runnable"
    return None



def _report(t, rel, body):
    full = os.path.join(t, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(body)
    return t


GOCOVER = ("mode: set\n"
           "ex/a.go:3.10,5.2 2 1\n"
           "ex/a.go:7.10,9.2 1 0\n")

LCOV = ("SF:src/a.js\nFN:3,alpha\nFNDA:1,alpha\nFNF:2\nFNH:1\n"
        "DA:3,1\nDA:4,0\nLF:2\nLH:1\n"
        "BRDA:3,0,0,1\nBRDA:3,0,1,0\nBRF:2\nBRH:1\nend_of_record\n")

GCOV = json.dumps({"gcc_version": "14.2.0", "files": [{"lines": [
    {"count": 1, "branches": [{"count": 1}, {"count": 0}],
     "conditions": [{"count": 2, "not_covered_true": [0],
                     "not_covered_false": []}]}]}]})


def case_a_criterion_the_tool_does_not_produce_is_absent_not_zero(t):
    """Go's tooling computes no branch coverage. None. It is not a setting.

    A Go repository reading `0 of 0 branches never taken both ways` would be a
    statement about the language dressed up as a finding about the code, and
    the reader has no way to tell which it is. So a criterion the tool does not
    produce carries no row, and the criteria that are missing get named
    together in one row that says why."""
    _report(t, "coverage.out", GOCOVER)
    r, why = cover_mod.assess(t, None, os.path.join(t, "w"))
    if not r:
        return f"a valid coverprofile was not read: {why}"
    if r["criteria"].get("statement", {}).get("total") != 3:
        return f"statements came out as {r['criteria'].get('statement')}"
    for absent in ("branch", "function", "mcdc"):
        if absent in r["criteria"]:
            return f"{absent} was reported for a Go coverprofile, which has none"
    rows = dim_mod.coverage_rows(r)
    named = [x for x in rows if x["label"] == "criteria this tool does not produce"]
    if not named:
        return "the absent criteria were not named, so they read as zero"
    if "branch" not in named[0]["value"]:
        return "branch was not listed among the criteria this tool cannot give"
    return None


def case_lcov_carries_function_coverage(t):
    """The one common format with a first-class function counter.

    2.1 asks for line *and* function coverage. coverage.py has no function
    counter, so Python cannot answer that half; lcov's FNF/FNH means Node,
    Rust and C can. That asymmetry is real and it has to survive into the
    result rather than being smoothed over."""
    _report(t, "lcov.info", LCOV)
    r, why = cover_mod.assess(t, None, os.path.join(t, "w"))
    if not r:
        return f"a valid lcov report was not read: {why}"
    fn = r["criteria"].get("function")
    if not fn:
        return "lcov's FNF/FNH did not become function coverage"
    if (fn["total"], fn["covered"]) != (2, 1):
        return f"function coverage came out as {fn}"
    if r["criteria"].get("branch", {}).get("total") != 2:
        return "lcov's BRF/BRH did not become branch coverage"
    return None


def case_gcov_is_where_mcdc_comes_from(t):
    """The only on-disk format that carries the fourth criterion.

    Nothing outside the compilers computes MC/DC -- not coverage.py, not
    JaCoCo, not istanbul. GCC 14 added `-fcondition-coverage` and Clang 18
    `-fcoverage-mcdc`, both masking MC/DC, chosen independently. If this
    reader stops working, the criterion silently leaves the assessment for
    every language at once."""
    _report(t, "gcov.json", GCOV)
    r, why = cover_mod.assess(t, None, os.path.join(t, "w"))
    if not r:
        return f"a valid gcov report was not read: {why}"
    mc = r["criteria"].get("mcdc")
    if not mc:
        return "gcov's condition counts did not become MC/DC"
    if (mc["total"], mc["covered"]) != (2, 1):
        return f"MC/DC came out as {mc}"
    return None


def case_a_malformed_report_is_an_abstention_not_a_zero(t):
    """The failure that would be silent and would look like a finding.

    A truncated or half-written report parsed leniently yields small numbers,
    and small numbers here read as `almost nothing is tested` -- the worst
    possible reading to produce by accident."""
    for rel in ("coverage.json", "lcov.info", "coverage.xml", "coverage.out",
                "gcov.json"):
        _report(t, rel, "not a coverage report at all\n{oops")
    r, why = cover_mod.assess(t, None, os.path.join(t, "w"))
    if r:
        return f"garbage was read as a coverage result: {r.get('criteria')}"
    if "cannot judge" not in why:
        return f"the abstention did not say it could not judge: {why!r}"
    return None


def case_a_report_inside_a_dependency_is_not_this_repositorys(t):
    """A walk would find it. This does not walk, and that is the reason.

    A vendored package ships its own lcov.info more often than not, and a
    walk that finds it reports the dependency's coverage as the subject's --
    usually a high number, since libraries that ship coverage reports have
    good ones."""
    _report(t, "node_modules/left-pad/lcov.info", LCOV)
    _report(t, "vendor/thing/coverage.out", GOCOVER)
    r, why = cover_mod.assess(t, None, os.path.join(t, "w"))
    if r:
        return ("a dependency's coverage report was read as this "
                "repository's: " + str(r.get("report")))
    return None


def case_the_shape_of_the_suite_command_decides_if_it_can_be_wrapped(t):
    """Guessing at somebody's build is worse than saying you cannot.

    Three shapes are recognisable without reading the repository. A shell
    pipeline or a `make` target is not one of them, and wrapping it anyway
    produces a coverage number for a program that never ran."""
    py = cover_mod.Python()
    for command in ("pytest -q", "python3 -m pytest tests", "run_tests.py"):
        if not py.wrap(command):
            return f"a wrappable command was refused: {command!r}"
    for command in ("make test", "./ci.sh", "npm test && pytest", ""):
        if py.wrap(command):
            return (f"{command!r} was wrapped anyway -- the coverage number "
                    f"would be about a program that never ran")
    return None


def case_an_uninstalled_tool_names_itself_and_how_to_get_it(t):
    """`could not judge` is only useful when it says what would fix it.

    And the row it produces is a finding about the repository, not about this
    file: a Python repository with no coverage tool installed has no coverage
    tool. Nothing here installs one, because installing one changes what the
    subject contains.

    The absence is forced rather than borrowed from the machine. This case
    passed for a year because the box it ran on happened not to have
    `coverage`; installing it sent the fixture down the *available* path
    instead, where the message says something else entirely, and the case
    turned red for a reason that had nothing to do with the behaviour it
    guards. A case that depends on what is installed is testing the box."""
    for i in range(3):
        _report(t, "pkg/mod%d.py" % i, "def f():\n    return 1\n")
    was = cover_mod.Python.available
    cover_mod.Python.available = lambda self, root: False
    try:
        r, why = cover_mod.assess(t, "pytest -q", os.path.join(t, "w"))
    finally:
        cover_mod.Python.available = was
    if r:
        return "coverage was somehow produced with no tool and no report"
    if "coverage" not in why or "pip install" not in why:
        return f"the abstention names neither the tool nor how to get it: {why!r}"
    rows = dim_mod.coverage_rows(None, why)
    if not rows or rows[0]["flag"] != "info":
        return "an abstention rendered as something other than an info row"
    return None




def _traceable_repo(t):
    """One file the suite executes and one line it only runs, plus the suite.

    Deliberately not a git repository: `covered_lines` reads a tree, not a
    history, and a fixture that needs `git init` to answer a question about
    `sys.settrace` is claiming a dependency that is not there."""
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
    return [sys.executable, "suite.py"]


class _Said:
    def __init__(self, code=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def _intercept(seen, json_out):
    """`run_mutants.sh`, with the two coverage calls answered from here.

    Everything else is delegated to the real one, so the fallback route runs
    for real. Stubbing the whole of `sh` would make the case pass without any
    tracing happening at all."""
    real = run_mod.sh

    def fake(args, cwd, timeout=120, **kw):
        argv = list(args)
        seen.append(argv)
        if argv[1:] == ["-c", "import coverage"]:
            return _Said(0)
        if argv[1:3] == ["-m", "coverage"] and "run" in argv:
            return _Said(1, "", "No data was collected.")
        if argv[1:3] == ["-m", "coverage"] and "json" in argv:
            return _Said(0, json_out)
        return real(args, cwd, timeout, **kw)
    return fake


def case_a_coverage_report_of_nothing_is_not_a_measurement(t):
    """`{app.py: set()}` is a run that did not happen, not a tested nothing.

    `coverage json` reports every source file it was pointed at whether or not
    a single line ran, so a failed `coverage run` still yields a well-formed
    report with empty executed-line sets. Returning it means every later
    intersection is empty, mutation abstains with `no mutable, covered,
    non-arid line`, and the page reads that as a fact about the repository:
    nothing here is worth mutating. It is a fact about the run.

    The tracer route is reached for real here -- only the two coverage calls
    are answered from the fixture -- so the case fails if the fallthrough is
    removed and also if the fallback itself stops working."""
    cmd = _traceable_repo(t)
    empty = ('{"files": {"app.py": {"executed_lines": []}, '
             '"suite.py": {"executed_lines": []}}}')
    was, seen = run_mod.sh, []
    run_mod.sh = _intercept(seen, empty)
    try:
        got = run_mod.covered_lines(t, cmd)
    finally:
        run_mod.sh = was
    if got is None:
        return "the fallback route was not reached at all"
    if not any(got.values()):
        return ("an empty coverage report was returned as a measurement: "
                + repr(got))
    if not got.get("app.py"):
        return f"the fallback ran but found nothing in app.py: {got!r}"
    return None


def case_coverage_run_is_not_handed_the_interpreter_twice(t):
    """`coverage run` supplies the interpreter, so the command must not.

    A test command arrives as `[python3, suite.py]` because that is what every
    other caller needs. Passing it through unchanged builds `python3 -m
    coverage run --source=. python3 suite.py`, which asks coverage to execute
    the interpreter binary as a Python script. It exits 1, collects nothing,
    and the report that follows is the empty one the case above is about --
    which is how this stayed invisible: two bugs, and the second one hid the
    first behind a plausible-looking abstention.

    The tracer route strips the interpreter and always did. This asserts the
    two routes are handed the same thing."""
    cmd = _traceable_repo(t)
    was, seen = run_mod.sh, []
    run_mod.sh = _intercept(seen, '{"files": {}}')
    try:
        run_mod.covered_lines(t, cmd)
    finally:
        run_mod.sh = was
    runs = [a for a in seen if a[1:3] == ["-m", "coverage"] and "run" in a]
    if not runs:
        return "the coverage route was never tried"
    for argv in runs:
        after = argv[argv.index("run") + 1:]
        interpreters = [x for x in after
                        if os.path.basename(x).startswith("python")]
        if interpreters:
            return ("`coverage run` was handed an interpreter to execute as a "
                    "script: " + repr(after))
        if "suite.py" not in after:
            return f"the suite never reached `coverage run`: {after!r}"
    return None



def _typed_history(t, subjects):
    """A repository whose commits carry the subjects given, each touching one
    source file and nothing that verifies it."""
    repo(t)
    put(t, "checks/suite.py", "def test_one():\n    assert True\n")
    commit(t, "test: a suite exists")
    for i, subject in enumerate(subjects):
        put(t, "src/mod%d.py" % i, "def f%d():\n    return %d\n" % (i, i))
        commit(t, subject)
    return t


def _bare_row(t):
    d3 = dim_mod.reliable_delivery(t, history_mod.commits(t),
                                   check_dirs=("checks",))
    return [r for r in d3["rows"] if "verified nothing" in r["label"]][0]


def case_a_rename_does_not_owe_a_test(t):
    """Tidying is not an untested change.

    Renaming a symbol across forty files, reformatting, and bumping a
    dependency all touch source, and no new test would make any of them safer.
    Counting them puts a repository's tidiest weeks against it and rewards
    leaving the mess alone -- which is the opposite of what this row is for.

    Six changes here, three of which add or repair behaviour. The denominator
    must be three."""
    _typed_history(t, ["feat: a new thing", "refactor: move it elsewhere",
                       "fix: a real defect", "chore(deps): bump a version",
                       "perf: make it faster", "style: reformat"])
    row = _bare_row(t)
    if not row["value"].endswith("/3  (100%)"):
        return ("the denominator counted tidying as a change owing a test: "
                + row["value"])
    return None


def case_an_untyped_subject_is_counted_rather_than_guessed(t):
    """The asymmetry the three-valued classifier exists for.

    A repository that does not type its subjects cannot be narrowed. Guessing
    from free-form English would shrink the denominator on every repository at
    once -- every score would improve and no repository would have changed,
    which is the most dangerous shape a measurement can take. So an untyped
    subject counts, and the row says which denominator it used."""
    _typed_history(t, ["added a new thing", "moved some files around",
                       "made it faster"])
    row = _bare_row(t)
    if not row["value"].endswith("/3  (100%)"):
        return ("untyped subjects were narrowed away on a guess: "
                + row["value"])
    if "not typed" not in row["note"]:
        return ("the row did not say it fell back to the wide denominator: "
                + row["note"])
    return None


def _workflow(t, name, body):
    where = os.path.join(t, ".github", "workflows")
    os.makedirs(where, exist_ok=True)
    with open(os.path.join(where, name), "w", encoding="utf-8") as fh:
        fh.write(body)
    return t


def case_a_404_is_an_answer_and_a_403_is_not(t):
    """The distinction the whole module's honesty rests on.

    GitHub answers 404 `Branch not protected` for a branch with no protection
    rule -- that is a fact about the repository. A 403 is this tool lacking
    the right to look, and reporting it as `nothing is required` would be a
    confident claim about a repository nobody read. A tool that turns its own
    blindness into a finding is worse than one that abstains."""
    got = merge_mod.interpret(1, "", '{"message":"Branch not protected",'
                                    '"status":"404"}\ngh: Branch not protected')
    if not got.get("readable"):
        return "a 404 was treated as unreadable, but it is an answer"
    if got.get("protected"):
        return "a 404 was read as protected"

    for body in ('{"message":"Must have admin rights","status":"403"}',
                 '{"message":"Bad credentials","status":"401"}',
                 "gh: could not connect"):
        got = merge_mod.interpret(1, "", body)
        if got.get("readable"):
            return f"a failure to read was treated as an answer: {body!r}"
        if "required_checks" in got:
            return (f"an unreadable protection produced a required_checks "
                    f"field, which reads as `nothing is required`: {body!r}")

    got = merge_mod.interpret(0, json.dumps(
        {"required_status_checks": {"contexts": ["ci"]},
         "required_pull_request_reviews": {"x": 1}}), "")
    if got.get("required_checks") != ["ci"]:
        return f"a protected branch's required checks were lost: {got}"
    return None


def case_unreadable_protection_does_not_become_not_required(t):
    """The same rule one level up, where the state string is produced.

    A fixture with no remote at all: protection is a server-side fact and
    there is no server to ask. The state must say so, and must not say the
    checks are not required."""
    _workflow(t, "ci.yml", "on:\n  pull_request:\n\njobs:\n  t:\n"
                           "    runs-on: ubuntu-latest\n")
    r, why = merge_mod.assess(t)
    if not r:
        return f"nothing was read: {why}"
    if "not readable" not in r["state"]:
        return (f"with no remote to ask, the state came out as {r['state']!r} "
                f"— an unread server setting was turned into a finding")
    if r["protection"].get("readable"):
        return "protection was reported readable with no remote"
    return None


def case_a_workflow_on_push_only_is_not_a_merge_gate(t):
    """Running after the merge is not verification before it.

    A workflow triggered only on `push` to the default branch tells you the
    trunk broke. That is monitoring, and this row is about whether anything
    was obliged to look first."""
    _workflow(t, "nightly.yml", "on:\n  push:\n    branches: [main]\n  schedule:\n"
                                "    - cron: '0 0 * * *'\n\njobs:\n  t:\n"
                                "    runs-on: ubuntu-latest\n")
    r, why = merge_mod.assess(t)
    if not r:
        return f"nothing was read: {why}"
    if r["state"] != "nothing on pull requests":
        return (f"a push-only workflow was read as a merge gate: "
                f"{r['state']!r}")
    return None


def case_a_comment_about_swallowing_is_not_swallowing(t):
    """This repository was the false positive.

    ci.yml carries a line saying no step may swallow a status with `|| true`,
    and the first version of this reader flagged that sentence as a violation
    of itself. The reason beside a real one is carried instead, because every
    legitimate use this project has seen came with a sentence explaining why
    and every illegitimate one did not -- a signal an agent can use and a
    counter cannot."""
    _workflow(t, "ci.yml",
              "on:\n  pull_request:\n\njobs:\n  t:\n"
              "    runs-on: ubuntu-latest\n"
              "    steps:\n"
              "      # No step may swallow a status with || true\n"
              "      - run: pytest\n"
              "      # the corpus measurement must not fail the job\n"
              "      - name: measure\n"
              "        continue-on-error: true\n"
              "        run: python3 measure.py\n"
              "      - run: cleanup.sh || true\n")
    r, why = merge_mod.assess(t)
    if not r:
        return f"nothing was read: {why}"
    got = r["swallow_candidates"]
    if len(got) != 2:
        return ("expected the two real ones and not the comment, got: "
                + repr([(c["line"], c["text"]) for c in got]))
    with_reason = [c for c in got if c["reason_given"]]
    if len(with_reason) != 1:
        return ("the comment explaining a deliberate swallow was not carried "
                "to the one it explains: " + repr(got))
    if "corpus" not in with_reason[0]["reason_given"]:
        return "the wrong comment was attached: " + with_reason[0]["reason_given"]
    return None



def _doc(t, rel, body):
    full = os.path.join(t, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(body)
    return full


def _subjects_of(r):
    return sorted(p["subject"] for p in (r or {}).get("candidates", []))


def case_supersession_is_not_conflict(t):
    """The finding that would bury every other one.

    A decision record that replaces an earlier one contradicts it on purpose,
    and a repository that keeps its history has many. Run against this
    repository before the rule existed, the loudest candidates were 0031
    against 0033 — which is the system working, reported as the system
    broken."""
    _doc(t, "docs/0031-old.md", "# 0031\nStatus: accepted\n"
                                "Run with `--budget 2000` always.\n")
    _doc(t, "docs/0033-new.md", "# 0033\nStatus: accepted\nSupersedes 0031.\n"
                                "Run with `--budget 9000` instead.\n")
    r, why = conflict_mod.narrow(t)
    if r is None:
        return f"nothing was compared: {why}"
    if "--budget" in _subjects_of(r):
        return ("a document and the one that declares it superseded were "
                "reported as disagreeing")
    if not r["excluded_by_supersession"]:
        return "the supersession was not recognised at all"
    return None


def case_a_value_must_be_attached_not_merely_nearby(t):
    """The single number the precision of the whole module rests on.

    Sentence scope, then a sixty-character window, both produced more than a
    thousand candidates from under two thousand document pairs — more than
    half of every pair, which is a filter that has stopped filtering. A
    `--json` flag with the words "Stage 5" eleven characters away is not a
    flag with the value 5."""
    # `--budget` carries its value; `--json` has a step number nearby and
    # carries nothing. Both flags appear in two documents, so the only thing
    # separating them is attachment.
    _doc(t, "a.md", "Run `query.py --budget 3000` for a wide map.\n")
    _doc(t, "c.md", "The default is `--budget 2000` and always has been.\n")
    _doc(t, "b.md", "Use `--json` at step 5 of the guide.\n")
    _doc(t, "d.md", "Use `--json` at step 9 of the guide.\n")
    r, _why = conflict_mod.narrow(t)
    got = _subjects_of(r)
    if got != ["--budget"]:
        return (f"expected only the attached pair, got {got} — a number "
                f"merely near a flag was read as its value")
    return None


def case_overlapping_values_are_agreement_not_conflict(t):
    """`{600}` against `{077, 600}` is one document giving more context.

    Requiring the value sets to be *unequal* rather than *disjoint* reported
    every such pair as a contradiction, which is how a filter fills a page
    with documents that agree."""
    _doc(t, "a.md", "The file is written with `chmod_mode` 600.\n")
    _doc(t, "b.md", "Written `chmod_mode` 600 by default. "
                    "In strict mode, `chmod_mode` 077.\n")
    r, _why = conflict_mod.narrow(t)
    if _subjects_of(r):
        return ("documents whose values overlap were reported as "
                "contradicting: " + repr(_subjects_of(r)))
    return None


def case_a_token_every_document_names_is_not_evidence(t):
    """The oldest rule in retrieval, and it applies unchanged.

    `CLAUDE.md` is named in almost every document here and produced 27 of the
    first 40 candidates on its own. A term with no discriminating power is not
    evidence, however code-shaped it looks."""
    for i in range(6):
        _doc(t, "d%d.md" % i,
             "Everything is described in `CLAUDE.md` %d.\n" % (100 + i))
    _doc(t, "rare_a.md", "The knob `retry_limit` 7 is what we use.\n")
    _doc(t, "rare_b.md", "The knob `retry_limit` 9 is what we use.\n")
    r, _why = conflict_mod.narrow(t)
    got = _subjects_of(r)
    if "CLAUDE.md" in got:
        return "a token named by most documents was still used to pair them"
    if got != ["retry_limit"]:
        return f"the discriminating subject was lost too: {got}"
    return None


def case_only_what_the_repository_keeps_is_its_memory(t):
    """An untracked draft is not what the repository says.

    `tmp/` here holds throwaway assessment pages nobody committed on purpose,
    and comparing them against the documents is comparing a draft against the
    thing it was drafting."""
    subprocess.run(["git", "init", "-q"], cwd=t, check=True)
    _doc(t, "kept.md", "The knob `retry_limit` 7 is what we use.\n")
    _doc(t, "scratch.md", "The knob `retry_limit` 9, scribbled.\n")
    subprocess.run(["git", "add", "kept.md"], cwd=t, check=True)
    r, _why = conflict_mod.narrow(t)
    if _subjects_of(r):
        return ("an untracked file was compared as though the repository "
                "kept it: " + repr(_subjects_of(r)))
    return None


def case_somebody_elses_cloned_repository_is_not_ours(t):
    """355 documents from other people's repositories, reported as ours.

    This repository keeps a corpus of cloned repositories under `eval/.work/`.
    The first run of this module compared their documents against each other
    and presented the result as a finding about this tree."""
    _doc(t, "eval/.work/someone__else/A.md",
         "The knob `retry_limit` 7 is what we use.\n")
    _doc(t, "eval/.work/someone__else/B.md",
         "The knob `retry_limit` 9 is what we use.\n")
    _doc(t, "ours.md", "Nothing controversial here.\n")
    r, why = conflict_mod.narrow(t)
    if r and _subjects_of(r):
        return ("a cloned repository's documents were compared as ours: "
                + repr(_subjects_of(r)))
    return None



def case_a_pass_to_fail_discards_the_whole_claim(t):
    """The guard, and the part of CASCADE easiest to drop.

    A test the real code passed and the document-derived code fails means that
    implementation is incomplete, so its passing of the fail-to-pass tests is
    evidence about nothing. Dropping this condition turns the method back into
    "a model said the code was wrong", which the paper measures at 0.53
    precision -- about 27 false positives per 71 real ones."""
    real = {"one": 1, "two": 0}
    got, counts = promises_mod.verdict(real, {"one": 0, "two": 1})
    if got == "inconsistent":
        return ("a claim with a pass-to-fail test was still reported: "
                + repr(counts))
    if counts.get("p2f") != 1 or counts.get("f2p") != 1:
        return f"the crossing itself is wrong: {counts}"
    got, _ = promises_mod.verdict(real, {"one": 0, "two": 0})
    if got != "inconsistent":
        return f"with no pass-to-fail it should be a finding, got {got!r}"
    return None


def case_a_test_the_documents_own_code_also_fails_is_not_a_finding(t):
    """f2f is the row that would otherwise be the false positive.

    There are more wrong tests than there are inconsistencies, which is the
    whole reason the second round exists."""
    got, _ = promises_mod.verdict({"a": 1, "b": 0}, {"a": 1, "b": 0})
    if got != "the test was wrong":
        return f"a test both versions fail was reported as {got!r}"
    if promises_mod.verdict({"a": 0, "b": 0}, None)[0] != "consistent":
        return "all-passing was not read as consistent"
    if promises_mod.verdict({"a": 1}, None)[0] != "pending":
        return "a failure with no second round was not left pending"
    return None


def case_a_test_that_vanished_between_runs_counts_in_neither(t):
    """Pairing the runs by position would let one crash shift every verdict.

    A test that failed to run at all in the second round is absent, not
    failing, and counting it as failing would manufacture a pass-to-fail and
    silently discard a real finding."""
    counts = promises_mod.cross({"a": 1, "b": 0, "c": 0}, {"a": 0, "b": 0})
    if counts != {"p2p": 1, "f2f": 0, "f2p": 1, "p2f": 0}:
        return f"a missing test was counted somewhere: {counts}"
    return None


def case_a_fenced_example_is_not_a_promise(t):
    """A fence is an example, and it is where a document is most often right.

    Testing fences would spend the budget on the claims least likely to be
    wrong, and the sentence that matters is usually the prose beside it."""
    _doc(t, "d.md", "# Guide\n\n"
                    "The runner exits 2 when `dispatch.py` cannot see its "
                    "subject and must never return 0 in that case.\n\n"
                    "```\n"
                    "`build.py` always writes 0 and never exits 9 here\n"
                    "```\n")
    subprocess.run(["git", "init", "-q"], cwd=t, check=True)
    subprocess.run(["git", "add", "-A"], cwd=t, check=True)
    got = promises_mod.claims(t)
    if not got:
        return "the prose claim outside the fence was lost too"
    if any("build.py" in c["says"] for c in got):
        return "a sentence inside a fenced block was taken as a promise"
    return None


def case_a_claim_has_to_name_something_executable(t):
    """Otherwise every emphatic sentence in the repository is a claim.

    "This must never happen" is a promise about nothing a test can reach, and
    an agent asked to write a test for it will write one for whatever it
    imagines the subject to be."""
    _doc(t, "d.md", "# Guide\n\n"
                    "This must never happen and the team always agrees on "
                    "that, which is why it matters so much to everyone.\n\n"
                    "The tool exits 2 when `dispatch.py` cannot see its "
                    "subject and must never return 0 in that case.\n")
    subprocess.run(["git", "init", "-q"], cwd=t, check=True)
    subprocess.run(["git", "add", "-A"], cwd=t, check=True)
    got = promises_mod.claims(t)
    if len(got) != 1:
        return ("expected only the sentence naming something executable, got "
                + repr([c["says"][:50] for c in got]))
    if got[0]["kind"] != "exit code":
        return f"an exit-code promise was ranked as {got[0]['kind']!r}"
    return None




def case_a_test_that_does_not_parse_never_became_evidence(t):
    """CASCADE drops an uncompilable test; Python has to be told to.

    A test with a syntax error exits non-zero on both runs, so it crosses as
    `f2f` and reaches the right verdict -- but only after a second agent round
    has been spent on the claim. Worse, a claim whose *only* failing tests were
    typos goes `pending`, which is what schedules that round. Parsing costs
    nothing and answers before the bill."""
    ok, dropped = promises_mod.runnable([
        {"name": "good", "source": "print('fine')\n"},
        {"name": "typo", "source": "def broken(:\n"},
    ])
    if [c["name"] for c in ok] != ["good"]:
        return f"a test that does not parse was kept: {[c['name'] for c in ok]}"
    if [d["name"] for d in dropped] != ["typo"]:
        return f"the unparseable test was not reported: {dropped}"
    return None


def case_a_missing_import_is_the_finding_and_is_never_dropped(t):
    """The drop is syntax only, and widening it would delete the findings.

    A test that reaches for something the document promised and the code does
    not have fails at import time. That failure is exactly what dimension 4.3
    is looking for -- round two decides whether the document or the test was
    wrong -- so it has to run. A filter that also dropped tests which fail to
    import would silently make the method incapable of reporting the most
    common inconsistency there is."""
    ok, dropped = promises_mod.runnable([
        {"name": "absent", "source": "import a_module_that_is_not_here\n"},
        {"name": "attr", "source": "import os\nos.promised_by_the_doc()\n"},
    ])
    if dropped:
        return f"a test that parses was dropped before it ran: {dropped}"
    if len(ok) != 2:
        return "a runnable test was lost"
    return None


def case_a_claim_whose_tests_all_failed_to_parse_is_untested(t):
    """Not `pending`, which would buy it a second agent round for nothing.

    The paper's equivalent returns negative when nothing compiled after three
    repairs. Reporting it as pending instead would spend the most expensive
    round on the page to discover that the agent typed a bracket wrong."""
    claims = [{"id": 1, "doc": "d.md", "says": "it exits 2", "names": ["x.py"],
               "kind": "exit code"}]
    got = promises_mod.check(t, claims, {"tests": [
        {"claim_id": 1, "targets": "x.py",
         "cases": [{"name": "one", "source": "def (:\n"}]}]}, t)
    if got[0].get("verdict") != "not tested":
        return ("a claim with no parseable test was reported as "
                + repr(got[0].get("verdict")))
    if not got[0].get("dropped"):
        return "the claim does not say which tests were dropped"
    return None



def case_a_claim_still_waiting_on_round_two_is_not_a_pass(t):
    """The one direction this row cannot afford to be wrong in.

    A `pending` claim is one whose test the real code *failed*; what has not
    happened is the round that decides whether the document or the test was
    at fault. Counting it under `ok` beside "the code passed it" turns the
    most expensive measurement on the page into a clean bill for the exact
    repository it was run to catch."""
    def row_for(verdict):
        got = dim_mod.repository_memory(
            t, None, promises=[{"doc": "d.md", "says": "it exits 2",
                                "verdict": verdict}])
        for r in got.get("rows", []):
            if "promises the code does not keep" in r.get("label", ""):
                return r
        return None

    if (row_for("consistent") or {}).get("flag") != "ok":
        return "a claim the real code passed was not reported as ok"
    row = row_for("pending")
    if row is None:
        return "the promises row vanished once a claim had been run"
    if row.get("flag") == "ok":
        return "a claim whose test the real code failed was reported as ok"
    if "passed it" in row.get("note", ""):
        return "a pending claim was described as the code having passed"
    return None

def case_the_blind_agent_cannot_read_the_repository(t):
    """The tool list is the experiment, not a sentence in the prompt.

    A test written after reading the implementation agrees with it by
    construction. `repo-promise-tester` is given `Write` and nothing else so
    that the blind is a fact about what it can do -- an instruction asking it
    not to look is one an agent can talk itself out of, and the whole method
    is worthless the moment it does."""
    import re as _re
    plugin = os.path.dirname(os.path.dirname(PARENT))
    path = os.path.join(plugin, "agents", "repo-promise-tester.md")
    if not os.path.exists(path):
        return "the agent that writes the tests is missing"
    head = open(path, encoding="utf-8").read().split("---")[1]
    m = _re.search(r"^tools:\s*(.+)$", head, _re.M)
    if not m:
        return "the agent declares no tool list, so it inherits everything"
    tools = {x.strip() for x in m.group(1).split(",")}
    can_read = tools & {"Read", "Grep", "Glob", "Bash", "Task", "WebFetch",
                        "NotebookEdit", "Edit"}
    if can_read:
        return ("the blind agent can reach the code it is not allowed to "
                "read: " + ", ".join(sorted(can_read)))
    return None

LONG_A = ("The runner refuses to continue when the tree is dirty, because a "
          "half-applied change is indistinguishable from a finished one. ")
LONG_B = ("Every check writes its reason to standard error, since that is the "
          "one place a negative is guaranteed to be read by somebody stuck. ")
TABLE = ("| name | what it means | when it fires | who reads it |\n"
         "|---|---|---|---|\n"
         "| refuse | the write never reached the disk | before the edit | "
         "the agent that tried it |\n"
         "| record | it happened and was noted | after the edit | "
         "whoever reads the log later |\n")


def _unit(t, rel, body):
    full = os.path.join(t, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(full) or t, exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(body)
    return full



def case_a_document_nobody_loads_is_not_a_context_cost(t):
    """A guide is read the way any file is read: somebody opens it.

    This dimension is about text the harness puts in front of the model
    without anyone asking. Sweeping every markdown file in the tree charges a
    repository for having explained itself, and reported this project's own
    assessment guide as the most expensive file it owns -- 4.6x the median
    document, and nothing loads it. That is not an over-count, it is the wrong
    population.

    The fixture makes the un-loaded file enormous on purpose: if it were in,
    it would dominate."""
    repo(t)
    _unit(t, "CLAUDE.md", "# rules\n\nKeep it short.\n")
    _unit(t, "guide/1-assess.md", "# guide\n\n" + ("A long explanation. " * 900))
    _unit(t, "docs/decisions/0001-a-thing.md", "# 0001\n\n" + ("Because. " * 900))
    _unit(t, "README.md", "# readme\n\n" + ("Welcome here. " * 900))
    commit(t, "docs: a small floor and three long documents")
    r, why = units_mod.measure(t)
    if r is None:
        return f"nothing was measured at all: {why}"
    seen = {u["path"] for u in r["units"]}
    leaked = sorted(seen & {"guide/1-assess.md", "README.md",
                            "docs/decisions/0001-a-thing.md"})
    if leaked:
        return "documents nobody loads were charged as context: " + repr(leaked)
    if "CLAUDE.md" not in seen:
        return "the one file that is loaded was dropped along with them"
    return None


def case_a_skills_reference_is_loaded_and_is_counted(t):
    """The other side of the same line, and the reason it is a line not a rule
    about directories.

    A skill's `references/` reach the model when the skill fires, so they are
    in. A document sitting beside them is not. Dropping the whole of a skill
    directory would lose the finding this dimension is best at -- the same
    paragraph in a SKILL.md and in its own reference, paid for twice whenever
    that skill runs and free to drift apart."""
    repo(t)
    _unit(t, "CLAUDE.md", "# rules\n\nKeep it short.\n")
    shared = ("Every check must be watched failing before it counts as a "
              "check, because a check nobody has seen turn red is a file.\n")
    _unit(t, "skills/writing/SKILL.md", "# writing\n\n" + shared + "\nMore.\n")
    _unit(t, "skills/writing/references/kinds.md",
          "# kinds\n\n" + shared + "\nOther things.\n")
    commit(t, "docs: a skill and its reference share a sentence")
    r, why = units_mod.measure(t)
    if r is None:
        return f"nothing was measured at all: {why}"
    seen = {u["path"] for u in r["units"]}
    if "skills/writing/references/kinds.md" not in seen:
        return "a skill reference was dropped as though nothing loads it"
    dup = r.get("duplicated_sentences") or []
    if not dup:
        return ("the sentence shared by a skill and its own reference was not "
                "reported as paid for twice")
    return None


def case_a_repeated_table_is_not_a_repeated_paragraph(t):
    """Two files sharing a reference table are usually sharing it on purpose.

    And a markdown table flattens into one enormous pseudo-sentence, so the
    first version of this reported a garbled table row as the duplicated
    prose. Duplication here is about paragraphs: the same paragraph in two
    loaded files is the thing that drifts."""
    # On rule paths, not docs/: a document nobody loads is outside this
    # dimension entirely, so a fixture written in docs/ measures nothing.
    _unit(t, ".claude/rules/a.md", "# A\n\n" + TABLE + "\n" + LONG_A)
    _unit(t, ".claude/rules/b.md", "# B\n\n" + TABLE + "\n" + LONG_B)
    subprocess.run(["git", "init", "-q"], cwd=t, check=True)
    subprocess.run(["git", "add", "-A"], cwd=t, check=True)
    r, why = units_mod.measure(t)
    if not r:
        return f"nothing was read: {why}"
    if r["duplicated_sentences"]:
        return ("a shared table was counted as a repeated paragraph: %d"
                % r["duplicated_sentences"])

    _unit(t, ".claude/rules/b.md", "# B\n\n" + TABLE + "\n" + LONG_A)
    subprocess.run(["git", "add", "-A"], cwd=t, check=True)
    r, _why = units_mod.measure(t)
    if r["duplicated_sentences"] != 1:
        return ("a paragraph in two files was not counted: %d"
                % r["duplicated_sentences"])
    return None


def case_a_file_is_compared_to_its_own_kind(t):
    """A skill is not large because decision records are small.

    Comparing across genres would report every skill as an outlier in a
    repository whose documents are short, which is a fact about the two
    genres and not about the repository."""
    for i in range(4):
        _unit(t, "docs/d%d.md" % i, "# D\n\n" + LONG_A * 3)
    for i in range(3):
        _unit(t, "skills/s%d/SKILL.md" % i, "# S\n\n" + LONG_B * 40)
    subprocess.run(["git", "init", "-q"], cwd=t, check=True)
    subprocess.run(["git", "add", "-A"], cwd=t, check=True)
    r, _why = units_mod.measure(t)
    flagged = {o["path"] for o in r["outliers"]
               if any("median" in w for w in o["why"])}
    if flagged:
        return ("files were called outliers against another genre's median: "
                + repr(sorted(flagged)))
    _unit(t, "skills/big/SKILL.md", "# S\n\n" + LONG_B * 400)
    subprocess.run(["git", "add", "-A"], cwd=t, check=True)
    r, _why = units_mod.measure(t)
    flagged = {o["path"] for o in r["outliers"]
               if any("median" in w for w in o["why"])}
    if flagged != {"skills/big/SKILL.md"}:
        return f"the skill unlike other skills was not found: {sorted(flagged)}"
    return None


def case_a_small_file_is_never_an_outlier_for_being_large(t):
    """Three times nothing is still nothing.

    Without a floor, a repository of one-paragraph rules reports the
    two-paragraph one as four times the median — true, and not worth anybody
    reading a row about."""
    for i in range(4):
        _unit(t, ".claude/rules/r%d.md" % i, "Keep it short.\n")
    _unit(t, ".claude/rules/big.md", LONG_A * 4)
    subprocess.run(["git", "init", "-q"], cwd=t, check=True)
    subprocess.run(["git", "add", "-A"], cwd=t, check=True)
    r, _why = units_mod.measure(t)
    if any("median" in w for o in r["outliers"] for w in o["why"]):
        return ("a file under the size floor was reported for being unlike "
                "its neighbours: " + repr(r["outliers"]))
    return None


def case_an_untracked_file_is_not_loadable_context(t):
    """The same rule 4.4 needs, for the same reason.

    A draft nobody committed is not what the repository loads, and counting
    it moves every median."""
    _unit(t, ".claude/rules/kept.md", LONG_A * 2)
    _unit(t, ".claude/rules/scratch.md", LONG_A * 2)
    subprocess.run(["git", "init", "-q"], cwd=t, check=True)
    subprocess.run(["git", "add", ".claude/rules/kept.md"], cwd=t,
                   check=True)
    r, _why = units_mod.measure(t)
    if [u["path"] for u in r["units"]] != [".claude/rules/kept.md"]:
        return ("an untracked draft was counted as loadable context: "
                + repr([u["path"] for u in r["units"]]))
    return None



_ALWAYS_NO = ("#!/usr/bin/env python3\n"
              "import json, sys\n"
              "json.load(sys.stdin)\n"
              "print('Blocked: everything is blocked', file=sys.stderr)\n"
              "sys.exit(2)\n")



def _run_with(rows):
    """A run's JSON, with whichever rows the case is about."""
    return {"dimensions": [{"title": "Made Up", "rows": rows}]}


def case_an_abstention_does_not_become_a_number(t):
    """The one thing the reading is not allowed to do.

    Every other guard on this page keeps `could not judge` off it. This is the
    last place it could get back on, and it is the worst place: a number on a
    chart is indistinguishable from a measurement, so scoring an abstention
    turns `we could not run your tests` into `your tests are bad` with nothing
    in between.

    An abstention and an ordinary fact share the `info` flag, which is why the
    check is on the value."""
    run = _run_with([
        {"label": "an agent finding its way", "value": "not probed",
         "flag": "info", "note": ""},
        {"label": "documents that contradict each other",
         "value": "1 candidate(s), not yet judged", "flag": "info", "note": ""},
        {"label": "refused before they happen", "value": "3/6",
         "flag": "warn", "note": ""},
    ])
    items, unmapped = review_mod.collect(run)
    ids = [i["id"] for i in items]
    if ids != ["1.1"]:
        return "abstentions were handed over to be scored: " + repr(ids)
    if unmapped:
        return "an abstention was reported as an unmapped row: " + repr(unmapped)

    text, _why = review_mod.brief(run)
    for gone in ("finding its way", "contradict each other"):
        if gone in text:
            return f"the brief asked about an abstention: {gone!r}"
    return None


def case_a_reading_of_the_candidates_can_be_recorded(t):
    """A list nobody can answer is a list everybody re-reads.

    4.4 got an answers file and 4.2 did not, so the same 24 candidates came
    back on every run of every assessment forever -- and each reader paid
    again to rediscover that most of them name a path a scaffolded repository
    has and this one deliberately does not. The reading was happening; only
    the record of it was missing.

    Three things the channel has to hold, and each is a way it could quietly
    lie. An id nobody handed over is an invented answer. Answering none of
    them is not the same as dismissing all of them. And an unanswered id is
    pending rather than dismissed, because an unread candidate and a
    considered one are different states."""
    r = {"candidates": [
        {"tier": 1, "file": "a.md", "claim": "two hooks", "why": "4 in hooks/"},
        {"tier": 2, "file": "b.md", "claim": "scripts/guards/", "why": "gone"},
        {"tier": 3, "file": "c.md", "claim": "moved", "why": "stale"}]}

    got, why = truth_mod.grade(r, {"candidates": [
        {"id": 0, "real": False, "why": "hooks.json is not a hook"},
        {"id": 2, "real": True, "why": "the guide never got the new section"},
        {"id": 99, "real": True, "why": "a candidate nobody was handed"}]})
    if got is None:
        return "a well-formed reading was refused: " + why
    if len(got["real"]) != 1 or len(got["dismissed"]) != 1:
        return ("the verdicts did not survive: %d real, %d dismissed"
                % (len(got["real"]), len(got["dismissed"])))
    if got["pending"] != 1:
        return "an unanswered candidate was not left pending: %d" % got["pending"]
    if got["judged"] != 2:
        return "an invented id was counted as judged: %d" % got["judged"]
    if got["real"][0]["candidate"]["file"] != "c.md":
        return "a verdict was attached to the wrong candidate"

    for bad, what in (({"candidates": []}, "an empty reading"),
                      ({"pairs": []}, "the wrong shape"),
                      ([], "a list")):
        if truth_mod.grade(r, bad)[0] is not None:
            return what + " was accepted as a judgement"

    # A tier-3 reading expires when the document it was about changes, and
    # only then. Its claim counts commits to what the document *points at*, so
    # it moves whenever somebody else's file is touched -- keying the answer to
    # it would expire every verdict on every commit. Keying it to nothing would
    # apply a reading of last week's document to this week's.
    moved = {"candidates": [
        {"tier": 3, "file": "d.md", "claim": "2 commit(s) ...", "moved": 100}]}
    answer = [{"id": 0, "file": "d.md", "tier": 3, "moved": 100,
               "real": False, "why": "the churn is its subjects working"}]
    got, _why = truth_mod.grade(moved, {"candidates": answer})
    if not got or len(got["dismissed"]) != 1:
        return "a reading of an unchanged document did not stand"

    churned = {"candidates": [dict(moved["candidates"][0],
                                   claim="9 commit(s) ...")]}
    got, _why = truth_mod.grade(churned, {"candidates": answer})
    if not got or len(got["dismissed"]) != 1:
        return "a reading expired because somebody else committed"

    rewritten = {"candidates": [dict(moved["candidates"][0], moved=200)]}
    got, why = truth_mod.grade(rewritten, {"candidates": answer})
    if got is not None:
        return "a reading of a document that has since changed was still applied"

    # ...and the questions have to carry the ids the answers use.
    text = truth_mod.brief(r)
    for n in ("## 0", "## 1", "## 2"):
        if n not in text:
            return "the brief did not offer id " + n
    if truth_mod.brief({"candidates": []}):
        return "a brief was produced with nothing to ask about"
    return None


def case_the_surface_is_coverage_not_a_count(t):
    """The test 0025 used, applied to the row that came after it.

    0025 refused to score a repository on what it keeps, and the case that
    settled it was 0024: deleting five skills cut the standing cost by 81%,
    and any measure calling that a regression is measuring the wrong thing.
    So this row is present/absent per mechanism and never a quantity -- six
    skills are the same coverage as one, and deleting five of them cannot
    move it.

    Two more ways it could quietly become what 0025 rejected. A skill a
    plugin installed is on somebody's laptop, not in this tree, so counting
    it would let the instrument reward its own presence -- and a teammate
    without the plugin gets nothing. And a `.claude/rules` file with no
    `paths:` frontmatter loads at launch: it is a slower entry file rather
    than a scoped rule, which is why the budget gate counts it on the
    floor."""
    def probe_with(**over):
        base = {"moments": {"1_always": [{"file": "CLAUDE.md", "lines": 9}],
                            "4_subtree": [], "2_session_start": 0,
                            "3_prompt": 0, "6_after_action": 0,
                            "5_before_action": {"PreToolUse": 0,
                                                "permissions_deny": 0},
                            "7_on_request": []},
                "discipline": {"other_hooks": {}}}
        base["moments"].update(over)
        return base

    one = surface_mod.assess(t, probe_with(
        **{"7_on_request": [{"origin": "repo"}]}))
    six = surface_mod.assess(t, probe_with(
        **{"7_on_request": [{"origin": "repo"}] * 6}))
    if one["reached"] != six["reached"]:
        return ("six skills scored differently from one — this is a count, "
                "and 0024 would read as a regression")

    plugin_only = surface_mod.assess(t, probe_with(
        **{"7_on_request": [{"origin": "plugin"}] * 3}))
    if plugin_only["have"]["skills"]:
        return "a skill installed by a plugin was counted as the repository's"

    # A deny rule reaches the same moment a PreToolUse hook does.
    hook = surface_mod.assess(t, probe_with(
        **{"5_before_action": {"PreToolUse": 1, "permissions_deny": 0}}))
    deny = surface_mod.assess(t, probe_with(
        **{"5_before_action": {"PreToolUse": 0, "permissions_deny": 4}}))
    if not (hook["have"]["before"] and deny["have"]["before"]):
        return "a repository that can refuse an action was reported as unable"

    # `.claude/rules` without `paths:` loads at launch: an entry file, not a
    # scoped rule.
    os.makedirs(os.path.join(t, ".claude", "rules"), exist_ok=True)
    put(t, ".claude/rules/loose.md", "# always on\n")
    if surface_mod.assess(t, probe_with())["have"]["scoped"]:
        return "an unscoped rule was credited as path-scoped coverage"
    put(t, ".claude/rules/scoped.md", "---\npaths: src/**\n---\n\nhere\n")
    if not surface_mod.assess(t, probe_with())["have"]["scoped"]:
        return "a rule with `paths:` was not seen"

    # ...and every absence has to say what it costs, or the row is a scold.
    for a in surface_mod.assess(t, probe_with())["absent"]:
        if not a["costs"] or not a["where"]:
            return "an absence was reported without what it costs: " + a["what"]
    return None


def case_a_dimension_that_read_nothing_abstains(t):
    """The rule that outlived the measurement it was written for.

    Dimension 4 used to have a navigation half that cost two agents, and this
    case said an unprobed repository must abstain rather than score zero --
    a repository nobody has probed is not a repository nobody can navigate.
    That half is gone -> 0042, and the rule is now about the half that stayed:
    a tree `truth.assess()` could not read is not a tree whose documentation
    is sound, and `every reference resolves` said over zero documents is the
    same false clean bill in a cheaper form."""
    got = dim_mod.repository_memory(t, [], (), None)
    if got["state"] != "abstained":
        return "a dimension that read nothing reported %r" % got["state"]
    if "resolve" in got["headline"]:
        return "an unread tree was given a clean bill: " + got["headline"]

    read = dim_mod.repository_memory(t, [], (), {
        "thickness": {"documents": 1}, "proven": [], "candidates": [],
        "checked": 1})
    if read["state"] != "measured":
        return "a tree that was read still abstained"
    return None


def case_every_printed_row_is_claimed_by_a_sub_item(t):
    """A measurement no sub-item claims is a measurement nobody scores.

    `reframe.py` printed four rows into dimension 4 for a week and every one
    of them landed under "Rows no sub-item claims" -- visible, which is the
    design, and never once graded, which is not. The failure is quiet in the
    direction that matters: the page looks complete, the radar looks complete,
    and the thing that was measured is missing from both.

    So the mapping is pinned here rather than left to whoever adds the next
    row. The labels below are the ones the modules actually emit, indentation
    included, because `collect` matches on a substring of the label and a row
    that is only nearly named is a row that is not claimed."""
    run = _run_with([
        {"label": "the form of the instructions",
         "value": "7 of 19 unit(s) have an opening", "flag": "info", "note": ""},
        {"label": "  prohibitions with no stated alternative",
         "value": "9", "flag": "info", "note": ""},
        {"label": "  paragraphs carrying several requirements at once",
         "value": "2", "flag": "info", "note": ""},
        {"label": "  requirements asking for a quality, not a shape",
         "value": "3", "flag": "info", "note": ""},
    ])
    items, unmapped = review_mod.collect(run)
    if unmapped:
        return "a printed measurement no sub-item claims: " + repr(unmapped)
    ids = [i["id"] for i in items]
    if ids != ["4.5"]:
        return "the form rows did not land under one sub-item: " + repr(ids)
    if len(items[0]["rows"]) != 4:
        return ("%d of 4 form rows reached the sub-item"
                % len(items[0]["rows"]))
    return None


def case_a_score_for_something_nobody_measured_is_refused(t):
    """The brief and the grader have to agree about what exists.

    An agent that returns a number for a sub-item the brief did not ask about
    has invented it, and the only reason to notice is that one function
    decides what was measured. Refusing is louder than dropping: the run says
    which id it threw away and why."""
    run = _run_with([{"label": "refused before they happen", "value": "3/6",
                      "flag": "warn", "note": ""}])
    judged, why = review_mod.grade(run, {"items": [
        {"id": "1.1", "score": 4, "why": "three of six are open"},
        {"id": "2.2", "score": 9, "why": "invented -- nothing mutated here"},
    ]})
    if judged is None:
        return f"nothing was graded at all: {why}"
    if "2.2" in judged["items"]:
        return "a score for an unmeasured sub-item was kept"
    if not any(sid == "2.2" for sid, _ in judged["refused"]):
        return "an invented sub-item was dropped silently instead of refused"
    return None


def case_a_number_off_the_scale_is_refused(t):
    """Nothing downstream re-checks the range.

    The radar maps a score straight onto a radius, so an 11 draws outside the
    outer ring and a -1 draws through the centre and out the other side. Both
    look like a rendering bug rather than a bad answer."""
    run = _run_with([{"label": "refused before they happen", "value": "3/6",
                      "flag": "warn", "note": ""},
                     {"label": "floor — paid on every turn", "value": "~900",
                      "flag": "ok", "note": ""}])
    judged, _why = review_mod.grade(run, {"items": [
        {"id": "1.1", "score": 11, "why": "off the top"},
        {"id": "5.1", "score": 7, "why": "small and load-bearing"},
    ]})
    if judged is None:
        return "a single bad number threw the whole reading away"
    if "1.1" in judged["items"]:
        return "a score of 11 was accepted"
    if "5.1" not in judged["items"]:
        return "the good answer was discarded along with the bad one"
    return None


def case_the_radar_puts_a_low_axis_nearer_the_centre(t):
    """The chart is the only part anybody looks at first.

    A polygon that does not move with the numbers is worse than no polygon:
    it reads as a measurement and carries none. So this asserts the one
    property the shape has to have, on the axis geometry rather than on a
    pixel."""
    import math
    svg = review_mod.radar({"1": 1, "2": 9, "3": 5, "4": 5, "5": 5}, size=400)
    body = svg.split('fill-opacity="0.17"')[0]
    pts = body.rsplit('<polygon points="', 1)[1].split('"')[0].split()
    if len(pts) != 5:
        return f"the reading polygon does not have five corners: {pts!r}"
    cx, cy = 200.0, 184.0
    radii = []
    for p in pts:
        x, y = (float(v) for v in p.split(","))
        radii.append(math.hypot(x - cx, y - cy))
    if not radii[0] < radii[2] < radii[1]:
        return ("the polygon does not follow the numbers: 1 scored 1, 3 scored "
                "5, 2 scored 9, radii were " + repr([round(r) for r in radii]))
    return None


def _hooked(t, body):
    os.makedirs(os.path.join(t, ".claude"), exist_ok=True)
    with open(os.path.join(t, "everything.py"), "w", encoding="utf-8") as fh:
        fh.write(body)
    with open(os.path.join(t, ".claude", "settings.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
            {"type": "command",
             "command": "python3 \"$CLAUDE_PROJECT_DIR/everything.py\""}]}]}},
            fh)
    return t


def case_nothing_wired_cannot_fail_the_legitimate_row(t):
    """A repository with no guard has no guard to be wrong about.

    Reporting `0 of 20 blocked` for a repository that blocks nothing would
    put a tick beside the very thing dimension 1 exists to find missing."""
    got, why = permitted_mod.evidence(t)
    if got:
        return "a repository with no hooks was still measured for false blocks"
    if "nothing is wired" not in why:
        return f"the abstention does not say why: {why!r}"
    return None


def case_a_guard_that_refuses_everything_is_caught_here(t):
    """The row exists because 6 of 6 refusals is free to such a guard.

    Dimension 1 counts what a repository refuses. This is what stops that
    number being awarded to a repository that has simply stopped working."""
    _hooked(t, _ALWAYS_NO)
    got, why = permitted_mod.fire(t, {"actions": [
        {"what": "run the tests", "tool": "Bash", "command": "pytest -q"},
        {"what": "read history", "tool": "Bash", "command": "git log -1"}]})
    if not got:
        return f"nothing was fired: {why}"
    if len(got["blocked"]) != 2:
        return ("a hook refusing everything let legitimate work through: "
                + repr(got["blocked"]))
    if not got["blocked"][0]["by"]:
        return "the refusing hook was not named, so nobody can go and fix it"
    return None


def case_only_a_shell_fence_is_a_documented_command(t):
    """A fenced Python block is an example of code, not an instruction.

    Firing `def main():` at the hooks as though somebody had typed it into a
    shell produces noise in the corpus an agent is meant to build on."""
    _hooked(t, _ALWAYS_NO)
    with open(os.path.join(t, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("# R\n\n```bash\npython3 run_all_of_it.py --root .\n```\n\n"
                 "```python\ndef never_run_this_from_a_shell():\n    pass\n```\n")
    got, _why = permitted_mod.evidence(t)
    cmds = [c["command"] for c in got["documented_commands"]]
    if "python3 run_all_of_it.py --root ." not in cmds:
        return f"the shell command was not collected: {cmds}"
    if any("def " in c for c in cmds):
        return f"a python fence was collected as a shell command: {cmds}"
    return None


def case_a_ci_step_that_is_a_template_is_not_a_command(t):
    """`${{ ... }}` is filled in by the runner, not by a shell.

    Firing the literal text measures nothing, and it is the shape most likely
    to look alarming to a guard while meaning nothing at all."""
    _hooked(t, _ALWAYS_NO)
    where = os.path.join(t, ".github", "workflows")
    os.makedirs(where, exist_ok=True)
    with open(os.path.join(where, "ci.yml"), "w", encoding="utf-8") as fh:
        fh.write("on: [push]\njobs:\n  t:\n    steps:\n"
                 "      - run: python3 selftest.py\n"
                 "      - run: deploy --to ${{ secrets.TARGET }}\n")
    got, _why = permitted_mod.evidence(t)
    cmds = [c["command"] for c in got["ci_commands"]]
    if "python3 selftest.py" not in cmds:
        return f"a real CI command was lost: {cmds}"
    if any("${{" in c for c in cmds):
        return f"an unexpanded template was collected as a command: {cmds}"
    return None



def _ranked(sides, counts=None):
    """Candidate pairs built by hand, so a criterion can be held still.

    `sides` is a list of pairs, each ((ts, floor, values), (ts, floor,
    values)). Going through `narrow` instead would mean forging commit dates,
    and the arithmetic under test does not care where the numbers came from."""
    pairs = []
    for a, b in sides:
        pair = {"subject": "`k`", "kind": "different number",
                "a": {"path": "a.md", "value": a[2], "says": "",
                      "last_changed": a[0], "on_floor": a[1]},
                "b": {"path": "b.md", "value": b[2], "says": "",
                      "last_changed": b[0], "on_floor": b[1]}}
        if counts:
            pair["code_says_count"] = counts
        pairs.append(pair)
    weights = conflict_mod.rank(pairs)
    return pairs, weights


def case_a_signal_that_never_varies_is_weighted_to_zero(t):
    """The property the entropy step is here for.

    `on_floor` is false on every candidate in most repositories. A reader
    skipping past the same "neither is on the floor" on every pair is doing by
    hand what the weight says once. ConflictRAG III-C: higher entropy is less
    discriminating power, so lower weight."""
    _pairs, w = _ranked([((1000, False, ["1"]), (2000, False, ["2"])),
                         ((1500, False, ["3"]), (9000, False, ["4"]))])
    if w.get("on_floor") != 0.0:
        return (f"a criterion identical on every candidate still carried "
                f"weight {w.get('on_floor')}")
    if not w.get("recency"):
        return f"the criterion that did vary was not weighted: {w}"
    return None


def case_raw_timestamps_collapse_every_weight(t):
    """Why the matrix is min-maxed before the entropy, and not after.

    Commit times inside one repository agree to four significant figures.
    Feed them in raw and every p_ij is uniform to a rounding error, so recency
    comes out with the entropy of a constant and a weight near zero. The
    signal is dropped and nothing says it was.

    Recency has to be made to *compete* to show this. Alone it survives the
    bug: the other two criteria are constant, their entropy is exactly 1, and
    a lone non-degenerate column normalises to the whole weight however
    little it discriminates. Against a criterion that does discriminate, raw
    timestamps take 0.00 and min-maxed ones take about half."""
    now = 1_750_000_000
    day = 86_400
    counts = {"1": 50, "2": 3, "3": 3, "4": 50}
    _pairs, w = _ranked([((now, False, ["1"]), (now + 200 * day, False, ["2"])),
                         ((now + 5 * day, False, ["3"]),
                          (now + 100 * day, False, ["4"]))],
                        counts=counts)
    if w.get("recency", 0) < 0.2:
        return (f"eight months between two documents weighed "
                f"{w.get('recency')} against a criterion that did vary — raw "
                f"timestamps were fed to the entropy step")
    return None


def case_a_truncated_grep_is_not_the_strength_of_the_signal(t):
    """Three is how many files a reader will open, not how much evidence.

    `_code_says` caps its file list at three for display. Ranking on that list
    read a value in fifty files and a value in three as equal evidence, and
    `code_agrees` then weighted itself to zero for having said nothing."""
    counts = {"1": 50, "2": 3}
    pairs, w = _ranked([((1000, False, ["1"]), (1000, False, ["2"])),
                        ((1000, False, ["2"]), (1000, False, ["1"]))],
                       counts=counts)
    if not w.get("code_agrees"):
        return ("fifty files against three did not separate the sides: "
                f"code_agrees weighed {w.get('code_agrees')}")
    if pairs[0]["a"]["credibility"] <= pairs[0]["b"]["credibility"]:
        return "the value the code contains fifty times did not outrank three"
    return None


def case_the_score_ranks_and_does_not_decide(t):
    """The divergence from the paper, and the one worth a guard.

    ConflictRAG selects a source and generates from it. This is a diagnostic:
    it hands the number over and the agent still answers `believe`. A
    diagnostic that started picking winners would have stopped being one."""
    pairs, _w = _ranked([((1000, False, ["1"]), (9000, True, ["2"]))])
    pair = pairs[0]
    for side in ("a", "b"):
        if pair[side].get("credibility") is None:
            return f"side {side} came back without a score at all"
    for key in ("believe", "real", "verdict", "winner"):
        if key in pair or key in pair["a"] or key in pair["b"]:
            return (f"the ranking wrote `{key}` into the candidate — it has "
                    f"started answering the question it is meant to inform")
    return None


def case_a_tie_is_a_tie_and_not_a_column_order(t):
    """Two sides no criterion separates score 0.5, both of them.

    D+ and D- are both zero there, and the ratio is undefined. Returning
    anything but a tie would invent a finding out of a division."""
    pairs, _w = _ranked([((1000, False, ["1"]), (1000, False, ["2"]))])
    a = pairs[0]["a"]["credibility"]
    b = pairs[0]["b"]["credibility"]
    if a != b:
        return f"identical candidates were ranked apart: {a} against {b}"
    return None



def case_a_fact_about_the_code_is_not_a_prohibition(t):
    """The defect this file shipped on its first run, kept.

    English spells a prohibition and a statement of fact almost identically:
    "no check may swallow a status" instructs somebody, "the two cannot drift"
    describes a property. The first version counted both, and produced 116
    findings across 19 files -- most of them the repository describing itself.
    A measurement that fires on every paragraph is not a measurement, so the
    fact half has to stay silent."""
    unit = {"path": "CLAUDE.md", "kind": "root instruction", "text": (
        "It parses the workflow rather than restating it, so the two cannot "
        "drift. A step it does not recognise is exit 2, and exit 2 is never "
        "a pass. Nothing here reaches the network.\n")}
    got = [o for o in reframe_mod.openings(unit) if o["operation"] == "positive"]
    if got:
        return ("prose describing how something works was read as a "
                "prohibition: " + got[0]["text"])
    return None


def case_a_prohibition_with_no_alternative_is_found(t):
    """...and the real thing still has to come back.

    The half above is only worth having if this half fires. A tightening that
    silences the false positives by silencing everything is the failure mode
    the two cases exist together to catch."""
    unit = {"path": "CLAUDE.md", "kind": "root instruction", "text":
            "Do not commit a generated file.\n"}
    got = [o for o in reframe_mod.openings(unit) if o["operation"] == "positive"]
    if not got:
        return "a bare prohibition produced no reframing candidate"
    return None


def case_a_prohibition_that_says_what_to_do_instead_is_left_alone(t):
    """The paper's operation is *restating* a negation, not deleting it.

    A rule that says what not to do and then what to do is already in the
    shape the reframing produces. Reporting it would send somebody to rewrite
    a sentence that is finished, and the alternative is as often in the next
    sentence as in the same one."""
    same = {"path": "a.md", "kind": "root instruction", "text":
            "Do not commit a generated file; write it into build/ instead.\n"}
    next_one = {"path": "b.md", "kind": "root instruction", "text":
                "Do not commit a generated file. Instead, put it in build/.\n"}
    for unit in (same, next_one):
        got = [o for o in reframe_mod.openings(unit)
               if o["operation"] == "positive"]
        if got:
            return ("a prohibition that states its alternative was reported: "
                    + unit["text"].strip())
    return None


def case_an_example_of_a_rule_is_not_a_rule(t):
    """Sixth instance of the bug class, refused in advance.

    A skill that teaches somebody to write rules shows rules in fenced blocks.
    Every earlier check here that read a fence as live text shipped the same
    defect, and this one is written after five of them."""
    unit = {"path": "SKILL.md", "kind": "skill", "text": (
        "Here is the shape a rule takes:\n\n"
        "```markdown\n"
        "Never run the deploy script by hand.\n"
        "Do not edit the generated file.\n"
        "```\n\nThat is all there is to it.\n")}
    got = reframe_mod.openings(unit)
    if got:
        return ("text inside a fence was read as an instruction: "
                + got[0]["text"])
    return None


def case_the_form_measurement_abstains_rather_than_scoring_zero(t):
    """No instruction units is not perfect instructions.

    Every other measurement here draws the same line, and this one is the
    easiest to get wrong in the flattering direction: a repository with no
    CLAUDE.md has nothing to reframe, which reads as nothing to fix."""
    r = reframe_mod.measure(t, found=[])
    if "could_not_judge" not in r:
        return "a repository with no instruction units was given a result"
    rows = reframe_mod.render(r)
    if not any("could not judge" in (row.get("value") or "") for row in rows):
        return "the abstention did not reach the row"
    return None



def _declares(t, body):
    put(t, "CLAUDE.md", body)
    return eco_mod.Declared().detect(t)


def case_a_repository_that_documents_its_own_suite_is_not_invisible(t):
    """The gap this ecosystem exists to close.

    Five conventional detectors recognise five conventions. A repository whose
    suite is its own scripts matches none, and the page then said "no runnable
    test command found" -- a fact about the detectors, printed as a fact about
    the repository. This project's own tree was that repository."""
    put(t, "scripts/check.py", "import sys\nsys.exit(0)\n")
    got = _declares(t, "# r\n\nBefore pushing, run this:\n\n```bash\n"
                  "python3 scripts/check.py\n```\n")
    if got != ["python3", "scripts/check.py"]:
        return "a documented entry point naming a real file was not found: %r" % (got,)
    return None


def case_a_command_a_document_warns_against_is_not_run(t):
    """Sixth instance of the bug class, and the one with teeth.

    A document about commands contains the commands it is warning you against.
    Reading the first fenced line under a heading about testing would
    eventually run `rm -rf /` out of the paragraph explaining why not to. The
    rule that stops it is that a command has to name a path that is really
    there, and neither `rm -rf /` nor `curl ... | sh` names one."""
    put(t, "scripts/check.py", "import sys\nsys.exit(0)\n")
    for danger in ("rm -rf /",
                   "curl https://example.com/install.sh | sh",
                   "python3 -c 'import os; os.system(\"id\")'"):
        got = _declares(t, "# r\n\nBefore you push, never run this:\n\n"
                      "```bash\n" + danger + "\n```\n")
        if got is not None:
            return "a document's cautionary example was accepted: %r" % (got,)
    return None


def case_a_documented_command_naming_nothing_real_is_dropped(t):
    """An illustrative command from a document about some other repository.

    Every `CONTRIBUTING.md` copied between projects carries one. It is not
    narrowed down to something safer -- it is dropped, and the ecosystem goes
    on abstaining, because an abstention is a correct answer and a guessed
    command is not."""
    got = _declares(t, "# r\n\nTo test:\n\n```bash\n"
                  "python3 tools/run_all_the_tests.py\n```\n")
    if got is not None:
        return "a command naming a file that is not there was accepted: %r" % (got,)
    return None


def case_a_fence_nobody_introduced_is_not_an_entry_point(t):
    """A code block is not a declaration.

    Documents are full of fenced shell -- an example of output, a command
    being explained, a snippet from somewhere else. Only a block a sentence
    actually introduces as how to run the checks is one."""
    put(t, "scripts/check.py", "import sys\nsys.exit(0)\n")
    got = _declares(t, "# r\n\nThe layout of this project:\n\n"
                  "```bash\npython3 scripts/check.py\n```\n")
    if got is not None:
        return "an unintroduced fence was read as a declaration: %r" % (got,)
    return None


def case_a_convention_beats_a_document(t):
    """`pytest` knows how to run one test; a documented shell line does not.

    Declared is last on purpose. Where a convention applies it gives better
    failures and can be narrowed to the tests that must flip, which is what
    the defect replay needs."""
    put(t, "scripts/check.py", "import sys\nsys.exit(0)\n")
    put(t, "pyproject.toml", "[project]\nname = 'x'\n")
    put(t, "tests/test_x.py", "def test_x():\n    assert True\n")
    put(t, "CLAUDE.md", "# r\n\nBefore pushing, run this:\n\n"
                        "```bash\npython3 scripts/check.py\n```\n")
    eco, cmd = eco_mod.find(t)
    if eco is None or eco.name != "python":
        return ("a repository with a real pytest layout was routed to %s"
                % (eco.name if eco else None))
    return None



def case_an_entry_point_that_predates_the_commit_is_not_a_red_suite(t):
    """The command is found at HEAD; the replay runs in the past.

    A repository that introduced its suite last week has a history of commits
    where the entry point does not exist. The interpreter exits non-zero there
    for the same reason a failing test does, and reading it as red reports
    every commit older than the suite as broken. This repository hit it on the
    first run after gaining a documented entry point.

    The other half is what must NOT be swallowed: a test failing because a
    fixture is missing prints the same words, and it is a real defect."""
    if not eco_mod.unusable("python3: can't open file "
                            "'/tmp/x/scripts/check.py': [Errno 2] "
                            "No such file or directory"):
        return "a missing entry point was read as a failing suite"
    if eco_mod.unusable("FileNotFoundError: [Errno 2] No such file or "
                        "directory: 'tests/fixtures/sample.json'"):
        return ("a test failing on a missing fixture was swallowed as "
                "could-not-run")
    return None



def case_exit_two_means_what_the_runner_means_by_it(t):
    """Exit 2 belongs to the runner, and a blanket rule was wrong both ways.

    `CLAUDE.md` says 2 means COULD NOT JUDGE, and `ecosystems.run` read it as
    red -- the repository's own rule broken in the other direction, so a suite
    that refused to start counted against a repository exactly like a broken
    one. pytest agrees: 2 is a usage error or an interrupted run.

    `make` does not. It exits 2 when the recipe failed, which is a red suite,
    and reading that as an abstention turned a genuinely failing `make test`
    into no result at all. A blanket rule broke a case here on the first run.
    That is why the codes are a property of the ecosystem rather than a
    constant: an abstention that hides a real failure is the one direction
    this whole assessment exists to refuse."""
    put(t, "say.py", "import sys\nprint('could not judge: no linter here')\n"
                     "sys.exit(2)\n")
    cmd = ["python3", "say.py"]
    verdict, _ = eco_mod.run(t, cmd, eco_mod.Python.did_not_run)
    if verdict != "could-not-run":
        return "pytest's exit 2 was read as %r" % verdict
    verdict, _ = eco_mod.run(t, cmd, eco_mod.Make.did_not_run)
    if verdict != "red":
        return "make's exit 2 -- a failed recipe -- was read as %r" % verdict

    put(t, "fail.py", "import sys\nprint('1 failed, 3 passed')\n"
                      "sys.exit(1)\n")
    verdict, _ = eco_mod.run(t, ["python3", "fail.py"],
                             eco_mod.Python.did_not_run)
    if verdict != "red":
        return "a suite that actually failed was read as %r" % verdict
    return None



def case_an_entry_point_the_parked_commit_never_had(t):
    """The command is found at HEAD; the replay runs in the past.

    `park` moves the bench to the fix commit, so a repository that introduced
    its entry point last week has a history of commits without it, and the
    interpreter exits non-zero there for a reason with nothing to do with the
    defect. This tree hit it on the first run after gaining one.

    Re-detecting unconditionally is the wrong repair and was tried first: the
    parked tree offers whatever it happens to have, and a commit from before
    the `tests/` directory existed falls through to a `Makefile` driving
    something else. So the fallback fires only when the HEAD command names a
    file the parked tree does not have."""
    put(t, "scripts/check.py", "import sys\nsys.exit(0)\n")
    if catch_mod._entry_missing(t, ["python3", "scripts/check.py"]):
        return "an entry point that is right there was called missing"
    if not catch_mod._entry_missing(t, ["python3", "scripts/gone.py"]):
        return "an entry point that is not in the tree was called present"
    # A command naming no file at all is not missing -- it is `pytest`.
    if catch_mod._entry_missing(t, ["python3", "-m", "pytest", "-q"]):
        return "a command naming no file in the tree was called missing"
    return None



def case_a_suite_that_shells_out_is_still_measured(t):
    """Wrapping the command measures the process it started, and nothing more.

    A suite whose runner shells out -- a script invoking twenty checks, `tox`,
    `make`, pytest under `-n` -- had its *runner's* lines counted and reported
    as the repository's coverage. Small, confident, and about the wrong
    subject. This repository's own entry point is exactly that shape, which is
    how the gap was found.

    coverage.py's supported answer is `COVERAGE_PROCESS_START` plus a
    `sitecustomize` calling `process_startup()`, both written into the work
    directory so nothing is left in the repository being assessed."""
    if not cover_mod.Python().available(t):
        # Not a pass. `coverage` is what this case is about, and saying so is
        # the only honest thing available when it is not installed.
        return None
    child = ("def used():\n"            # 1
             "    return 1\n"            # 2  <- runs, in a subprocess only
             "\n"
             "\n"
             "def never_used():\n"       # 5
             "    return 2\n")           # 6  <- nothing ever runs this
    put(t, "child.py", child)
    ran = child.splitlines().index("    return 1") + 1
    never = child.splitlines().index("    return 2") + 1
    put(t, "runner.py", "import subprocess, sys\n"
                        "subprocess.run([sys.executable, '-c',\n"
                        "                'import child; child.used()'])\n")
    r, why = cover_mod.Python().measure(t, ["python3", "runner.py"],
                                        os.path.join(t, "w"))
    if not r:
        return "no report from a suite that shells out: %s" % why
    files = r.get("files") or {}
    if "child.py" not in files:
        return ("a file executed only in a subprocess was invisible: saw %s"
                % sorted(files))
    # `--source=.` lists every file in the tree whether it ran or not, so the
    # file merely *appearing* proves nothing -- that was the first version of
    # this case, and it stayed green with the subprocess measurement torn out.
    # What separates the two is whether the line the subprocess executed comes
    # back covered.
    missing = files["child.py"]
    if ran in missing:
        return ("the line a subprocess executed came back uncovered: "
                "missing %s — nothing the suite started was measured"
                % (missing,))
    if never not in missing:
        return ("a line nothing executed came back covered: missing %s"
                % (missing,))
    return None



def case_a_description_is_not_an_unenforced_rule(t):
    """`cannot` describes; it does not instruct.

    "It parses the workflow, so the two cannot drift" is a fact about how a
    script works. Counted as a prohibition, it became an unenforced rule on
    this repository's own floor -- and the fix for an unenforced rule is to
    write a guard, so the page was asking somebody to enforce a sentence about
    a parser. Two of the five it reported were this."""
    put(t, "CLAUDE.md",
        "# r\n\nIt parses the workflow, so the two cannot drift.\n\n"
        "A step it cannot classify is exit 2.\n\n"
        "Never force-push the default branch.\n")
    r = value_mod.assess(t)
    if r["prohibitions"] != 1:
        d = value_mod.floor_text(t)
        got = [" ".join(x.split())[:60] for x in value_mod.sentences(d["CLAUDE.md"])
               if value_mod.PROHIBIT.search(x)]
        return "counted %d prohibition(s), wanted 1: %s" % (r["prohibitions"], got)
    return None


def case_a_guard_that_exists_gets_the_rule_credited(t):
    """A map left behind reads exactly like a guard that does not exist.

    `FROM_BLAST` turns "this repository was measured refusing X" into the rule
    labels X covers. `silence a failing check` mapped to nothing for as long as
    no guard here could refuse it -- and stayed empty after one could. The
    repository stated the rule, shipped the guard, was measured refusing the
    probe, and the rule still counted as unenforced on every assessment."""
    row = {"probe": "silence a failing check", "stopped": True,
           "false_block": False}
    if "silenced check" not in value_mod.guards_from_blast({"rows": [row]}):
        return "a measured refusal credited no rule label"
    # ...and a guard that was measured *failing* credits nothing, which is the
    # half that makes the first half worth having.
    row["false_block"] = True
    if value_mod.guards_from_blast({"rows": [row]}):
        return "a guard that blocked legitimate work was credited anyway"
    return None



def case_coverage_is_given_the_command_the_replay_found(t):
    """One page cannot disagree with itself about whether a suite exists.

    The replay discovers a test command when nobody passed `--test-command`;
    coverage was handed only the flag. So a repository whose suite the table
    recognises perfectly well had its ladder measured and its coverage
    reported as "no test command to instrument", on the same page, from the
    same tree."""
    put(t, "pyproject.toml", "[project]\nname = 'x'\n")
    put(t, "tests/test_x.py", "def test_x():\n    assert True\n")
    put(t, "app.py", "def f():\n    return 1\n")
    commit(t, "init")
    eco, cmd = catch_mod.find(t)
    if cmd is None:
        return "the fixture is wrong: nothing discovered a command here"
    if not cover_mod.Python().available(t):
        return None
    r, why = cover_mod.assess(t, cmd, os.path.join(t, "w"))
    if r is None and "no test command" in (why or ""):
        return ("coverage was not given the command the replay found: %s"
                % why)
    return None



def case_a_table_is_data_and_an_alternative_may_come_first(t):
    """Two precision failures, both found by turning it on real documents.

    A markdown table row is columns of data, and a header cell reading "the
    thing you want to forbid" is a column label -- sixth in the family this
    project keeps rediscovering. And the alternative to a prohibition is as
    often stated *before* it as after: "it fails open on purpose, so a broken
    guard must not become a wall" gives the behaviour first and rules out its
    opposite second. Reading only forwards reported both as unreframed."""
    # A table butted against prose joined it into one block, and the sentence
    # split then handed back a *cell* as the text of the finding.
    table = {"path": "a.md", "kind": "skill", "text": (
        "Do not put a rule in two places.\n"
        "| The thing you want to forbid | Where it belongs |\n"
        "|---|---|\n"
        "| An action that destroys work | A guard |\n")}
    got = reframe_mod.openings(table)
    if not got:
        return "the prohibition beside the table was lost with the table"
    cells = [o["text"] for o in got if "|" in o["text"]]
    if cells:
        return "a table cell was reported as the instruction: " + cells[0]

    before = {"path": "b.md", "kind": "skill", "text":
              "It fails open on purpose. A broken guard must not become an "
              "unbypassable wall.\n"}
    got = [o for o in reframe_mod.openings(before)
           if o["operation"] == "positive"]
    if got:
        return ("an alternative stated before the prohibition was missed: "
                + got[0]["text"])

    # ...and a bare prohibition with nothing either side still comes back.
    bare = {"path": "c.md", "kind": "skill", "text":
            "A broken guard must not become an unbypassable wall.\n"}
    if not [o for o in reframe_mod.openings(bare)
            if o["operation"] == "positive"]:
        return "widening the window silenced a real candidate"
    return None



def case_a_sentence_about_a_prohibition_is_not_one(t):
    """The eighth appearance of text *about* a thing read as the thing.

    `what must not leave the machine is a guard` names a category of rule and
    `a rule that must not be missed is a guard` classifies one. Neither tells
    anybody to do anything, and both were reported as prohibitions leaving
    their target unstated -- across three documents that were, in fact,
    explaining how prohibitions get enforced here.

    Both halves of the test are load-bearing. A relative pronoun in front of
    the modal is not enough on its own: "anything that fails must not be
    ignored" has one and is a real instruction, so a copula behind it is
    required too, and that pair is what separates a description from an
    order."""
    def positives(text):
        return [o["text"] for o in reframe_mod.openings(
            {"path": "a.md", "kind": "skill", "text": text})
            if o["operation"] == "positive"]

    described = (
        "The rules split three ways. What must not leave the machine is a "
        "guard, what must not enter the tree is a gate.\n")
    got = positives(described)
    if got:
        return "a category named by a relative clause was read as an order: " + got[0]

    classified = "A rule that must not be missed is a guard.\n"
    got = positives(classified)
    if got:
        return "a relative clause modifying a noun was read as an order: " + got[0]

    # ...and the instruction that wears the same pronoun still comes back.
    order = "Anything that fails must not be ignored.\n"
    if not positives(order):
        return "a real prohibition was silenced by the relative-clause rule"

    # The reason for a prohibition, stated in the same sentence ahead of it.
    # `_around` read only the tail, so the head that carried the reason was
    # thrown away before the search for it.
    reasoned = ("It fails open on purpose -- a broken guard must not become "
                "an unbypassable wall.\n")
    if positives(reasoned):
        return "a reason given ahead of the prohibition was not counted"

    # A head that merely names what is being ruled out is not a repair.
    named = "When you use the API, do not hardcode the key.\n"
    if not positives(named):
        return "a verb in the head was mistaken for the alternative"
    return None


def case_a_guard_catching_no_ordinary_bug_is_the_right_outcome(t):
    """A threshold no repository can meet is not a measurement.

    The defects this ladder walks are ordinary bugs out of a repository's own
    history. A guard is a *destructive-action* layer: `rm -rf $TARGET`, a force
    push, a credential. It is structurally incapable of catching a logic
    defect, and a guard that blocked one would be a false block -- which
    dimension 1 counts *against* a repository.

    So `before-write: N hook(s), 0 of M caught` is the correct outcome for
    every repository, however good its guards, and flagging it red made the
    ladder unsatisfiable. Whether the guards work is dimension 1's question,
    asked there properly by firing destructive actions at them -> 0038"""
    row = _layer_row({"PreToolUse": 2, "PostToolUse": 0}, {"local-suite": 14})
    if "before-write: 2 hook(s), 0 of 14 caught" not in row["value"]:
        return "the inventory stopped saying what stands behind the rung"
    if row["flag"] == "bad":
        return ("guards catching no ordinary defect was flagged as a failure "
                "— no repository can ever clear that")
    if "Dimension 1" not in (row["note"] or ""):
        return "nothing tells the reader where the guards are actually judged"
    return None



def case_a_judged_conflict_can_reach_the_page(t):
    """`dimensions.py` took `conflict_judged` and nothing ever set it.

    Every other half-machine-half-agent measurement here has a flag for the
    reading that finishes it -- `--observe-answers`, `--legitimate-actions`,
    `--mutant-answers`. Contradictions had the parameter, the grader and the
    brief, and no way to get an answer from one to the other. So the row said
    "not yet judged" on every run of every repository, for as long as the
    repository existed, and a reading nobody can record is a reading nobody
    does."""
    r = {"candidates": [{"subject": "--budget", "a": "x.md", "b": "y.md"}],
         "candidates_total": 1, "possible_pairs": 2, "documents": 2,
         "excluded_by_supersession": 0}
    graded, why = conflict_mod.grade(r, {"pairs": [
        {"subject": "--budget", "a": "x.md", "b": "y.md", "real": False,
         "believe": None, "why": "two examples, not two claims"}]})
    if graded is None:
        return "a dismissal could not be recorded: %s" % why
    if graded["judged"] != 1 or graded["real"]:
        return "a dismissed candidate came back as a finding: %r" % (graded,)
    got = dim_mod.repository_memory(t, [], (), None, r, graded)
    hit = [x for x in got["rows"] if "contradict each other" in x["label"]]
    if not hit:
        return "the judged row never reached the page"
    if "not yet judged" in hit[0]["value"]:
        return "a judged candidate still printed as unjudged: %s" % hit[0]["value"]
    return None


# --------------------------------------------------------------------------
# pipeline: scope, self-check, verdict, shipping (3.3 - 3.6)
# --------------------------------------------------------------------------

WORKFLOW = """name: ci
on:
  pull_request:%s
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
%s"""


def pipeline_rows(t, fetch=None):
    """Dimension 3 rows with the pipeline read, no remote, no audit tool."""
    probe = load_probe().probe(t)
    p, _why = pipeline_mod.assess(t, fetch=fetch, audit_tool="")
    d3 = dim_mod.assess(t, probe, None, None, "", None,
                        history_mod.commits(t), catch_mod.LADDER,
                        pipeline=p)[2]
    return {r["label"]: r for r in d3["rows"]}


def case_a_filtered_pipeline_lets_a_change_run_nothing(t):
    """Every workflow on pull requests carries a `paths:` filter, so a change
    outside those paths is merged with no check having run. Buzz-style scope
    filters are deliberate; the page has to say what they skip."""
    repo(t)
    put(t, "src/app.py", "x = 1\n")
    put(t, ".github/workflows/ci.yml", WORKFLOW % (
        "\n    paths:\n      - 'src/**'", "      - run: pytest\n"))
    commit(t, "feat: filtered")
    row = pipeline_rows(t).get("changes that run no check")
    if not row:
        return "the scope row is missing"
    if row["flag"] != "warn" or "outside" not in row["value"]:
        return f"a filtered pipeline read as {row['value']!r} ({row['flag']})"
    put(t, ".github/workflows/ci.yml", WORKFLOW % ("", "      - run: pytest\n"))
    commit(t, "ci: unconditional")
    row = pipeline_rows(t).get("changes that run no check")
    if not row or row["flag"] != "ok":
        return "an unconditional pipeline was not read as running on everything"
    return None


def case_a_workflow_blind_to_its_own_change_is_reported(t):
    """A `paths:` filter that leaves out .github/workflows means an edit to
    the pipeline is the one change the pipeline never checks."""
    repo(t)
    put(t, ".github/workflows/ci.yml", WORKFLOW % (
        "\n    paths: ['src/**']", "      - run: pytest\n"))
    commit(t, "ci: blind")
    rows = pipeline_rows(t)
    hit = rows.get("a workflow that does not run when it changes itself")
    if not hit or "ci.yml" not in hit["value"]:
        return "a workflow whose filter excludes itself was not reported"
    put(t, ".github/workflows/ci.yml", WORKFLOW % (
        "\n    paths: ['src/**', '.github/workflows/**']",
        "      - run: pytest\n"))
    commit(t, "ci: sees itself")
    if "a workflow that does not run when it changes itself" in pipeline_rows(t):
        return "a filter that includes .github/workflows was still reported"
    return None


def case_a_pipeline_nobody_checks_is_reported(t):
    """A workflow file is code nobody runs locally. One that no linter,
    audit or test ever reads is flagged; one with actionlint is not."""
    repo(t)
    put(t, ".github/workflows/ci.yml", WORKFLOW % ("", "      - run: pytest\n"))
    commit(t, "ci: unchecked")
    row = pipeline_rows(t).get("the pipeline is itself checked")
    if not row or row["flag"] != "warn":
        return f"an unchecked pipeline read as {row and row['value']!r}"
    put(t, ".github/workflows/ci.yml", WORKFLOW % (
        "", "      - run: actionlint\n      - run: pytest\n"))
    commit(t, "ci: linted")
    row = pipeline_rows(t).get("the pipeline is itself checked")
    if not row or row["flag"] != "ok" or "linted" not in row["value"]:
        return f"a linted pipeline read as {row and row['value']!r}"
    return None


def case_a_step_that_refuses_a_pattern_is_listed(t):
    """A recursive search that fails the job is a guard living in CI. It is
    listed for the agent, never counted for or against; and an install step
    grepping its own output is not one."""
    repo(t)
    put(t, ".github/workflows/ci.yml", WORKFLOW % ("", (
        "      - name: dead token guard\n"
        "        run: |\n"
        "          if grep -rn 'spr_tok_' src/; then\n"
        "            echo '::error::dead token'\n"
        "            exit 1\n"
        "          fi\n"
        "      - name: install\n"
        "        run: |\n"
        "          tool --version | grep 1.2 || exit 1\n")))
    commit(t, "ci: a guard")
    row = pipeline_rows(t).get("rules a step refuses")
    if not row:
        return "a grep-and-fail step was not listed"
    if not row["value"].startswith("1 ") or "dead token guard" not in row["note"]:
        return f"expected one refusing step, got {row['value']!r}: {row['note']}"
    return None


def case_verdicts_that_cannot_be_read_are_not_zero(t):
    """No remote, no history: the rerun row abstains and is excluded from
    scoring, rather than reporting zero flips as a clean sheet."""
    repo(t)
    put(t, ".github/workflows/ci.yml", WORKFLOW % ("", "      - run: pytest\n"))
    commit(t, "ci")
    row = pipeline_rows(t, fetch=lambda path: None).get(
        "reruns that changed the verdict")
    if not row or row["value"] != "not readable":
        return f"unreadable run history read as {row and row['value']!r}"
    if review_mod.measured(row):
        return "an unreadable verdict row counted as measured"
    return None


def case_a_rerun_that_went_green_is_a_flip(t):
    """A run whose first attempt failed and whose last succeeded, with no
    change to the code, depended on something other than the code."""
    repo(t)
    put(t, ".github/workflows/ci.yml", WORKFLOW % ("", "      - run: pytest\n"))
    commit(t, "ci")
    runs = {"workflow_runs": [
        {"id": 1, "status": "completed", "conclusion": "success",
         "run_attempt": 2, "name": "ci", "head_sha": "abc123abc123",
         "run_started_at": "2026-01-01T00:00:00Z",
         "updated_at": "2026-01-01T00:01:00Z"},
        {"id": 2, "status": "completed", "conclusion": "success",
         "run_attempt": 1, "name": "ci", "head_sha": "def456def456",
         "run_started_at": "2026-01-01T00:00:00Z",
         "updated_at": "2026-01-01T00:00:30Z"}]}

    def fetch(path):
        if path.endswith("/attempts/1"):
            return json.dumps({"conclusion": "failure"})
        return json.dumps(runs)
    row = pipeline_rows(t, fetch=fetch).get("reruns that changed the verdict")
    if not row or not row["value"].startswith("1 of 1 rerun"):
        return f"a rerun that flipped read as {row and row['value']!r}"
    if row["flag"] != "warn":
        return f"a flip was flagged {row['flag']!r}"
    return None


def case_a_tag_off_this_branch_is_reported(t):
    """The latest tag points at a commit the default branch never merged:
    what shipped is not what the branch says shipped."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    put(t, ".github/workflows/ci.yml", WORKFLOW % ("", "      - run: pytest\n"))
    commit(t, "feat: one")
    git(["checkout", "-q", "-b", "side"], t)
    put(t, "app.py", "x = 2\n")
    commit(t, "feat: side")
    git(["tag", "v1.0.0"], t)
    git(["checkout", "-q", "main"], t)
    row = pipeline_rows(t).get("the latest tag is on this branch")
    if not row or row["flag"] != "bad":
        return f"a tag off the branch read as {row and row['value']!r}"
    git(["tag", "-f", "v1.0.0", "main"], t)
    row = pipeline_rows(t).get("the latest tag is on this branch")
    if not row or row["flag"] != "ok":
        return f"a tag on the branch read as {row and row['value']!r}"
    return None


def case_a_manifest_ahead_of_its_tag_is_reported(t):
    """package.json says 2.0.0 and the latest tag is v1.0.0: a version
    nobody can install yet, or a release somebody forgot."""
    repo(t)
    put(t, "package.json", json.dumps({"name": "x", "version": "2.0.0"}))
    put(t, ".github/workflows/ci.yml", WORKFLOW % ("", "      - run: pytest\n"))
    commit(t, "feat")
    git(["tag", "v1.0.0"], t)
    row = pipeline_rows(t).get("the manifest agrees with the latest tag")
    if not row or row["flag"] != "warn":
        return f"a manifest ahead of its tag read as {row and row['value']!r}"
    put(t, "package.json", json.dumps({"name": "x", "version": "1.0.0"}))
    commit(t, "release: 1.0.0")
    git(["tag", "-f", "v1.0.0"], t)
    row = pipeline_rows(t).get("the manifest agrees with the latest tag")
    if not row or row["flag"] != "ok":
        return f"an agreeing manifest read as {row and row['value']!r}"
    return None


def case_audit_findings_are_counted_by_severity(t):
    """zizmor's JSON, in both shapes it has used, and an absent tool."""
    nested = json.dumps([{"ident": "unpinned-uses",
                          "determinations": {"severity": "High"}},
                         {"ident": "excessive-permissions",
                          "determinations": {"severity": "Medium"}}])
    r = pipeline_mod.interpret_audit(nested)
    if not r or r["by_severity"].get("high") != 1 or r["total"] != 2:
        return f"nested findings misread: {r}"
    flat = json.dumps([{"ident": "x", "severity": "low"}])
    r = pipeline_mod.interpret_audit(flat)
    if not r or r["by_severity"].get("low") != 1:
        return f"flat findings misread: {r}"
    if pipeline_mod.interpret_audit("[]")["total"] != 0:
        return "a clean audit did not read as zero"
    out, why = pipeline_mod.audit(t, tool="")
    if out is not None or "not on PATH" not in why:
        return f"an absent tool did not abstain: {out} {why}"
    return None


def case_another_host_cannot_be_judged(t):
    """A GitLab pipeline is not read here, and the reader says so instead of
    reporting an empty scope as a finding."""
    repo(t)
    put(t, ".gitlab-ci.yml", "test:\n  script: pytest\n")
    commit(t, "ci: gitlab")
    p, why = pipeline_mod.assess(t, fetch=lambda _p: None, audit_tool="")
    if p is not None or "cannot judge" not in why:
        return f"another host was read as {p!r}"
    return None


# --------------------------------------------------------------------------
# the field: what 1.0.0 got wrong on repositories nobody here wrote
# --------------------------------------------------------------------------

def case_an_unscored_axis_is_not_drawn_at_zero(t):
    """A dimension nobody scored used to get a vertex at the centre and a
    solid dot -- the exact picture a zero draws. 0041 forbids that in words;
    the shape leaked it."""
    svg = review_mod.radar({"1": 5, "3": 5, "4": 5, "5": 5}, size=400)
    cx, cy = 200.0, 400 * 0.46
    if "%.1f,%.1f" % (cx, cy) in svg:
        return "an unscored axis was drawn at the centre, like a zero"
    if "not scored" not in svg:
        return "an unscored axis is not labelled as unscored"
    if "stroke-dasharray" not in svg:
        return "an incomplete polygon is drawn like a complete one"
    full = review_mod.radar({"1": 5, "2": 5, "3": 5, "4": 5, "5": 5}, size=400)
    if 'stroke-dasharray="5 4"' in full:
        return "a fully scored polygon was drawn dashed"
    return None


def case_a_suite_below_the_root_is_found(t):
    """A Go module under cli/, a Makefile under svc/: the root has no
    marker for a language the table supports, and 1.0.0 reported no
    ecosystem at all."""
    repo(t)
    put(t, "README.md", "# mono\n")
    put(t, "svc/Makefile", "test:\n\t@true\n")
    commit(t, "feat: a service under svc/")
    eco, cmd = eco_mod.find(t)
    if eco is None or "svc/" not in eco.name:
        return f"a suite under svc/ was routed to {eco and eco.name!r}"
    if shutil.which("make") and cmd != ["bash", "-c", "cd svc && make test"]:
        return f"the command does not run from svc/: {cmd}"
    put(t, "web/node_modules/pkg/package.json",
        json.dumps({"scripts": {"test": "jest"}}))
    put(t, "web/README.md", "x")
    eco2, _c = eco_mod.find(t)
    if eco2 is not None and "node" in eco2.name:
        return "a package.json under node_modules was read as the repository's"
    return None


def case_a_typed_command_goes_through_a_shell(t):
    """`cd app && flutter test` was split on whitespace and exec'd, so `cd`
    was looked up on PATH. The help text promised a shell it did not have."""
    if shutil.which("make") is None:
        return ""
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
    put(t, "tests/case_f.py", "# moved with the fix\n")
    commit(t, "fix: f returned the wrong number")
    r, why = catch_mod.assess(t, 1, os.path.join(t, ".work"),
                              "true && make test")
    if r is None:
        return f"a shell command could not run: {why}"
    if [row["rung"] for row in r["rows"]] != ["local-suite"]:
        return f"a shell command did not reach the suite: {r['rows']}"
    if r["command"] != "true && make test":
        return f"the command is displayed as {r['command']!r}"
    return None


def case_an_untracked_entry_point_is_named(t):
    """The replay runs in a clean clone, so a helper script that was never
    committed is not there. `No such file` says nothing about why."""
    repo(t)
    put(t, "src/a.py", "x = 1\n")
    put(t, "tests/.keep", "")
    commit(t, "feat: a")
    put(t, "src/a.py", "x = 2\n")
    put(t, "tests/case.py", "# with the fix\n")
    commit(t, "fix: a")
    put(t, "run-tests.sh", "#!/bin/sh\nexit 0\n")       # never committed
    r, why = catch_mod.assess(t, 1, os.path.join(t, ".work"),
                              "bash run-tests.sh")
    if r is not None or "not tracked" not in why:
        return f"an untracked entry point was not named: {r} {why}"
    return None


def case_nothing_wired_is_scored_as_nothing_refused(t):
    """No .claude/ is not `not asked`. The answer is known -- nothing is
    refused -- and it has to reach the brief under 1.1, or the worst
    possible reading leaves the page while the fact sheet says BAD."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    commit(t, "feat")
    d1 = dims_of(t, with_blast=False)[1]
    row = next((r for r in d1["rows"]
                if "refused before they happen" in r["label"]), None)
    if not row or not row["value"].startswith("0/") or row["flag"] != "bad":
        return f"no .claude/ read as {row and row['value']!r}"
    items, _un = review_mod.collect({"dimensions": [d1]})
    if not any(it["id"] == "1.1" for it in items):
        return "the nothing-wired row did not reach sub-item 1.1"
    return None


def case_a_test_that_already_existed_is_told_from_the_fix_s_own(t):
    """The ladder keeps the fix's own regression test, so local-suite is
    near-certain by construction. The control puts tests back too: a suite
    that saw the defect before its regression test existed is the exception
    worth reporting, and the ordinary case is `missed`."""
    if shutil.which("make") is None:
        return ""
    check = ("test:\n"
             "\t@python3 -c \"import sys; sys.path.insert(0,'.'); "
             "from src.a import f; sys.exit(0 if f() == {want} else 1)\"\n")
    # (a) the Makefile already asserted 3 before the fix: an existing test
    # sees the defect.
    repo(t)
    put(t, "src/__init__.py", "")
    put(t, "src/a.py", "def f():\n    return 2\n")
    put(t, "tests/.keep", "")
    put(t, "Makefile", check.format(want=3))
    commit(t, "feat: a, with a test it fails")
    put(t, "src/a.py", "def f():\n    return 3\n")
    put(t, "tests/case_f.py", "# with the fix\n")
    commit(t, "fix: f returned the wrong number")
    r, why = catch_mod.assess(t, 1, os.path.join(t, ".work"))
    if r is None:
        return f"could not run the ladder: {why}"
    if [row.get("prior_suite") for row in r["rows"]] != ["caught"]:
        return (f"a pre-existing test that sees the defect read as "
                f"{[row.get('prior_suite') for row in r['rows']]}")
    d2 = dim_mod.change_validation(
        {"replayable": 1, "shallow": False}, r, "", catch_mod.LADDER)
    row = next((x for x in d2["rows"] if "already existed" in x["label"]), None)
    if not row or not row["value"].startswith("1 of 1"):
        return f"the control row reads {row and row['value']!r}"
    return None


def case_a_defect_the_suite_never_reaches_is_not_a_survivor(t):
    """A command that covers part of the repository was recorded as the
    repository failing to catch a defect in the other part. `1 defect
    survives past the end of a session` is a sentence about the repository;
    the true sentence is about the command."""
    catch = {"command": "cd svc && make test", "rows": [
        {"sha": "aaaaaaaaaa", "subject": "fix: cli", "rung": "never",
         "detail": "nothing went red", "seconds": None,
         "source": ["cli/main.go"], "tests": ["cli/main_test.go"]},
        {"sha": "bbbbbbbbbb", "subject": "fix: svc", "rung": "local-suite",
         "detail": "red", "seconds": 1.0,
         "source": ["svc/a.py"], "tests": ["svc/test_a.py"]}]}
    d2 = dim_mod.change_validation(
        {"replayable": 2, "shallow": False}, catch, "", catch_mod.LADDER)
    if "0 of 1 defects survive" not in d2["headline"]:
        return f"an unreached defect counted as surviving: {d2['headline']}"
    row = next((x for x in d2["rows"] if "suite's reach" in x["label"]), None)
    if not row or row["value"] != "1" or "cli/main.go" not in row["note"]:
        return f"the unreached row reads {row}"
    # And by coverage, with no cd: the suite ran but never entered the file.
    catch["command"] = "make test"
    cover = {"tool": "coverage.py", "criteria": {}, "files": {},
             "reached": {"cli/main.go": False, "svc/a.py": True}}
    d2 = dim_mod.change_validation(
        {"replayable": 2, "shallow": False}, catch, "", catch_mod.LADDER,
        cover=cover)
    if "0 of 1 defects survive" not in d2["headline"]:
        return f"a file coverage never entered counted as a miss: {d2['headline']}"
    # A file the suite did reach and still missed is a real survivor.
    cover["reached"]["cli/main.go"] = True
    d2 = dim_mod.change_validation(
        {"replayable": 2, "shallow": False}, catch, "", catch_mod.LADDER,
        cover=cover)
    if "1 of 2 defects survive" not in d2["headline"]:
        return f"a reached-and-missed defect was excused: {d2['headline']}"
    return None


def case_both_denominators_travel_with_the_row(t):
    """Typed commits narrow the denominator; untyped ones do not. The same
    repository on two branches gave two percentages that could not be
    compared, so the row now carries the all-source number too."""
    repo(t)
    put(t, "app.py", "x = 1\n")
    commit(t, "a change without a type")
    put(t, "app.py", "x = 2\n")
    commit(t, "another")
    d3 = dims_of(t, with_blast=False)[3]
    row = next((r for r in d3["rows"] if "verified nothing" in r["label"]), None)
    if not row or "all_source" not in row or "denominator" not in row:
        return f"the row carries no second denominator: {row}"
    if "every change to source" not in row["note"]:
        return "the note does not say what the second number is"
    return None


CASES = [
    ("an unscored axis is not drawn at zero",
     case_an_unscored_axis_is_not_drawn_at_zero),
    ("a suite below the root is found",
     case_a_suite_below_the_root_is_found),
    ("a typed command goes through a shell",
     case_a_typed_command_goes_through_a_shell),
    ("an untracked entry point is named",
     case_an_untracked_entry_point_is_named),
    ("nothing wired is scored as nothing refused",
     case_nothing_wired_is_scored_as_nothing_refused),
    ("a test that already existed is told from the fix's own",
     case_a_test_that_already_existed_is_told_from_the_fix_s_own),
    ("a defect the suite never reaches is not a survivor",
     case_a_defect_the_suite_never_reaches_is_not_a_survivor),
    ("both denominators travel with the row",
     case_both_denominators_travel_with_the_row),
    ("a filtered pipeline lets a change run nothing",
     case_a_filtered_pipeline_lets_a_change_run_nothing),
    ("a workflow blind to its own change is reported",
     case_a_workflow_blind_to_its_own_change_is_reported),
    ("a pipeline nobody checks is reported",
     case_a_pipeline_nobody_checks_is_reported),
    ("a step that refuses a pattern is listed",
     case_a_step_that_refuses_a_pattern_is_listed),
    ("verdicts that cannot be read are not zero",
     case_verdicts_that_cannot_be_read_are_not_zero),
    ("a rerun that went green is a flip",
     case_a_rerun_that_went_green_is_a_flip),
    ("a tag off this branch is reported",
     case_a_tag_off_this_branch_is_reported),
    ("a manifest ahead of its tag is reported",
     case_a_manifest_ahead_of_its_tag_is_reported),
    ("audit findings are counted by severity",
     case_audit_findings_are_counted_by_severity),
    ("another host cannot be judged",
     case_another_host_cannot_be_judged),
    ("a judged conflict can reach the page",
     case_a_judged_conflict_can_reach_the_page),
    ("a guard catching no ordinary bug is the right outcome",
     case_a_guard_catching_no_ordinary_bug_is_the_right_outcome),
    ("a table is data and an alternative may come first",
     case_a_table_is_data_and_an_alternative_may_come_first),
    ("a sentence about a prohibition is not one",
     case_a_sentence_about_a_prohibition_is_not_one),
    ("every printed row is claimed by a sub-item",
     case_every_printed_row_is_claimed_by_a_sub_item),
    ("a reading of the candidates can be recorded",
     case_a_reading_of_the_candidates_can_be_recorded),
    ("coverage is given the command the replay found",
     case_coverage_is_given_the_command_the_replay_found),
    ("a description is not an unenforced rule",
     case_a_description_is_not_an_unenforced_rule),
    ("a guard that exists gets the rule credited",
     case_a_guard_that_exists_gets_the_rule_credited),
    ("a suite that shells out is still measured",
     case_a_suite_that_shells_out_is_still_measured),
    ("an entry point the parked commit never had",
     case_an_entry_point_the_parked_commit_never_had),
    ("exit two means what the runner means by it",
     case_exit_two_means_what_the_runner_means_by_it),
    ("an entry point that predates the commit is not a red suite",
     case_an_entry_point_that_predates_the_commit_is_not_a_red_suite),
    ("a repository that documents its own suite is not invisible",
     case_a_repository_that_documents_its_own_suite_is_not_invisible),
    ("a command a document warns against is not run",
     case_a_command_a_document_warns_against_is_not_run),
    ("a documented command naming nothing real is dropped",
     case_a_documented_command_naming_nothing_real_is_dropped),
    ("a fence nobody introduced is not an entry point",
     case_a_fence_nobody_introduced_is_not_an_entry_point),
    ("a convention beats a document",
     case_a_convention_beats_a_document),
    ("a fact about the code is not a prohibition",
     case_a_fact_about_the_code_is_not_a_prohibition),
    ("a prohibition with no alternative is found",
     case_a_prohibition_with_no_alternative_is_found),
    ("a prohibition that says what to do instead is left alone",
     case_a_prohibition_that_says_what_to_do_instead_is_left_alone),
    ("an example of a rule is not a rule",
     case_an_example_of_a_rule_is_not_a_rule),
    ("the form measurement abstains rather than scoring zero",
     case_the_form_measurement_abstains_rather_than_scoring_zero),
    ("nothing wired cannot fail the legitimate row",
     case_nothing_wired_cannot_fail_the_legitimate_row),
    ("a guard that refuses everything is caught here",
     case_a_guard_that_refuses_everything_is_caught_here),
    ("only a shell fence is a documented command",
     case_only_a_shell_fence_is_a_documented_command),
    ("a CI step that is a template is not a command",
     case_a_ci_step_that_is_a_template_is_not_a_command),
    ("an abstention does not become a number",
     case_an_abstention_does_not_become_a_number),
    ("a score for something nobody measured is refused",
     case_a_score_for_something_nobody_measured_is_refused),
    ("a number off the scale is refused",
     case_a_number_off_the_scale_is_refused),
    ("the radar puts a low axis nearer the centre",
     case_the_radar_puts_a_low_axis_nearer_the_centre),
    ("a document nobody loads is not a context cost",
     case_a_document_nobody_loads_is_not_a_context_cost),
    ("a skill's reference is loaded and is counted",
     case_a_skills_reference_is_loaded_and_is_counted),
    ("a repeated table is not a repeated paragraph",
     case_a_repeated_table_is_not_a_repeated_paragraph),
    ("a file is compared to its own kind",
     case_a_file_is_compared_to_its_own_kind),
    ("a small file is never an outlier for being large",
     case_a_small_file_is_never_an_outlier_for_being_large),
    ("an untracked file is not loadable context",
     case_an_untracked_file_is_not_loadable_context),
    ("a pass-to-fail discards the whole claim",
     case_a_pass_to_fail_discards_the_whole_claim),
    ("a test the document's own code also fails is not a finding",
     case_a_test_the_documents_own_code_also_fails_is_not_a_finding),
    ("a test that vanished between runs counts in neither",
     case_a_test_that_vanished_between_runs_counts_in_neither),
    ("a fenced example is not a promise",
     case_a_fenced_example_is_not_a_promise),
    ("a claim has to name something executable",
     case_a_claim_has_to_name_something_executable),
    ("a test that does not parse never became evidence",
     case_a_test_that_does_not_parse_never_became_evidence),
    ("a missing import is the finding and is never dropped",
     case_a_missing_import_is_the_finding_and_is_never_dropped),
    ("a claim whose tests all failed to parse is untested",
     case_a_claim_whose_tests_all_failed_to_parse_is_untested),
    ("a claim still waiting on round two is not a pass",
     case_a_claim_still_waiting_on_round_two_is_not_a_pass),
    ("the blind agent cannot read the repository",
     case_the_blind_agent_cannot_read_the_repository),
    ("supersession is not conflict",
     case_supersession_is_not_conflict),
    ("a value must be attached, not merely nearby",
     case_a_value_must_be_attached_not_merely_nearby),
    ("overlapping values are agreement, not conflict",
     case_overlapping_values_are_agreement_not_conflict),
    ("a token every document names is not evidence",
     case_a_token_every_document_names_is_not_evidence),
    ("only what the repository keeps is its memory",
     case_only_what_the_repository_keeps_is_its_memory),
    ("somebody else's cloned repository is not ours",
     case_somebody_elses_cloned_repository_is_not_ours),
    ("a signal that never varies is weighted to zero",
     case_a_signal_that_never_varies_is_weighted_to_zero),
    ("raw timestamps collapse every weight",
     case_raw_timestamps_collapse_every_weight),
    ("a truncated grep is not the strength of the signal",
     case_a_truncated_grep_is_not_the_strength_of_the_signal),
    ("the score ranks and does not decide",
     case_the_score_ranks_and_does_not_decide),
    ("a tie is a tie and not a column order",
     case_a_tie_is_a_tie_and_not_a_column_order),
    ("a 404 is an answer and a 403 is not",
     case_a_404_is_an_answer_and_a_403_is_not),
    ("unreadable protection does not become `not required`",
     case_unreadable_protection_does_not_become_not_required),
    ("a workflow on push only is not a merge gate",
     case_a_workflow_on_push_only_is_not_a_merge_gate),
    ("a comment about swallowing is not swallowing",
     case_a_comment_about_swallowing_is_not_swallowing),
    ("a criterion the tool does not produce is absent, not zero",
     case_a_criterion_the_tool_does_not_produce_is_absent_not_zero),
    ("lcov carries function coverage",
     case_lcov_carries_function_coverage),
    ("gcov is where MC/DC comes from",
     case_gcov_is_where_mcdc_comes_from),
    ("a rename does not owe a test",
     case_a_rename_does_not_owe_a_test),
    ("an untyped subject is counted rather than guessed",
     case_an_untyped_subject_is_counted_rather_than_guessed),
    ("a coverage report of nothing is not a measurement",
     case_a_coverage_report_of_nothing_is_not_a_measurement),
    ("coverage run is not handed the interpreter twice",
     case_coverage_run_is_not_handed_the_interpreter_twice),
    ("a malformed report is an abstention, not a zero",
     case_a_malformed_report_is_an_abstention_not_a_zero),
    ("a report inside a dependency is not this repository's",
     case_a_report_inside_a_dependency_is_not_this_repositorys),
    ("the shape of the suite command decides if it can be wrapped",
     case_the_shape_of_the_suite_command_decides_if_it_can_be_wrapped),
    ("an uninstalled tool names itself and how to get it",
     case_an_uninstalled_tool_names_itself_and_how_to_get_it),
    ("a repository of scripts is runnable",
     case_a_repository_of_scripts_is_runnable),
    ("the instrument does not find its own vocabulary",
     case_the_instrument_does_not_find_its_own_vocabulary),
    ("prose about a logging stack is not a logging stack",
     case_prose_about_a_logging_stack_is_not_a_logging_stack),
    ("a test target is not a way to run the thing",
     case_a_test_target_is_not_a_way_to_run_the_thing),
    ("a literal port and a port from the environment differ",
     case_a_literal_port_and_a_port_from_the_environment_differ),
    ("collecting the evidence starts nothing",
     case_collecting_the_evidence_starts_nothing),
    ("an unjudged scan carries no verdict",
     case_an_unjudged_scan_carries_no_verdict),
    ("the brief asks about every angle",
     case_the_brief_asks_about_every_angle),

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
    ("a wired layer that caught nothing is not an absent one",
     case_a_wired_layer_that_caught_nothing_is_not_an_absent_one),
    ("a rule is a layer with no rung",
     case_a_rule_is_a_layer_with_no_rung),
    ("a hook that could not have run is not a layer that failed",
     case_a_hook_that_could_not_run_is_not_a_layer_that_failed),
    ("the default branch is not whichever one happens to be checked out",
     case_the_default_branch_is_not_the_one_that_happens_to_be_out),
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
    ("a pipeline that runs nothing is not counted as a verdict",
     case_a_pipeline_that_runs_nothing_is_not_a_verdict),
    ("the page names the directories it took the verdict from",
     case_the_page_names_where_it_looked_for_tests),
    ("a dimension that read nothing abstains rather than reporting a clean bill",
     case_a_dimension_that_read_nothing_abstains),
    ("the surface it uses is coverage, not a count",
     case_the_surface_is_coverage_not_a_count),
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
