#!/usr/bin/env python3
"""Summarize Claude Code plugin-eval JSON without inventing missing evidence."""
from __future__ import annotations

import argparse
import json
import os
import sys


def summarize(data):
    if not isinstance(data, dict) or data.get("schemaVersion") != 1:
        raise ValueError("plugin-eval result must use schemaVersion 1")
    if data.get("partial"):
        raise ValueError("partial eval result: " + str(data.get("partialReason") or "unknown"))
    aggregates = data.get("aggregates")
    cases = data.get("cases")
    if not isinstance(aggregates, dict) or not isinstance(cases, list) or not cases:
        raise ValueError("plugin-eval result has no complete aggregate/case data")
    if aggregates.get("casesTotal") != len(cases):
        raise ValueError("aggregate case count does not match case records")

    rows = []
    runtime_errors = []
    for case in cases:
        name = case.get("name")
        agg = case.get("aggregates", {})
        score, delta = agg.get("score"), agg.get("delta")
        if not isinstance(name, str) or not isinstance(score, (int, float)):
            raise ValueError("case is missing name or score")
        for arm_name, runs in (case.get("arms") or {}).items():
            if not isinstance(runs, list):
                raise ValueError("case arm is not a run list")
            for index, run in enumerate(runs, 1):
                if not isinstance(run, dict):
                    raise ValueError("case run is not an object")
                if run.get("error"):
                    runtime_errors.append(f"{name}/{arm_name}/{index}: {run['error']}")
                if run.get("aborted"):
                    runtime_errors.append(f"{name}/{arm_name}/{index}: aborted {run['aborted']}")
                if run.get("skippedPaidGraders"):
                    runtime_errors.append(f"{name}/{arm_name}/{index}: skipped paid graders")
        rows.append((name, score, delta))

    lines = [
        "# Native Claude Code plugin eval",
        "",
        "| Case | WITH | Delta |",
        "|---|---:|---:|",
    ]
    for name, score, delta in rows:
        rendered = "n/a" if delta is None else f"{delta:+.3f}"
        lines.append(f"| {name} | {score:.3f} | {rendered} |")
    lines += [
        "",
        f"- Overall WITH score: **{aggregates.get('overallScore', 0):.3f}**",
        f"- Mean plugin delta: **{aggregates.get('meanDelta', 0):+.3f}**",
        f"- Cases: **{aggregates.get('casesPassed')}/{aggregates.get('casesTotal')}** at the configured threshold",
        f"- Estimated cost (USD): **{data.get('costUsd', 0):.2f}**",
        f"- Claude Code: **{data.get('claudeVersion', 'unknown')}**",
    ]
    return "\n".join(lines) + "\n", runtime_errors


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("result")
    ap.add_argument("--summary")
    args = ap.parse_args()
    try:
        with open(args.result, encoding="utf-8") as fh:
            data = json.load(fh)
        summary, errors = summarize(data)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print("could not summarize plugin eval: " + str(exc), file=sys.stderr)
        return 2
    print(summary, end="")
    target = args.summary or os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(summary)
    if errors:
        print("agent runs ended abnormally:", file=sys.stderr)
        for error in errors:
            print("  " + error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
