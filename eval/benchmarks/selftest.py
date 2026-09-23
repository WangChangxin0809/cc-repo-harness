#!/usr/bin/env python3
"""Defect-based tests for benchmark evidence; no model or network calls."""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))


def small_fixture():
    return {'cases': [
        {'id': 'positive', 'expected_ids': ['accepted'], 'expected_code': 0,
         'budget_bytes': 100, 'required_excluded': [], 'required_text': ['safe']},
        {'id': 'negative', 'expected_ids': [], 'expected_code': 0,
         'budget_bytes': 100, 'required_excluded': ['retired']}],
        'forbidden_markers': ['FORBIDDEN_BODY'],
        'records': [{'id': 'accepted', 'title': 'safe title', 'body': ['safe']}]}


def samples():
    result = [
        {'id': 'positive', 'samples': [{'seconds': 0.25, 'phase': 'cold',
         'actual_ids': ['accepted'], 'text': '[accepted] safe', 'used_bytes': 15,
         'records': [{'id': 'accepted', 'title': 'safe title', 'summary': 'safe title',
                      'body': ['safe']}], 'code': 0, 'excluded_ids': []}]},
        {'id': 'negative', 'samples': [{'seconds': 0.50, 'phase': 'warm',
         'actual_ids': [], 'text': '', 'used_bytes': 0,
         'records': [], 'code': 0, 'excluded_ids': ['retired']}]}]
    for case in result:
        case['samples'][0]['receipt'] = {
            'head': 'a' * 40, 'accepted_ref': 'refs/heads/main',
            'accepted_ancestor': 'b' * 40, 'accepted_tip': 'c' * 40,
            'revocation_watermark': 'c' * 40, 'policy_digest': 'd' * 64}
    return result


def complete_report():
    fixture_hash = hashlib.sha256(json.dumps(small_fixture(), sort_keys=True,
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    return {'schema_version': 1, 'status': 'passed', 'code': 0,
        'contract': {'benchmark': 'memory-recall-v1', 'fixture_sha256': fixture_hash,
            'harness_sha256': 'a' * 64, 'case_ids': ['positive', 'negative'],
            'repeats': 1, 'measurement': 'recall-new-repository-v1'},
        'implementation': {'commit': 'b' * 40, 'dirty': False, 'runtime_sha256': 'c' * 64,
                           'root': '/fixture/implementation'},
        'environment': {'python': '3.12.1', 'platform': 'fixture-os', 'machine': 'fixture-cpu',
                        'node': 'same-runner', 'git': 'git version fixture'},
        'cases': samples(),
        'quality': {'case_count': 2, 'sample_count': 2, 'expected_matches': 1,
                    'true_positive': 1, 'false_positive': 0, 'false_negative': 0,
                    'precision': 1.0, 'recall': 1.0, 'empty_cases': 1,
                    'dangerous_leaks': 0, 'byte_violations': 0, 'code_mismatches': 0,
                    'exclusion_misses': 0, 'rendered_misses': 0, 'passed_cases': 2, 'failed_cases': 0}}


class ScorerTests(unittest.TestCase):
    def setUp(self):
        try:
            self.protocol = importlib.import_module('protocol')
        except ImportError:
            self.fail('benchmark evidence scorer is not implemented')

    def score(self, value=None, fixture=None):
        return self.protocol.score_cases(value if value is not None else samples(),
                                         fixture or small_fixture(), repeats=1)

    def test_complete_positive_and_empty_negative_pass_without_inflating_recall(self):
        result = self.score()
        self.assertEqual(result['code'], 0)
        self.assertEqual(result['quality']['true_positive'], 1)
        self.assertEqual(result['quality']['expected_matches'], 1)
        self.assertEqual(result['quality']['recall'], 1.0)
        self.assertEqual(result['quality']['empty_cases'], 1)

    def test_unexpected_record_is_quality_failure(self):
        value = samples()
        value[1]['samples'][0].update(actual_ids=['retired'], records=[{'id': 'retired'}])
        result = self.score(value)
        self.assertEqual(result['code'], 1)
        self.assertEqual(result['quality']['false_positive'], 1)

    def test_leak_in_text_or_structured_body_cannot_hide_behind_correct_ids(self):
        for field in ('text', 'records'):
            value = samples()
            if field == 'text':
                value[1]['samples'][0].update(text='FORBIDDEN_BODY', used_bytes=14)
            else:
                value[0]['samples'][0]['records'][0]['body'] = ['FORBIDDEN_BODY']
            with self.subTest(field=field):
                self.assertEqual(self.score(value)['code'], 1)

    def test_missing_case_cannot_pass(self):
        self.assertEqual(self.score(samples()[:1])['code'], 2)

    def test_duplicate_case_or_record_ids_cannot_pass(self):
        value = samples()
        value.append(copy.deepcopy(value[0]))
        self.assertEqual(self.score(value)['code'], 2)
        value = samples()
        value[0]['samples'][0]['actual_ids'].append('accepted')
        value[0]['samples'][0]['records'].append({'id': 'accepted'})
        self.assertEqual(self.score(value)['code'], 2)

    def test_missing_sample_or_nonfinite_boolean_timing_cannot_pass(self):
        value = samples()
        value[0]['samples'] = []
        self.assertEqual(self.score(value)['code'], 2)
        for invalid in (float('nan'), float('inf'), True, -1):
            value = samples()
            value[0]['samples'][0]['seconds'] = invalid
            self.assertEqual(self.score(value)['code'], 2)

    def test_utf8_budget_and_missing_exclusion_are_quality_failures(self):
        value = samples()
        value[0]['samples'][0].update(text='界' * 40, used_bytes=120)
        self.assertEqual(self.score(value)['code'], 1)
        value = samples()
        value[1]['samples'][0]['excluded_ids'] = []
        self.assertEqual(self.score(value)['code'], 1)

    def test_expected_unjudged_runtime_case_is_judged_behavior(self):
        fixture, value = small_fixture(), samples()
        fixture['cases'][1]['expected_code'] = 2
        value[1]['samples'][0]['code'] = 2
        self.assertEqual(self.score(value, fixture)['code'], 0)
        value[1]['samples'][0]['code'] = 0
        self.assertEqual(self.score(value, fixture)['code'], 1)

    def test_comparable_complete_reports_pass_and_timing_change_does_not_fail(self):
        base, head = complete_report(), complete_report()
        head['implementation']['commit'] = 'd' * 40
        head['cases'][0]['samples'][0]['seconds'] = 25.0
        result = self.protocol.compare_reports(base, head, small_fixture())
        self.assertEqual(result['code'], 0)
        self.assertIn('100.000', result['markdown'])

    def test_incompatible_fingerprints_environment_or_sample_count_are_unjudged(self):
        for field in ('fixture_sha256', 'harness_sha256', 'measurement', 'repeats'):
            base, head = complete_report(), complete_report()
            head['contract'][field] = (2 if field == 'repeats' else
                                       'e' * 64 if field.endswith('sha256') else 'changed')
            self.assertEqual(self.protocol.compare_reports(base, head, small_fixture())['code'], 2)
        base, head = complete_report(), complete_report()
        head['environment']['node'] = 'other-machine'
        self.assertEqual(self.protocol.compare_reports(base, head, small_fixture())['code'], 2)

    def test_fabricated_nan_boolean_or_inconsistent_scores_are_unjudged(self):
        for invalid in (float('nan'), True, 0.5):
            base, head = complete_report(), complete_report()
            head['quality']['recall'] = invalid
            self.assertEqual(self.protocol.compare_reports(base, head, small_fixture())['code'], 2)

    def test_malformed_environment_container_is_classified_not_a_traceback(self):
        base, head = complete_report(), complete_report()
        head['environment'] = list(head['environment'])
        try:
            result = self.protocol.compare_reports(base, head, small_fixture())
        except Exception as exc:
            self.fail('malformed evidence escaped classification: ' + type(exc).__name__)
        self.assertEqual(result['code'], 2)

    def test_comparator_rejects_missing_samples_and_forged_success(self):
        base, head = complete_report(), complete_report()
        head['cases'][0]['samples'] = []
        self.assertEqual(self.protocol.compare_reports(base, head, small_fixture())['code'], 2)
        head = complete_report()
        head['cases'][1]['samples'][0].update(actual_ids=['retired'], records=[{'id': 'retired'}])
        self.assertEqual(self.protocol.compare_reports(base, head, small_fixture())['code'], 2)

    def test_matching_ids_with_missing_rendered_text_are_quality_failures(self):
        for text in ('', '[accepted] wrong body', 'safe with no source identity'):
            value = samples()
            value[0]['samples'][0].update(text=text, used_bytes=len(text.encode()))
            with self.subTest(text=text):
                self.assertEqual(self.score(value)['code'], 1)

    def test_empty_selection_cannot_deliver_unattributed_text(self):
        value = samples()
        text = 'unexpected secret content'
        value[1]['samples'][0].update(text=text, used_bytes=len(text.encode()))
        self.assertEqual(self.score(value)['code'], 1)

    def test_structured_content_must_match_the_manually_defined_gold(self):
        for field in ('title', 'summary', 'body'):
            value = samples()
            value[0]['samples'][0]['records'][0][field] = ['wrong decision'] if field == 'body' else 'wrong decision'
            self.assertEqual(self.score(value)['code'], 1)

    def test_missing_or_malformed_receipt_is_unjudged(self):
        for receipt in ({}, {'head': 'not-an-oid'}, None):
            value = samples()
            value[0]['samples'][0]['receipt'] = receipt
            self.assertEqual(self.score(value)['code'], 2)

    def test_changed_phase_or_fabricated_median_is_unjudged(self):
        value = samples()
        value[0]['samples'][0]['phase'] = 'warm'
        self.assertEqual(self.score(value)['code'], 2)
        value = samples()
        value[0]['median_seconds'] = 0.001
        self.assertEqual(self.score(value)['code'], 2)

    def test_relabelled_expectations_cannot_disguise_the_gold_contract(self):
        value = samples()
        value[0]['expected_ids'] = ['other']
        self.assertEqual(self.score(value)['code'], 2)


class CommandTests(unittest.TestCase):
    def test_missing_implementation_is_unjudged_with_an_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'result.json'
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('memory.py')),
                '--implementation-root', str(root), '--output', str(output), '--repeats', '1'],
                capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 2)
            self.assertTrue(output.is_file(), result.stderr)
            self.assertEqual(json.loads(output.read_text())['status'], 'unjudged')

    def test_missing_comparison_input_is_unjudged_and_writes_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'summary.md'
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('compare.py')),
                str(output.with_name('absent-base.json')), str(output.with_name('absent-head.json')),
                '--summary', str(output)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertTrue(output.is_file(), result.stderr)
            self.assertIn('Could not judge', output.read_text())


class LiveRunnerTests(unittest.TestCase):
    def check_real_git_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'result.json'
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('memory.py')),
                '--implementation-root', str(Path(__file__).resolve().parents[2]),
                '--output', str(output), '--repeats', '1'], capture_output=True,
                text=True, encoding='utf-8', timeout=300)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(report['quality']['case_count'], 12)
            self.assertEqual(report['quality']['dangerous_leaks'], 0)
            self.assertEqual(report['quality']['expected_matches'], 3)


if __name__ == '__main__':
    integration = '--integration' in sys.argv
    if integration:
        sys.argv.remove('--integration')
    suite = unittest.TestSuite([
        unittest.defaultTestLoader.loadTestsFromTestCase(ScorerTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(CommandTests)])
    if integration:
        suite.addTest(LiveRunnerTests('check_real_git_runner'))
    sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
