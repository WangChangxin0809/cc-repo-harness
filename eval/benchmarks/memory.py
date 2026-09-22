#!/usr/bin/env python3
"""Measure fixed memory recall cases against a separately imported implementation."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time

from protocol import (BENCHMARK, HERE, MEASUREMENT, EvidenceError, canonical,
                      digest, fixture, score_cases, validate_report)


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                            timeout=30, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0',
                                             'GIT_OPTIONAL_LOCKS': '0'})
    if result.returncode:
        raise EvidenceError('Git could not judge: ' + result.stderr.decode('utf-8', 'replace')[:1000])
    return result.stdout.decode('utf-8').strip()


def files_digest(directory, names):
    value = hashlib.sha256()
    for name in sorted(names):
        value.update(name.encode('utf-8') + b'\0' + (directory / name).read_bytes() + b'\0')
    return value.hexdigest()


def harness_digest():
    return files_digest(HERE, ('memory.py', 'protocol.py', 'compare.py'))


def implementation_metadata(root):
    root = root.resolve()
    if Path(git(root, 'rev-parse', '--show-toplevel')).resolve() != root:
        raise EvidenceError('--implementation-root must identify the repository root')
    directory = root / 'shared/scripts/memory'
    required = ('__init__.py', 'repository.py', 'retrieve.py', 'store.py')
    if any(not (directory / name).is_file() for name in required):
        raise EvidenceError('implementation is missing the memory runtime')
    files = [p.name for p in directory.glob('*.py') if not p.name.startswith('test_') and p.name != 'selftest.py']
    return {'root': str(root), 'commit': git(root, 'rev-parse', 'HEAD'),
            'dirty': bool(git(root, 'status', '--porcelain', '--untracked-files=all', '--', 'shared/scripts/memory')),
            'runtime_sha256': files_digest(directory, files)}


def record(spec, gold):
    value = {'schema_version': 1, 'id': spec['id'], 'kind': 'decision',
             'title': spec['title'], 'summary': spec['title'], 'body': spec['body'],
             'scope': {'repository': gold['repository_id'], 'paths': spec['paths'],
                       'tags': [], 'environment': spec.get('environment', {})},
             'evidence': [{'type': 'decision', 'reason': 'Manually specified benchmark gold decision'}],
             'freshness': {'dependencies': []}, 'state': 'active'}
    if spec.get('source_dependency'):
        value['freshness']['dependencies'].append({
            'path': gold['source']['path'],
            'content_digest': hashlib.sha256(gold['source']['original'].encode()).hexdigest()})
    return value


def write(root, path, data):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data if isinstance(data, bytes) else canonical(data))


def commit(root, message):
    git(root, 'add', '.')
    git(root, 'commit', '--no-gpg-sign', '-m', message)
    return git(root, 'rev-parse', 'HEAD')


def build_fixture(root, gold, repository, store):
    git(root, 'init', '--template=', '-b', 'main')
    for key, value in (('user.email', 'benchmark@example.invalid'), ('user.name', 'Offline benchmark'),
                       ('core.autocrlf', 'false'), ('core.fsmonitor', 'false'), ('commit.gpgsign', 'false')):
        git(root, 'config', key, value)
    write(root, '.harness/memory/config.json', {'schema_version': 1,
        'repository_id': gold['repository_id'], 'accepted_ref': 'refs/heads/main',
        'review': {'mode': 'git-review'}})
    write(root, gold['source']['path'], gold['source']['original'].encode())
    records = {spec['id']: record(spec, gold) for spec in gold['records']}
    for key, value in records.items():
        write(root, '.harness/memory/records/' + key + '.json', value)
    accepted = commit(root, 'accept manually specified benchmark records')
    repo = repository(root)
    repo.initialize('refs/heads/main')
    retired = {'schema_version': 1, 'id': gold['retire_id'], 'state': 'retired',
               'retirement': {'previous_record_hash': digest(records[gold['retire_id']]),
                              'reason': 'Benchmark withdrawal is explicitly accepted'}}
    write(root, '.harness/memory/records/' + gold['retire_id'] + '.json', retired)
    commit(root, 'accept withdrawal')
    # The checkout predates the tombstone; the adopted main ref still sees it.
    git(root, 'checkout', '-b', 'benchmark-topic', accepted)
    draft = record(gold['branch_record'], gold)
    write(root, '.harness/memory/records/' + draft['id'] + '.json', draft)
    commit(root, 'unaccepted branch draft')
    dirty = copy.deepcopy(records[gold['dirty_id']])
    dirty['body'][0] += ' locally altered without review'
    write(root, '.harness/memory/records/' + gold['dirty_id'] + '.json', dirty)
    write(root, gold['source']['path'], gold['source']['changed'].encode())
    store(repo, 'benchmark-private').remember(record(gold['private_record'], gold),
                                            processing_id='fixed-private-discovery')


def worker(root, repeats):
    # Isolate each implementation in its own interpreter. Never import current
    # runtime modules and then try to substitute a baseline in sys.modules.
    runtime_path = root / 'shared/scripts'
    sys.path.insert(0, str(runtime_path))
    from memory.repository import Repository
    from memory.retrieve import recall
    from memory.store import MemoryStore
    import memory.repository as imported_repository
    if not Path(imported_repository.__file__).resolve().is_relative_to(runtime_path.resolve()):
        raise EvidenceError('runtime import escaped the requested implementation')
    gold = fixture()
    before = implementation_metadata(root)
    harness = harness_digest()
    report = {'schema_version': 1,
        'contract': {'benchmark': BENCHMARK, 'fixture_sha256': digest(gold),
                     'harness_sha256': harness, 'case_ids': [case['id'] for case in gold['cases']],
                     'repeats': repeats, 'measurement': MEASUREMENT},
        'implementation': before,
        'environment': {'python': sys.version, 'platform': platform.platform(),
                        'machine': platform.machine(), 'node': platform.node(),
                        'git': git(root, '--version')}, 'cases': []}
    # Prevent user-global Git hooks, signing and line-ending settings from
    # changing the generated history. No external repository is contacted.
    fixture_environment = {'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
                           'GIT_AUTHOR_DATE': '2000-01-01T00:00:00+00:00',
                           'GIT_COMMITTER_DATE': '2000-01-01T00:00:00+00:00'}
    previous_environment = {key: os.environ.get(key) for key in fixture_environment}
    os.environ.update(fixture_environment)
    with tempfile.TemporaryDirectory(prefix='harness-memory-benchmark-') as directory:
        project = Path(directory) / 'project with spaces'
        project.mkdir()
        build_fixture(project, gold, Repository, MemoryStore)
        first = True
        for case in gold['cases']:
            row = {'id': case['id'], 'expected_ids': case['expected_ids'],
                   'expected_code': case['expected_code'], 'budget_bytes': case['budget_bytes'],
                   'samples': []}
            for _ in range(repeats):
                started = time.perf_counter()
                try:
                    result = recall(Repository(project), query=case['query'], paths=case['paths'],
                                    environment=case['environment'], budget=case['budget_bytes'])
                    seconds = time.perf_counter() - started
                    records = result['records']
                    row['samples'].append({'seconds': seconds, 'phase': 'cold' if first else 'warm',
                        'actual_ids': [r['id'] for r in records], 'records': records,
                        'text': result['text'], 'used_bytes': result['used_bytes'], 'code': result['code'],
                        'excluded_ids': sorted({item['id'] for item in result.get('excluded', []) if 'id' in item}),
                        'receipt': result.get('receipt', {}), 'status': result['status']})
                except Exception as exc:
                    # Imported historical runtimes may fail in ways this harness
                    # cannot anticipate. Preserve the failed case as unjudged.
                    row['error'] = type(exc).__name__ + ': ' + str(exc)
                    break
                finally:
                    first = False
            row['median_seconds'] = statistics.median(s['seconds'] for s in row['samples']) if row['samples'] else None
            report['cases'].append(row)
    for key, previous in previous_environment.items():
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous
    report.update(score_cases(report['cases'], gold, repeats))
    if before != implementation_metadata(root) or harness != harness_digest() or digest(gold) != digest(fixture()):
        report.update(code=2, status='unjudged', message='implementation, fixture or harness changed during measurement')
    if report['code'] != 2:
        validate_report(report, gold)
    return report


def save(path, value):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='wb', dir=str(path.parent), delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8') + b'\n')
    try:
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--implementation-root', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.worker and args.output is None:
        parser.error('--output is required')
    try:
        if not 1 <= args.repeats <= 30:
            raise EvidenceError('--repeats must be between 1 and 30')
        root = args.implementation_root.resolve()
        implementation_metadata(root)
        if args.worker:
            result = worker(root, args.repeats)
        else:
            completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker',
                '--implementation-root', str(root), '--repeats', str(args.repeats)],
                capture_output=True, timeout=min(1800, 180 * args.repeats + 60))
            if completed.returncode not in (0, 1, 2) or not completed.stdout:
                raise EvidenceError('benchmark worker failed: ' + completed.stderr.decode('utf-8', 'replace')[:2000])
            result = json.loads(completed.stdout)
            if result.get('code') != completed.returncode:
                raise EvidenceError('worker exit and result disagree')
    except Exception as exc:
        result = {'schema_version': 1, 'status': 'unjudged', 'code': 2,
                  'message': type(exc).__name__ + ': ' + str(exc)}
    if args.worker:
        sys.stdout.buffer.write(canonical(result) + b'\n')
    else:
        try:
            save(args.output, result)
        except OSError as exc:
            print('could not save benchmark evidence: ' + str(exc), file=sys.stderr)
            return 2
        print(json.dumps({key: value for key, value in result.items()
                          if key in ('status', 'code', 'quality', 'message')}, ensure_ascii=False))
    return result['code']


if __name__ == '__main__':
    sys.exit(main())
