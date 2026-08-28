#!/usr/bin/env python3
"""SessionStart: print what is only true right now.

Keep the output under ~20 lines. It is paid at every session start, and a brief
long enough to skim is a brief that gets skimmed. Everything here is knowledge
no file can hold -- which is exactly why it otherwise never gets delivered, and
the agent spends its first turns rediscovering it, or does not.
"""

import subprocess


def sh(*args):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def main():
    lines = []
    branch = sh("git", "rev-parse", "--abbrev-ref", "HEAD")
    dirty = sh("git", "status", "--porcelain")
    n = len(dirty.splitlines()) if dirty else 0
    lines.append(f"branch {branch or '?'} · "
                 f"{'clean' if not n else f'{n} uncommitted file(s)'}")

    behind = sh("git", "rev-list", "--count", "HEAD..@{u}")
    if behind and behind != "0":
        lines.append(f"{behind} commit(s) behind upstream")

    # Concurrent agent sessions writing to this repo. Left undetected this
    # produces edits that appear and vanish between reads, which is a very
    # confusing thing to debug and a very cheap thing to report.
    others = [p for p in sh("pgrep", "-af", "claude").splitlines()
              if "--print" not in p]
    if len(others) > 1:
        lines.append(f"!! {len(others)} agent session(s) appear active in this repo "
                     "— append to shared files rather than rewriting them")

    # TODO: add what is specific to this repo — which gates are currently red,
    # which plan in docs/exec-plans/ is in progress. Keep the total under ~20.
    print("\n".join(lines))


if __name__ == "__main__":
    main()
