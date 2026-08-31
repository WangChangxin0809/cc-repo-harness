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
import memory as memory_mod        # noqa: E402


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
