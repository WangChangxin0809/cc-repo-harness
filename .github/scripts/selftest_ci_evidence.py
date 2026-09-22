#!/usr/bin/env python3
"""Regression tests for the terminal CI verdict; no GitHub access."""
import unittest

import check_ci_results as fanin


class FanInTests(unittest.TestCase):
    def setUp(self):
        self.env = dict.fromkeys(fanin.CONDITIONAL.values(), "false")
        self.needs = {name: {"result": "success"}
                      for name in (*fanin.ALWAYS, "release-hygiene")}
        self.needs.update({name: {"result": "skipped"}
                           for name in fanin.CONDITIONAL})

    def test_explicit_unselected_skips_pass(self):
        self.assertEqual(fanin.check(self.needs, "pull_request", self.env), [])

    def test_missing_or_invalid_selector_cannot_hide_skips(self):
        for value in (None, "", "TRUE", "yes", "0"):
            with self.subTest(value=value):
                env = dict(self.env)
                if value is None:
                    del env["RUN_PYTHON"]
                else:
                    env["RUN_PYTHON"] = value
                with self.assertRaises(ValueError):
                    fanin.check(self.needs, "pull_request", env)

    def test_nonselected_failure_or_cancellation_still_fails(self):
        for result in ("failure", "cancelled", "timed_out"):
            with self.subTest(result=result):
                needs = {**self.needs, "python-compat": {"result": result}}
                self.assertEqual(fanin.check(needs, "pull_request", self.env),
                                 [("python-compat", result)])

    def test_nonselected_lane_must_still_be_wired(self):
        del self.needs["python-compat"]
        with self.assertRaises(ValueError):
            fanin.check(self.needs, "pull_request", self.env)

    def test_malformed_unselected_result_is_not_a_skip(self):
        for item in ({}, {"result": None}, {"result": 0}):
            with self.subTest(item=item):
                with self.assertRaises(ValueError):
                    fanin.check({**self.needs, "python-compat": item},
                                "pull_request", self.env)

    def test_selected_skip_fails_and_success_passes(self):
        self.env["RUN_PYTHON"] = "true"
        self.assertEqual(fanin.check(self.needs, "pull_request", self.env),
                         [("python-compat", "skipped")])
        self.needs["python-compat"]["result"] = "success"
        self.assertEqual(fanin.check(self.needs, "pull_request", self.env), [])

    def test_unknown_event_cannot_skip_release_hygiene(self):
        with self.assertRaises(ValueError):
            fanin.check(self.needs, "", self.env)


if __name__ == "__main__":
    unittest.main()
