#!/usr/bin/env python3
"""Exercise release authorization against fixed API-shaped evidence, offline."""
import copy
import os
from pathlib import Path
import subprocess
import sys
import unittest

import release_evidence as evidence

REPO = "owner/project"
SHA = "a" * 40


def run(workflow="ci.yml", **changes):
    result = {"id": 30, "run_attempt": 1, "event": "push",
              "head_branch": "main", "head_sha": SHA,
              "head_repository": {"full_name": REPO},
              "path": ".github/workflows/" + workflow,
              "status": "completed", "conclusion": "success"}
    result.update(changes)
    return result


class ReleaseTests(unittest.TestCase):
    def judge(self, runs):
        return evidence.judge({"workflow_runs": runs}, REPO, SHA, "ci.yml")[0]

    def test_exact_success_and_pending_twins(self):
        self.assertEqual(self.judge([run()]), "success")
        self.assertEqual(self.judge([run(status="in_progress", conclusion=None)]),
                         "pending")
        self.assertEqual(self.judge([]), "pending")

    def test_terminal_failures_never_authorize_release(self):
        for conclusion in ("failure", "cancelled", "timed_out", "skipped", "neutral"):
            with self.subTest(conclusion=conclusion):
                self.assertEqual(self.judge([run(conclusion=conclusion)]), "failure")

    def test_wrong_identity_is_not_success(self):
        for change in ({"head_sha": "b" * 40}, {"head_branch": "feature"},
                       {"event": "pull_request"}, {"event": "workflow_dispatch"},
                       {"head_repository": {"full_name": "other/project"}},
                       {"path": ".github/workflows/unrelated.yml"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.judge([run(**change)])

    def test_newer_failed_run_overrides_older_success(self):
        self.assertEqual(self.judge([run(id=10), run(id=20, conclusion="failure")]),
                         "failure")
        self.assertEqual(self.judge([run(id=20), run(id=10, conclusion="failure")]),
                         "success")

    def test_latest_attempt_overrides_prior_success(self):
        self.assertEqual(self.judge([run(), run(run_attempt=2, conclusion="failure")]),
                         "failure")
        self.assertEqual(self.judge([run(), run(run_attempt=2, status="queued",
                                               conclusion=None)]), "pending")

    def test_conflicting_duplicate_run_cannot_hide_failure(self):
        with self.assertRaises(ValueError):
            self.judge([run(), run(conclusion="failure")])

    def test_malformed_evidence_is_not_a_pass(self):
        for payload in (None, [], {}, {"workflow_runs": None},
                        {"workflow_runs": [{}]}, {"workflow_runs": [None]}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                evidence.judge(payload, REPO, SHA, "ci.yml")
        for key, value in (("id", True), ("id", 0), ("run_attempt", "1"),
                           ("status", None), ("status", "unknown"),
                           ("conclusion", None), ("conclusion", "made-up")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.judge([run(**{key: value})])

    def test_waits_for_both_workflows_not_just_ci(self):
        ticks, calls = [0.0], []

        def fetch(repo, workflow, sha):
            self.assertEqual((repo, sha), (REPO, SHA))
            calls.append(workflow)
            rows = [] if workflow == "postmerge-ci.yml" and ticks[0] == 0 else [run(workflow)]
            return {"workflow_runs": rows}

        def sleep(seconds):
            ticks[0] += seconds

        code = evidence.verify(REPO, "refs/heads/main", SHA, fetch=fetch,
                               wait_seconds=2, poll_seconds=1,
                               clock=lambda: ticks[0], sleep=sleep)
        self.assertEqual(code, 0)
        self.assertEqual(ticks[0], 1)
        self.assertIn("postmerge-ci.yml", calls)

    def test_missing_or_pending_evidence_times_out(self):
        for rows in ([], [run(status="queued", conclusion=None)]):
            with self.subTest(rows=rows):
                self.assert_evidence_times_out(rows)

    def assert_evidence_times_out(self, rows):
        ticks = [0.0]

        def fetch(_repo, workflow, _sha):
            payload = copy.deepcopy(rows)
            for row in payload:
                row["path"] = ".github/workflows/" + workflow
            return {"workflow_runs": payload}

        def sleep(seconds):
            ticks[0] += seconds

        code = evidence.verify(REPO, "refs/heads/main", SHA, fetch=fetch,
                               wait_seconds=2, poll_seconds=1,
                               clock=lambda: ticks[0], sleep=sleep)
        self.assertEqual(code, 2)
        self.assertEqual(ticks[0], 2)

    def test_ci_failure_does_not_wait_for_deadline(self):
        def fetch(_repo, workflow, _sha):
            return {"workflow_runs": [run(workflow, conclusion="failure")]}

        def no_sleep(_seconds):
            self.fail("a completed failure must stop immediately")

        self.assertEqual(evidence.verify(REPO, "refs/heads/main", SHA,
                                         fetch=fetch, sleep=no_sleep), 1)

    def test_non_main_cli_refuses_before_network_access(self):
        env = dict(os.environ, GITHUB_REPOSITORY=REPO, GITHUB_SHA=SHA,
                   GITHUB_REF="refs/heads/feature", GH_TOKEN="")
        result = subprocess.run([sys.executable, str(Path(evidence.__file__))],
                                env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("refs/heads/main", result.stderr)

    def test_missing_identity_cli_is_unjudged(self):
        env = dict(os.environ, GITHUB_REPOSITORY=REPO, GITHUB_SHA="",
                   GITHUB_REF="refs/heads/main", GH_TOKEN="")
        result = subprocess.run([sys.executable, str(Path(evidence.__file__))],
                                env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("GITHUB_SHA", result.stderr)


if __name__ == "__main__":
    unittest.main()
