#!/usr/bin/env python3
"""Assessment selftest cases: probe_repo's own defects.

Split out of ``assess/selftest.py`` to keep every file under this
repository's line-count ceiling; see that file for the CLI, exit codes, and
why this selftest exists. Every case here is unchanged from the original --
same name, body, docstring, comments -- and this module's own ``CASES`` list
keeps them in the same order relative to each other that the original single
list held. ``selftest.py`` concatenates every case module's list, so all 192
cases still run, each exactly once.
"""

from __future__ import annotations


import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _support import (
    commit,
    load_probe,
    put,
    repo,
)



# --------------------------------------------------------------------------
# probe_repo: the two defects it shipped with
# --------------------------------------------------------------------------


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


CASES = [
    ('checks are found where the repository put them, not where we would',
     case_checks_are_found_outside_scripts),
    ('a dispatcher and a selftest are not themselves checks',
     case_machinery_is_not_counted_as_checks),
    ("a dependency's gates are not counted as this repository's",
     case_vendored_checks_are_not_this_repos),
    ("an installed plugin's standing skill cost is counted",
     case_plugin_skill_cost_is_counted),
]
