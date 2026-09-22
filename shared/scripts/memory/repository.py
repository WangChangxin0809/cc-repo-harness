"""Immutable Git authority plus an explicit private adoption anchor."""
import datetime
import copy
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unicodedata
import uuid

from .errors import MemoryFailure
from .schema import (canonical_bytes, digest, load_json, parse_json, safe_path,
                     validate_generation, validate_policy, validate_record, validate_transition)

CONFIG = '.harness/memory/config.json'
RECORDS = '.harness/memory/records/'


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.memory-', dir=str(path.parent))
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(canonical_bytes(value) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Repository:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root = Path(self.git('rev-parse', '--show-toplevel').decode().strip()).resolve()
        self.git_dir = Path(self.git('rev-parse', '--absolute-git-dir').decode().strip()).resolve()
        self.private = self.git_dir / 'harness-memory'
        self.private.mkdir(parents=True, exist_ok=True)
        self.anchor_path = self.private / 'adoption.json'
        self._bytes_cache = {}
        self._record_cache = {}
        self._resolved = set()

    def git(self, *args):
        try:
            process = subprocess.run(['git', '-C', str(self.root), *args],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     check=False, timeout=30,
                                     env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0'})
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise MemoryFailure('unjudged', 'Git unavailable: ' + str(exc)) from exc
        if process.returncode:
            raise MemoryFailure('unjudged', 'Git could not judge repository state',
                                {'arguments': list(args), 'error': process.stderr.decode('utf-8', 'replace')[:2048]})
        return process.stdout

    def resolve(self, ref):
        if not isinstance(ref, str) or not ref or ref.startswith('-') or '\x00' in ref:
            raise MemoryFailure('invalid', 'Invalid Git revision')
        if ref in self._resolved:
            return ref
        result = self.git('rev-parse', '--verify', '--end-of-options', ref + '^{commit}').decode().strip()
        self._resolved.add(result)
        return result

    def _ancestor(self, ancestor, descendant):
        if ancestor == descendant:
            return True
        return ancestor in self.git('rev-list', descendant).decode().splitlines()

    def _anchor(self):
        if getattr(self, '_ci_anchor', None) is not None:
            return copy.deepcopy(self._ci_anchor)
        if not self.anchor_path.exists():
            raise MemoryFailure('unjudged', 'Explicit local adoption required: initialize a trusted accepted ref')
        return load_json(self.anchor_path)

    def for_ci(self, base):
        """Bind an explicitly trusted CI base in memory, with no local adoption write.

        The caller supplies the protected target OID from its trusted CI event.
        Candidate policy is never read to select that target or to enable review.
        """
        oid = self.resolve(base)
        policy = validate_policy(parse_json(self.read_bytes(CONFIG, oid)))
        self._ci_anchor = {'schema_version': 1, 'accepted_ref': oid, 'accepted_oid': oid,
                           'policy_ref': policy['accepted_ref'], 'repository_id': policy['repository_id'],
                           'policy_digest': digest(policy),
                           'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                           'mode': 'explicit-ci-base'}
        return self

    def _authority(self):
        anchor = self._anchor()
        try:
            tip = self.resolve(anchor['accepted_ref'])
        except MemoryFailure:
            if anchor.get('bootstrap_policy') and anchor.get('accepted_oid') is None:
                return anchor, None, anchor['bootstrap_policy']
            raise
        if anchor.get('accepted_oid') and not self._ancestor(anchor['accepted_oid'], tip):
            raise MemoryFailure('unjudged', 'Accepted ref no longer descends from the local trusted anchor')
        try:
            policy = validate_policy(parse_json(self.read_bytes(CONFIG, tip)))
        except MemoryFailure as exc:
            if anchor.get('bootstrap_policy') and exc.status == 'unjudged':
                return anchor, None, anchor['bootstrap_policy']
            raise
        if policy['repository_id'] != anchor['repository_id'] or policy['accepted_ref'] != anchor.get('policy_ref', anchor['accepted_ref']):
            raise MemoryFailure('unjudged', 'Accepted policy changes repository identity or authority; explicit readoption required')
        return anchor, tip, policy

    def policy(self):
        return self._authority()[2]

    def observe_authority(self, expected_tip=None):
        """Refresh observation time after caller's explicit verified remote fetch.

        This never moves the trusted anchor or authorizes another ref. Callers
        must not use it for a local-only sync or an unrelated remote fetch.
        """
        if getattr(self, '_ci_anchor', None) is not None or not self.anchor_path.exists():
            raise MemoryFailure('unjudged', 'A persisted adoption anchor is required to refresh observation')
        anchor, tip, _ = self._authority()
        if tip is None:
            raise MemoryFailure('unjudged', 'Draft-only authority cannot acquire a revocation observation')
        if expected_tip is not None and tip != self.resolve(expected_tip):
            raise MemoryFailure('conflict', 'Fetched authority tip changed before observation')
        fresh_anchor, fresh_tip, _ = self._authority()
        if tip != fresh_tip or anchor != fresh_anchor:
            raise MemoryFailure('conflict', 'Authority changed during observation; retry synchronization')
        updated = dict(anchor, observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        atomic_json(self.anchor_path, updated)
        return {'status': 'ok', 'code': 0, 'accepted_tip': tip, 'observed_at': updated['observed_at']}

    def initialize(self, accepted_ref):
        """Trust only the explicitly named local ref; never infer trust from HEAD."""
        # Validate ref syntax before a missing ref can become a draft anchor.
        validate_policy({'schema_version': 1, 'repository_id': 'validation', 'accepted_ref': accepted_ref,
                         'review': {'mode': 'git-review'}})
        try:
            tip = self.resolve(accepted_ref)
        except MemoryFailure:
            if self.git('rev-list', '--all').strip():
                raise MemoryFailure('unjudged', 'Explicit accepted ref does not exist in a nonempty repository') from None
            tip = None
        bootstrap = False
        try:
            if tip is None:
                raise MemoryFailure('unjudged', 'Unborn repository')
            policy = validate_policy(parse_json(self.read_bytes(CONFIG, tip)))
        except MemoryFailure as exc:
            if exc.status != 'unjudged':
                raise
            bootstrap = True
            working = self._working_path(CONFIG)
            if working.exists():
                policy = validate_policy(parse_json(self.read_bytes(CONFIG)))
            else:
                policy = {'schema_version': 1, 'repository_id': 'repo-' + uuid.uuid4().hex,
                          'accepted_ref': accepted_ref, 'review': {'mode': 'git-review'}}
                atomic_json(working, policy)
        policy_alias = None
        if accepted_ref.startswith('refs/remotes/'):
            pieces = accepted_ref.split('/', 3)
            if len(pieces) == 4:
                policy_alias = 'refs/heads/' + pieces[3]
        if policy['accepted_ref'] not in (accepted_ref, policy_alias):
            raise MemoryFailure('invalid', 'Explicit accepted ref differs from its policy')
        records = self.record_files(tip) if tip is not None and not bootstrap else {}
        findings = validate_generation(records, policy)
        if findings:
            status = 'unjudged' if all(f['status'] == 'unjudged' for f in findings) else 'conflict'
            raise MemoryFailure(status, 'Adoption record generation is invalid', {'findings': findings})
        anchor = {'schema_version': 1, 'accepted_ref': accepted_ref, 'accepted_oid': tip,
                  'policy_ref': policy['accepted_ref'],
                  'repository_id': policy['repository_id'], 'policy_digest': digest(policy),
                  'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        if bootstrap:
            anchor['bootstrap_policy'] = policy
        atomic_json(self.anchor_path, anchor)
        return {'status': 'ok', 'code': 0, 'anchor': anchor, 'mode': 'draft-only' if bootstrap else 'accepted',
                'policy': policy, 'enforcement': 'unverified',
                'message': 'Local Git authority explicitly adopted; remote branch protection is not verified'}

    def _working_path(self, path):
        safe_path(path)
        current = self.root
        for part in path.split('/'):
            if current.is_symlink():
                raise MemoryFailure('invalid', 'Symlink source is not supported')
            if current.exists():
                entries = list(current.iterdir())
                aliases = [p.name for p in entries if unicodedata.normalize('NFC', p.name).casefold() == unicodedata.normalize('NFC', part).casefold()]
                if aliases and (part not in aliases or len(aliases) > 1):
                    raise MemoryFailure('unjudged', 'Ambiguous filesystem path spelling: ' + path)
            current = current / part
        if current.is_symlink() or not current.resolve().is_relative_to(self.root):
            raise MemoryFailure('invalid', 'Source escapes repository or is a symlink')
        return current

    def read_bytes(self, path, ref=None):
        safe_path(path)
        if ref is None:
            try:
                target = self._working_path(path)
                if target.stat().st_size > 8 * 1024 * 1024:
                    raise MemoryFailure('unjudged', 'Source exceeds 8 MiB inspection bound')
                return target.read_bytes()
            except OSError as exc:
                raise MemoryFailure('unjudged', 'Source unavailable: ' + path) from exc
        oid = self.resolve(ref)
        if (oid, path) in self._bytes_cache:
            return self._bytes_cache[(oid, path)]
        entries = self.git('ls-tree', '-l', '-z', oid, '--', path).split(b'\x00')
        exact = []
        for entry in entries:
            if entry:
                meta, name = entry.split(b'\t', 1)
                if name.decode('utf-8') == path:
                    exact.append(meta.decode().split())
        if len(exact) != 1 or exact[0][0] not in ('100644', '100755') or exact[0][1] != 'blob':
            raise MemoryFailure('unjudged', 'Source missing, symlinked or non-regular in Git snapshot: ' + path)
        object_id = exact[0][2]
        if int(exact[0][3]) > 8 * 1024 * 1024:
            raise MemoryFailure('unjudged', 'Source exceeds 8 MiB inspection bound')
        raw = self.git('cat-file', 'blob', object_id)
        self._bytes_cache[(oid, path)] = raw
        return raw

    def source_bytes(self, path, ref=None):
        """Return canonical Git bytes for clean tracked sources; raw bytes for drafts.

        Git decides clean equivalence, so CRLF/attributes are handled by its own
        rules. Dirty bytes are never normalized or substituted from an old tree.
        Use this helper when authoring a source content_digest; read_bytes remains
        exact filesystem bytes for transaction concurrency checks.
        """
        if ref is not None:
            return self.read_bytes(path, ref)
        raw = self.read_bytes(path)
        try:
            head = self.resolve('HEAD')
            tracked = self.read_bytes(path, head)
        except MemoryFailure:
            return raw
        changed = self.git('diff', '--no-ext-diff', '--no-textconv', '--name-only', '-z', head, '--', path)
        return raw if changed else tracked

    def current_code_changes(self, tested, artifact=None):
        """Paths changed since tested revision, including dirty and untracked code."""
        tested = self.resolve(tested)
        changed = self.git('diff', '--no-ext-diff', '--no-textconv', '--name-only', '-z', tested, '--')
        changed += self.git('ls-files', '--others', '--exclude-standard', '-z')
        return [path.decode('utf-8') for path in changed.split(b'\x00') if path and
                not path.decode('utf-8').startswith('.harness/memory/') and path.decode('utf-8') != artifact]

    def record_files(self, ref=None):
        if ref is None:
            directory = self._working_path(RECORDS.rstrip('/'))
            if not directory.exists():
                return {}
            paths = [str(path.relative_to(self.root)).replace('\\', '/') for path in directory.iterdir()]
        else:
            oid = self.resolve(ref)
            if oid in self._record_cache:
                return copy.deepcopy(self._record_cache[oid])
            entries = [p for p in self.git('ls-tree', '-r', '-l', '-z', oid, '--', RECORDS).split(b'\x00') if p]
            paths = []
            blobs = []
            total_size = 0
            for entry in entries:
                metadata, name = entry.split(b'\t', 1)
                mode, kind, blob, size = metadata.decode().split()
                path = name.decode('utf-8')
                if mode not in ('100644', '100755') or kind != 'blob' or int(size) > 65536:
                    raise MemoryFailure('invalid', 'Record must be a regular file of at most 64 KiB')
                paths.append(path)
                blobs.append(blob)
                total_size += int(size)
            if len(paths) > 10000 or total_size > 64 * 1024 * 1024:
                raise MemoryFailure('unjudged', 'Record snapshot exceeds bounded inspection limits')
            if blobs:
                # One bounded cat-file process avoids spawning Git for every record.
                try:
                    process = subprocess.run(['git', '-C', str(self.root), 'cat-file', '--batch'],
                        input=('\n'.join(blobs) + '\n').encode('ascii'), stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, timeout=30, check=False)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise MemoryFailure('unjudged', 'Cannot inspect record objects') from exc
                if process.returncode:
                    raise MemoryFailure('unjudged', 'Cannot inspect record objects')
                offset = 0
                for path, blob in zip(paths, blobs):
                    end = process.stdout.index(b'\n', offset)
                    object_id, kind, size = process.stdout[offset:end].decode().split()
                    if object_id != blob or kind != 'blob':
                        raise MemoryFailure('unjudged', 'Git batch object mismatch')
                    offset = end + 1
                    size = int(size)
                    self._bytes_cache[(oid, path)] = process.stdout[offset:offset + size]
                    offset += size + 1
        if len(paths) > 10000:
            raise MemoryFailure('unjudged', 'Record count exceeds inspection bound')
        result = {}
        for path in sorted(paths):
            if not path.endswith('.json') or '/' in path[len(RECORDS):]:
                raise MemoryFailure('invalid', 'Unexpected file in record directory: ' + path)
            raw = self.read_bytes(path, ref)
            if len(raw) > 65536:
                raise MemoryFailure('invalid', 'Record file exceeds 64 KiB')
            record = validate_record(parse_json(raw))
            if path != RECORDS + record['id'] + '.json':
                raise MemoryFailure('invalid', 'Record filename and identity differ')
            result[record['id']] = record
        if ref is not None:
            self._record_cache[oid] = copy.deepcopy(result)
        return result

    def _withdrawals(self, tip):
        """Negative overlay scans accepted first-parent history, not current branch data."""
        seen, previous = {}, {}
        cache_path = self.private / 'derived' / ('withdrawals-' + tip + '.json')
        if cache_path.exists():
            try:
                cached = load_json(cache_path)
                if cached.get('tip') == tip and cached.get('version') == 1 and cached.get('checksum') == digest(cached.get('withdrawals')):
                    return cached['withdrawals']
            except MemoryFailure:
                pass  # Disposable cache corruption triggers a rebuild.
        commits = self.git('log', '--first-parent', '--reverse', '--format=%H', tip, '--', RECORDS).decode().splitlines()
        if len(commits) > 10000:
            raise MemoryFailure('unjudged', 'Accepted history exceeds inspection bound')
        for commit in commits:
            records = self.record_files(commit)
            transitions = validate_transition(previous, records) if previous else []
            if transitions:
                raise MemoryFailure('conflict', 'Accepted history contains an invalid lifecycle transition', {'findings': transitions})
            for key, record in records.items():
                if record['state'] == 'retired':
                    seen[key] = {'retirement_hash': digest(record), 'active_hash': None, 'commit': commit}
                elif key in seen:
                    seen[key]['active_hash'] = digest(record)
            previous = records
        atomic_json(cache_path, {'version': 1, 'tip': tip, 'withdrawals': seen, 'checksum': digest(seen)})
        return seen

    def view(self, environment=None):
        from .evidence import check_record
        try:
            anchor, tip, policy = self._authority()
            if tip is None:
                return {'status': 'empty', 'code': 0, 'mode': 'draft-only', 'policy': policy,
                        'records': [], 'excluded': [], 'receipt': {'repository_id': policy['repository_id'],
                        'policy_digest': digest(policy), 'accepted_tip': None, 'accepted_ancestor': None,
                        'revocation_watermark': None, 'accepted_ref': anchor['accepted_ref'],
                        'head': anchor.get('accepted_oid'), 'mode': 'draft-only'}}
            head = self.resolve('HEAD')
            bases = self.git('merge-base', '--all', head, tip).decode().splitlines()
            if len(bases) != 1:
                raise MemoryFailure('unjudged', 'A unique accepted ancestor is required')
            ancestor = bases[0]
            if not self._ancestor(anchor['accepted_oid'], ancestor):
                # Earlier history is accepted by explicit adoption too, but must contain the same policy namespace.
                earlier = validate_policy(parse_json(self.read_bytes(CONFIG, ancestor)))
                if earlier['repository_id'] != policy['repository_id']:
                    raise MemoryFailure('unjudged', 'Accepted ancestor precedes the adopted repository namespace')
            records = self.record_files(ancestor)
            findings = validate_generation(records, policy)
            if findings:
                status = 'unjudged' if all(f['status'] == 'unjudged' for f in findings) else 'conflict'
                raise MemoryFailure(status, 'Accepted record generation contains conflicts', {'findings': findings})
            withdrawals = self._withdrawals(tip)
            dirty = self.git('status', '--porcelain=v1', '-z', '--untracked-files=all', '--', '.harness/memory')
            dirty_content = self.git('diff', '--no-ext-diff', '--no-textconv', '--binary', head, '--', '.harness/memory')
            untracked = self.git('ls-files', '--others', '--exclude-standard', '-z', '--', '.harness/memory').split(b'\x00')
            for entry in untracked:
                if entry:
                    try:
                        dirty_content += entry + hashlib.sha256(self.read_bytes(entry.decode('utf-8'))).digest()
                    except MemoryFailure:
                        dirty_content += entry + b'UNAVAILABLE'
            eligible, excluded = [], []
            for key, record in sorted(records.items()):
                reason, status = None, 'stale'
                if record['state'] == 'retired':
                    reason = 'retired'
                elif key in withdrawals and withdrawals[key]['active_hash'] != digest(record):
                    reason = 'withdrawn by latest known accepted history'
                elif any(name not in (environment or {}) or canonical_bytes((environment or {}).get(name)) not in [canonical_bytes(v) for v in allowed]
                         for name, allowed in record['scope'].get('environment', {}).items()):
                    reason = 'environment applicability missing or mismatched'
                    status = 'unjudged'
                if not reason:
                    path = RECORDS + key + '.json'
                    # A branch proposal for this identity and arbitrary edits are excluded, never substituted.
                    try:
                        expected = self.read_bytes(path, ancestor)
                        working = self.read_bytes(path)
                        if self.read_bytes(path, head) != expected or (working != expected and self.source_bytes(path) != expected):
                            reason = 'branch or dirty record overlay'
                    except MemoryFailure:
                        reason = 'record removed or unavailable in checkout'
                if not reason:
                    source_findings = check_record(self, record, ancestor)
                    if source_findings:
                        excluded.extend(source_findings)
                        continue
                if not reason and policy.get('revocation'):
                    config = policy['revocation']
                    kinds = config.get('kinds', [])
                    observed = datetime.datetime.fromisoformat(anchor['observed_at'])
                    if (not kinds or record['kind'] in kinds) and (datetime.datetime.now(datetime.timezone.utc) - observed).total_seconds() > config['max_age_seconds']:
                        reason, status = 'revocation observation exceeds policy age', 'unjudged'
                if reason:
                    excluded.append({'id': key, 'status': status, 'reason': reason})
                else:
                    eligible.append(record)
            receipt = {'repository_id': policy['repository_id'], 'head': head,
                       'accepted_ref': anchor['accepted_ref'], 'accepted_ancestor': ancestor, 'accepted_tip': tip,
                       'record_set_digest': digest(records), 'policy_digest': digest(policy),
                       'dirty_overlay_digest': hashlib.sha256(dirty + dirty_content).hexdigest(), 'revocation_watermark': tip,
                       'adapter_version': '1.0.0', 'synchronization': 'locally-known-only',
                       'authority_observed_at': anchor['observed_at']}
            receipt['authority_digest'] = digest(receipt)
            receipt['checked_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            receipt['accepted_ahead'] = ancestor != tip
            return {'status': 'ok' if eligible else ('unjudged' if any(x['status'] == 'unjudged' for x in excluded) else 'empty'),
                    'code': 2 if any(x['status'] == 'unjudged' for x in excluded) else 0,
                    'policy': policy, 'records': eligible, 'excluded': excluded, 'receipt': receipt}
        except MemoryFailure as exc:
            return {'status': exc.status, 'code': exc.code, 'policy': {}, 'records': [],
                    'excluded': [{'status': exc.status, 'reason': str(exc), **exc.details}], 'receipt': {}}
