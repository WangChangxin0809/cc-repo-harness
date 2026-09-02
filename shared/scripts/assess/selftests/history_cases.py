#!/usr/bin/env python3
"""Assessment selftest cases: history: what counts as a defect.

Split out of ``assess/selftest.py`` to keep every file under this
repository's line-count ceiling; see that file for the CLI, exit codes, and
why this selftest exists. Every case here is unchanged from the original --
same name, body, docstring, comments -- and this module's own ``CASES`` list
keeps them in the same order relative to each other that the original single
list held. ``selftest.py`` concatenates every case module's list, so all 192
cases still run, each exactly once.
"""

from __future__ import annotations

import subprocess

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _support import (
    HERE,
    commit,
    dims_of,
    git,
    history_mod,
    load_probe,
    put,
    repo,
)



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


CASES = [
    ('a fix with a test is a replayable instance',
     case_a_fix_with_a_test_is_an_instance),
    ('source files named in another language are not invisible',
     case_source_files_named_in_another_language_are_not_invisible),
    ('a repair is found when the commit subject is not English',
     case_a_repair_is_found_when_the_subject_is_not_english),
    ('a documentation-only fix is not a code defect',
     case_a_docs_only_fix_is_not_a_defect),
    ('a commit too large to attribute is not one defect',
     case_a_large_commit_is_not_one_defect),
    ('a shallow clone cannot judge, and does not report zero',
     case_a_shallow_clone_cannot_judge),
]
