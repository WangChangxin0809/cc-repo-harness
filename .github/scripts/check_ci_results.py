#!/usr/bin/env python3
"""Fail the stable terminal CI context unless every selected lane succeeded.

Skipped jobs are acceptable only when the version-controlled path selector says
that lane was not relevant to this pull request. Pushes and manual runs require
all optional lanes. release-hygiene is the inverse: it is required on pull
requests and intentionally absent elsewhere.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


CONDITIONAL = {
    "python-compat": "RUN_PYTHON",
    "acceptance": "RUN_ACCEPTANCE",
    "preview-native": "RUN_PREVIEW",
    "plugin-host": "RUN_PLUGIN_HOST",
}
ALWAYS = ("changes", "surface", "hygiene")


def truth(value: str | None) -> bool:
    if value not in ("true", "false"):
        raise ValueError("selector outputs must be exactly true or false")
    return value == "true"


def expected_jobs(event: str, env: dict[str, str]) -> set[str]:
    if event not in ("pull_request", "push", "workflow_dispatch"):
        raise ValueError("unsupported or missing CI event: " + event)
    jobs = set(ALWAYS)
    if event == "pull_request":
        jobs.add("release-hygiene")
        for job, key in CONDITIONAL.items():
            if truth(env.get(key)):
                jobs.add(job)
    else:
        jobs.update(CONDITIONAL)
    return jobs


def check(needs: dict, event: str, env: dict[str, str]) -> list[tuple[str, str]]:
    if not isinstance(needs, dict):
        raise ValueError("NEEDS must decode to an object")
    expected = expected_jobs(event, env)
    # Unselected means a deliberate skip, not absent wiring or a failed job.
    missing = sorted((set(ALWAYS) | set(CONDITIONAL) | {"release-hygiene"}) - set(needs))
    if missing:
        raise ValueError("required fan-in is missing dependencies: " + ", ".join(missing))
    failures = []
    for name in sorted(needs):
        item = needs.get(name)
        if not isinstance(item, dict) or not isinstance(item.get("result"), str):
            raise ValueError("dependency has no result: " + name)
        allowed = {"success"} if name in expected else {"success", "skipped"}
        if item["result"] not in allowed:
            failures.append((name, item["result"]))
    return failures


def selftest() -> int:
    base = {
        "changes": {"result": "success"},
        "surface": {"result": "success"},
        "hygiene": {"result": "success"},
        "release-hygiene": {"result": "success"},
        "python-compat": {"result": "skipped"},
        "acceptance": {"result": "skipped"},
        "preview-native": {"result": "skipped"},
        "plugin-host": {"result": "skipped"},
    }
    cases = [
        ("docs-only PR accepts unselected skips", "pull_request",
         dict(RUN_PYTHON="false", RUN_ACCEPTANCE="false",
              RUN_PREVIEW="false", RUN_PLUGIN_HOST="false"), base, []),
        ("selected Python must pass", "pull_request",
         dict(RUN_PYTHON="true", RUN_ACCEPTANCE="false",
              RUN_PREVIEW="false", RUN_PLUGIN_HOST="false"), base,
         [("python-compat", "skipped")]),
        ("push requires every optional lane", "push", {}, base,
         [("acceptance", "skipped"), ("plugin-host", "skipped"),
          ("preview-native", "skipped"), ("python-compat", "skipped")]),
        ("failed always-on lane is fatal", "pull_request",
         dict(RUN_PYTHON="false", RUN_ACCEPTANCE="false",
              RUN_PREVIEW="false", RUN_PLUGIN_HOST="false"),
         {**base, "surface": {"result": "failure"}},
         [("surface", "failure")]),
    ]
    bad = 0
    for name, event, env, needs, want in cases:
        got = check(needs, event, env)
        ok = got == want
        print(("ok  " if ok else "FAIL") + name)
        if not ok:
            print("     expected", want)
            print("     got     ", got)
            bad += 1
    try:
        check({"changes": {"result": "success"}}, "pull_request", {})
    except ValueError:
        print("ok  missing fan-in dependency is rejected")
    else:
        print("FAIL missing fan-in dependency was accepted")
        bad += 1
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return selftest()
    try:
        needs = json.loads(os.environ["NEEDS"])
        event = os.environ.get("EVENT_NAME", "")
        failures = check(needs, event, dict(os.environ))
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        print("could not judge CI fan-in: " + str(exc), file=sys.stderr)
        return 2
    if failures:
        print("selected CI dependencies did not succeed:", file=sys.stderr)
        for name, result in failures:
            print(f"  {name}: {result}", file=sys.stderr)
        return 1
    print("All selected CI dependencies succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
