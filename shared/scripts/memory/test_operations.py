"""Real-Git behavioral checks for private memory operations."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memory.repository import Repository
from memory.store import MemoryStore
from memory.dream import Dream
from memory.errors import MemoryFailure


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(MemoryStore, 'MemoryStore runtime is not implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-b', 'main')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Memory Test')
        self.write('README.md', 'source v1\n')
        self.write('.harness/memory/config.json', json.dumps({
            'schema_version': 1, 'repository_id': 'sample',
            'accepted_ref': 'refs/heads/main', 'review': {'mode': 'git-review'}}))
        self.git('add', '.')
        self.git('commit', '-m', 'initial policy')
        self.repo = Repository(self.root)
        self.repo.initialize('refs/heads/main')
        self.store = MemoryStore(self.repo, 'session-a')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.STDOUT)

    def write(self, path, value):
        dest = self.root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(value, encoding='utf-8')

    def record(self, key='first', text='Keep the compatibility interface.'):
        return {'schema_version': 1, 'id': key, 'kind': 'decision',
                'title': key, 'summary': text, 'body': [text],
                'scope': {'repository': 'sample', 'paths': ['**'], 'tags': [], 'environment': {}},
                'evidence': [{'type': 'decision', 'reason': 'Explicit reviewed team decision'}],
                'freshness': {'dependencies': []}, 'state': 'active'}

    def capture(self, key='first'):
        return self.store.remember(self.record(key), processing_id='capture-' + key)['id']

    def test_capture_is_private_durable_and_session_scoped(self):
        candidate = self.capture()
        self.assertEqual([], MemoryStore(self.repo, 'session-b').candidates())
        self.assertEqual(candidate, MemoryStore(self.repo, 'session-a').candidates()[0]['id'])
        self.assertFalse(self.store.directory.is_relative_to(self.root / '.harness'))
        self.assertEqual('', self.git('status', '--porcelain').decode())
        self.assertNotEqual(MemoryStore(self.repo).session, MemoryStore(self.repo).session)

    def test_processing_replay_is_idempotent_but_changed_payload_conflicts(self):
        a = self.capture()
        self.assertEqual(a, self.capture())
        self.assertEqual(1, len(self.store.candidates()))
        with self.assertRaises(MemoryFailure):
            self.store.remember(self.record(text='Different'), processing_id='capture-first')

    def test_apply_is_reviewable_and_never_accepts(self):
        head = self.repo.resolve('HEAD')
        proposal = self.store.propose([self.capture()])
        self.assertTrue(Path(proposal['preview']).is_file())
        applied = self.store.apply(proposal['id'])
        self.assertEqual('ok', applied['status'])
        self.assertTrue((self.root / '.harness/memory/records/first.json').is_file())
        self.assertEqual(head, self.repo.resolve('HEAD'))
        self.assertEqual([], self.repo.view()['records'])

    def test_apply_cas_rejects_editor_change(self):
        proposal = self.store.propose([self.capture()])
        self.write('.harness/memory/records/first.json', json.dumps(self.record(text='Editor owns this')))
        before = (self.root / '.harness/memory/records/first.json').read_bytes()
        with self.assertRaises(MemoryFailure):
            self.store.apply(proposal['id'])
        self.assertEqual(before, (self.root / '.harness/memory/records/first.json').read_bytes())

    def test_recovery_finishes_interrupted_multi_record_apply(self):
        proposal = self.store.propose([self.capture('first'), self.capture('second')])
        from memory import store as module
        original = module._atomic_write
        writes = []
        def interrupted(path, data):
            if Path(path).parent == self.root / '.harness/memory/records':
                writes.append(path)
                if len(writes) == 2:
                    raise OSError('simulated process interruption')
            return original(path, data)
        with patch.object(module, '_atomic_write', interrupted):
            with self.assertRaises(OSError):
                self.store.apply(proposal['id'])
        recovered = MemoryStore(self.repo, 'session-a').apply(proposal['id'])
        self.assertEqual('ok', recovered['status'])
        self.assertEqual({'first', 'second'}, set(self.repo.record_files()))
        pointer = json.loads((self.repo.private / 'current-generation.json').read_text())
        self.assertEqual(proposal['id'], pointer['id'])

    def test_recovery_never_overwrites_external_edit(self):
        proposal = self.store.propose([self.capture('first'), self.capture('second')])
        from memory import store as module
        original = module._atomic_write
        def interrupted(path, data):
            if Path(path).name == 'second.json' and Path(path).parent.name == 'records':
                raise OSError('simulated crash')
            return original(path, data)
        with patch.object(module, '_atomic_write', interrupted):
            with self.assertRaises(OSError):
                self.store.apply(proposal['id'])
        self.write('.harness/memory/records/first.json', json.dumps(self.record(text='Concurrent edit')))
        with self.assertRaises(MemoryFailure):
            MemoryStore(self.repo, 'session-a').apply(proposal['id'])
        self.assertFalse((self.repo.private / 'current-generation.json').exists())

    def test_private_forget_purges_dependent_snapshots_and_previews(self):
        candidate = self.capture()
        proposal = self.store.propose([candidate])
        dream = Dream(self.store).prepare([candidate])
        receipt = self.store.forget(candidate, 'user request', private=True)
        self.assertEqual('ok', receipt['status'])
        self.assertEqual([], self.store.candidates())
        self.assertFalse(Path(proposal['preview']).exists())
        self.assertFalse(Path(dream['output']).parent.exists())
        with self.assertRaises(MemoryFailure):
            self.store.apply(proposal['id'])

    def test_retirement_is_minimal_proposal(self):
        proposal = self.store.propose([self.capture()])
        self.store.apply(proposal['id'])
        self.git('add', '.')
        self.git('commit', '-m', 'accept first')
        retirement = self.store.forget('first', 'obsolete')
        self.store.apply(retirement['id'])
        record = self.repo.record_files()['first']
        self.assertEqual({'schema_version', 'id', 'state', 'retirement'}, set(record))
        self.assertEqual('retired', record['state'])

    def test_dream_replay_is_immutable_and_deterministic(self):
        candidate = self.capture()
        dream = Dream(self.store)
        job = dream.prepare([candidate])
        self.assertEqual(job['id'], dream.prepare([candidate])['id'])
        result = dream.finish(job['id'])
        self.assertEqual('completed', result['state'])
        self.assertEqual('no-change', result['result'])
        self.assertEqual('unavailable', result['semantic_executor'])
        self.assertEqual([], self.repo.view()['records'])

    def test_dream_rejects_missing_dispositions_and_unknown_provenance(self):
        candidate = self.capture()
        dream = Dream(self.store)
        job = dream.prepare([candidate])
        with self.assertRaises(MemoryFailure):
            dream.finish(job['id'], {'records': [self.record('synthesis')], 'dispositions': [],
                                      'provenance': {'synthesis': ['missing']}})

    def test_dream_output_retains_provenance_and_does_not_accept(self):
        candidate = self.capture()
        dream = Dream(self.store)
        job = dream.prepare([candidate])
        new = self.record('synthesis')
        result = dream.finish(job['id'], {'records': [new],
            'dispositions': [{'input': 'candidate:' + candidate, 'action': 'mapped', 'outputs': ['synthesis']}],
            'provenance': {'synthesis': ['candidate:' + candidate]}})
        self.assertEqual('proposal-ready', result['result'])
        self.assertEqual(2, len(self.store.candidates()))
        self.assertEqual([], self.repo.view()['records'])
        self.assertEqual(2, len(self.store.candidates()))
        self.assertEqual(result['proposal'], dream.finish(job['id'])['proposal'])

    def test_dream_cancellation_and_budget_are_sticky(self):
        dream = Dream(self.store)
        job = dream.prepare([self.capture()])
        self.assertEqual('canceled', dream.cancel(job['id'])['state'])
        with self.assertRaises(MemoryFailure):
            dream.finish(job['id'])
        self.assertEqual('canceled', dream.prepare([self.capture()])['state'])
        with self.assertRaises(MemoryFailure):
            dream.prepare([self.capture()], max_bytes=1)

    def test_dream_baseline_change_requires_rebase(self):
        candidate = self.capture()
        dream = Dream(self.store)
        job = dream.prepare([candidate])
        self.write('.harness/memory/records/elsewhere.json', json.dumps(self.record('elsewhere')))
        result = dream.finish(job['id'])
        self.assertEqual('needs-rebase', result['result'])

    def test_dream_source_change_requires_rebase(self):
        record = self.record()
        record['freshness']['dependencies'] = [{'path': 'README.md',
            'content_digest': hashlib.sha256((self.root / 'README.md').read_bytes()).hexdigest()}]
        candidate = self.store.remember(record)['id']
        job = Dream(self.store).prepare([candidate])
        self.write('README.md', 'changed source\n')
        self.assertEqual('needs-rebase', Dream(self.store).finish(job['id'])['result'])

    def test_dream_snapshot_mutation_is_rejected(self):
        job = Dream(self.store).prepare([self.capture()])
        snapshot = Path(job['snapshot'])
        value = json.loads(snapshot.read_text())
        value['inputs'].clear()
        snapshot.write_text(json.dumps(value))
        with self.assertRaises(MemoryFailure):
            Dream(self.store).finish(job['id'])

    def test_structured_conflict_cannot_create_a_proposal(self):
        records = [self.record('first'), self.record('second')]
        records[0]['claim'] = {'key': 'api.enabled', 'value': True}
        records[1]['claim'] = {'key': 'api.enabled', 'value': False}
        candidates = [self.store.remember(record)['id'] for record in records]
        with self.assertRaises(MemoryFailure):
            self.store.propose(candidates)
        self.assertFalse((self.root / '.harness/memory/records').exists())

    def test_capture_baseline_is_checked_before_propose(self):
        candidate = self.capture()
        self.write('.harness/memory/records/first.json', json.dumps(self.record(text='Edit after capture')))
        with self.assertRaises(MemoryFailure):
            self.store.propose([candidate])

    def test_private_purge_preserves_unrelated_proposal(self):
        first, second = self.capture('first'), self.capture('second')
        self.store.propose([first])
        unrelated = self.store.propose([second])
        self.store.forget(first, 'remove selected item', private=True)
        self.assertTrue(Path(unrelated['preview']).exists())
        self.assertEqual([second], [c['id'] for c in self.store.candidates()])

    def test_dream_cannot_silently_change_scope(self):
        candidate = self.capture()
        job = Dream(self.store).prepare([candidate])
        changed = self.record('synthesis')
        changed['scope']['paths'] = ['src/**']
        with self.assertRaises(MemoryFailure):
            Dream(self.store).finish(job['id'], {'records': [changed],
                'dispositions': [{'input': 'candidate:' + candidate, 'action': 'mapped', 'outputs': ['synthesis']}],
                'provenance': {'synthesis': ['candidate:' + candidate]}})

    def test_dream_conflicting_candidates_with_same_identity_are_reported(self):
        first = self.record()
        first['claim'] = {'key': 'setting', 'value': True}
        second = self.record(text='Incompatible source')
        second['claim'] = {'key': 'setting', 'value': False}
        candidates = [self.store.remember(record)['id'] for record in (first, second)]
        dream = Dream(self.store)
        job = dream.prepare(candidates)
        self.assertEqual('needs-review', dream.finish(job['id'])['result'])

    def test_proposal_cannot_be_mutated_after_preview(self):
        proposal = self.store.propose([self.capture()])
        path = Path(proposal['preview']).parent / 'proposal.json'
        value = json.loads(path.read_text())
        value['changes']['first']['summary'] = 'Changed behind the preview'
        path.write_text(json.dumps(value))
        with self.assertRaises(MemoryFailure):
            self.store.apply(proposal['id'])

    def test_unattributed_restore_is_rejected_before_apply(self):
        proposal = self.store.propose([self.capture()])
        self.store.apply(proposal['id'])
        self.git('add', '.')
        self.git('commit', '-m', 'accept record before retirement')
        retirement = self.store.forget('first', 'withdraw')
        self.store.apply(retirement['id'])
        restore = self.store.remember(self.record())['id']
        with self.assertRaises(MemoryFailure) as caught:
            self.store.propose([restore])
        self.assertTrue(any(finding['reason'] == 'restore must name exact prior retirement hash'
                            for finding in caught.exception.details['findings']))

    def test_generation_not_published_when_editor_reverts_an_earlier_write(self):
        proposal = self.store.propose([self.capture('first'), self.capture('second')])
        from memory import store as module
        original = module._atomic_write
        def concurrent_revert(path, data):
            original(path, data)
            if Path(path) == self.root / '.harness/memory/records/second.json':
                (self.root / '.harness/memory/records/first.json').unlink()
        with patch.object(module, '_atomic_write', concurrent_revert):
            with self.assertRaises(MemoryFailure):
                self.store.apply(proposal['id'])
        self.assertFalse((self.repo.private / 'current-generation.json').exists())

    def test_dream_default_includes_only_current_session_candidates(self):
        candidate = self.capture()
        MemoryStore(self.repo, 'session-b').remember(self.record('private-other'))
        job = Dream(self.store).prepare()
        snapshot = json.loads(Path(job['snapshot']).read_text())
        self.assertEqual({'candidate:' + candidate}, set(snapshot['inputs']))
        report = json.loads(Path(job['report']).read_text())
        self.assertIn('output_contract', report)
        self.assertEqual({'records', 'dispositions', 'provenance'}, set(report['output_template']))

    def test_old_branch_candidate_cannot_reintroduce_known_withdrawal(self):
        proposal = self.store.propose([self.capture()])
        self.store.apply(proposal['id'])
        self.git('add', '.')
        self.git('commit', '-m', 'accepted record')
        self.git('branch', 'old')
        retirement = self.store.forget('first', 'withdrawn')
        self.store.apply(retirement['id'])
        self.git('add', '.')
        self.git('commit', '-m', 'accepted withdrawal')
        self.git('checkout', 'old')
        candidate = self.store.remember(self.record(), processing_id='old-branch-replay')['id']
        with self.assertRaises(MemoryFailure):
            self.store.propose([candidate])

    def test_unborn_repository_can_capture_and_propose_drafts(self):
        unborn = self.root / 'unborn'
        unborn.mkdir()
        subprocess.check_output(['git', '-C', str(unborn), 'init', '-b', 'main'], stderr=subprocess.STDOUT)
        repo = Repository(unborn)
        repo.initialize('refs/heads/main')
        store = MemoryStore(repo, 'new-session')
        record = self.record()
        record['scope']['repository'] = repo.policy()['repository_id']
        candidate = store.remember(record)
        self.assertIsNone(candidate['origin']['head'])
        proposal = store.propose([candidate['id']])
        self.assertEqual('ok', store.apply(proposal['id'])['status'])
        self.assertEqual([], repo.view()['records'])

    def test_interrupted_dream_preparation_resumes_same_snapshot(self):
        candidate = self.capture()
        from memory import dream as module
        original = module._save
        def interrupted(path, value):
            if Path(path).name == 'job.json':
                raise OSError('interrupted before checkpoint')
            original(path, value)
        with patch.object(module, '_save', interrupted):
            with self.assertRaises(OSError):
                Dream(self.store).prepare([candidate])
        snapshot = next((self.store.directory / 'jobs').glob('*/snapshot.json'))
        before = snapshot.read_bytes()
        job = Dream(self.store).prepare([candidate])
        self.assertEqual('queued', job['state'])
        self.assertEqual(before, Path(job['snapshot']).read_bytes())

    def test_dream_rejects_unavailable_accepted_generation(self):
        for key, value in [('first', True), ('second', False)]:
            record = self.record(key)
            record['claim'] = {'key': 'same-claim', 'value': value}
            self.write('.harness/memory/records/' + key + '.json', json.dumps(record))
        self.git('add', '.')
        self.git('commit', '-m', 'invalid accepted claims')
        with self.assertRaises(MemoryFailure):
            Dream(self.store).prepare([])

    def test_dream_reports_excluded_accepted_records(self):
        record = self.record()
        record['freshness']['expires_at'] = '2000-01-01T00:00:00Z'
        self.write('.harness/memory/records/first.json', json.dumps(record))
        self.git('add', '.')
        self.git('commit', '-m', 'expired accepted record')
        dream = Dream(self.store)
        job = dream.prepare([])
        report = json.loads(Path(job['report']).read_text())
        self.assertTrue(any(f.get('id') == 'first' for f in report['findings']))
        self.assertEqual('needs-review', dream.finish(job['id'])['result'])

    def test_private_policy_budgets_are_enforced(self):
        policy = self.repo.policy()
        policy['limits'] = {'candidate_count': 1, 'candidate_bytes': 65536, 'dream_bytes': 1}
        self.write('.harness/memory/config.json', json.dumps(policy))
        self.git('add', '.')
        self.git('commit', '-m', 'bounded private policy')
        self.capture()
        with self.assertRaises(MemoryFailure):
            self.capture('second')
        with self.assertRaises(MemoryFailure):
            Dream(self.store).prepare()


if __name__ == '__main__':
    unittest.main()
