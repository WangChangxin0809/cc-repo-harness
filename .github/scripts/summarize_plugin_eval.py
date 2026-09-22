#!/usr/bin/env python3
"""Judge complete native evidence: pass=0, quality/safety defect=1, cannot judge=2."""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import sys

from validate_plugin_eval import (DEFAULT_POLICY, DEFAULTS, load_policy, number,
                                 read_json, require, text_sha256, validate_inputs)


def object_(value, label):
    require(isinstance(value, dict), f"{label}: expected object")
    return value


def records(value, expected, label):
    require(isinstance(value, list), f"{label}: expected array")
    found = {}
    for item in value:
        object_(item, label)
        name = item.get("name")
        require(isinstance(name, str) and name in expected and name not in found,
                f"{label}: unexpected or duplicate name {name!r}")
        found[name] = item
    require(set(found) == set(expected), f"{label}: missing expected records")
    return found


def same_number(actual, expected, label, minimum=0, maximum=1, integer=False):
    number(actual, label, minimum, maximum, integer)
    require(math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9),
            f"{label}: inconsistent with underlying evidence ({actual} != {expected})")


def nonempty_string(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"{label}: missing string")


def run_score(run, expected, label, safety):
    object_(run, label)
    require("error" in run and run["error"] in (None, "") and not run.get("aborted"), f"{label}: missing status or abnormal/aborted run")
    require(run.get("skippedPaidGraders") is False, f"{label}: missing or skipped paid-grader evidence")
    for field in ("costUsd", "judgeCostUsd", "durationSeconds"):
        number(run.get(field), f"{label}/{field}")
    number(run.get("turns"), f"{label}/turns", integer=True)
    nonempty_string(run.get("startedAt"), f"{label}/startedAt")
    nonempty_string(run.get("tracePath"), f"{label}/tracePath")
    graders = records(run.get("graders"), expected, f"{label}/graders")
    passed_weight, total_weight = 0, 0
    for name, spec in expected.items():
        grader = graders[name]
        where = f"{label}/{name}"
        same_number(grader.get("weight"), spec["weight"], where + "/weight", maximum=None)
        require(type(grader.get("passed")) is bool, where + ": passed must be boolean")
        require(isinstance(grader.get("explanation"), str), where + ": missing grader explanation")
        require(not grader["explanation"].startswith("grader threw:"), where + ": grader execution failed")
        require(grader.get("scored") is spec["scored"] and grader.get("withOnly") is (not spec["scored"]),
                where + ": scoring flags differ from policy")
        if spec["scored"]:
            total_weight += spec["weight"]
            if grader["passed"]:
                passed_weight += spec["weight"]
        if spec["hardSafety"] and not grader["passed"]:
            safety.append(where)
    score = passed_weight / total_weight
    same_number(run.get("score"), score, label + "/score")
    require(run.get("passed") is (score >= 1), label + ": passed disagrees with native perfect-score rule")
    return score


def summarize(data, policy=None, inputs=None):
    policy = load_policy() if policy is None else policy
    inputs = validate_inputs(DEFAULTS if inputs is None else inputs)
    object_(data, "result")
    require(type(data.get("schemaVersion")) is int and data["schemaVersion"] == policy["nativeSchemaVersion"], "unsupported native schemaVersion")
    require(data.get("claudeVersion") == policy["claudeVersion"], "native version differs from reviewed policy")
    require(data.get("partial") is False, "partial or missing completion evidence: " + str(data.get("partialReason", "unknown")))
    require(not data.get("partialReason"), "completed result has a partial reason")
    number(data.get("costUsd"), "costUsd")
    number(data.get("durationSeconds"), "durationSeconds")
    nonempty_string(data.get("startedAt"), "startedAt")
    suite = object_(data.get("suite"), "suite")
    require(suite.get("ablation") == "with-without", "both plugin arms are required")
    require(suite.get("modelOverride") == inputs["model"], "suite model differs from validated dispatch inputs")
    same_number(suite.get("threshold"), inputs["threshold"], "suite/threshold")
    same_number(suite.get("concurrency"), inputs["concurrency"], "suite/concurrency", maximum=4, integer=True)
    require(not suite.get("caseFilter") and not suite.get("tagFilters"), "filtered evidence is not a complete suite")
    plugins = records(suite.get("plugins"), {policy["pluginName"]}, "suite/plugins")
    for plugin in plugins.values():
        require(plugin.get("problem") in (None, "identity_unverified", "archive_not_probed"), "plugin was not loadable or has an unknown problem")
        nonempty_string(plugin.get("path"), "plugin/path")
    cases = records(data.get("cases"), policy["cases"], "cases")
    failures, baseline_safety, rows = [], [], []
    traces = set()
    total_cost = 0
    for name, spec in policy["cases"].items():
        case = cases[name]
        metadata = records(case.get("graders"), spec["graders"], name + "/grader definitions")
        for grader_name, grader_spec in spec["graders"].items():
            definition = metadata[grader_name]
            require(definition.get("type") == grader_spec["type"], name + ": grader type differs from policy")
            same_number(definition.get("weight"), grader_spec["weight"], name + "/grader weight", maximum=None)
        arms = object_(case.get("arms"), name + "/arms")
        require(set(arms) == {"with", "without"}, name + ": expected WITH and WITHOUT arms")
        computed = {}
        for arm in ("with", "without"):
            runs = arms[arm]
            require(isinstance(runs, list) and len(runs) == inputs["runs"], f"{name}/{arm}: run count differs from validated inputs")
            safety = []
            # Native 2.1.273 Ul omits with-only graders from WITHOUT entirely.
            expected = {key: grader for key, grader in spec["graders"].items()
                        if arm == "with" or grader["scored"]}
            scores = [run_score(run, expected, f"{name}/{arm}/{index}", safety)
                      for index, run in enumerate(runs, 1)]
            for run in runs:
                require(run["tracePath"] not in traces, f"{name}/{arm}: duplicate run tracePath")
                traces.add(run["tracePath"])
            computed[arm] = (sum(scores) / len(scores), sum(score >= 1 for score in scores) / len(scores))
            total_cost += sum(run["costUsd"] for run in runs)
            if arm == "with":
                failures.extend("Hard safety: " + item for item in safety)
            else:
                baseline_safety.extend(safety)
        with_score, with_pass = computed["with"]
        without_score, without_pass = computed["without"]
        delta = with_score - without_score
        agg = object_(case.get("aggregates"), name + "/aggregates")
        for field, value in (("score", with_score), ("passRate", with_pass),
                             ("scoreWithout", without_score), ("passRateWithout", without_pass), ("delta", delta)):
            same_number(agg.get(field), value, name + "/" + field, minimum=-1 if field == "delta" else 0)
        if with_score < inputs["threshold"]:
            failures.append(f"Quality: {name} WITH {with_score:.3f} < {inputs['threshold']:.3f}")
        rows.append((name, with_score, without_score, delta, with_pass, without_pass))
    agg = object_(data.get("aggregates"), "aggregates")
    same_number(agg.get("casesTotal"), len(rows), "casesTotal", maximum=None, integer=True)
    passed = sum(row[1] >= inputs["threshold"] for row in rows)
    same_number(agg.get("casesPassed"), passed, "casesPassed", maximum=None, integer=True)
    overall = sum(row[1] for row in rows) / len(rows)
    mean_delta = sum(row[3] for row in rows) / len(rows)
    same_number(agg.get("overallScore"), overall, "overallScore")
    same_number(agg.get("overallPassRate"), sum(row[4] for row in rows) / len(rows), "overallPassRate")
    same_number(agg.get("meanDelta"), mean_delta, "meanDelta", minimum=-1)
    same_number(data["costUsd"], total_cost, "costUsd", maximum=None)
    lines = ["# Native Claude Code plugin eval", "",
             "Judgment: **" + ("FAIL (quality/safety)" if failures else "PASS") + "**", "",
             "| Case | WITH | WITHOUT | Delta | Perfect runs WITH / WITHOUT |",
             "|---|---:|---:|---:|---:|"]
    for name, with_score, without_score, delta, with_pass, without_pass in rows:
        lines.append(f"| {name} | {with_score:.3f} | {without_score:.3f} | {delta:+.3f} | {with_pass:.1%} / {without_pass:.1%} |")
    lines += ["", f"- WITH quality: **{passed}/{len(rows)}** cases at threshold {inputs['threshold']:.3f}; overall {overall:.3f}.",
              f"- Mean plugin delta: **{mean_delta:+.3f}** (descriptive; no positive-delta gate).",
              f"- Complete evidence: {inputs['runs']} runs per arm per case; Claude Code {data['claudeVersion']}.",
              f"- Claude list-price estimate: **${data['costUsd']:.4f}**; requested stop threshold ${inputs['max_cost_usd']:g}.",
              "- Cost is an estimate/stop mechanism, not an actual vendor billing guarantee.",
              "- Baseline safety failures: " + str(len(baseline_safety)) + " (reported separately; WITH safety is the hard gate)."]
    lines.extend("  - " + item for item in baseline_safety)
    if failures:
        lines += ["", "Failures:"] + ["- " + item for item in failures]
    return "\n".join(lines) + "\n", failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--summary")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--inputs", type=Path, help="independent validated dispatch metadata; defaults are for offline use")
    args = parser.parse_args()
    status = 2
    try:
        inputs = read_json(args.inputs) if args.inputs else DEFAULTS
        if args.inputs:
            object_(inputs, "inputs")
            require(type(inputs.get("schemaVersion")) is int and inputs["schemaVersion"] == 1, "unsupported inputs schema")
            require(inputs.get("policySha256") == text_sha256(args.policy), "inputs were validated against a different policy")
        summary, failures = summarize(read_json(args.result), load_policy(args.policy), inputs)
        status = 1 if failures else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        summary = "# Native Claude Code plugin eval\n\nJudgment: **CANNOT JUDGE**\n\n" + str(exc) + "\n"
        print("cannot judge plugin eval: " + str(exc), file=sys.stderr)
    print(summary, end="")
    target = args.summary or os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        try:
            with open(target, "a", encoding="utf-8") as fh:
                fh.write(summary)
        except OSError as exc:
            print("cannot write summary: " + str(exc), file=sys.stderr)
            return 2
    return status


if __name__ == "__main__":
    sys.exit(main())
