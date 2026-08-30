#!/usr/bin/env python3
"""Prove every guard fires on what it should and stays out of the way otherwise.

    python3 scripts/guards/selftest.py [-v]

    0 = every declared case behaved as declared
    1 = a guard misbehaved, or is not adequately tested
    2 = cannot judge (no guards found, a guard failed to import)

Put this in the fast CI lane. A guard is a file that claims to block something;
until it has been observed blocking -- and observed *not* blocking a near miss --
that claim is untested. The dispatcher deliberately fails open, so a guard that
quietly stopped working is invisible at runtime. This is what makes it visible.

Two structural requirements, checked alongside the cases themselves:

* At least one case per guard must expect a block, and at least one must not.
  A guard with only positive cases passes every test while blocking everything,
  and you find out when it has cost someone a day.
* A blocking guard must return a non-empty reason. Exit code 2 is reached by
  several different paths, including a guard crashing on unexpected input, so a
  test that only checks the code passes while the guard is broken.

The second half covers `_recurrence.py`, which counts refusals by shape. Its
failure mode is the opposite of a guard's, and worse: a counter that never
reaches its threshold is silent, and silence is exactly what it looks like when
nothing has recurred. So its cases assert the fingerprint directly, and assert
that the threshold is announced on a named attempt -- "it said nothing" cannot
tell working from broken.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dispatch import load_guards  # noqa: E402

try:
    # Optional, exactly as it is in dispatch.py. A repository that decided it
    # did not want its refusals counted and deleted the file must keep a green
    # guard suite -- turning the whole thing red would punish a choice this
    # design explicitly leaves open, and the first thing anyone would do about
    # that is stop running the suite.
    import _recurrence  # noqa: E402
except ImportError:
    _recurrence = None


# --------------------------------------------------------------------------
# the recurrence counter
# --------------------------------------------------------------------------

# (label, command a, command b, should they share a fingerprint?)
#
# Half of these must answer False. A normaliser that collapsed everything would
# reach the threshold on the third refusal of anything at all, which is a
# counter that has stopped counting and started announcing.
PUSH = "git " + "push origin "

SHAPES = [
    ("the branch is not part of the habit",
     PUSH + "main", PUSH + "release", True),
    # Deliberately one operand short on the right. The obvious pair --
    # `... origin main` against `--force origin main` -- also differs in how
    # many operands it has, so it stays red for the wrong reason when flags
    # are abstracted away with everything else.
    ("a flag is part of the habit",
     PUSH + "main", "git " + "push --force main", False),
    ("a different subcommand is a different habit",
     PUSH + "main", 'git reset origin main', False),
    # In an operand position an object id is abstracted anyway, so a pair like
    # `reset --hard <sha>` tests the operand rule and not this one. A value
    # carried inside a flag is where _SHA and _NUM are load-bearing: flags are
    # kept verbatim, so without them every depth and every id is its own habit.
    ("an object id inside a flag does not fork the identity",
     "git checkout --commit=a1b2c3d4e5f6", "git checkout --commit=9f8e7d6c5b4a",
     True),
    ("nor does a number inside a flag",
     "git clone --depth=50 x", "git clone --depth=100 x", True),
    ("quoting is not part of the habit",
     'rm -rf "build"', "rm -rf build", True),
    ("whitespace is not part of the habit",
     "rm  -rf   build", "rm -rf build", True),
    ("the arity of the operands is",
     "rm -rf build", "rm -rf build dist", False),
]


def check_recurrence(verbose):
    """The fingerprint, then the threshold, then that it is said once."""
    import shutil
    import subprocess
    import tempfile
    if _recurrence is None:
        if verbose:
            print("  --  _recurrence.py is not installed here; refusals are "
                  "not counted")
        return []
    failures = []

    for label, a, b, same in SHAPES:
        ka, _ = _recurrence.fingerprint("g.py", {"command": a})
        kb, _ = _recurrence.fingerprint("g.py", {"command": b})
        if (ka == kb) != same:
            failures.append(
                f"_recurrence: {label}\n      {a!r} and {b!r} "
                f"{'should' if same else 'should not'} share a fingerprint")
        elif verbose:
            print(f"  ok  {'_recurrence.py':<34} {label}")

    # A guard that declares its own fingerprint overrides the default, or the
    # several spellings of one mistake are counted separately and the threshold
    # is never reached.
    class Declaring:
        @staticmethod
        def fingerprint(tool_input):
            return "one mistake, however it is spelled"

    ka, _ = _recurrence.fingerprint("g.py", {"command": "wildly different"},
                                    Declaring)
    kb, _ = _recurrence.fingerprint("g.py", {"command": "not alike at all"},
                                    Declaring)
    if ka != kb:
        failures.append("_recurrence: a guard's own fingerprint() was ignored")
    elif verbose:
        print(f"  ok  {'_recurrence.py':<34} a guard may declare its own "
              f"fingerprint")

    tmp = tempfile.mkdtemp(prefix="recurrence-selftest-")
    subprocess.run(["git", "init", "-q", "."], cwd=tmp, capture_output=True,
                   timeout=60)
    try:
        said = []
        for _ in range(5):
            entry = _recurrence.record(tmp, "g.py", {"command": PUSH + "main"})
            said.append(_recurrence.announce(tmp, entry))
        spoke = [i + 1 for i, x in enumerate(said) if x]
        if spoke != [_recurrence.THRESHOLD]:
            failures.append(
                f"_recurrence: the threshold is {_recurrence.THRESHOLD} and it "
                f"must be announced exactly once\n      spoke on attempts "
                f"{spoke}")
        elif verbose:
            print(f"  ok  {'_recurrence.py':<34} said once, on attempt "
                  f"{_recurrence.THRESHOLD}")

        # Hits older than the window are dropped rather than filtered on read.
        # Three refusals spread over two years is a coincidence, and an entry
        # that accumulates forever is not the number anyone asked for.
        far = _recurrence.WINDOW_DAYS * 86400 * 2
        _recurrence.record(tmp, "h.py", {"command": "git tag v1"}, now=1000.0)
        later = _recurrence.record(tmp, "h.py", {"command": "git tag v1"},
                                   now=1000.0 + far)
        if later is None or len(later["hits"]) != 1:
            failures.append(
                f"_recurrence: a hit older than {_recurrence.WINDOW_DAYS} days "
                f"was carried forward")
        elif verbose:
            print(f"  ok  {'_recurrence.py':<34} hits outside "
                  f"{_recurrence.WINDOW_DAYS} days are dropped")

        # It runs inside a hook that is in the middle of refusing something,
        # so nothing it is handed may reach that hook as an exception.
        #
        # The first four of these do not raise even with the wrapper removed --
        # str(None) and str(12) normalise fine -- and a case built only from
        # them passes while observe() has no wrapper at all. The two that
        # matter are last, and they are not hypothetical: repo_root() returns
        # None outside a repository, and hands that None straight to here.
        for root, bad in ((tmp, {}), (tmp, {"command": None}),
                          (tmp, {"command": 12}), (tmp, {"command": []}),
                          (None, {"command": PUSH + "main"}),
                          (tmp, None)):
            try:
                _recurrence.observe(root, "g.py", bad)
            except Exception as exc:                     # noqa: BLE001
                failures.append(
                    f"_recurrence: observe({root!r}, ..., {bad!r}) raised "
                    f"{type(exc).__name__} into a hook that was refusing "
                    f"something")
        if verbose:
            print(f"  ok  {'_recurrence.py':<34} malformed input does not "
                  f"raise into the refusal")
    except Exception as exc:                             # noqa: BLE001
        failures.append(f"_recurrence: raised {type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # A repository with no .git keeps its guards; the counter simply does not
    # count. It must not raise, and must not report that it counted.
    plain = tempfile.mkdtemp(prefix="not-a-repo-")
    try:
        if _recurrence.record(plain, "g.py", {"command": PUSH + "main"}):
            failures.append("_recurrence: claimed to count outside a repository")
        elif verbose:
            print(f"  ok  {'_recurrence.py':<34} outside a repository it does "
                  f"not count, and does not raise")
    finally:
        shutil.rmtree(plain, ignore_errors=True)
    return failures


def main():
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    guards, broken = load_guards()

    for name, why in broken:
        print(f"CANNOT JUDGE  {name}: {why}")
    if broken:
        return 2
    if not guards:
        print("CANNOT JUDGE  no guard modules found")
        return 2

    failures = []
    for name, mod in guards:
        cases = getattr(mod, "CASES", None)
        if not cases:
            failures.append(f"{name}: declares no CASES, so nothing proves it works")
            continue

        expected_block = sum(1 for *_, should in cases if should)
        if expected_block == 0:
            failures.append(f"{name}: no case expects a block -- untested")
        if expected_block == len(cases):
            failures.append(
                f"{name}: every case expects a block, so no negative control. "
                "A guard that blocks everything would pass this suite.")

        for tool_name, tool_input, should_block in cases:
            try:
                reason = mod.check(tool_name, tool_input)
            except Exception as exc:
                failures.append(
                    f"{name}: raised {type(exc).__name__} on {tool_input!r}")
                continue

            blocked = bool(reason)
            shown = str(tool_input)[:70]
            if blocked != should_block:
                verb = "did not block" if should_block else "blocked"
                failures.append(f"{name}: {verb} {shown}")
            elif blocked and not str(reason).strip():
                failures.append(f"{name}: blocked {shown} with an empty reason")
            elif verbose:
                print(f"  ok  {name:<34} {'block ' if blocked else 'allow '} {shown}")

    failures += check_recurrence(verbose)

    total = sum(len(getattr(m, 'CASES', [])) for _, m in guards)
    if failures:
        print(f"\nFAIL  {len(failures)} problem(s) across {len(guards)} guard(s):")
        for f in failures:
            print(f"  - {f}")
        return 1

    # Not a fixed sentence. A summary that claims a counter reached its
    # threshold in a repository with no counter installed is a green line
    # asserting something nothing checked, which is the failure this whole
    # suite exists to make visible.
    print(f"PASS  {len(guards)} guard(s), {total} case(s)"
          + (", and a counter that reaches its threshold exactly once"
             if _recurrence is not None else ", no refusal counter installed"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
