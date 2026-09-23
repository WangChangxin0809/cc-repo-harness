#!/usr/bin/env python3
"""Validate bounded dispatch inputs and the reviewed suite, without model access."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "evals/policy.json"
DEFAULTS = {"model": "nvidia/nemotron-3-super-120b-a12b", "runs": 3,
            "concurrency": 1, "max_cost_usd": 20, "threshold": .67}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, label, minimum=0, maximum=None, integer=False):
    require(type(value) in (int, float) and abs(value) <= sys.float_info.max
            and (type(value) is int or math.isfinite(value)), f"{label}: expected finite number")
    require(value >= minimum and (maximum is None or value <= maximum), f"{label}: outside allowed range")
    require(not integer or type(value) is int, f"{label}: expected integer")
    return value


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("nonfinite JSON constant: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=constant)


def text_sha256(path):
    # Normalize CRLF through text mode, so Git's Windows checkout is equivalent.
    return hashlib.sha256(Path(path).read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def load_policy(path=DEFAULT_POLICY):
    policy = read_json(path)
    require(isinstance(policy, dict) and type(policy.get("schemaVersion")) is int
            and policy["schemaVersion"] == 1, "invalid policy schema")
    require(policy.get("nativeSchemaVersion") == 1 and policy.get("hardSafetyArm") == "with", "invalid policy contract")
    for key in ("claudeVersion", "pluginName"):
        require(isinstance(policy.get(key), str) and policy[key], f"missing policy {key}")
    cases = policy.get("cases")
    require(isinstance(cases, dict) and cases, "empty policy case inventory")
    for name, case in cases.items():
        require(re.fullmatch(r"[a-z0-9-]+", name) is not None and isinstance(case, dict), "invalid policy case")
        graders = case.get("graders")
        require(isinstance(graders, dict) and graders, f"{name}: empty policy graders")
        for grader, spec in graders.items():
            require(isinstance(spec, dict) and re.fullmatch(r"[a-z0-9-]+", grader) is not None, "invalid policy grader")
            number(spec.get("weight"), "policy weight", minimum=1)
            require(spec.get("type") in ("tool_used", "file_exists", "regex"), "policy requires reviewed deterministic grader type")
            require(type(spec.get("scored")) is bool and type(spec.get("hardSafety")) is bool, "invalid policy grader flags")
        require(any(g["scored"] for g in graders.values()), "policy has no scored graders")
        files = case.get("filesSha256")
        expected = {"case.yaml", "prompt.md", "fixture.sh"} | {f"graders/{g}.md" for g in graders}
        require(isinstance(files, dict) and set(files) == expected, "policy file inventory must cover every grader and case input")
        require(all(isinstance(h, str) and re.fullmatch(r"[a-f0-9]{64}", h) for h in files.values()), "invalid policy file hash")
    return policy


def validate_suite(suite, policy):
    suite = Path(suite)
    require(suite.is_dir(), "suite directory missing")
    observed = {p.parent.relative_to(suite).as_posix() for p in suite.rglob("case.yaml")}
    # A missing case.yaml must not hide an otherwise present case directory.
    observed |= {p.parent.relative_to(suite).as_posix() for p in suite.rglob("prompt.md")}
    observed |= {p.parent.relative_to(suite).as_posix() for p in suite.rglob("graders") if p.is_dir()}
    require(observed == set(policy["cases"]), "suite case inventory differs from policy")
    for name, case in policy["cases"].items():
        directory = suite / name
        files = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
        require(files == set(case["filesSha256"]), f"{name}: case/grader file inventory differs from policy")
        for filename, digest in case["filesSha256"].items():
            require(text_sha256(directory / filename) == digest, f"{name}/{filename}: changed since explicit policy review")


def validate_inputs(values):
    require(isinstance(values, dict), "inputs must be an object")
    result = {}
    for key, minimum, maximum, integer in (
            ("runs", 1, 10, True), ("concurrency", 1, 4, True),
            ("max_cost_usd", 0, 20, False), ("threshold", 0, 1, False)):
        value = values.get(key)
        if isinstance(value, str):
            if integer:
                require(re.fullmatch(r"[0-9]+", value) is not None, f"{key}: expected integer")
                value = int(value)
            else:
                try:
                    value = float(value)
                except ValueError as exc:
                    raise ValueError(f"{key}: expected number") from exc
        result[key] = number(value, key, minimum, maximum, integer)
    require(result["max_cost_usd"] > 0, "max_cost_usd: must be positive")
    model = values.get("model")
    require(isinstance(model, str) and 0 < len(model) <= 256 and model.strip() == model
            and bool(model.strip()) and not any(unicodedata.category(c).startswith("C") for c in model),
            "model: expected 1..256 characters without surrounding whitespace or control characters")
    result["model"] = model
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--inputs", action="store_true")
    parser.add_argument("--from-env", action="store_true")
    parser.add_argument("--output", type=Path)
    for key, default in DEFAULTS.items():
        parser.add_argument("--" + key.replace("_", "-"), default=default)
    args = parser.parse_args()
    try:
        policy = load_policy(args.policy)
        if args.suite:
            validate_suite(args.suite, policy)
            pinned = read_json(ROOT / "eval/agent/package.json")["dependencies"]["@anthropic-ai/claude-code"]
            require(pinned == policy["claudeVersion"], "native host pin differs from reviewed policy")
        if args.inputs or args.from_env:
            values = {k: os.environ.get("UPSTREAM_MODEL" if k == "model" else k.upper(), "")
                      if args.from_env else getattr(args, k) for k in DEFAULTS}
            result = validate_inputs(values)
            result.update(schemaVersion=1, policySha256=text_sha256(args.policy))
            if args.output:
                args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(result, sort_keys=True))
        require(args.suite or args.inputs or args.from_env, "choose --suite or --inputs/--from-env")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("cannot judge plugin eval: " + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
