"""Acceptance tests use independent real Git histories, never fake repository objects."""
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-b', 'main')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Test')
        try:
            self.schema = importlib.import_module('memory.schema')
            self.repo_module = importlib.import_module('memory.repository')
            self.evidence = importlib.import_module('memory.evidence')
            self.retrieve = importlib.import_module('memory.retrieve')
            self.failure = importlib.import_module('memory.errors').MemoryFailure
        except ImportError as exc:
            self.fail('Foundation runtime missing: ' + str(exc))
        self.policy = {'schema_version': 1, 'repository_id': 'fixture',
                       'accepted_ref': 'refs/heads/main', 'review': {'mode': 'git-review'}}
        self.write('.harness/memory/config.json', self.policy)
        self.write('src/code.txt', b'original source\n')
        self.commit('initial policy')
        self.repo = self.repo_module.Repository(self.root)
        self.repo.initialize('refs/heads/main')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.STDOUT).decode().strip()

    def write(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode())

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-m', message)
        return self.git('rev-parse', 'HEAD')

    def record(self, record_id='fact', **changes):
        value = {'schema_version': 1, 'id': record_id, 'kind': 'decision', 'title': 'Use Unicode 标准',
                 'summary': 'Team decision on source encoding', 'body': ['Use UTF-8.'],
                 'scope': {'repository': 'fixture', 'paths': ['**'], 'tags': []},
                 'evidence': [{'type': 'decision', 'reason': 'Reviewed team decision'}],
                 'freshness': {'dependencies': []}, 'state': 'active'}
        value.update(changes)
        return value

    def accept(self, record):
        self.write('.harness/memory/records/' + record['id'] + '.json', record)
        return self.commit('accept ' + record['id'])

    def test_branch_and_dirty_records_never_become_accepted(self):
        self.accept(self.record())
        self.git('checkout', '-b', 'topic')
        self.accept(self.record('branch'))
        self.assertEqual(['fact'], [r['id'] for r in self.repo.view()['records']])
        self.write('.harness/memory/records/fact.json', self.record(body=['Unreviewed edit']))
        self.assertEqual([], self.repo.view()['records'])

    def test_branch_cannot_rewrite_acceptance_policy(self):
        self.accept(self.record())
        self.git('checkout', '-b', 'topic')
        self.policy['accepted_ref'] = 'refs/heads/topic'
        self.write('.harness/memory/config.json', self.policy)
        self.accept(self.record('unreviewed'))
        self.assertEqual('refs/heads/main', self.repo.policy()['accepted_ref'])
        self.assertEqual(['fact'], [r['id'] for r in self.repo.view()['records']])

    def test_new_clone_requires_explicit_adoption(self):
        self.accept(self.record())
        with tempfile.TemporaryDirectory() as destination:
            subprocess.check_output(['git', 'clone', str(self.root), destination], stderr=subprocess.STDOUT)
            clone = self.repo_module.Repository(destination)
            self.assertEqual('unjudged', clone.view()['status'])
            clone.initialize('refs/heads/main')
            self.assertEqual(['fact'], [r['id'] for r in clone.view()['records']])

    def test_latest_retirement_suppresses_old_checkout_and_restore_is_version_bound(self):
        record = self.record()
        old = self.accept(record)
        tombstone = {'schema_version': 1, 'id': 'fact', 'state': 'retired',
                     'retirement': {'previous_record_hash': self.schema.digest(record), 'reason': 'obsolete'}}
        self.accept(tombstone)
        self.git('checkout', '--detach', old)
        self.assertEqual([], self.repo.view()['records'])
        self.git('checkout', 'main')
        restored = self.record(body=['New reviewed replacement'], restores={
            'retirement_record_hash': self.schema.digest(tombstone), 'reason': 'reassessed'})
        self.accept(restored)
        self.git('checkout', '--detach', old)
        self.assertEqual([], self.repo.view()['records'])
        self.git('checkout', 'main')
        self.assertEqual([restored], self.repo.view()['records'])

    def test_source_change_is_stale_and_receipt_pins_source(self):
        source_digest = hashlib.sha256(b'original source\n').hexdigest()
        record = self.record(target={'path': 'src/code.txt', 'content_digest': source_digest})
        del record['body']
        accepted = self.accept(record)
        view = self.repo.view()
        self.assertEqual([record], view['records'])
        self.assertEqual(accepted, view['receipt']['accepted_ancestor'])
        self.write('src/code.txt', b'changed source\n')
        view = self.repo.view()
        self.assertEqual([], view['records'])
        self.assertTrue(any(x['status'] == 'stale' for x in view['excluded']))

    def test_strict_json_schema_paths_and_nested_secret_scan(self):
        for bad in (b'{"id":"a","id":"b"}', b'{"a":NaN}', b'\xff'):
            with self.assertRaises(self.failure):
                self.schema.parse_json(bad)
        for changes in ({'id': '../escape'}, {'id': 'CON'}, {'unexpected': True}, {'body': ['x' * 4097]},
                        {'scope': {'repository': 'fixture', 'paths': ['src/../secrets']}},
                        {'evidence': [{'type': 'repository', 'path': 'src/code.txt', 'content_digest': 'a' * 64, 'object_id': 3}]},
                        {'evidence': [{'type': 'external', 'url': 'http://[', 'content_digest': 'a' * 64, 'observed_at': '2026-01-01'}]},
                        {'evidence': [{'type': 'decision', 'reason': 'ghp_' + 'A' * 36}]}):
            with self.assertRaises(self.failure):
                self.schema.validate_record(self.record(**changes))

    def test_conflicting_claims_checked_in_merge_result(self):
        base = self.accept(self.record('one', claim={'key': 'encoding', 'value': 'utf8'}))
        self.git('checkout', '-b', 'topic')
        result = self.accept(self.record('two', claim={'key': 'encoding', 'value': 'ascii'}))
        checked = self.evidence.validate_tree(self.repo, base, result)
        self.assertEqual(1, checked['code'])
        self.assertEqual('conflict', checked['status'])
        self.assertTrue(checked['findings'])

    def test_tombstone_deletion_and_unattributed_restore_rejected(self):
        original = self.record()
        self.accept(original)
        tombstone = {'schema_version': 1, 'id': 'fact', 'state': 'retired', 'retirement': {
            'previous_record_hash': self.schema.digest(original), 'reason': 'withdrawn'}}
        base = self.accept(tombstone)
        self.git('checkout', '-b', 'topic')
        (self.root / '.harness/memory/records/fact.json').unlink()
        deleted = self.commit('delete tombstone')
        self.assertEqual(1, self.evidence.validate_tree(self.repo, base, deleted)['code'])
        result = self.accept(original)
        self.assertEqual(1, self.evidence.validate_tree(self.repo, base, result)['code'])
        original['restores'] = {'retirement_record_hash': self.schema.digest(tombstone), 'reason': 'reviewed'}
        result = self.accept(original)
        self.assertEqual(0, self.evidence.validate_tree(self.repo, base, result)['code'])
        self.assertEqual(2, self.evidence.validate_tree(self.repo, None, result)['code'])

    def test_environment_missing_is_unjudged_and_disjoint_claims_valid(self):
        a = self.record('one', claim={'key': 'mode', 'value': 'a'})
        a['scope']['environment'] = {'os': ['linux']}
        self.accept(a)
        self.assertEqual([], self.repo.view()['records'])
        self.assertEqual([a], self.repo.view({'os': 'linux'})['records'])
        b = self.record('two', claim={'key': 'mode', 'value': 'b'})
        b['scope']['environment'] = {'os': ['windows']}
        self.assertEqual([], self.schema.validate_generation([a, b], self.policy))

    def test_unicode_budget_and_stable_ranking(self):
        self.accept(self.record('aaa'))
        self.accept(self.record('bbb'))
        recall = self.retrieve.recall(self.repo, query='标准', budget=250)
        self.assertLessEqual(len(recall['text'].encode('utf-8')), 250)
        self.assertIn('reference data', recall['text'])
        self.assertIn(recall['receipt']['accepted_ancestor'], recall['text'])
        self.assertEqual(recall['text'], self.retrieve.recall(self.repo, query='标准', budget=250)['text'])
        self.assertEqual('aaa', recall['records'][0]['id'])

    def test_unrelated_or_missing_authority_is_unjudged(self):
        self.repo.git('update-ref', '-d', 'refs/heads/main')
        self.assertEqual('unjudged', self.repo.view()['status'])

    def test_unrelated_query_abstains(self):
        self.accept(self.record())
        self.assertEqual([], self.retrieve.recall(self.repo, query='unrelated-quasar')['records'])

    def test_first_adoption_creates_draft_policy_until_integration(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.check_output(['git', 'init', '-b', 'main', directory], stderr=subprocess.STDOUT)
            repo = self.repo_module.Repository(directory)
            initialized = repo.initialize('refs/heads/main')
            self.assertEqual('draft-only', initialized['mode'])
            self.assertEqual([], repo.view()['records'])
            self.assertTrue((Path(directory) / '.harness/memory/config.json').is_file())
            self.assertTrue(repo.policy()['repository_id'])

    def test_new_clone_can_explicitly_adopt_remote_tracking_alias(self):
        self.accept(self.record())
        with tempfile.TemporaryDirectory() as destination:
            subprocess.check_output(['git', 'clone', str(self.root), destination], stderr=subprocess.STDOUT)
            clone = self.repo_module.Repository(destination)
            clone.initialize('refs/remotes/origin/main')
            self.assertEqual(['fact'], [r['id'] for r in clone.view()['records']])

    def test_shared_transition_rejects_wrong_retirement_parent(self):
        record = self.record()
        tombstone = {'schema_version': 1, 'id': 'fact', 'state': 'retired', 'retirement': {
            'previous_record_hash': '0' * 64, 'reason': 'withdrawn'}}
        helper = getattr(self.schema, 'validate_transition', None)
        self.assertIsNotNone(helper, 'Shared lifecycle validator missing')
        self.assertTrue(helper({'fact': record}, {'fact': tombstone}))
        tombstone['retirement']['previous_record_hash'] = 'sha256:' + self.schema.digest(record)
        self.assertFalse(helper({'fact': record}, {'fact': tombstone}))
        restored = self.record(restores={'retirement_record_hash': 'sha256:' + self.schema.digest(tombstone), 'reason': 'reviewed'})
        self.assertFalse(helper({'fact': tombstone}, {'fact': restored}))

    def test_old_gate_base_cannot_bypass_latest_retirement(self):
        original = self.record()
        base = self.accept(original)
        self.git('checkout', '-b', 'topic')
        proposed = self.accept(self.record('other'))
        self.git('checkout', 'main')
        self.accept({'schema_version': 1, 'id': 'fact', 'state': 'retired', 'retirement': {
            'previous_record_hash': self.schema.digest(original), 'reason': 'withdrawn'}})
        gate = self.evidence.validate_tree(self.repo, base, proposed)
        self.assertNotEqual(0, gate['code'])

    def test_gate_reads_result_sources_not_dirty_checkout(self):
        base = self.git('rev-parse', 'HEAD')
        source_digest = hashlib.sha256(b'original source\n').hexdigest()
        record = self.record(target={'path': 'src/code.txt', 'content_digest': source_digest})
        del record['body']
        self.git('checkout', '-b', 'topic')
        result = self.accept(record)
        self.write('src/code.txt', b'unrelated dirty content')
        self.assertEqual(0, self.evidence.validate_tree(self.repo, base, result)['code'])

    def test_expiry_external_unknown_and_bad_pinned_revision_are_not_fresh(self):
        expired = self.record(freshness={'dependencies': [], 'expires_at': '2000-01-01T00:00:00Z'})
        self.accept(expired)
        self.assertEqual([], self.repo.view()['records'])
        record = self.record('external', evidence=[{'type': 'external', 'url': 'https://example.invalid/source',
                             'content_digest': 'a' * 64, 'observed_at': '2026-01-01T00:00:00Z'}])
        self.accept(record)
        self.assertTrue(any(x['id'] == 'external' and x['status'] == 'unjudged' for x in self.repo.view()['excluded']))

    def test_missing_git_revision_is_unjudged(self):
        with self.assertRaises(self.failure) as caught:
            self.repo.resolve('a' * 40)
        self.assertEqual('unjudged', caught.exception.status)

    def test_record_aliases_and_supersession_cycles_are_rejected(self):
        first = self.record('first', supersedes=['second'], replacement_reason='replace')
        second = self.record('second', supersedes=['first'], replacement_reason='replace')
        self.assertTrue(self.schema.validate_generation([first, second], self.policy))
        self.assertTrue(self.schema.validate_generation([self.record('Fact'), self.record('fact')], self.policy))
        first = self.record('first', claim={'key': 'mode', 'value': 'one'})
        second = self.record('second', claim={'key': 'mode', 'value': 'two'})
        first['scope']['paths'] = ['SRC/**']
        second['scope']['paths'] = ['src/code.txt']
        findings = self.schema.validate_generation([first, second], self.policy)
        self.assertTrue(any(f['status'] == 'unjudged' for f in findings))

    def test_ci_explicit_base_is_ephemeral_and_uses_prior_policy(self):
        base = self.git('rev-parse', 'HEAD')
        self.git('checkout', '-b', 'topic')
        result = self.accept(self.record())
        self.repo.anchor_path.unlink()
        helper = getattr(self.repo, 'for_ci', None)
        self.assertIsNotNone(helper, 'Ephemeral CI authority API missing')
        ci = helper(base)
        self.assertEqual(0, self.evidence.validate_tree(ci, base, result)['code'])
        self.assertFalse(self.repo.anchor_path.exists())

    def test_clean_crlf_checkout_preserves_git_source_identity(self):
        self.git('config', 'core.autocrlf', 'true')
        target = self.root / 'src/code.txt'
        target.unlink()
        self.git('checkout', 'HEAD', '--', 'src/code.txt')
        self.assertEqual(b'original source\r\n', target.read_bytes())
        source_digest = hashlib.sha256(b'original source\n').hexdigest()
        record = self.record(target={'path': 'src/code.txt', 'content_digest': source_digest})
        del record['body']
        self.accept(record)
        self.assertEqual([record], self.repo.view()['records'])
        target.write_bytes(b'actually changed\r\n')
        self.assertEqual([], self.repo.view()['records'])

    def test_clean_crlf_record_checkout_is_not_a_dirty_proposal(self):
        self.git('config', 'core.autocrlf', 'true')
        record = self.record()
        path = self.root / '.harness/memory/records/fact.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(json.dumps(record, ensure_ascii=False, indent=2).encode('utf-8') + b'\n')
        self.commit('accepted formatted record')
        path.unlink()
        self.git('checkout', 'HEAD', '--', '.harness/memory/records/fact.json')
        self.assertIn(b'\r\n', path.read_bytes())
        self.assertEqual('', self.git('status', '--porcelain'))
        self.assertEqual([record], self.repo.view()['records'])
        record['body'] = ['Actual unreviewed edit']
        path.write_bytes(json.dumps(record, ensure_ascii=False, indent=2).encode('utf-8'))
        self.assertEqual([], self.repo.view()['records'])

    def test_test_observation_survives_memory_only_commit(self):
        self.write('test-result.txt', b'passed\n')
        tested = self.commit('tested code and artifact')
        record = self.record(evidence=[{'type': 'test', 'revision': tested, 'command': 'unit-test',
                             'artifact_digest': hashlib.sha256(b'passed\n').hexdigest(), 'path': 'test-result.txt'}])
        self.accept(record)
        self.assertEqual([record], self.repo.view()['records'])
        self.write('src/code.txt', b'changed\n')
        self.commit('change tested code')
        self.assertEqual([], self.repo.view()['records'])

    def test_structured_recall_response_has_independent_hard_limit(self):
        for index in range(70):
            record = self.record('large-%03d' % index, evidence=[{'type': 'decision', 'reason': str(n) + 'x' * 1000} for n in range(16)])
            self.write('.harness/memory/records/' + record['id'] + '.json', record)
        self.commit('accepted large provenance generation')
        response = self.retrieve.recall(self.repo, budget=65536)
        self.assertIn('serialized_return_limit', response)
        self.assertLessEqual(len(self.schema.canonical_bytes(response)), response['serialized_return_limit'])
        self.assertGreater(response['metadata_budget_omitted'], 0)
        again = self.retrieve.recall(self.repo, budget=65536)
        self.assertEqual([r['id'] for r in response['records']], [r['id'] for r in again['records']])

    def test_authority_observation_refresh_preserves_trust_anchor(self):
        self.accept(self.record())
        anchor = self.schema.load_json(self.repo.anchor_path)
        anchor['observed_at'] = '2000-01-01T00:00:00+00:00'
        self.repo.anchor_path.write_bytes(self.schema.canonical_bytes(anchor))
        tip = self.repo.resolve('refs/heads/main')
        refreshed = self.repo.observe_authority(expected_tip=tip)
        current = self.schema.load_json(self.repo.anchor_path)
        self.assertEqual('ok', refreshed['status'])
        self.assertNotEqual(anchor['observed_at'], current['observed_at'])
        self.assertEqual({k: v for k, v in anchor.items() if k != 'observed_at'},
                         {k: v for k, v in current.items() if k != 'observed_at'})
        with self.assertRaises(self.failure):
            self.repo.observe_authority(expected_tip=anchor['accepted_oid'])


if __name__ == '__main__':
    unittest.main()
