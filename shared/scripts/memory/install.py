"""Copy memory runtime with hash-safe upgrades and explicitly owned hooks."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import uuid

from .errors import MemoryFailure


EVENTS = ('SessionStart', 'UserPromptSubmit', 'PreToolUse', 'PostCompact')


def file_hash(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(root, relative):
    target = root / relative
    if target.is_symlink() or root not in target.resolve().parents:
        raise MemoryFailure('invalid', 'installation path escapes repository',
                            {'path': relative})
    return target


def write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.memory-' + uuid.uuid4().hex)
    try:
        with temp.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def adopt(repo, accepted_ref, readopt=False):
    """Installation/ordinary init preserves trust; replacing it is explicit."""
    if repo.anchor_path.exists() and not readopt:
        from .schema import load_json
        anchor = load_json(repo.anchor_path)
        if anchor.get('accepted_ref') != accepted_ref:
            raise MemoryFailure('conflict', 'Changing authority requires init --readopt')
        policy = repo.policy()  # Detect moved history/identity using the existing anchor.
        return {'status': 'ok', 'code': 0, 'anchor': anchor, 'policy': policy,
                'mode': 'existing', 'enforcement': 'unverified'}
    return repo.initialize(accepted_ref)


WORKFLOW = '''name: repository memory validation
on:
  pull_request:
permissions:
  contents: read
jobs:
  memory:
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          path: candidate
          fetch-depth: 0
          persist-credentials: false
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          ref: ${{ github.event.pull_request.base.sha }}
          path: trusted-validator
          fetch-depth: 0
          persist-credentials: false
      - name: Validate the result with the trusted base runtime
        shell: bash
        env:
          MEMORY_BASE: ${{ github.event.pull_request.base.sha }}
          MEMORY_RESULT: ${{ github.sha }}
        run: |
          if [ ! -f trusted-validator/scripts/memory/cli.py ]; then
            echo "Memory validator unavailable at trusted base; bootstrap requires review."
            exit 2
          fi
          python3 trusted-validator/scripts/memory/cli.py --root candidate check --ci --base "$MEMORY_BASE" --result "$MEMORY_RESULT"
'''


def _settings(data, owned):
    if not isinstance(data, dict) or not isinstance(data.get('hooks', {}), dict):
        raise MemoryFailure('invalid', 'settings hooks must be an object')
    if not isinstance(owned, dict) or any(not isinstance(v, str) for v in owned.values()):
        raise MemoryFailure('invalid', 'vendor hook identities must be strings')
    cfg = copy.deepcopy(data)
    hooks = cfg.setdefault('hooks', {})
    # Validate all entries before any file changes, including custom events.
    for entries in hooks.values():
        if not isinstance(entries, list):
            raise MemoryFailure('invalid', 'hook event must contain a list')
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get('hooks'), list):
                raise MemoryFailure('invalid', 'hook entry must contain a hooks list')
            if any(not isinstance(h, dict) for h in entry['hooks']):
                raise MemoryFailure('invalid', 'individual hooks must be objects')
    commands = {}
    for event in EVENTS:
        command = 'python3 "${CLAUDE_PROJECT_DIR}/scripts/memory/host.py" --event ' + event + ' --timeout 5'
        commands[event] = command
        entries = hooks.setdefault(event, [])
        previous = owned.get(event)
        if previous and previous != command:
            for entry in entries:
                entry['hooks'] = [h for h in entry['hooks'] if h.get('command') != previous]
            entries[:] = [entry for entry in entries if entry['hooks']]
        if not any(h.get('command') == command for entry in entries for h in entry['hooks']):
            matcher = 'Write|Edit|MultiEdit|NotebookEdit' if event == 'PreToolUse' else '*'
            entries.append({'matcher': matcher, 'hooks': [
                {'type': 'command', 'command': command, 'timeout': 7}]})
    return (json.dumps(cfg, indent=2) + '\n').encode(), commands


def _bytes(path):
    return path.read_bytes() if path.exists() else None


def _restore(entries):
    """Restore only our exact intended bytes; preserve unrelated external edits."""
    for target, before, after in reversed(entries):
        current = _bytes(target)
        if current == before:
            continue
        if current != after:
            raise MemoryFailure('conflict', 'Installation recovery found an external edit',
                                {'path': str(target)})
        if before is None:
            target.unlink()
        else:
            write_atomic(target, before)


def _journal_entries(repo, rows):
    entries = []
    for row in rows:
        root = repo.root if row['domain'] == 'root' else repo.private
        target = safe_path(root, row['path'])
        before = base64.b64decode(row['before']) if row['before'] is not None else None
        after = base64.b64decode(row['after']) if row['after'] is not None else None
        entries.append((target, before, after))
    return entries


def _save_journal(repo, journal, entries, pending=False):
    rows = []
    for target, before, after in entries:
        domain = 'root' if repo.root in target.parents else 'private'
        root = repo.root if domain == 'root' else repo.private
        rows.append({'domain': domain, 'path': target.relative_to(root).as_posix(),
                     'before': base64.b64encode(before).decode() if before is not None else None,
                     'after': base64.b64encode(after).decode() if after is not None else None})
    write_atomic(journal, json.dumps({'version': 1, 'adoption_pending': pending, 'files': rows}).encode())


def install(repo, source=None, wire_hooks=True, accepted_ref=None):
    from .store import _locked
    with _locked(repo):
        return _install(repo, source, wire_hooks, accepted_ref)


def _install(repo, source, wire_hooks, accepted_ref):
    from .schema import load_json
    source = Path(source or Path(__file__).parent).resolve()
    root = repo.root
    journal = repo.private / 'install' / 'transaction.json'
    if journal.exists():
        pending = load_json(journal)
        if pending.get('adoption_pending'):
            raise MemoryFailure('unjudged', 'Installation interrupted during adoption; inspect private install journal before recovery')
        _restore(_journal_entries(repo, pending['files']))
        journal.unlink()
    manifest_path = safe_path(root, '.harness/memory/vendor.json')
    old = load_json(manifest_path) if manifest_path.exists() else {}
    if not isinstance(old, dict) or not isinstance(old.get('files', {}), dict):
        raise MemoryFailure('invalid', 'invalid vendor manifest')
    files = {f'scripts/memory/{p.name}': p.read_bytes()
             for p in sorted(source.glob('*.py')) if not p.is_symlink()}
    skill = source.parent.parent / 'skills' / 'project-memory' / 'SKILL.md'
    if skill.is_file():
        files['.claude/skills/project-memory/SKILL.md'] = skill.read_bytes()
    changes, conflicts, entries = [], [], []
    hashes = dict(old.get('files', {}))
    for name, data in files.items():
        path = safe_path(root, name)
        current = path.read_bytes() if path.exists() else None
        if current is not None and current != data and file_hash(current) != hashes.get(name):
            conflicts.append({'path': name, 'reason': 'local changes preserved'})
            continue
        if current != data:
            entries.append((path, current, data))
            changes.append(name)
        hashes[name] = file_hash(data)
    commands = {}
    if wire_hooks:
        settings = safe_path(root, '.claude/settings.json')
        cfg = load_json(settings) if settings.exists() else {}
        data, commands = _settings(cfg, old.get('hooks', {}))
        if _bytes(settings) != data:
            entries.append((settings, _bytes(settings), data))
            changes.append('.claude/settings.json')
    if conflicts:
        return {'status': 'conflict', 'code': 1, 'changed': [], 'conflicts': conflicts,
                'hooks': 'unchanged', 'ci': 'not-verified'}
    manifest = {'schema_version': 1, 'runtime_version': 1, 'files': hashes,
                'hooks': commands or old.get('hooks', {})}
    data = (json.dumps(manifest, indent=2) + '\n').encode()
    if _bytes(manifest_path) != data:
        entries.append((manifest_path, _bytes(manifest_path), data))
    workflow = repo.private / 'install' / 'memory-validation.yml'
    entries.append((workflow, _bytes(workflow), WORKFLOW.encode()))
    adoption = None
    if accepted_ref and repo.anchor_path.exists():
        adoption = adopt(repo, accepted_ref)  # No anchor writes on normal upgrades.
    # Durable rollback journal plus complete preflight avoids mixed generations.
    _save_journal(repo, journal, entries)
    try:
        if accepted_ref and not repo.anchor_path.exists():
            config = safe_path(root, '.harness/memory/config.json')
            before_config = _bytes(config)
            _save_journal(repo, journal, entries, pending=True)
            try:
                adoption = adopt(repo, accepted_ref)
            finally:
                for target, before in ((config, before_config), (repo.anchor_path, None)):
                    if _bytes(target) != before:
                        entries.append((target, before, _bytes(target)))
                _save_journal(repo, journal, entries)
        for target, before, after in entries:
            current = _bytes(target)
            if current == after:
                continue
            if current != before:
                raise MemoryFailure('conflict', 'Installation destination changed during preflight', {'path': str(target)})
            write_atomic(target, after)
        journal.unlink()
    except BaseException:
        _restore(entries)
        journal.unlink(missing_ok=True)
        raise
    return {'status': 'ok', 'code': 0, 'changed': changes,
            'conflicts': [], 'manifest': str(manifest_path), 'adoption': adoption,
            'ci_proposal': str(workflow), 'ci_target': '.github/workflows/memory-validation.yml',
            'ci': 'review-required',
            'hooks': 'wired-not-host-verified' if commands else 'unchanged'}
