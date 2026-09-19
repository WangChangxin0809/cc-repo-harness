#!/usr/bin/env python3
"""Classify a PR diff into conservative CI lanes.

The selector is an optimization, never a source of correctness. On pushes to
main the workflow runs every blocking lane regardless of these outputs. Any
change to the selector, workflow wiring, or local CI runner forces every lane.

Usage:
    python3 .github/scripts/select_ci.py --base <sha> --head <sha>
    python3 .github/scripts/select_ci.py --files path [path ...]
    python3 .github/scripts/select_ci.py --self-test
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import PurePosixPath


FORCE_ALL = (
    ".github/workflows/",
    ".github/scripts/select_ci.py",
    ".github/scripts/check_ci_results.py",
    "scripts/check.py",
)

PLUGIN_SURFACE = (
    ".claude-plugin/",
    "skills/",
    "agents/",
    "commands/",
    "hooks/",
    "eval/agent/",
    "evals/",
)

ACCEPTANCE_SURFACE = (
    "shared/",
    "skills/bootstrap-repo-harness/",
    "scripts/sync_template.py",
)

PREVIEW_SURFACE = (
    "shared/optional/",
    "shared/scripts/assess/concurrency",
)

PYTHON_SURFACE = (
    ".github/scripts/",
    "shared/",
    "hooks/",
    "scripts/",
    "eval/",
)


def norm(path: str) -> str:
    path = path.replace("\\", "/")
    if not path or path.startswith("/"):
        raise ValueError("changed paths must be repository-relative")
    while path.startswith("./"):
        path = path[2:]
    if not path or ".." in PurePosixPath(path).parts:
        raise ValueError("changed paths must be repository-relative")
    return path


def starts(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix)
               for prefix in prefixes)


def classify(paths: list[str]) -> dict[str, bool]:
    paths = [norm(p) for p in paths]
    force = not paths or any(starts(p, FORCE_ALL) for p in paths)
    return {
        "python": force or any(
            starts(p, PYTHON_SURFACE)
            and not p.startswith("eval/agent/")
            and p.endswith((".py", ".json", ".toml"))
            for p in paths
        ),
        "acceptance": force or any(starts(p, ACCEPTANCE_SURFACE) for p in paths),
        "preview": force or any(starts(p, PREVIEW_SURFACE) for p in paths),
        "plugin_host": force or any(starts(p, PLUGIN_SURFACE) for p in paths),
        "force_all": force,
    }


def changed_files(base: str, head: str) -> list[str]:
    if not base or not head or set(base) == {"0"}:
        return []
    proc = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", base, head],
        capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    if proc.returncode:
        raise ValueError(proc.stderr.strip() or "git diff failed")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def write_outputs(path: str, result: dict[str, bool]) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        for key, value in result.items():
            fh.write(f"{key}={'true' if value else 'false'}\n")


def selftest() -> int:
    cases = [
        ("README only", ["README.md"],
         dict(python=False, acceptance=False, preview=False, plugin_host=False, force_all=False)),
        ("docs only", ["docs/reference/foo.md"],
         dict(python=False, acceptance=False, preview=False, plugin_host=False, force_all=False)),
        ("core Python", ["shared/scripts/gates/check_docs_index.py"],
         dict(python=True, acceptance=True, preview=False, plugin_host=False, force_all=False)),
        ("plugin skill", ["skills/bootstrap-repo-harness/SKILL.md"],
         dict(python=False, acceptance=True, preview=False, plugin_host=True, force_all=False)),
        ("manifest", [".claude-plugin/plugin.json"],
         dict(python=False, acceptance=False, preview=False, plugin_host=True, force_all=False)),
        ("AgentRoom", ["shared/optional/agentroom/store.py"],
         dict(python=True, acceptance=True, preview=True, plugin_host=False, force_all=False)),
        ("eval agent", ["eval/agent/package-lock.json"],
         dict(python=False, acceptance=False, preview=False, plugin_host=True, force_all=False)),
        ("plugin eval case", ["evals/bootstrap-existing-repo/prompt.md"],
         dict(python=False, acceptance=False, preview=False, plugin_host=True, force_all=False)),
        ("workflow forces all", [".github/workflows/ci.yml"],
         dict(python=True, acceptance=True, preview=True, plugin_host=True, force_all=True)),
        ("selector forces all", [".github/scripts/select_ci.py"],
         dict(python=True, acceptance=True, preview=True, plugin_host=True, force_all=True)),
        ("mixed docs and code", ["README.md", "hooks/run_repo_guards.py"],
         dict(python=True, acceptance=False, preview=False, plugin_host=True, force_all=False)),
        ("unknown file stays cheap", ["assets/logo.svg"],
         dict(python=False, acceptance=False, preview=False, plugin_host=False, force_all=False)),
        ("empty diff is conservative", [],
         dict(python=True, acceptance=True, preview=True, plugin_host=True, force_all=True)),
    ]
    bad = 0
    for name, paths, expected in cases:
        got = classify(paths)
        ok = got == expected
        print(("ok  " if ok else "FAIL") + name)
        if not ok:
            print("     expected", expected)
            print("     got     ", got)
            bad += 1
    try:
        classify(["../outside"])
    except ValueError:
        print("ok  path traversal is rejected")
    else:
        print("FAIL path traversal was accepted")
        bad += 1
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base")
    ap.add_argument("--head")
    ap.add_argument("--files", nargs="*")
    ap.add_argument("--github-output")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return selftest()
    try:
        paths = args.files if args.files is not None else changed_files(args.base or "", args.head or "")
        result = classify(paths)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("could not classify CI paths: " + str(exc), file=sys.stderr)
        return 2
    payload = {"paths": paths, **result}
    print(json.dumps(payload, indent=2))
    if args.github_output:
        write_outputs(args.github_output, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
