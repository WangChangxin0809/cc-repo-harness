#!/usr/bin/env python3
"""Offline defect witnesses; synthetic records follow native 2.1.273 serialization."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import summarize_plugin_eval as subject

# Intentionally independent of the production policy/score calculator.
GRADERS = {
    "bootstrap-existing-repo": [
        ("bootstrap-skill-fired", "tool_used", 1, False),
        ("docs-router-created", "file_exists", 1, True),
        ("guard-created", "file_exists", 2, True),
        ("guard-is-wired", "regex", 2, True),
        ("preserves-project-instructions", "regex", 2, True)],
    "ignores-unrelated-request": [
        ("bootstrap-skill-stays-off", "tool_used", 2, True),
        ("no-bash", "tool_used", 1, True),
        ("no-edit", "tool_used", 1, True),
        ("no-write", "tool_used", 1, True),
        ("no-harness-files", "file_exists", 1, True),
        ("reads-the-project", "regex", 2, True)],
    "new-repo-routes-to-template": [
        ("bootstrap-skill-fired", "tool_used", 1, False),
        ("does-not-scaffold-existing-repo-path", "file_exists", 1, True),
        ("names-template", "regex", 3, True)],
}


def fixture():
    data = {
        "schemaVersion": 1, "claudeVersion": "2.1.273", "partial": False,
        "startedAt": "2026-09-23T00:00:00.000Z", "durationSeconds": 180,
        "costUsd": 1.8,
        "suite": {"ablation": "with-without", "threshold": .67,
                  "concurrency": 1, "modelOverride": "nvidia/nemotron-3-super-120b-a12b",
                  "plugins": [{"name": "cc-repo-harness", "version": "1.12.0", "path": "/repo"}]},
        "cases": [], "aggregates": {"casesTotal": 3, "casesPassed": 3,
            "overallScore": 1, "overallPassRate": 1, "meanDelta": 0}}
    for name, graders in GRADERS.items():
        case = {"name": name, "runsPerCase": 1,
                "graders": [{"name": n, "type": t, "weight": w, "config": {}}
                            for n, t, w, _ in graders], "arms": {},
                "aggregates": {"score": 1, "scoreWithout": 1, "passRate": 1,
                               "passRateWithout": 1, "delta": 0}}
        for arm in ("with", "without"):
            case["arms"][arm] = [{
                "score": 1, "passed": True, "turns": 2, "costUsd": .1,
                "judgeCostUsd": 0, "durationSeconds": 10,
                "startedAt": data["startedAt"], "tracePath": f"{name}/{arm}/{i}.jsonl",
                "skippedPaidGraders": False, "error": None,
                "graders": [{"name": n, "passed": True, "weight": w,
                             "withOnly": not s, "scored": s, "explanation": "synthetic"}
                            for n, _, w, s in graders if arm == "with" or s]} for i in range(3)]
        data["cases"].append(case)
    return data


def failed_grader(data, case_index, grader_index, arm="with"):
    """Recalculate native aggregates after an intentional behavioral failure."""
    case = data["cases"][case_index]
    for run in case["arms"][arm]:
        grader_name = GRADERS[case["name"]][grader_index][0]
        next(g for g in run["graders"] if g["name"] == grader_name)["passed"] = False
        scored = [g for g in run["graders"] if g["scored"]]
        run["score"] = sum(g["weight"] for g in scored if g["passed"]) / sum(g["weight"] for g in scored)
        run["passed"] = run["score"] >= 1
    agg = case["aggregates"]
    agg["score" if arm == "with" else "scoreWithout"] = case["arms"][arm][0]["score"]
    agg["passRate" if arm == "with" else "passRateWithout"] = 0
    agg["delta"] = agg["score"] - agg["scoreWithout"]
    data["aggregates"].update(
        casesPassed=sum(c["aggregates"]["score"] >= .67 for c in data["cases"]),
        overallScore=sum(c["aggregates"]["score"] for c in data["cases"])/3,
        overallPassRate=sum(c["aggregates"]["passRate"] for c in data["cases"])/3,
        meanDelta=sum(c["aggregates"]["delta"] for c in data["cases"])/3)


class EvidenceTests(unittest.TestCase):
    def test_complete_passing_twin_and_unknown_fields(self):
        data = fixture()
        data["futureField"] = {"foo": "bar"}
        text, failures = subject.summarize(data)
        self.assertFalse(failures)
        self.assertIn("WITHOUT", text)

    def test_absent_empty_or_wrong_count_arms(self):
        for replacement in (None, {}, {"with": []}, {"with": [], "without": []}):
            with self.subTest(arms=replacement):
                data = fixture()
                data["cases"][0]["arms"] = replacement
                with self.assertRaises(ValueError):
                    subject.summarize(data)
        for arm in ("with", "without"):
            for count in (1, 2, 4):
                data = fixture()
                data["cases"][0]["arms"][arm] = [copy.deepcopy(data["cases"][0]["arms"][arm][0]) for _ in range(count)]
                with self.subTest(arm=arm, count=count), self.assertRaises(ValueError):
                    subject.summarize(data)

    def test_case_inventory(self):
        for mutation in (lambda d: d["cases"].pop(),
                         lambda d: d["cases"].append(copy.deepcopy(d["cases"][0])),
                         lambda d: d["cases"][0].update(name="unexpected"),
                         lambda d: d["cases"].__setitem__(0, 7)):
            data = fixture()
            mutation(data)
            data["aggregates"]["casesTotal"] = len(data["cases"])
            with self.subTest(data=data["cases"][0]), self.assertRaises(ValueError):
                subject.summarize(data)

    def test_grader_inventory_and_contract(self):
        for location in ("metadata", "run"):
            for defect in ("missing", "duplicate", "extra", "weight", "boolean_weight", "scored", "withOnly", "passed"):
                if location == "metadata" and defect in ("scored", "withOnly", "passed"):
                    continue
                data = fixture()
                case = data["cases"][0]
                graders = case["graders"] if location == "metadata" else case["arms"]["without"][0]["graders"]
                if defect == "missing": graders.pop()
                elif defect == "duplicate": graders.append(copy.deepcopy(graders[0]))
                elif defect == "extra": graders[0]["name"] = "unknown"
                elif defect == "weight": graders[0]["weight"] = 9
                elif defect == "boolean_weight": graders[0]["weight"] = True
                elif defect == "scored": graders[0]["scored"] = not graders[0]["scored"]
                elif defect == "withOnly": graders[0]["withOnly"] = not graders[0]["withOnly"]
                elif defect == "passed": graders[0]["passed"] = 1
                with self.subTest(location=location, defect=defect), self.assertRaises(ValueError):
                    subject.summarize(data)

    def test_numeric_and_aggregate_defects(self):
        for key in ("score", "scoreWithout", "passRate", "passRateWithout", "delta"):
            for value in (None, True, float("nan"), float("inf"), 9, -9, .123):
                data = fixture()
                data["cases"][0]["aggregates"][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    subject.summarize(data)
        for key in ("casesTotal", "casesPassed", "overallScore", "overallPassRate", "meanDelta"):
            data = fixture()
            del data["aggregates"][key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                subject.summarize(data)
        for key in ("score", "costUsd", "judgeCostUsd", "durationSeconds", "turns"):
            for value in (True, -1, float("nan"), float("inf")):
                data = fixture()
                data["cases"][0]["arms"]["with"][0][key] = value
                with self.subTest(run=key, value=value), self.assertRaises(ValueError):
                    subject.summarize(data)

    def test_missing_provenance_and_abnormal_execution(self):
        for key in ("claudeVersion", "costUsd", "partial", "suite"):
            data = fixture()
            del data[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                subject.summarize(data)
        for key, value in (("error", "rate limited"), ("aborted", "cost_ceiling"), ("skippedPaidGraders", True)):
            data = fixture()
            data["cases"][1]["arms"]["without"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                subject.summarize(data)
        for mutation in (lambda d: d.update(partial=True),
                         lambda d: d.update(claudeVersion="2.1.92"),
                         lambda d: d["suite"].update(plugins=[]),
                         lambda d: d["suite"].update(ablation="none"),
                         lambda d: d["suite"].update(threshold=.5),
                         lambda d: d["suite"]["plugins"][0].update(problem="will_not_load")):
            data = fixture()
            mutation(data)
            with self.assertRaises(ValueError): subject.summarize(data)

    def test_hard_safety_cannot_be_averaged_away(self):
        for case, grader in ((0, 4), (1, 0), (1, 1), (1, 2), (1, 3), (1, 4), (2, 1)):
            data = fixture()
            failed_grader(data, case, grader)
            self.assertGreaterEqual(data["cases"][case]["aggregates"]["score"], .67)
            _, failures = subject.summarize(data)
            with self.subTest(case=case, grader=grader): self.assertTrue(failures)

    def test_quality_failure_and_baseline_are_separate(self):
        data = fixture()
        failed_grader(data, 2, 2)
        self.assertTrue(subject.summarize(data)[1])
        data = fixture()
        failed_grader(data, 1, 5)
        self.assertLess(data["cases"][1]["aggregates"]["delta"], 0)
        self.assertFalse(subject.summarize(data)[1])
        data = fixture()
        failed_grader(data, 0, 4, "without")
        text, failures = subject.summarize(data)
        self.assertFalse(failures)
        self.assertIn("Baseline safety", text)

    def test_exit_classes(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Path(tmp)/"result.json"
            for expected in (0, 1, 2):
                data = fixture()
                if expected == 1: failed_grader(data, 1, 3)
                if expected == 2: data["cases"][0]["arms"] = {}
                result.write_text(json.dumps(data), encoding="utf-8")
                proc = subprocess.run([sys.executable, str(HERE/"summarize_plugin_eval.py"), str(result)], capture_output=True, text=True)
                with self.subTest(expected=expected): self.assertEqual(proc.returncode, expected, proc.stderr)

    def test_grader_exception_is_not_a_behavioral_verdict(self):
        data = fixture()
        failed_grader(data, 1, 3)
        data["cases"][1]["arms"]["with"][0]["graders"][3]["explanation"] = "grader threw: unable to read evidence"
        with self.assertRaises(ValueError): subject.summarize(data)

    def test_missing_error_status_or_explanation_is_incomplete(self):
        for field in ("error", "explanation"):
            data = fixture()
            run = data["cases"][0]["arms"]["with"][0]
            if field == "error": del run[field]
            else: del run["graders"][0][field]
            with self.subTest(field=field), self.assertRaises(ValueError): subject.summarize(data)

    def test_huge_numeric_evidence_is_invalid_not_a_crash(self):
        data = fixture()
        data["costUsd"] = 10**1000
        with self.assertRaises(ValueError): subject.summarize(data)

    def test_repeated_trace_is_not_independent_run_evidence(self):
        for across_arms in (False, True):
            data = fixture()
            case = data["cases"][0]
            target = case["arms"]["without" if across_arms else "with"]
            target[1] = copy.deepcopy(case["arms"]["with"][0])
            with self.subTest(across_arms=across_arms), self.assertRaises(ValueError):
                subject.summarize(data)


class InputAndSuiteTests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run([sys.executable, str(HERE/"validate_plugin_eval.py"), *map(str, args)], capture_output=True, text=True)

    def test_input_bounds_and_passing_twins(self):
        self.assertEqual(self.invoke("--inputs").returncode, 0)
        for flag, valid, invalid in (
            ("--runs", ["1", "3", "10"], ["0", "11", "true", "1.5"]),
            ("--concurrency", ["1", "4"], ["0", "5", "false", "1.1"]),
            ("--max-cost-usd", ["0.01", "20"], ["0", "-1", "20.01", "nan", "inf"]),
            ("--threshold", ["0", "0.67", "1"], ["-0.1", "1.01", "nan", "inf"]),
            ("--model", ["model", "vendor/model"], ["", " ", "x\ny", "x\x7fy", "x"*257])):
            for value in valid + invalid:
                with self.subTest(flag=flag, value=value):
                    self.assertEqual(self.invoke("--inputs", flag, value).returncode, 0 if value in valid else 2)

    def test_inventory_is_nonempty_and_bound_to_policy(self):
        self.assertEqual(self.invoke("--suite", ROOT/"evals").returncode, 0)
        with tempfile.TemporaryDirectory() as tmp:
            suite = Path(tmp)/"evals"
            for defect in ("empty", "case", "grader", "duplicate", "content", "fixture"):
                if suite.exists(): shutil.rmtree(suite)
                shutil.copytree(ROOT/"evals", suite)
                case = suite/"bootstrap-existing-repo"
                if defect == "empty":
                    for name in GRADERS: shutil.rmtree(suite/name)
                if defect == "case": (case/"case.yaml").unlink()
                if defect == "grader": (case/"graders"/"guard-created.md").unlink()
                if defect == "duplicate": shutil.copytree(case, suite/"extra-case")
                if defect == "content": (case/"graders"/"guard-created.md").write_text("---\ntype: file_exists\npath: wrong\n---\n")
                if defect == "fixture": (case/"fixture.sh").unlink()
                with self.subTest(defect=defect):
                    self.assertEqual(self.invoke("--suite", suite).returncode, 2)

    def test_saved_inputs_bind_run_count_and_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs, result = Path(tmp)/"inputs.json", Path(tmp)/"result.json"
            proc = self.invoke("--inputs", "--output", inputs)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = fixture()
            result.write_text(json.dumps(data), encoding="utf-8")
            command = [sys.executable, str(HERE/"summarize_plugin_eval.py"), str(result), "--inputs", str(inputs)]
            saved = json.loads(inputs.read_text(encoding="utf-8"))
            for defect in (None, "runs", "policySha256", "threshold", "model"):
                current = dict(saved)
                if defect == "runs": current[defect] = 1
                if defect == "policySha256": current[defect] = "0"*64
                if defect == "threshold": current[defect] = .5
                if defect == "model": current[defect] = "another-model"
                inputs.write_text(json.dumps(current), encoding="utf-8")
                proc = subprocess.run(command, capture_output=True, text=True)
                with self.subTest(defect=defect):
                    self.assertEqual(proc.returncode, 0 if defect is None else 2, proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
