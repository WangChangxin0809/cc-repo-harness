#!/usr/bin/env python3
"""Require successful main push CI for the exact release repository and SHA.

0 = complete successful evidence; 1 = rejected; 2 = could not judge.
Only reads GitHub; tagging belongs to the separately permissioned workflow job.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

WORKFLOWS = ("ci.yml", "postmerge-ci.yml")
PENDING = {"queued", "in_progress", "waiting", "pending", "requested"}
CONCLUSIONS = {"success", "failure", "cancelled", "timed_out", "skipped",
               "neutral", "action_required", "stale", "startup_failure"}


def judge(payload, repository, sha, workflow):
    """Judge API evidence; malformed or mismatched responses cannot authorize."""
    if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
        raise ValueError(f"{workflow}: missing workflow_runs list")
    rows = payload["workflow_runs"]
    if not rows:
        return "pending", f"{workflow}: no main push run for {sha} yet"
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{workflow}: malformed run")
        origin = row.get("head_repository")
        if (not isinstance(origin, dict)
                or origin.get("full_name") != repository
                or row.get("head_sha") != sha
                or row.get("head_branch") != "main"
                or row.get("event") != "push"
                or row.get("path") != ".github/workflows/" + workflow):
            raise ValueError(f"{workflow}: run identity does not match release evidence")
        for key in ("id", "run_attempt"):
            if type(row.get(key)) is not int or row[key] < 1:
                raise ValueError(f"{workflow}: invalid run {key}")
        identity = (row["id"], row["run_attempt"])
        if identity in seen:
            raise ValueError(f"{workflow}: duplicate run attempt")
        seen.add(identity)
        status, conclusion = row.get("status"), row.get("conclusion")
        if not isinstance(status, str) or status not in PENDING | {"completed"}:
            raise ValueError(f"{workflow}: unknown run status")
        if status == "completed":
            if not isinstance(conclusion, str) or conclusion not in CONCLUSIONS:
                raise ValueError(f"{workflow}: missing or unknown completed conclusion")
        elif conclusion is not None:
            raise ValueError(f"{workflow}: incomplete run has a conclusion")
    latest = max(rows, key=lambda row: (row["id"], row["run_attempt"]))
    detail = (f"{workflow}: run {latest['id']} attempt {latest['run_attempt']} "
              f"{latest['status']}/{latest['conclusion']}")
    if latest["status"] != "completed":
        return "pending", detail
    return ("success" if latest["conclusion"] == "success" else "failure"), detail


def fetch_runs(repository, workflow, sha):
    # Workflow-specific endpoint and all identity filters constrain the server
    # response; judge checks them again rather than trusting an API-shaped blob.
    endpoint = f"repos/{repository}/actions/workflows/{workflow}/runs"
    result = subprocess.run(
        ["gh", "api", "--method", "GET", endpoint,
         "-f", "branch=main", "-f", "event=push", "-f", f"head_sha={sha}",
         "-f", "per_page=100"],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    if result.returncode:
        raise ValueError(f"{workflow}: GitHub run evidence unavailable: {result.stderr.strip()}")
    return json.loads(result.stdout)


def verify(repository, ref, sha, *, fetch=fetch_runs, wait_seconds=1800,
           poll_seconds=15, clock=time.monotonic, sleep=time.sleep):
    if ref != "refs/heads/main":
        print("release requires refs/heads/main", file=sys.stderr)
        return 1
    if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("GITHUB_REPOSITORY must identify owner/repository")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("GITHUB_SHA must be an exact commit SHA")
    if wait_seconds < 0 or poll_seconds <= 0:
        raise ValueError("wait must be nonnegative and poll interval positive")
    deadline = clock() + wait_seconds
    while True:
        states = []
        for workflow in WORKFLOWS:
            state, detail = judge(fetch(repository, workflow, sha), repository, sha, workflow)
            print(detail, flush=True)
            if state == "failure":
                return 1
            states.append(state)
        if all(state == "success" for state in states):
            print(f"Release evidence verified for {repository}@{sha}.")
            return 0
        remaining = deadline - clock()
        if remaining <= 0:
            print("release evidence deadline reached before both workflows succeeded", file=sys.stderr)
            return 2
        sleep(min(poll_seconds, remaining))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wait-seconds", type=int, default=1800)
    parser.add_argument("--poll-seconds", type=int, default=15)
    args = parser.parse_args(argv)
    try:
        return verify(os.environ.get("GITHUB_REPOSITORY", ""),
                      os.environ.get("GITHUB_REF", ""),
                      os.environ.get("GITHUB_SHA", ""),
                      wait_seconds=args.wait_seconds, poll_seconds=args.poll_seconds)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print("could not judge release evidence: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
