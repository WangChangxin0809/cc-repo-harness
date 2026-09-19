"""Read-only experimental concurrency annex. No sixth score, no target execution.

A supplied conformance report can establish only that the copied implementation
matches tested bytes. It does not establish that a host loaded the MCP, that
agents respect claims, that edits merge, or that real tasks improve.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

UNMEASURED = {"status": "not-measured"}

def assess(root, evidence=None):
    command = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, encoding="utf-8", timeout=10)
    if command.returncode:
        raise ValueError("a Git worktree is required")
    root = Path(command.stdout.strip()).resolve()
    path = root / ".mcp.json"
    if path.is_symlink():
        raise ValueError(".mcp.json is a symlink; inspect the configuration explicitly")
    config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(config, dict) or not isinstance(config.get("mcpServers", {}), dict):
        raise ValueError("malformed MCP configuration")
    servers = config.get("mcpServers", {})
    if "room" in servers and not isinstance(servers["room"], dict):
        raise ValueError("room MCP declaration must be an object")
    declared = "room" in servers
    result = {
        "schema": 1, "scope": "experimental-concurrency-annex", "score": None,
        "configuration": {"status": "declared-not-executed" if declared else "not-configured",
                          "absence_is_not_a_defect": True},
        "implementation_conformance": dict(UNMEASURED),
        "mcp_host_integration": dict(UNMEASURED),
        "mandatory_write_exclusion": dict(UNMEASURED),
        "semantic_conflict_detection": dict(UNMEASURED),
        "real_agent_task_outcomes": dict(UNMEASURED),
        "limitations": ["self-reported evidence is not a signed attestation",
                        "no repository code or hooks were executed",
                        "coordination is not CRDT or enforced filesystem locking"],
    }
    if evidence is None:
        return result
    report = json.loads(Path(evidence).read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("evidence must be a JSON object")
    expected_scope = "implementation-conformance-not-repository-readiness"
    if report.get("schema") != 1 or report.get("scope") != expected_scope:
        raise ValueError("unsupported evidence schema or scope")
    for field in ("tests", "failed", "skipped", "exit_code"):
        if type(report.get(field)) is not int or report[field] < 0:
            raise ValueError("invalid evidence counts")
    if report["tests"] <= 0 or report["failed"] + report["skipped"] > report["tests"]:
        raise ValueError("inconsistent evidence counts")
    expected_code = 1 if report["failed"] else 2 if report["skipped"] else 0
    if report["exit_code"] != expected_code:
        raise ValueError("inconsistent evidence exit code")
    hashes = report.get("sha256", {})
    if not isinstance(hashes, dict):
        raise ValueError("evidence sha256 must be an object")
    stale = []
    for name in ("store.py", "selftest.py"):
        installed = root / "scripts" / "room" / name
        if (any(p.is_symlink() for p in (root / "scripts", root / "scripts/room", installed)) or not installed.is_file()
                or hashlib.sha256(installed.read_bytes()).hexdigest() != hashes.get(name)):
            stale.append(name)
    status = "stale-or-not-installed" if stale else (
        "failed" if report["failed"] else "could-not-judge" if report["skipped"] else "pass")
    result["implementation_conformance"] = {
        "status": status, "tests": report["tests"], "failed": report["failed"],
        "skipped": report["skipped"], "mismatched_files": stale,
        "scope": expected_scope,
        "evidence_environment": {"python": report.get("python"), "platform": report.get("platform")},
    }
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    try:
        result = assess(args.root, args.evidence)
        body = json.dumps(result, indent=2) + "\n"
        if args.json:
            args.json.write_text(body, encoding="utf-8")
        print(body, end="")
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("could not judge concurrency: " + str(exc), file=sys.stderr)
        return 2
    measured = result["implementation_conformance"]["status"]
    return 1 if measured == "failed" else 2 if measured in ("could-not-judge", "stale-or-not-installed") else 0

if __name__ == "__main__":
    sys.exit(main())
