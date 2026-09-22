#!/usr/bin/env python3
"""Repository memory: private discoveries, reviewed Git knowledge, bounded recall."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory.errors import MemoryFailure
from memory.repository import Repository
from memory.schema import load_json


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', default='.')
    p.add_argument('--session', help='resume an explicit private session token')
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('init', 'install'):
        s = sub.add_parser(name)
        s.add_argument('--accepted-ref', required=True,
                       help='explicit trusted Git integration reference')
        if name == 'init':
            s.add_argument('--readopt', action='store_true',
                           help='explicitly replace an existing local trust decision')
    sub.add_parser('inspect')
    sub.add_parser('doctor')
    s = sub.add_parser('remember')
    s.add_argument('--record', help='strict record JSON file')
    s.add_argument('--title')
    s.add_argument('--body')
    s.add_argument('--reason')
    s.add_argument('--kind', default='constraint')
    s.add_argument('--path', action='append', default=[])
    s.add_argument('--processing-id')
    s = sub.add_parser('recall')
    s.add_argument('--query', default='')
    s.add_argument('--path', action='append', default=[])
    s.add_argument('--environment', help='JSON object of environment predicates')
    s.add_argument('--budget', type=int)
    sub.add_parser('verify')
    s = sub.add_parser('check')
    s.add_argument('--ci', action='store_true',
                   help='use the explicitly trusted base in memory, without local adoption')
    s.add_argument('--base', help='trusted CI integration base OID')
    s.add_argument('--result', default='HEAD')
    s = sub.add_parser('propose')
    s.add_argument('ids', nargs='+')
    s = sub.add_parser('apply')
    s.add_argument('id')
    s = sub.add_parser('forget')
    s.add_argument('id')
    s.add_argument('--reason', required=True)
    s.add_argument('--private', action='store_true')
    s.add_argument('--replacement')
    s = sub.add_parser('sync')
    s.add_argument('--remote', help='explicit configured Git remote to fetch; no merge')
    s = sub.add_parser('export')
    s.add_argument('--id', action='append', required=True, dest='ids')
    s.add_argument('--out', required=True)
    s = sub.add_parser('import')
    s.add_argument('file')
    s = sub.add_parser('dream')
    d = s.add_subparsers(dest='action', required=True)
    prepare = d.add_parser('prepare')
    prepare.add_argument('--id', action='append', dest='ids')
    prepare.add_argument('--max-bytes', type=int, default=1048576)
    for name in ('finish', 'inspect', 'cancel'):
        action = d.add_parser(name)
        action.add_argument('id')
        if name == 'finish':
            action.add_argument('--output', help='explicit synthesis output JSON')
    return p


def doctor(repo):
    policy = repo.policy()
    required = [key for key in ('native_capture', 'relay', 'durable_private')
                if policy.get(key) is True or (isinstance(policy.get(key), dict)
                                              and policy[key].get('required') is True)]
    return {'status': 'unjudged' if required else 'ok', 'code': 2 if required else 0,
            'required_unavailable': required, 'profile': 'git-only', 'policy': policy,
            'capabilities': {
                'local_recall': 'available', 'private_capture': 'filesystem',
                'git_proposals': 'available', 'dream': 'prepare-and-validate',
                'semantic_executor': 'external-agent-explicit-output',
                'automatic_hooks': 'requires-installed-wiring-and-host-verification',
                'native_capture': 'unsupported', 'native_prompt_isolation': 'unsupported',
                'cloud': 'explicit-per-repository-bootstrap',
                'relay': 'unsupported', 'private_remote_vault': 'unsupported'},
            'limits': ['Host memory outside this runtime remains unmanaged.',
                       'Private state lasts only as long as its Git administrative directory.',
                       'No automatic model requests or background scheduler are installed.']}


def sync_authority(repo, remote):
    """Fetch the adopted authority's bound branch; never merge or move its anchor."""
    from memory.store import _locked
    with _locked(repo):
        if remote not in repo.git('remote').decode().splitlines():
            raise MemoryFailure('invalid', 'sync requires an existing named Git remote')
        accepted = repo._anchor()['accepted_ref']
        if accepted.startswith('refs/remotes/' + remote + '/'):
            tracking = accepted
            source = 'refs/heads/' + accepted[len('refs/remotes/' + remote + '/'):]
        elif accepted.startswith('refs/heads/'):
            binding = repo.git('for-each-ref', '--format=%(upstream:remotename)%00%(upstream:remoteref)%00%(upstream)',
                               accepted).decode().strip().split('\x00')
            if len(binding) != 3 or binding[0] != remote or not binding[1] or not binding[2]:
                raise MemoryFailure('unjudged', 'Accepted branch needs an upstream bound to the named remote')
            _, source, tracking = binding
        else:
            raise MemoryFailure('unjudged', 'Named remote is not bound to the adopted authority')
        # Explicit refspec proves this fetch observed the authoritative branch,
        # even if the remote's default fetch configuration excludes that branch.
        repo.git('fetch', '--no-recurse-submodules', remote, source + ':' + tracking)
        fetched_tip = repo.resolve(tracking)
        if repo.resolve(accepted) != fetched_tip:
            raise MemoryFailure('unjudged', 'Fetched upstream differs from the accepted branch; integrate it explicitly before refreshing observation')
        return repo.observe_authority(expected_tip=fetched_tip)


def execute(a):
    from memory.evidence import validate_tree, verify
    from memory.retrieve import recall
    from memory.store import MemoryStore
    repo = Repository(a.root)
    if a.command in ('init', 'install'):
        from memory.install import adopt, install
        if a.command == 'install':
            return install(repo, accepted_ref=a.accepted_ref)
        return adopt(repo, a.accepted_ref, a.readopt)
    if a.command == 'doctor':
        return doctor(repo)
    if a.command == 'inspect':
        view = repo.view()
        return {'status': view['status'], 'code': view.get('code', 0), 'policy': view['policy'],
                'receipt': view.get('receipt'), 'excluded': view.get('excluded', [])}
    if a.command == 'recall':
        env = json.loads(a.environment) if a.environment else None
        if env is not None and not isinstance(env, dict):
            raise MemoryFailure('invalid', '--environment must be a JSON object')
        return recall(repo, a.query, a.path, env, a.budget)
    if a.command == 'verify':
        return verify(repo)
    if a.command == 'check':
        if not a.base:
            raise MemoryFailure('unjudged', 'check requires --base from trusted CI context')
        if a.ci:
            repo = repo.for_ci(a.base)
        return validate_tree(repo, a.base, a.result)
    if a.command == 'sync':
        if a.remote:
            sync_authority(repo, a.remote)
        view = repo.view()
        return {'status': view['status'], 'code': view.get('code', 0), 'receipt': view.get('receipt'),
                'fetched': a.remote, 'worktree_changed': False}
    store = MemoryStore(repo, a.session)
    if a.command == 'remember':
        if a.record:
            record = load_json(Path(a.record))
        else:
            if not all((a.title, a.body, a.reason)):
                raise MemoryFailure('invalid', 'remember needs --record or --title, --body and --reason')
            namespace = repo.policy()['repository_id']
            identity = (hashlib.sha256(json.dumps([namespace, store.session, a.processing_id],
                        ensure_ascii=False).encode()).hexdigest() if a.processing_id else uuid.uuid4().hex)
            record = {'schema_version': 1, 'id': 'm-' + identity,
                      'kind': a.kind, 'title': a.title,
                      'summary': a.title, 'body': a.body.splitlines(),
                      'scope': {'repository': namespace,
                                'paths': a.path or ['**'], 'tags': [], 'environment': {}},
                      'evidence': [{'type': 'decision', 'reason': a.reason}],
                      'freshness': {'dependencies': []}, 'state': 'active'}
        return store.remember(record, a.processing_id, {'channel': 'explicit-cli'})
    if a.command == 'propose':
        return store.propose(a.ids)
    if a.command == 'apply':
        return store.apply(a.id)
    if a.command == 'forget':
        return store.forget(a.id, a.reason, a.private, a.replacement)
    if a.command == 'export':
        from memory.install import write_atomic
        view = repo.view()
        records = [r for r in view['records'] if r['id'] in a.ids]
        if set(a.ids) != {r['id'] for r in records}:
            raise MemoryFailure('invalid', 'export selects only currently eligible accepted IDs')
        out = Path(a.out).resolve()
        if out.exists():
            raise MemoryFailure('conflict', 'export destination already exists')
        write_atomic(out, (json.dumps({'schema_version': 1, 'records': records,
                                      'receipt': view['receipt']}, ensure_ascii=False,
                                     indent=2) + '\n').encode())
        return {'status': 'ok', 'count': len(records), 'out': str(out)}
    if a.command == 'import':
        bundle = load_json(Path(a.file))
        if (not isinstance(bundle, dict) or bundle.get('schema_version') != 1
                or not isinstance(bundle.get('records'), list)):
            raise MemoryFailure('invalid', 'unsupported export bundle')
        from memory.schema import validate_record
        for record in bundle['records']:
            validate_record(record)
        return {'status': 'ok', 'candidates': [store.remember(
            record, origin={'channel': 'explicit-import'}) for record in bundle['records']]}
    if a.command == 'dream':
        from memory.dream import Dream
        dream = Dream(store)
        if a.action == 'prepare':
            return dream.prepare(a.ids, a.max_bytes)
        if a.action == 'finish':
            return dream.finish(a.id, a.output)
        return getattr(dream, a.action)(a.id)
    raise MemoryFailure('unsupported', 'unsupported operation')


def main(argv=None):
    a = parser().parse_args(argv)
    try:
        result = execute(a)
        status = result.get('status', 'ok')
        code = result.get('code', 2 if status in ('unjudged', 'unsupported') else
                          1 if status in ('conflict', 'invalid', 'stale') else 0)
        if type(code) is not int or code not in (0, 1, 2):
            raise MemoryFailure('unjudged', 'Operation returned an invalid exit code')
    except MemoryFailure as exc:
        result = {'status': exc.status, 'message': str(exc), 'details': exc.details}
        code = exc.code
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        result = {'status': 'unjudged', 'message': str(exc)}
        code = 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    sys.exit(main())
