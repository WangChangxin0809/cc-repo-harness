"""Exercise the shipped CLI and installer in repositories without the plugin."""
from __future__ import annotations

import json
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project with spaces'
        self.root.mkdir()
        self.git('init', '-b', 'main')
        self.git('config', 'user.email', 'memory@example.invalid')
        self.git('config', 'user.name', 'Memory fixture')
        (self.root / 'README.md').write_text('Fixture\n', encoding='utf-8')
        self.commit('initial')

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, check=True,
                              capture_output=True).stdout.decode().strip()

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-m', message)

    def cli(self, *args, code=0, installed=False):
        entry = self.root / 'scripts/memory/cli.py' if installed else HERE / 'cli.py'
        result = subprocess.run([sys.executable, str(entry), '--root', str(self.root),
                                 *args], capture_output=True, text=True,
                                encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_installed_runtime_survives_plugin_removal_and_preserves_hooks(self):
        settings = self.root / '.claude/settings.json'
        settings.parent.mkdir()
        settings.write_text(json.dumps({'hooks': {'SessionStart': [
            {'hooks': [{'type': 'command', 'command': 'custom-context'}]}]}}))
        self.cli('install', '--accepted-ref', 'refs/heads/main')
        self.cli('install', '--accepted-ref', 'refs/heads/main')
        data = json.loads(settings.read_text())
        commands = [h['command'] for event in data['hooks'].values()
                    for item in event for h in item['hooks']]
        self.assertEqual(commands.count('custom-context'), 1)
        self.assertEqual(len(commands), len(set(commands)))
        self.commit('adopt installed memory')
        result = self.cli('inspect', installed=True)
        self.assertIn('policy', result)

    def test_installer_preserves_custom_runtime_and_reports_conflict(self):
        self.cli('install', '--accepted-ref', 'refs/heads/main')
        target = self.root / 'scripts/memory/host.py'
        target.write_text('# custom host\n', encoding='utf-8')
        result = self.cli('install', '--accepted-ref', 'refs/heads/main', code=1)
        self.assertEqual(result['status'], 'conflict')
        self.assertEqual(target.read_text(), '# custom host\n')

    def test_teacher_to_new_clone_requires_acceptance(self):
        self.cli('install', '--accepted-ref', 'refs/heads/main')
        self.commit('adopt memory')
        candidate = self.cli('--session', 'teacher', 'remember', '--title', 'Keep v1',
                             '--body', 'Keep the v1 endpoint until migration finishes.',
                             '--path', 'src/api/**', '--reason', 'Team compatibility decision')
        before = self.cli('recall', '--query', 'v1', '--path', 'src/api/server.py')
        self.assertEqual(before['records'], [])
        proposal = self.cli('--session', 'teacher', 'propose', candidate['id'])
        self.cli('--session', 'teacher', 'apply', proposal['id'])
        self.assertEqual(self.cli('recall', '--query', 'v1')['records'], [])
        self.commit('accept compatibility decision')
        clone = Path(self.temp.name) / 'fresh clone'
        self.git('clone', str(self.root), str(clone))
        self.root = clone
        self.cli('init', '--accepted-ref', 'refs/remotes/origin/main', installed=True)
        recalled = self.cli('recall', '--query', 'v1', '--path', 'src/api/server.py',
                            installed=True)
        self.assertEqual(len(recalled['records']), 1)
        self.assertIn('Keep the v1 endpoint', recalled['text'])

    def test_dream_is_a_private_reviewable_job(self):
        self.cli('init', '--accepted-ref', 'refs/heads/main')
        self.commit('adopt memory')
        self.cli('--session', 'teacher', 'remember', '--title', 'Keep v1',
                 '--body', 'Keep v1.', '--reason', 'Team decision')
        job = self.cli('--session', 'teacher', 'dream', 'prepare')
        result = self.cli('--session', 'teacher', 'dream', 'inspect', job['id'])
        self.assertIn('state', result)
        self.assertEqual(self.cli('recall', '--query', 'v1')['records'], [])
        tracked = self.git('status', '--porcelain')
        self.assertNotIn('candidate', tracked)
        self.assertNotIn('snapshot', tracked)

    def test_merge_gate_demands_a_trusted_base(self):
        self.cli('init', '--accepted-ref', 'refs/heads/main')
        self.cli('check', code=2)

    def test_host_context_is_bounded_and_compaction_can_redeliver(self):
        self.cli('install', '--accepted-ref', 'refs/heads/main')
        self.commit('adopt memory')
        host = self.root / 'scripts/memory/host.py'
        def invoke(event, **extra):
            p = subprocess.run([sys.executable, str(host), '--timeout', '15'], input=json.dumps({
                'cwd': str(self.root), 'hook_event_name': event,
                'session_id': 'host-session', **extra}),
                capture_output=True, text=True, encoding='utf-8', timeout=18)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertLessEqual(len(p.stdout.encode()), 8192)
            return p.stdout
        self.assertIn('memory', invoke('SessionStart').lower())
        self.assertEqual(invoke('UserPromptSubmit', prompt='unrelated'), '')
        invoke('PostCompact')
        self.assertIn('memory', invoke('SessionStart', source='compact').lower())

    def test_sync_does_not_merge_or_touch_worktree(self):
        self.cli('init', '--accepted-ref', 'refs/heads/main')
        self.commit('adopt memory')
        before = self.git('rev-parse', 'HEAD')
        result = self.cli('sync')
        self.assertIn('receipt', result)
        self.assertEqual(self.git('rev-parse', 'HEAD'), before)
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_invalid_record_returns_diagnostic_not_traceback(self):
        self.cli('init', '--accepted-ref', 'refs/heads/main')
        bad = Path(self.temp.name) / 'bad.json'
        bad.write_text('{"id":"one","id":"two"}', encoding='utf-8')
        result = self.cli('remember', '--record', str(bad), code=1)
        self.assertEqual(result['status'], 'invalid')

    def accepted_record(self, record_id, environment=None):
        from memory.repository import Repository
        record = {'schema_version': 1, 'id': record_id, 'kind': 'constraint',
                  'title': 'Compatibility ' + record_id, 'summary': 'Preserve compatibility',
                  'body': ['Keep the supported interface.'], 'state': 'active',
                  'scope': {'repository': Repository(self.root).policy()['repository_id'],
                            'paths': ['**'], 'environment': environment or {}},
                  'evidence': [{'type': 'decision', 'reason': 'Team decision'}],
                  'freshness': {'dependencies': []}}
        directory = self.root / '.harness/memory/records'
        directory.mkdir(exist_ok=True)
        (directory / (record_id + '.json')).write_text(json.dumps(record))
        return record

    def test_partial_applicability_preserves_cli_exit_two(self):
        self.cli('init', '--accepted-ref', 'refs/heads/main')
        self.commit('policy')
        self.accepted_record('known')
        self.accepted_record('unknown', {'platform': ['linux']})
        self.commit('reviewed records')
        result = self.cli('recall', code=2)
        self.assertEqual(len(result['records']), 1)
        self.assertEqual(result['code'], 2)
        self.cli('inspect', code=2)
        self.cli('sync', code=2)
        self.cli('recall', '--environment', '[]', code=1)

    def test_required_unavailable_adapter_is_not_a_green_doctor(self):
        self.cli('init', '--accepted-ref', 'refs/heads/main')
        config = self.root / '.harness/memory/config.json'
        policy = json.loads(config.read_text())
        policy['durable_private'] = {'required': True, 'profile': 'user-vault'}
        config.write_text(json.dumps(policy))
        self.commit('require durable vault')
        result = self.cli('doctor', code=2)
        self.assertIn('durable_private', json.dumps(result))

    def test_upgrade_conflict_preserves_complete_generation_and_anchor(self):
        from memory.install import install
        from memory.repository import Repository
        self.cli('init', '--accepted-ref', 'refs/heads/main')
        source = Path(self.temp.name) / 'vendor'
        source.mkdir()
        for name in ('a.py', 'z.py'):
            (source / name).write_text('VERSION = 1\n')
        repo = Repository(self.root)
        install(repo, source, wire_hooks=False)
        anchor = repo.anchor_path.read_bytes()
        manifest = (self.root / '.harness/memory/vendor.json').read_bytes()
        (self.root / 'scripts/memory/z.py').write_text('# customized\n')
        for name in ('a.py', 'z.py'):
            (source / name).write_text('VERSION = 2\n')
        result = install(repo, source, wire_hooks=False)
        self.assertEqual(result['status'], 'conflict')
        self.assertEqual((self.root / 'scripts/memory/a.py').read_text(), 'VERSION = 1\n')
        self.assertEqual(repo.anchor_path.read_bytes(), anchor)
        self.assertEqual((self.root / '.harness/memory/vendor.json').read_bytes(), manifest)

    def test_install_rejects_bad_settings_before_any_adoption_or_copy(self):
        settings = self.root / '.claude/settings.json'
        settings.parent.mkdir()
        settings.write_text('{"hooks":{"SessionStart":[null]}}')
        before = settings.read_bytes()
        self.cli('install', '--accepted-ref', 'refs/heads/main', code=1)
        self.assertEqual(settings.read_bytes(), before)
        self.assertFalse((self.root / 'scripts/memory').exists())
        self.assertFalse((self.root / '.git/harness-memory/adoption.json').exists())
        self.assertFalse((self.root / '.harness/memory/config.json').exists())

    def test_reinstall_does_not_refresh_or_rebind_trust(self):
        from memory.repository import Repository
        self.cli('install', '--accepted-ref', 'refs/heads/main')
        self.commit('adopt')
        repo = Repository(self.root)
        anchor = repo.anchor_path.read_bytes()
        self.cli('install', '--accepted-ref', 'refs/heads/main')
        self.assertEqual(repo.anchor_path.read_bytes(), anchor)
        config = self.root / '.harness/memory/config.json'
        policy = json.loads(config.read_text())
        policy['repository_id'] = 'different-repository'
        config.write_text(json.dumps(policy))
        self.commit('unexpected identity change')
        self.cli('install', '--accepted-ref', 'refs/heads/main', code=2)
        self.assertEqual(repo.anchor_path.read_bytes(), anchor)

    def test_ci_proposal_is_a_separate_trusted_base_workflow(self):
        ci = self.root / 'ci.sh'
        ci.write_text('#!/bin/sh\nexit 0\n')
        result = self.cli('install', '--accepted-ref', 'refs/heads/main')
        self.assertEqual(ci.read_text(), '#!/bin/sh\nexit 0\n')
        workflow = Path(result['ci_proposal']).read_text()
        self.assertIn('fetch-depth: 0', workflow)
        self.assertIn('github.event.pull_request.base.sha', workflow)
        self.assertIn('trusted-validator/scripts/memory/cli.py', workflow)
        self.assertIn('check --ci --base', workflow)
        self.assertNotIn('pull_request_target', workflow)

    def test_hook_withdrawal_notice_and_compaction_order(self):
        from memory.host import deliver
        self.cli('init', '--accepted-ref', 'refs/heads/main')
        self.commit('policy')
        active = {'status': 'ok', 'code': 0, 'records': [{'id': 'r1'}],
                  'text': '[r1] sensitive-old-body\n', 'receipt': {'accepted_tip': 'one'}}
        retired = {'status': 'empty', 'code': 0, 'records': [], 'text': '',
                   'excluded': [{'id': 'r1', 'status': 'stale', 'reason': 'retired'}],
                   'receipt': {'accepted_tip': 'two'}}
        payload = {'cwd': str(self.root), 'session_id': 'hook', 'hook_event_name': 'UserPromptSubmit'}
        with patch('memory.retrieve.recall', side_effect=[active, retired]):
            self.assertIn('sensitive-old-body', deliver(payload))
            notice = deliver(payload)
        self.assertIn('r1', notice)
        self.assertNotIn('sensitive-old-body', notice)
        self.assertIn('invalid', notice.lower())
        with patch('memory.retrieve.recall', return_value=active):
            compact = {**payload, 'session_id': 'compact'}
            self.assertTrue(deliver({**compact, 'hook_event_name': 'SessionStart', 'source': 'compact'}))
            deliver({**compact, 'hook_event_name': 'PostCompact'})
            self.assertEqual(deliver(compact), '')

    def test_real_accepted_record_reaches_prompt_hook(self):
        self.cli('init', '--accepted-ref', 'refs/heads/main')
        self.commit('policy')
        self.accepted_record('warm-delivery')
        self.commit('review accepted record')
        self.cli('recall', '--query', 'Compatibility')  # warm the disposable Git view
        start = time.monotonic()
        result = subprocess.run([sys.executable, str(HERE / 'host.py'), '--timeout', '15'],
            input=json.dumps({'cwd': str(self.root), 'session_id': 'real-hook',
                              'hook_event_name': 'UserPromptSubmit', 'prompt': 'Compatibility'}),
            text=True, capture_output=True, timeout=18)
        elapsed = time.monotonic() - start
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('warm-delivery', result.stdout, result.stderr)
        self.assertLess(elapsed, 17)
        print('real accepted-record warm hook (configured 15s cap): %.3fs' % elapsed)

    def test_ci_check_does_not_adopt_candidate_policy_or_persist_anchor(self):
        self.cli('init', '--accepted-ref', 'refs/heads/main')
        self.commit('policy')
        base = self.git('rev-parse', 'HEAD')
        clone = Path(self.temp.name) / 'ci-clone'
        self.git('clone', str(self.root), str(clone))
        self.root = clone
        config = clone / '.harness/memory/config.json'
        policy = json.loads(config.read_text())
        policy['repository_id'] = 'candidate-self-authorization'
        config.write_text(json.dumps(policy))
        self.git('config', 'user.email', 'memory@example.invalid')
        self.git('config', 'user.name', 'Memory fixture')
        self.commit('candidate policy')
        self.cli('check', '--ci', '--base', base, '--result', 'HEAD', code=1)
        self.assertFalse((clone / '.git/harness-memory/adoption.json').exists())

    def test_installer_rolls_back_an_interrupted_write(self):
        from memory import install as installer
        from memory.repository import Repository
        self.cli('init', '--accepted-ref', 'refs/heads/main')
        source = Path(self.temp.name) / 'vendor'
        source.mkdir()
        for name in ('a.py', 'z.py'):
            (source / name).write_text('VERSION = 1\n')
        repo = Repository(self.root)
        installer.install(repo, source, wire_hooks=False)
        for name in ('a.py', 'z.py'):
            (source / name).write_text('VERSION = 2\n')
        original = installer.write_atomic
        failed = []
        def fail_once(path, data):
            if path.name == 'z.py' and not failed:
                failed.append(True)
                raise OSError('planted installation interruption')
            return original(path, data)
        with patch.object(installer, 'write_atomic', side_effect=fail_once):
            with self.assertRaises(OSError):
                installer.install(repo, source, wire_hooks=False)
        self.assertEqual((self.root / 'scripts/memory/a.py').read_text(), 'VERSION = 1\n')
        self.assertEqual((self.root / 'scripts/memory/z.py').read_text(), 'VERSION = 1\n')

    def test_old_owned_hook_timeout_is_upgraded_as_one_identity(self):
        self.cli('install', '--accepted-ref', 'refs/heads/main')
        settings = self.root / '.claude/settings.json'
        manifest = self.root / '.harness/memory/vendor.json'
        cfg = json.loads(settings.read_text())
        vendor = json.loads(manifest.read_text())
        for event, command in list(vendor['hooks'].items()):
            legacy = command.replace(' --timeout 5', '')
            vendor['hooks'][event] = legacy
            for entry in cfg['hooks'][event]:
                for hook in entry['hooks']:
                    if hook.get('command') == command:
                        hook['command'], hook['timeout'] = legacy, 3
        settings.write_text(json.dumps(cfg))
        manifest.write_text(json.dumps(vendor))
        self.cli('install', '--accepted-ref', 'refs/heads/main')
        hooks = [hook for entries in json.loads(settings.read_text())['hooks'].values()
                 for entry in entries for hook in entry['hooks']]
        self.assertTrue(all(hook['timeout'] == 7 for hook in hooks))
        self.assertEqual(len(hooks), 4)

    def test_quick_remember_processing_id_replays_same_candidate(self):
        self.cli('init', '--accepted-ref', 'refs/heads/main')
        self.commit('policy')
        args = ('--session', 'replay', 'remember', '--title', 'Retry safe', '--body',
                'Preserve this decision.', '--reason', 'Team choice', '--processing-id', 'one')
        first = self.cli(*args)
        replay = self.cli(*args)
        self.assertEqual(first['id'], replay['id'])
        changed = list(args)
        changed[changed.index('Preserve this decision.')] = 'Different decision.'
        self.cli(*changed, code=1)

    def test_resume_preserves_delivered_inventory_for_invalidation(self):
        from memory.host import deliver
        active = {'status': 'ok', 'code': 0, 'records': [{'id': 'r1'}],
                  'text': '[r1] OLD_PRIVATE_MARKER\n', 'receipt': {'accepted_tip': 'one'}}
        retired = {'status': 'empty', 'code': 0, 'records': [], 'text': '',
                   'excluded': [{'id': 'r1', 'status': 'stale', 'reason': 'retired'}],
                   'receipt': {'accepted_tip': 'two'}}
        payload = {'cwd': str(self.root), 'session_id': 'resume', 'hook_event_name': 'SessionStart'}
        with patch('memory.retrieve.recall', side_effect=[active, retired]):
            self.assertIn('OLD_PRIVATE_MARKER', deliver({**payload, 'source': 'startup'}))
            resumed = deliver({**payload, 'source': 'resume'})
        self.assertIn('invalidation', resumed)
        self.assertIn('r1', resumed)
        self.assertNotIn('OLD_PRIVATE_MARKER', resumed)

    def test_timeout_notices_cover_prompt_and_tool_events(self):
        for event in ('SessionStart', 'UserPromptSubmit', 'PreToolUse'):
            result = subprocess.run([sys.executable, str(HERE / 'host.py'), '--timeout', '0.001'],
                input=json.dumps({'cwd': str(self.root), 'session_id': 'timeout-' + event,
                                  'hook_event_name': event, 'prompt': 'retry'}),
                text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0)
            self.assertIn('Do not reuse', result.stdout)
            self.assertLess(len(result.stdout.encode()), 1024)

    def test_sync_refreshes_only_bound_authority_without_reanchoring(self):
        from memory.repository import Repository
        self.cli('init', '--accepted-ref', 'refs/heads/main')
        config = self.root / '.harness/memory/config.json'
        policy = json.loads(config.read_text())
        policy['revocation'] = {'max_age_seconds': 60}
        config.write_text(json.dumps(policy))
        self.accepted_record('observed')
        self.commit('bounded observation')
        self.git('remote', 'add', 'origin', str(self.root))
        self.git('remote', 'add', 'unrelated', str(self.root))
        self.git('fetch', 'origin')
        self.git('branch', '--set-upstream-to=origin/main', 'main')
        repo = Repository(self.root)
        anchor = json.loads(repo.anchor_path.read_text())
        anchor['observed_at'] = '2000-01-01T00:00:00+00:00'
        repo.anchor_path.write_text(json.dumps(anchor))
        self.cli('sync', code=2)
        self.assertEqual(json.loads(repo.anchor_path.read_text()), anchor)
        self.cli('sync', '--remote', 'unrelated', code=2)
        self.assertEqual(json.loads(repo.anchor_path.read_text()), anchor)
        self.cli('sync', '--remote', 'origin')
        refreshed = json.loads(repo.anchor_path.read_text())
        self.assertNotEqual(refreshed.pop('observed_at'), anchor.pop('observed_at'))
        self.assertEqual(refreshed, anchor)
        self.assertEqual(len(self.cli('recall')['records']), 1)

    def test_timeout_terminates_worker_descendants(self):
        from memory import host
        ready, escaped = Path(self.temp.name) / 'ready', Path(self.temp.name) / 'escaped'
        child_code = ('import os,time; from pathlib import Path; '
                      'Path(%r).write_text(str(os.getpid())); time.sleep(5); Path(%r).write_text("alive")'
                      % (str(ready), str(escaped)))
        worker_code = ('import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",%r]); time.sleep(30)'
                       % child_code)
        original = subprocess.Popen
        def fixed_workload(command, *args, **kwargs):
            if '--worker' in command:
                command = [sys.executable, '-c', worker_code]
            return original(command, *args, **kwargs)
        payload = io.TextIOWrapper(io.BytesIO(json.dumps({'cwd': str(self.root),
            'hook_event_name': 'UserPromptSubmit', 'session_id': 'descendant'}).encode()))
        try:
            with patch('memory.host.subprocess.Popen', side_effect=fixed_workload), \
                    patch('sys.stdin', payload), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(host.main(['--timeout', '3']), 0)
            self.assertTrue(ready.exists(), 'fixed sleeping descendant must actually have started')
            time.sleep(3)
            self.assertFalse(escaped.exists(), 'worker descendant survived the timeout')
        finally:
            if ready.exists():
                child_pid = int(ready.read_text())
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(child_pid), '/T', '/F'],
                                   capture_output=True, timeout=2)
                else:
                    import signal
                    try:
                        os.kill(child_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass


if __name__ == '__main__':
    unittest.main()
