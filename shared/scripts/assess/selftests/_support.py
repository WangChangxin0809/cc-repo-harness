#!/usr/bin/env python3
"""Shared fixtures for the assessment selftest, split across ``selftests/``.

Every helper here -- the small repo/commit/put fixture builders, the
per-dimension repo builders, and the ``import X as Y_mod`` aliases the case
modules assess against -- used to sit at the top of ``assess/selftest.py``
itself. They moved here, unchanged, so that every case module can import
exactly the names it needs instead of repeating this scaffolding 14 times.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import blast as blast_mod          # noqa: E402,F401
import catch as catch_mod          # noqa: E402,F401
import dimensions as dim_mod       # noqa: E402,F401
import history as history_mod      # noqa: E402,F401
import truth as truth_mod          # noqa: E402,F401
import value as value_mod          # noqa: E402,F401
import arid as arid_mod            # noqa: E402,F401
import judge as judge_mod          # noqa: E402,F401
import mutate as mutate_mod        # noqa: E402,F401
import run_mutants as run_mod      # noqa: E402,F401
import coverage_tools as cover_mod  # noqa: E402,F401
import observe as observe_mod      # noqa: E402,F401
import merge as merge_mod          # noqa: E402,F401
import conflict as conflict_mod    # noqa: E402,F401
import promises as promises_mod    # noqa: E402,F401
import units as units_mod          # noqa: E402,F401
import review as review_mod        # noqa: E402,F401
import permitted as permitted_mod  # noqa: E402,F401
import reframe as reframe_mod      # noqa: E402,F401
import surface as surface_mod      # noqa: E402,F401
import ecosystems as eco_mod       # noqa: E402,F401
import pipeline as pipeline_mod    # noqa: E402,F401


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

def load_probe():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "probe_repo", os.path.join(PARENT, "probe_repo.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _factsheet(args, timeout=600):
    return subprocess.run([sys.executable, os.path.join(HERE, "factsheet.py")]
                          + args, capture_output=True, text=True, timeout=timeout)

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

def truth_repo(t):
    repo(t)
    put(t, "src/pay/charge.py", "def charge():\n    return 1\n")
    put(t, "docs/guide.md", "See [charge](../src/pay/charge.py).\n")
    git(["add", "-A"], t)
    git(["commit", "-q", "-m", "feat: charging"], t)
    return t

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

def _layer_row(hooks, counts, value=None, ci=""):
    probe = {"moments": {"5_before_action": {"PreToolUse": hooks.get(
        "PreToolUse", 0), "permissions_deny": 0}},
        "discipline": {"check_dirs": ["tests"], "ci_entry": ["github-actions"]}}
    catch = {"hooks": hooks, "command": "pytest", "ci": ci}
    return dim_mod.interception_layers(probe, catch, None, value,
                                       catch_mod.LADDER, counts)


def _memwork(t):
    w = os.path.join(t, "..", "memwork")
    w = os.path.abspath(w)
    shutil.rmtree(w, ignore_errors=True)
    os.makedirs(w)
    return w



def _observable_repo(t, **files):
    """A tree with whatever pieces the case is about, and nothing else."""
    for rel, body in files.items():
        full = os.path.join(t, rel.replace("|", os.sep))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(body)
    return t



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


def _workflow(t, name, body):
    where = os.path.join(t, ".github", "workflows")
    os.makedirs(where, exist_ok=True)
    with open(os.path.join(where, name), "w", encoding="utf-8") as fh:
        fh.write(body)
    return t



def _doc(t, rel, body):
    full = os.path.join(t, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(body)
    return full


def _subjects_of(r):
    return sorted(p["subject"] for p in (r or {}).get("candidates", []))

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



_ALWAYS_NO = ("#!/usr/bin/env python3\n"
              "import json, sys\n"
              "json.load(sys.stdin)\n"
              "print('Blocked: everything is blocked', file=sys.stderr)\n"
              "sys.exit(2)\n")



def _run_with(rows):
    """A run's JSON, with whichever rows the case is about."""
    return {"dimensions": [{"title": "Made Up", "rows": rows}]}


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



def _declares(t, body):
    put(t, "CLAUDE.md", body)
    return eco_mod.Declared().detect(t)

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

def _two_suite_root(t):
    """Python at the root and a Makefile under svc/: two suites, no
    aggregate. A repository shaped like this was measured as one suite."""
    repo(t)
    put(t, "pyproject.toml", "[project]\nname = 'x'\n")
    put(t, "a.py", "def f():\n    return 1\n")
    put(t, "tests/test_a.py", "from a import f\n\ndef test_f():\n"
                              "    assert f() == 1\n")
    put(t, "svc/Makefile", "test:\n\t@true\n")
    commit(t, "feat: two suites")
    return t


def _pytest_here():
    """The two-suite replay cases run pytest inside each suite, so they
    abstain -- loudly -- on a machine without it."""
    if subprocess.run([sys.executable, "-m", "pytest", "--version"],
                      capture_output=True, text=True).returncode == 0:
        return True
    print("  note: pytest is not installed; the two-suite replay cases "
          "were not run", file=sys.stderr)
    return False


def _pooled_python_history(t):
    """Two rooted Python suites and no marker at the root. The fix, and the
    regression test that arrives with it, live under b/; a/ stays green
    through all of it."""
    repo(t)
    for sub in ("a", "b"):
        put(t, f"{sub}/pyproject.toml", "[project]\nname = '%s'\n" % sub)
        put(t, f"{sub}/mod.py", "def f():\n    return 2\n")
        put(t, f"{sub}/tests/test_mod.py",
            "from mod import f\n\ndef test_f():\n    assert f() == 2\n")
    commit(t, "feat: a and b")
    put(t, "b/mod.py", "def f():\n    return 3\n")
    put(t, "b/tests/test_mod.py",
        "from mod import f\n\ndef test_f():\n    assert f() == 3\n")
    commit(t, "fix: b returned the wrong number")
    return t
