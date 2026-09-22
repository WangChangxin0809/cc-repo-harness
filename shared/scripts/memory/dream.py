"""Bounded immutable consolidation jobs without an external model executor.

An agent may explicitly write the indicated output JSON. This is an input/output
contract, not a sandbox: hashes and validators detect changes at finish time.
"""
from pathlib import Path
import re

from .errors import MemoryFailure
from .schema import canonical_bytes, digest, validate_record, validate_generation, load_json
from .evidence import check_record
from .store import _id, _safe, _save, _locked, _authority


class Dream:
    VERSION = 1
    MAX_BYTES = 16 * 1024 * 1024
    MAX_ATTEMPTS = 8

    def __init__(self, store):
        self.store = store
        self.repo = store.repo

    def _folder(self, job_id):
        return _safe(self.store.directory, 'jobs', _id(job_id))

    def _load(self, job_id):
        folder = self._folder(job_id)
        job = self.store._read(folder / 'job.json')
        snapshot = self.store._read(folder / 'snapshot.json')
        if digest(snapshot) != job['snapshot_digest'] or job_id != 'd-' + digest(snapshot)[:32]:
            raise MemoryFailure('invalid', 'Dream immutable snapshot was modified')
        return folder, job, snapshot

    def _receipt(self, folder, job):
        return dict(job, output=str(folder / 'output.json'), snapshot=str(folder / 'snapshot.json'),
                    report=str(folder / 'report.json'), accepted=False,
                    semantic_executor='unavailable', isolation='no-executor-launched')

    def prepare(self, ids=None, max_bytes=1048576):
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or not 1 <= max_bytes <= self.MAX_BYTES:
            raise MemoryFailure('invalid', 'Dream byte budget must be between 1 and 16777216')
        if ids is not None and not isinstance(ids, (list, tuple)):
            raise MemoryFailure('invalid', 'Selected candidate IDs must be a list')
        with _locked(self.repo):
            self.store._pending()
            view = self.repo.view()
            if not view.get('receipt'):
                raise MemoryFailure(view['status'], 'Cannot freeze unavailable accepted knowledge',
                                    {'findings': view.get('excluded', [])})
            max_bytes = min(max_bytes, view['policy'].get('limits', {}).get('dream_bytes', max_bytes))
            inputs = {}
            for record in view['records']:
                inputs['accepted:' + record['id']] = record
            selected = [c['id'] for c in self.store.candidates()] if ids is None else ids
            for candidate_id in sorted(set(selected)):
                candidate = self.store._candidate(candidate_id)
                if digest(candidate['record']) != candidate['record_digest']:
                    raise MemoryFailure('invalid', 'Candidate digest changed')
                inputs['candidate:' + candidate_id] = candidate['record']
            baseline = self.store._baseline(inputs.values())
            sources = {}
            for path in self.store._sources(inputs.values()):
                source_path = _safe(self.repo.root, path)
                if source_path.exists() and source_path.stat().st_size > max_bytes:
                    raise MemoryFailure('invalid', 'Dream source exceeds input budget', {'path': path})
                raw = self.store._bytes(source_path)
                sources[path] = raw.hex() if raw is not None else None
                if sum(len(value or '') // 2 for value in sources.values()) > max_bytes:
                    raise MemoryFailure('invalid', 'Dream source input budget exhausted')
            snapshot = {'version': self.VERSION, 'inputs': inputs, 'baseline': baseline,
                        'sources': sources, 'view': _authority(view.get('receipt', {})),
                        'excluded': view.get('excluded', [])}
            size = len(canonical_bytes(snapshot))
            if size > max_bytes:
                raise MemoryFailure('invalid', 'Dream snapshot exceeds input budget', {'bytes': size, 'limit': max_bytes})
            job_id = 'd-' + digest(snapshot)[:32]
            folder = self._folder(job_id)
            if (folder / 'job.json').exists():
                _, job, _ = self._load(job_id)
                return self._receipt(folder, job)
            if (folder / 'snapshot.json').exists() and digest(self.store._read(folder / 'snapshot.json')) != digest(snapshot):
                raise MemoryFailure('invalid', 'Interrupted preparation snapshot was modified')
            # Single live job per worktree; other sessions' candidate contents are never loaded.
            for existing in _safe(self.repo.private, 'sessions').glob('*/jobs/*/job.json'):
                metadata = self.store._read(existing)
                if metadata.get('state') in ('queued', 'running'):
                    raise MemoryFailure('conflict', 'A dream job is already active in this worktree')
            folder.mkdir(exist_ok=True)
            if not (folder / 'snapshot.json').exists():
                _save(folder / 'snapshot.json', snapshot)
            report = self._report(inputs, snapshot['excluded'])
            _save(folder / 'report.json', report)
            job = {'id': job_id, 'state': 'queued', 'status': 'ok', 'result': None,
                   'snapshot_digest': digest(snapshot), 'input_bytes': size,
                   'budget': max_bytes, 'used_bytes': size, 'attempts': 0,
                   'output_digests': [], 'candidates': [], 'proposal': None}
            _save(folder / 'job.json', job)
            return self._receipt(folder, job)

    def _report(self, inputs, excluded):
        groups = {}
        findings = list(excluded)
        for key, record in sorted(inputs.items()):
            semantic = {k: v for k, v in record.items() if k not in ('id', 'evidence')}
            groups.setdefault(digest(semantic), []).append(key)
            findings.extend(check_record(self.repo, record))
        # Input duplicates may share an ID; generation checking still exposes claim conflicts.
        findings.extend(validate_generation(list(inputs.values()), self.repo.policy()))
        dispositions = [{'input': key, 'action': 'keep', 'outputs': []} for key in sorted(inputs)]
        return {'kind': 'deterministic-report', 'duplicates': [v for v in groups.values() if len(v) > 1],
                'findings': findings, 'inputs': sorted(inputs),
                'dispositions': dispositions,
                'output_template': {'records': [], 'dispositions': dispositions, 'provenance': {}},
                'output_contract': {
                    'records': 'Array of complete schema-version-1 active records; unique output IDs.',
                    'dispositions': 'Exactly one entry per input: {input,action,outputs?,reason?}. '
                                    'action is keep, mapped, unresolved or retire. Only mapped has nonempty '
                                    'outputs (output record IDs). unresolved/retire require reason.',
                    'provenance': 'Object mapping every output record ID to nonempty input-ID arrays; '
                                  'must agree with mapped dispositions in both directions.',
                    'preservation': 'Preserve every supporting source scope, evidence, freshness, target and '
                                    'structured claim. Retirements are suggestions; use explicit forget.',
                    'execution': 'Write only job output.json. Runtime launches no model or generated code; '
                                 'this instruction is not a sandbox. Human review remains required.'},
                'semantic_synthesis': 'unavailable',
                'limitations': ['Format, exact evidence and structured claims can be checked; '
                                'semantic correctness requires review.']}

    def inspect(self, job_id):
        folder, job, _ = self._load(job_id)
        return self._receipt(folder, job)

    def cancel(self, job_id):
        with _locked(self.repo):
            folder, job, _ = self._load(job_id)
            if job['state'] != 'completed':
                job.update(state='canceled', status='ok')
                _save(folder / 'job.json', job)
            return self._receipt(folder, job)

    def finish(self, job_id, output=None):
        with _locked(self.repo):
            folder, job, snapshot = self._load(job_id)
            if job['state'] in ('canceled', 'budget-exhausted'):
                raise MemoryFailure('conflict', 'Dream job cannot be resumed', {'state': job['state']})
            # Even replay must recheck withdrawal/authority/source baselines.
            try:
                self.store._check_baseline(snapshot['baseline'])
            except MemoryFailure as exc:
                job.update(state='completed', status='stale', result='needs-rebase', findings=[exc.details],
                           purge_inventory=[str(p) for p in folder.iterdir() if p.name != 'job.json'])
                _save(folder / 'job.json', job)
                return self._receipt(folder, job)
            if job['state'] == 'completed':
                return self._receipt(folder, job)
            if output is None and (folder / 'output.json').exists():
                output = folder / 'output.json'
            if output is None:
                report = self.store._read(folder / 'report.json')
                job.update(state='completed', status='ok', result='needs-review' if report['findings'] else 'no-change')
                _save(folder / 'job.json', job)
                return self._receipt(folder, job)
            if isinstance(output, (str, Path)):
                output_path = Path(output)
                if output_path.resolve() != (folder / 'output.json').resolve() or output_path.is_symlink():
                    raise MemoryFailure('invalid', 'Write synthesis only to this job output.json')
                if output_path.stat().st_size > job['budget']:
                    job.update(state='budget-exhausted', status='invalid')
                    _save(folder / 'job.json', job)
                    raise MemoryFailure('invalid', 'Dream output budget exhausted')
                output = load_json(output_path)
            encoded = canonical_bytes(output)
            output_digest = digest(output)
            if output_digest not in job['output_digests']:
                job['used_bytes'] += len(encoded)
                job['output_digests'].append(output_digest)
            job['attempts'] += 1
            if job['used_bytes'] > job['budget'] or job['attempts'] > self.MAX_ATTEMPTS:
                job.update(state='budget-exhausted', status='invalid')
                _save(folder / 'job.json', job)
                raise MemoryFailure('invalid', 'Dream cumulative budget exhausted')
            job.update(state='running')
            _save(folder / 'job.json', job)
            try:
                records, warnings = self._validate_output(snapshot['inputs'], output)
                self.store._validate({r['id']: r for r in records})
                _save(folder / 'validated-output.json', output)
                candidates = []
                for record in records:
                    value = self.store._remember(record, processing_id=job_id + ':' + record['id'],
                        origin={'channel': 'dream', 'job': job_id, 'sources': output['provenance'][record['id']],
                                'snapshot_digest': job['snapshot_digest']})
                    candidates.append(value['id'])
                proposal = self.store._propose(candidates) if candidates else None
                job.update(state='completed', status='ok', candidates=candidates,
                           proposal=proposal['id'] if proposal else None,
                           result='needs-review' if warnings else ('proposal-ready' if proposal else 'no-change'),
                           findings=warnings, output_digest=output_digest)
            except MemoryFailure as exc:
                job.update(state='failed', status=exc.status, findings=[{'reason': str(exc), 'details': exc.details}])
                _save(folder / 'job.json', job)
                raise
            _save(folder / 'job.json', job)
            return self._receipt(folder, job)

    def _validate_output(self, inputs, output):
        if not isinstance(output, dict) or set(output) != {'records', 'dispositions', 'provenance'}:
            raise MemoryFailure('invalid', 'Output requires records, dispositions and provenance only')
        if not isinstance(output['records'], list) or not isinstance(output['dispositions'], list) or not isinstance(output['provenance'], dict):
            raise MemoryFailure('invalid', 'Invalid synthesis output containers')
        records = [validate_record(record) for record in output['records']]
        ids = {r['id'] for r in records}
        if len(ids) != len(records) or set(output['provenance']) != ids:
            raise MemoryFailure('invalid', 'Each unique output requires provenance')
        dispositions = {}
        for item in output['dispositions']:
            if not isinstance(item, dict) or not {'input', 'action'} <= set(item) or set(item) - {'input', 'action', 'outputs', 'reason'}:
                raise MemoryFailure('invalid', 'Invalid input disposition')
            key = item['input']
            if key not in inputs or key in dispositions:
                raise MemoryFailure('invalid', 'Unknown or duplicate input disposition')
            action = item['action']
            targets = item.get('outputs', [])
            if not isinstance(targets, list) or any(not isinstance(v, str) or v not in ids for v in targets):
                raise MemoryFailure('invalid', 'Unknown disposition output')
            if action not in ('keep', 'mapped', 'unresolved', 'retire'):
                raise MemoryFailure('invalid', 'Unknown disposition action')
            if (action == 'mapped') != bool(targets):
                raise MemoryFailure('invalid', 'Only mapped inputs specify nonempty outputs')
            if action in ('unresolved', 'retire') and not item.get('reason'):
                raise MemoryFailure('invalid', 'Unresolved/retirement suggestions require a reason')
            dispositions[key] = item
        if set(dispositions) != set(inputs):
            raise MemoryFailure('invalid', 'Every input needs an explicit disposition')
        warnings = []
        for record in records:
            sources = output['provenance'][record['id']]
            if not isinstance(sources, list) or not sources or any(not isinstance(key, str) or key not in inputs for key in sources):
                raise MemoryFailure('invalid', 'Unknown or missing output provenance')
            if record['state'] != 'active':
                raise MemoryFailure('invalid', 'Use explicit forget for retirement; dream may only suggest it')
            for key in sources:
                source = inputs[key]
                if record['id'] not in dispositions[key].get('outputs', []):
                    raise MemoryFailure('invalid', 'Provenance must agree with input disposition')
                if record.get('scope') != source.get('scope'):
                    raise MemoryFailure('invalid', 'Synthesis changed source scope')
                if any(e not in record.get('evidence', []) for e in source.get('evidence', [])):
                    raise MemoryFailure('invalid', 'Synthesis dropped source evidence')
                if record.get('freshness') != source.get('freshness'):
                    raise MemoryFailure('invalid', 'Synthesis changed source version/freshness')
                if source.get('target') and record.get('target') != source['target']:
                    raise MemoryFailure('invalid', 'Synthesis changed source target')
                if source.get('claim') and record.get('claim') != source['claim']:
                    raise MemoryFailure('invalid', 'Synthesis changed structured source claim')
                old = ' '.join([source.get('summary', '')] + source.get('body', []))
                new = ' '.join([record.get('summary', '')] + record.get('body', []))
                critical = re.findall(r'\b(?:\d[\w.%-]*|not|never|unless|except|must)\b', old, re.I)
                missing = sorted(set(t for t in critical if t.lower() not in new.lower()))
                if missing:
                    warnings.append({'id': record['id'], 'reason': 'Possible qualification/value loss', 'tokens': missing})
        for key, item in dispositions.items():
            for target in item.get('outputs', []):
                if key not in output['provenance'][target]:
                    raise MemoryFailure('invalid', 'Disposition must agree with output provenance')
            if item['action'] in ('unresolved', 'retire'):
                warnings.append({'input': key, 'reason': item['reason'], 'action': item['action']})
        return records, warnings
