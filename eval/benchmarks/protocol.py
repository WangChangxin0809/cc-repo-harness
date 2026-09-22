"""Strict evidence and deterministic quality scoring for the offline benchmark."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import statistics

HERE = Path(__file__).resolve().parent
BENCHMARK = 'memory-recall-v1'
MEASUREMENT = 'recall-new-repository-v1'


class EvidenceError(ValueError):
    """The input cannot establish a complete, comparable measurement."""


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read_json(path):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise EvidenceError('duplicate JSON key: ' + key)
            value[key] = item
        return value
    def constant(value):
        raise EvidenceError('non-finite JSON number: ' + value)
    raw = Path(path).read_bytes()
    if len(raw) > 16 * 1024 * 1024:
        raise EvidenceError('result exceeds the 16 MiB evidence bound')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def fixture():
    return read_json(HERE / 'fixture.json')


def unique_strings(value, label):
    if not isinstance(value, list) or any(not isinstance(v, str) or not v for v in value):
        raise EvidenceError(label + ' must be a list of nonempty strings')
    if len(set(value)) != len(value):
        raise EvidenceError(label + ' contains duplicate IDs')
    return value


def number(value, label, minimum=0, maximum=None):
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        raise EvidenceError(label + ' must be a finite number, not a boolean')
    if maximum is not None and value > maximum:
        raise EvidenceError(label + ' exceeds its allowed maximum')
    return value


def _case_specs(gold):
    specs = gold['cases']
    if not isinstance(specs, list) or not specs or len(specs) > 1000:
        raise EvidenceError('fixture has no bounded case list')
    ids = unique_strings([c['id'] for c in specs], 'fixture cases')
    for case in specs:
        unique_strings(case['expected_ids'], 'expected IDs')
        unique_strings(case['required_excluded'], 'required exclusions')
        unique_strings(case.get('required_text', []), 'required rendered fragments')
        if type(case['expected_code']) is not int or case['expected_code'] not in (0, 1, 2):
            raise EvidenceError('fixture exit code must be 0, 1 or 2')
        if type(case['budget_bytes']) is not int or not 0 <= case['budget_bytes'] <= 1048576:
            raise EvidenceError('fixture byte budget is invalid')
    unique_strings(gold['forbidden_markers'], 'forbidden markers')
    return dict(zip(ids, specs))


def _receipt(value):
    if not isinstance(value, dict):
        raise EvidenceError('sample receipt is missing')
    for key in ('head', 'accepted_ancestor', 'accepted_tip', 'revocation_watermark'):
        if not isinstance(value.get(key), str) or not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', value[key]):
            raise EvidenceError('sample receipt lacks a valid ' + key)
    if value.get('accepted_ref') != 'refs/heads/main':
        raise EvidenceError('sample receipt does not identify the fixture authority')
    if not isinstance(value.get('policy_digest'), str) or not re.fullmatch('[0-9a-f]{64}', value['policy_digest']):
        raise EvidenceError('sample receipt lacks its policy digest')
    if value['accepted_tip'] != value['revocation_watermark']:
        raise EvidenceError('sample authority and revocation watermark disagree')


def score_cases(cases, gold, repeats):
    """Return 1 for observed defects, 2 for incomplete/malformed evidence."""
    try:
        canonical(cases)  # Reject non-finite values anywhere in raw evidence.
        specs = _case_specs(gold)
        if type(repeats) is not int or not 1 <= repeats <= 30:
            raise EvidenceError('repeats must be an integer from 1 to 30')
        if not isinstance(cases, list):
            raise EvidenceError('result cases must be a list')
        ids = unique_strings([c['id'] for c in cases], 'result cases')
        if set(ids) != set(specs):
            raise EvidenceError('result case set differs from the fixed fixture')
        quality = {key: 0 for key in (
            'case_count', 'sample_count', 'expected_matches', 'true_positive',
            'false_positive', 'false_negative', 'empty_cases', 'dangerous_leaks',
            'byte_violations', 'code_mismatches', 'exclusion_misses', 'rendered_misses',
            'passed_cases', 'failed_cases')}
        findings = []
        record_gold = {record['id']: record for record in gold.get('records', [])}
        for case in cases:
            spec = specs[case['id']]
            for key in ('expected_ids', 'expected_code', 'budget_bytes'):
                if key in case and case[key] != spec[key]:
                    raise EvidenceError('reported expectations disagree with fixed gold: ' + case['id'])
            expected = set(spec['expected_ids'])
            values = case['samples']
            if not isinstance(values, list) or len(values) != repeats:
                raise EvidenceError('missing or extra samples: ' + case['id'])
            quality['case_count'] += 1
            quality['empty_cases'] += int(not expected)
            case_failed = False
            for index, sample in enumerate(values):
                number(sample['seconds'], 'sample seconds', minimum=0.000000001)
                if sample['phase'] not in ('cold', 'warm'):
                    raise EvidenceError('sample phase is not cold or warm')
                if sample['phase'] != ('cold' if case['id'] == next(iter(specs)) and index == 0 else 'warm'):
                    raise EvidenceError('sample phase differs from the defined execution order')
                _receipt(sample.get('receipt'))
                actual = set(unique_strings(sample['actual_ids'], 'actual IDs'))
                records = sample['records']
                if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
                    raise EvidenceError('records must be objects')
                record_ids = unique_strings([r['id'] for r in records], 'structured record IDs')
                if set(record_ids) != actual:
                    raise EvidenceError('structured records and actual IDs disagree')
                excluded = set(unique_strings(sample['excluded_ids'], 'excluded IDs'))
                if type(sample['code']) is not int or sample['code'] not in (0, 1, 2):
                    raise EvidenceError('runtime exit code must be 0, 1 or 2')
                text = sample['text']
                if not isinstance(text, str) or type(sample['used_bytes']) is not int:
                    raise EvidenceError('rendered text/byte count is missing or invalid')
                actual_bytes = len(text.encode('utf-8'))
                if sample['used_bytes'] != actual_bytes:
                    raise EvidenceError('claimed UTF-8 byte count disagrees with text')
                quality['sample_count'] += 1
                quality['expected_matches'] += len(expected)
                quality['true_positive'] += len(expected & actual)
                quality['false_positive'] += len(actual - expected)
                quality['false_negative'] += len(expected - actual)
                surface = text + '\n' + canonical(records).decode('utf-8')
                leaks = [marker for marker in gold['forbidden_markers'] if marker in surface]
                missing_exclusions = sorted(set(spec['required_excluded']) - excluded)
                fragments = ['[' + key + ']' for key in actual] + spec.get('required_text', [])
                rendered_misses = [part for part in fragments if part not in text]
                unattributed_text = bool(not actual and text)
                content_mismatches = []
                for delivered in records:
                    original = record_gold.get(delivered['id'])
                    if original is not None and any(delivered.get(key) != wanted for key, wanted in (
                            ('title', original['title']), ('summary', original['title']), ('body', original['body']))):
                        content_mismatches.append(delivered['id'])
                violations = {
                    'unexpected_ids': sorted(actual - expected),
                    'missing_ids': sorted(expected - actual),
                    'dangerous_markers': leaks,
                    'byte_budget_exceeded': actual_bytes > spec['budget_bytes'],
                    'wrong_exit_code': sample['code'] != spec['expected_code'],
                    'missing_exclusions': missing_exclusions,
                    'missing_rendered_fragments': rendered_misses,
                    'unattributed_text': unattributed_text,
                    'record_content_mismatches': content_mismatches}
                quality['dangerous_leaks'] += len(leaks)
                quality['byte_violations'] += int(violations['byte_budget_exceeded'])
                quality['code_mismatches'] += int(violations['wrong_exit_code'])
                quality['exclusion_misses'] += len(missing_exclusions)
                quality['rendered_misses'] += len(rendered_misses) + int(unattributed_text) + len(content_mismatches)
                if any(violations.values()):
                    findings.append({'case': case['id'], 'sample': index + 1, **violations})
                    case_failed = True
            if 'median_seconds' in case:
                number(case['median_seconds'], 'median seconds', minimum=0.000000001)
                if case['median_seconds'] != statistics.median(s['seconds'] for s in values):
                    raise EvidenceError('reported median differs from raw samples')
            quality['failed_cases' if case_failed else 'passed_cases'] += 1
        denominator = quality['true_positive'] + quality['false_positive']
        quality['precision'] = quality['true_positive'] / denominator if denominator else None
        denominator = quality['expected_matches']
        quality['recall'] = quality['true_positive'] / denominator if denominator else None
        return {'code': 1 if findings else 0, 'status': 'failed' if findings else 'passed',
                'quality': quality, 'findings': findings}
    except (EvidenceError, KeyError, TypeError, ValueError, UnicodeError) as exc:
        return {'code': 2, 'status': 'unjudged', 'message': str(exc)}


def validate_report(report, gold=None):
    gold = fixture() if gold is None else gold
    if not isinstance(report, dict) or type(report.get('schema_version')) is not int or report['schema_version'] != 1:
        raise EvidenceError('unsupported benchmark result schema')
    contract = report['contract']
    if contract['benchmark'] != BENCHMARK or contract['measurement'] != MEASUREMENT:
        raise EvidenceError('unsupported benchmark or measurement protocol')
    for name in ('fixture_sha256', 'harness_sha256'):
        if not isinstance(contract[name], str) or not re.fullmatch('[0-9a-f]{64}', contract[name]):
            raise EvidenceError('invalid ' + name)
    if contract['fixture_sha256'] != digest(gold):
        raise EvidenceError('fixture fingerprint differs from the comparator fixture')
    if contract['case_ids'] != list(_case_specs(gold)):
        raise EvidenceError('contract case IDs differ from the fixed fixture')
    implementation = report['implementation']
    if not isinstance(implementation['commit'], str) or not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', implementation['commit']):
        raise EvidenceError('implementation commit is missing')
    if type(implementation['dirty']) is not bool:
        raise EvidenceError('implementation dirty flag must be explicit')
    if not re.fullmatch('[0-9a-f]{64}', implementation['runtime_sha256']):
        raise EvidenceError('implementation runtime fingerprint is missing')
    if not isinstance(implementation['root'], str) or not implementation['root']:
        raise EvidenceError('implementation root is missing')
    environment = report['environment']
    if not isinstance(environment, dict) or set(environment) != {'python', 'platform', 'machine', 'node', 'git'}:
        raise EvidenceError('environment fingerprint is incomplete')
    if any(not isinstance(value, str) or not value for value in environment.values()):
        raise EvidenceError('environment values must be nonempty strings')
    scored = score_cases(report['cases'], gold, contract['repeats'])
    if scored['code'] == 2:
        raise EvidenceError(scored['message'])
    if type(report['code']) is not int or report['code'] != scored['code'] or report['status'] != scored['status']:
        raise EvidenceError('reported status differs from raw sample evidence')
    claimed = report['quality']
    if not isinstance(claimed, dict) or set(claimed) != set(scored['quality']):
        raise EvidenceError('quality summary fields are incomplete')
    for key, expected in scored['quality'].items():
        actual = claimed[key]
        if key in ('precision', 'recall'):
            if actual is not None:
                number(actual, key, maximum=1)
        elif type(actual) is not int or actual < 0:
            raise EvidenceError('invalid quality counter: ' + key)
        if actual != expected:
            raise EvidenceError('quality summary disagrees with raw samples: ' + key)
    return scored


def compare_reports(base, head, gold=None):
    try:
        before, after = validate_report(base, gold), validate_report(head, gold)
        if base['contract'] != head['contract']:
            raise EvidenceError('incompatible harness, fixture, cases or sample count')
        if base['environment'] != head['environment']:
            raise EvidenceError('environment differs; use the same runner and interpreter')
        lines = ['# Offline memory benchmark comparison', '',
                 'Synthetic engineering regression evidence; timing is reported, never gated.', '',
                 'Base: `%s` (runtime dirty: %s).' % (base['implementation']['commit'], base['implementation']['dirty']),
                 'Head: `%s` (runtime dirty: %s).' % (head['implementation']['commit'], head['implementation']['dirty']), '',
                 '| Case / phase | Base median (s) | Head median (s) | Head/base |',
                 '|---|---:|---:|---:|']
        base_cases = {case['id']: case for case in base['cases']}
        for case in head['cases']:
            for phase in ('cold', 'warm'):
                values = [s['seconds'] for s in case['samples'] if s['phase'] == phase]
                if not values:
                    continue
                old = statistics.median(s['seconds'] for s in base_cases[case['id']]['samples'] if s['phase'] == phase)
                new = statistics.median(values)
                lines.append('| %s / %s | %.6f | %.6f | %.3fx |' % (case['id'], phase, old, new, new / old))
        lines.extend(['', 'Quality: base **%s**, head **%s**.' % (before['status'], after['status']),
                      'Dangerous marker leaks: base **%s**, head **%s**.' % (
                          before['quality']['dangerous_leaks'], after['quality']['dangerous_leaks']),
                      'Fixture: `%s`.' % head['contract']['fixture_sha256'],
                      'Harness: `%s`.' % head['contract']['harness_sha256'],
                      'Cold denotes the first fixture recall; all subsequent samples are warm.'])
        return {'code': max(before['code'], after['code']), 'markdown': '\n'.join(lines) + '\n'}
    except (EvidenceError, KeyError, TypeError, ValueError) as exc:
        return {'code': 2, 'markdown': '# Offline memory benchmark comparison\n\nCould not judge: %s\n' % exc}
