"""Private candidates and recoverable, review-only worktree transactions.

Locks serialize cooperating runtimes. They do not constrain arbitrary editors.
Committed recall continues to use immutable Git trees during an interrupted apply.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from .errors import MemoryFailure
from .schema import (canonical_bytes, digest, load_json, validate_record,
                     validate_generation, validate_transition, scan_publication)
from .evidence import check_record


def _hash(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _authority(receipt):
    return {key: receipt.get(key) for key in ('head', 'accepted_ancestor', 'accepted_tip',
            'policy_digest', 'revocation_watermark')}


def _atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.memory-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        if os.name != 'nt':
            directory = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _save(path, value):
    _atomic_write(path, canonical_bytes(value))


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', value):
        raise MemoryFailure('invalid', 'Invalid private object identifier')
    return value


def _safe(base, *parts):
    """Reject symlink escape, including a not-yet-created final component."""
    base = Path(base).resolve()
    path = base.joinpath(*parts)
    if not path.resolve().is_relative_to(base):
        raise MemoryFailure('invalid', 'Path escapes its storage root')
    current = path
    while current != base:
        if current.is_symlink():
            raise MemoryFailure('invalid', 'Symlinked memory storage is unsupported')
        current = current.parent
    return path


@contextmanager
def _locked(repo):
    """OS-owned locks are released even when a process terminates."""
    path = _safe(repo.private, 'writer.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise MemoryFailure('conflict', 'Another memory writer is active') from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class MemoryStore:
    MAX_CANDIDATES = 2048
    MAX_PRIVATE_BYTES = 32 * 1024 * 1024

    def __init__(self, repo, session=None):
        self.repo = repo
        self.session = _id(session or uuid.uuid4().hex)
        self.directory = _safe(repo.private, 'sessions', self.session)
        self.directory.mkdir(parents=True, exist_ok=True)
        for name in ('candidates', 'proposals', 'jobs'):
            _safe(self.directory, name).mkdir(exist_ok=True)

    def _read(self, path):
        try:
            return load_json(path)
        except FileNotFoundError as exc:
            raise MemoryFailure('invalid', 'Private object does not exist') from exc

    def _candidate(self, candidate_id):
        return self._read(_safe(self.directory, 'candidates', _id(candidate_id) + '.json'))

    def candidates(self):
        return [self._read(p) for p in sorted(_safe(self.directory, 'candidates').glob('*.json'))]

    def _record_path(self, record_id):
        return _safe(self.repo.root, '.harness', 'memory', 'records', _id(record_id) + '.json')

    def _bytes(self, path):
        try:
            return Path(path).read_bytes()
        except FileNotFoundError:
            return None

    def _head(self):
        try:
            return self.repo.resolve('HEAD')
        except MemoryFailure:
            # A valid symbolic HEAD with no commits is an unborn repository.
            # Missing/corrupt HEAD in a nonempty repository remains unjudged.
            if self.repo.git('rev-list', '--all').strip():
                raise
            self.repo.git('symbolic-ref', '--quiet', 'HEAD')
            return None

    def _sources(self, records):
        paths = set()
        for record in records:
            items = [record.get('target', {})] + record.get('freshness', {}).get('dependencies', [])
            items += record.get('evidence', [])
            for item in items:
                if isinstance(item, dict) and item.get('path'):
                    paths.add(item['path'])
        result = {}
        for path in sorted(paths):
            # Source schema validates relative paths; containment is checked again here.
            dest = _safe(self.repo.root, path)
            result[path] = _hash(self._bytes(dest))
        return result

    def _baseline(self, records=()):
        existing = self.repo.record_files()
        return {'head': self._head(), 'policy': digest(self.repo.policy()),
                'policy_file': _hash(self._bytes(_safe(self.repo.root, '.harness', 'memory', 'config.json'))),
                'records': {key: _hash(self._bytes(self._record_path(key))) for key in sorted(existing)},
                'sources': self._sources(list(existing.values()) + list(records)),
                'view': digest(_authority(self.repo.view().get('receipt', {})))}

    def _check_baseline(self, baseline, changes=None):
        changes = changes or {}
        current = self._baseline()
        for key in ('head', 'policy', 'policy_file', 'view'):
            if current[key] != baseline[key]:
                raise MemoryFailure('conflict', 'Repository baseline changed', {'field': key})
        expected_keys = set(baseline['records']) | set(changes)
        if set(current['records']) - expected_keys:
            raise MemoryFailure('conflict', 'Record set changed')
        for key in expected_keys:
            found = current['records'].get(key)
            allowed = {baseline['records'].get(key)}
            if key in changes:
                allowed.add(_hash(canonical_bytes(changes[key])))
            if found not in allowed:
                raise MemoryFailure('conflict', 'Record bytes changed', {'id': key})
        for path, expected in baseline['sources'].items():
            if _hash(self._bytes(_safe(self.repo.root, path))) != expected:
                raise MemoryFailure('stale', 'Source baseline changed', {'path': path})

    def remember(self, record, processing_id=None, origin=None):
        record = validate_record(record)
        if origin is not None and not isinstance(origin, dict):
            raise MemoryFailure('invalid', 'Candidate origin must be an object')
        if processing_id is not None and (not isinstance(processing_id, str) or len(processing_id) > 512):
            raise MemoryFailure('invalid', 'Invalid processing ID')
        with _locked(self.repo):
            return self._remember(record, processing_id, origin)

    def _remember(self, record, processing_id=None, origin=None):
        content = digest(record)
        existing = self.candidates()
        for item in existing:
            if processing_id and item.get('processing_id') == processing_id:
                if item['record_digest'] != content:
                    raise MemoryFailure('conflict', 'Processing ID was already used for different content')
                return dict(item, duplicate=True)
        candidate_id = 'c-' + digest({'record': content, 'processing_id': processing_id})[:32]
        for item in existing:
            if item['id'] == candidate_id:
                return dict(item, duplicate=True)
        value = {'id': candidate_id, 'status': 'ok', 'state': 'candidate', 'session': self.session,
                 'durability': 'filesystem', 'record': record, 'record_digest': content,
                 'processing_id': processing_id,
                 'origin': {'head': self._head(), 'session': self.session,
                            'worktree': str(self.repo.git_dir), 'source': origin or {'channel': 'explicit'},
                            'baseline': _hash(self._bytes(self._record_path(record['id'])))}}
        size = sum(p.stat().st_size for p in self.directory.rglob('*') if p.is_file())
        limits = self.repo.policy().get('limits', {})
        max_count = min(self.MAX_CANDIDATES, limits.get('candidate_count', self.MAX_CANDIDATES))
        max_size = min(self.MAX_PRIVATE_BYTES, limits.get('candidate_bytes', self.MAX_PRIVATE_BYTES))
        if len(existing) >= max_count or size + len(canonical_bytes(value)) > max_size:
            raise MemoryFailure('invalid', 'Private candidate quota exhausted; export or explicitly purge first')
        _save(_safe(self.directory, 'candidates', candidate_id + '.json'), value)
        return value

    def _validate(self, changes):
        policy = self.repo.policy()
        records = self.repo.record_files()
        before = dict(records)
        records.update(changes)
        findings = validate_generation(list(records.values()), policy)
        findings.extend(validate_transition(before, records))
        view = self.repo.view()
        if not view.get('receipt'):
            raise MemoryFailure('unjudged', 'Cannot establish proposal authority baseline',
                                {'findings': view.get('excluded', [])})
        tip = view['receipt'].get('accepted_tip')
        if tip:
            latest = self.repo.record_files(tip)
            ancestor = self.repo.record_files(view['receipt']['accepted_ancestor'])
            merged = dict(latest, **changes)
            findings.extend(validate_transition(latest, merged))
            findings.extend(validate_generation(merged, policy))
            for key in changes:
                if key in latest and latest[key]['state'] == 'active' and ancestor.get(key) != latest[key]:
                    findings.append({'id': key, 'status': 'conflict',
                                     'reason': 'Checkout is behind the accepted record version'})
        for record in changes.values():
            findings.extend(check_record(self.repo, record))
        if findings:
            status = 'unjudged' if all(f['status'] == 'unjudged' for f in findings) else 'conflict'
            raise MemoryFailure(status, 'Proposed generation failed validation', {'findings': findings})
        return records

    def _pending(self, except_id=None):
        for path in _safe(self.repo.private, 'transactions').glob('*.json'):
            journal = self._read(path)
            if journal.get('state') == 'applying' and journal.get('id') != except_id:
                raise MemoryFailure('conflict', 'Resume the interrupted transaction before new publication',
                                    {'id': journal['id'], 'session': journal['session']})

    def propose(self, ids):
        if not isinstance(ids, (list, tuple)) or not ids:
            raise MemoryFailure('invalid', 'Explicit candidate IDs are required')
        with _locked(self.repo):
            return self._propose(ids)

    def _propose(self, ids):
        self._pending()
        candidates = [self._candidate(value) for value in sorted(set(ids))]
        changes = {}
        for candidate in candidates:
            record = validate_record(candidate['record'])
            if digest(record) != candidate['record_digest']:
                raise MemoryFailure('invalid', 'Candidate content digest changed')
            key = record['id']
            if key in changes and changes[key] != record:
                raise MemoryFailure('conflict', 'Selected candidates disagree on one record', {'id': key})
            if _hash(self._bytes(self._record_path(key))) != candidate['origin']['baseline']:
                raise MemoryFailure('conflict', 'Candidate target baseline changed', {'id': key})
            changes[key] = record
        self._validate(changes)
        baseline = self._baseline(changes.values())
        value = {'changes': changes, 'candidates': [c['id'] for c in candidates], 'baseline': baseline,
                 'provenance': {c['record']['id']: {'candidate': c['id'], 'digest': c['record_digest']}
                                for c in candidates}, 'session': self.session}
        proposal_id = 'p-' + digest(value)[:32]
        folder = _safe(self.directory, 'proposals', proposal_id)
        if (folder / 'proposal.json').exists():
            return self._proposal(proposal_id)
        folder.mkdir(exist_ok=True)
        lines = ['# Memory proposal', '', 'Provisional reference material; requires repository review.', '']
        for key, record in sorted(changes.items()):
            prior = self.repo.record_files().get(key)
            fields = sorted(k for k in set(record) | set(prior or {}) if record.get(k) != (prior or {}).get(k))
            lines += ['## ' + key, '', 'Changed fields: ' + ', '.join(fields), '',
                      '```json', json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2), '```', '']
        preview = folder / 'preview.md'
        scan_publication('\n'.join(lines))
        _atomic_write(preview, '\n'.join(lines).encode('utf-8'))
        value.update(id=proposal_id, status='ok', state='proposal', preview=str(preview), accepted=False)
        _save(folder / 'proposal.json', value)
        return value

    def _proposal(self, proposal_id):
        proposal = self._read(_safe(self.directory, 'proposals', _id(proposal_id), 'proposal.json'))
        identity = {key: proposal[key] for key in ('changes', 'candidates', 'baseline', 'provenance', 'session')}
        if proposal_id != 'p-' + digest(identity)[:32] or proposal['id'] != proposal_id:
            raise MemoryFailure('invalid', 'Proposal changed after its preview was created')
        return proposal

    def apply(self, proposal_id):
        with _locked(self.repo):
            self._pending(proposal_id)
            proposal = self._proposal(proposal_id)
            journal_path = _safe(self.repo.private, 'transactions', proposal_id + '.json')
            journal = self._read(journal_path) if journal_path.exists() else None
            changes = proposal['changes']
            if journal is None:
                self._check_baseline(proposal['baseline'])
            else:
                if journal['proposal_digest'] != digest(proposal):
                    raise MemoryFailure('conflict', 'Transaction proposal changed')
                self._check_baseline(proposal['baseline'], changes)
            generation = self._validate(changes)
            if journal is None:
                journal = {'id': proposal_id, 'session': self.session, 'state': 'applying',
                           'proposal_digest': digest(proposal), 'changes': changes,
                           'old': proposal['baseline']['records'],
                           'new': {key: _hash(canonical_bytes(value)) for key, value in changes.items()}}
                _save(journal_path, journal)
            for key, record in sorted(changes.items()):
                path = self._record_path(key)
                current = _hash(self._bytes(path))
                if current not in (journal['old'].get(key), journal['new'][key]):
                    raise MemoryFailure('conflict', 'Concurrent edit during transaction', {'id': key})
                if current != journal['new'][key]:
                    _atomic_write(path, canonical_bytes(record))
            self._check_baseline(proposal['baseline'], changes)
            self._validate(changes)
            for key in changes:
                if _hash(self._bytes(self._record_path(key))) != journal['new'][key]:
                    raise MemoryFailure('conflict', 'Record changed before generation publication', {'id': key})
            manifest = {'id': proposal_id, 'complete': True, 'accepted': False,
                        'records': generation, 'digest': digest(generation)}
            _save(_safe(self.repo.private, 'generations', proposal_id + '.json'), manifest)
            _save(_safe(self.repo.private, 'current-generation.json'), {'id': proposal_id, 'digest': digest(manifest)})
            journal['state'] = 'completed'
            _save(journal_path, journal)
            return {'id': proposal_id, 'status': 'ok', 'state': 'applied', 'accepted': False,
                    'changes': sorted(changes), 'preview': proposal['preview']}

    def forget(self, record_id, reason, private=False, replacement=None):
        if not isinstance(reason, str) or not reason.strip():
            raise MemoryFailure('invalid', 'An explicit forgetting reason is required')
        if private:
            with _locked(self.repo):
                return self._purge(_id(record_id))
        record = self.repo.record_files().get(_id(record_id))
        if not record:
            raise MemoryFailure('invalid', 'Unknown record')
        retirement = {'previous_record_hash': digest(record), 'reason': reason}
        if replacement:
            retirement['replacement'] = _id(replacement)
        tombstone = {'schema_version': 1, 'id': record_id, 'state': 'retired', 'retirement': retirement}
        candidate = self.remember(tombstone, origin={'channel': 'explicit-retirement'})
        proposal = self.propose([candidate['id']])
        proposal['remaining_source'] = record.get('target', {}).get('path')
        proposal['limitations'] = ['Git history and existing model context are not erased.']
        return proposal

    def _purge(self, candidate_id):
        self._candidate(candidate_id)
        inventory = []
        removed = {candidate_id}
        candidates = self.candidates()
        while True:
            before = set(removed)
            for item in candidates:
                source = item['origin'].get('source', {})
                if any('candidate:' + key in source.get('sources', []) for key in removed):
                    removed.add(item['id'])
            if removed == before:
                break
        record_ids = {item['record']['id'] for item in candidates if item['id'] in removed}
        proposal_ids = set()
        # Generated jobs/proposals can contain derivative text; remove their complete private
        # containers rather than attempting unreliable substring redaction.
        for name in ('jobs', 'proposals'):
            folder = _safe(self.directory, name)
            for child in list(folder.iterdir()):
                if child.is_symlink():
                    raise MemoryFailure('invalid', 'Symlink in purge inventory')
                if name == 'jobs':
                    snapshot = self._read(child / 'snapshot.json')
                    if not any('candidate:' + key in snapshot['inputs'] for key in removed):
                        continue
                else:
                    proposal = self._read(child / 'proposal.json')
                    if not set(proposal['candidates']) & removed:
                        continue
                    proposal_ids.add(proposal['id'])
                inventory.append(str(child.relative_to(self.directory)))
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        for item in candidates:
            if item['id'] in removed:
                path = _safe(self.directory, 'candidates', item['id'] + '.json')
                inventory.append(str(path.relative_to(self.directory)))
                path.unlink()
        for name in ('transactions', 'generations'):
            folder = _safe(self.repo.private, name)
            for path in folder.glob('*.json'):
                value = self._read(path)
                if value.get('id') in proposal_ids or record_ids & set(value.get('records', {})):
                    inventory.append(name + '/' + path.name)
                    path.unlink()
        pointer = _safe(self.repo.private, 'current-generation.json')
        if pointer.exists() and not _safe(self.repo.private, 'generations', self._read(pointer)['id'] + '.json').exists():
            pointer.unlink()
        return {'id': candidate_id, 'status': 'ok', 'state': 'purged', 'inventory': inventory,
                'scope': 'this-session', 'remote_deletion': 'not-configured',
                'limitations': ['Filesystem forensic erasure, backups, exports outside runtime, Git history, '
                                'and existing model context are not erased.'], 'accepted': False}
