"""Negative cases for the concurrency annex: no fabricated score or target execution."""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from concurrency import assess

class ConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="concurrency-annex-")
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)
        self.report = Path(self.tmp.name) / "evidence.json"
        self.payload = self.root / "scripts/room"
        self.payload.mkdir(parents=True)
        hashes = {}
        for name in ("store.py", "selftest.py"):
            body = b"raise RuntimeError('the assessor must never execute this')\n"
            (self.payload / name).write_bytes(body)
            hashes[name] = hashlib.sha256(body).hexdigest()
        self.data = {"schema": 1, "scope": "implementation-conformance-not-repository-readiness",
                     "tests": 4, "failed": 0, "skipped": 0, "exit_code": 0, "sha256": hashes}
        self.write_report()

    def tearDown(self):
        self.tmp.cleanup()

    def write_report(self):
        self.report.write_text(json.dumps(self.data), encoding="utf-8")

    def test_absence_is_not_a_defect_or_zero_score(self):
        result = assess(self.root)
        self.assertIsNone(result["score"])
        self.assertTrue(result["configuration"]["absence_is_not_a_defect"])
        self.assertEqual(result["implementation_conformance"]["status"], "not-measured")

    def test_code_matching_report_does_not_prove_host_or_tasks(self):
        result = assess(self.root, self.report)
        self.assertEqual(result["implementation_conformance"]["status"], "pass")
        for key in ("mcp_host_integration", "mandatory_write_exclusion",
                    "semantic_conflict_detection", "real_agent_task_outcomes"):
            self.assertEqual(result[key]["status"], "not-measured")

    def test_changed_code_invalidates_evidence(self):
        (self.payload / "store.py").write_text("changed", encoding="utf-8")
        result = assess(self.root, self.report)
        self.assertEqual(result["implementation_conformance"]["status"], "stale-or-not-installed")

    def test_failure_is_not_green(self):
        self.data.update(failed=1, exit_code=1)
        self.write_report()
        self.assertEqual(assess(self.root, self.report)["implementation_conformance"]["status"], "failed")

    def test_skip_is_not_green(self):
        self.data.update(skipped=1, exit_code=2)
        self.write_report()
        self.assertEqual(assess(self.root, self.report)["implementation_conformance"]["status"], "could-not-judge")

    def test_false_green_report_is_rejected(self):
        self.data.update(failed=1, exit_code=0)
        self.write_report()
        with self.assertRaises(ValueError):
            assess(self.root, self.report)

    def test_invalid_report_is_not_a_pass(self):
        for value in ([], {}, {"schema": 1}):
            self.report.write_text(json.dumps(value), encoding="utf-8")
            with self.subTest(value=value), self.assertRaises(ValueError):
                assess(self.root, self.report)

    def test_room_declaration_is_not_host_validation(self):
        (self.root / ".mcp.json").write_text('{"mcpServers":{"room":{}}}', encoding="utf-8")
        result = assess(self.root)
        self.assertEqual(result["configuration"]["status"], "declared-not-executed")
        self.assertEqual(result["mcp_host_integration"]["status"], "not-measured")
        (self.root / ".mcp.json").write_text('{"mcpServers":{"room":[]}}', encoding="utf-8")
        with self.assertRaises(ValueError):
            assess(self.root)

    def test_malformed_config_is_not_absence(self):
        (self.root / ".mcp.json").write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError):
            assess(self.root)

if __name__ == "__main__":
    unittest.main(verbosity=2)
