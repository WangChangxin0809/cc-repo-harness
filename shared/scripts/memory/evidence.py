"""Source/version checks and merge-result gate. No command or external URL executes."""
import datetime
import hashlib

from .errors import MemoryFailure
from .schema import content_hash, digest, parse_json, validate_generation, validate_policy, validate_transition


def _result(findings):
    violations = [f for f in findings if f['status'] not in ('unjudged', 'unsupported')]
    code = 1 if violations else 2 if findings else 0
    return {'status': 'conflict' if violations else 'unjudged' if findings else 'ok',
            'code': code, 'findings': findings}


def validate_records(records, policy=None):
    try:
        return _result(validate_generation(records, policy))
    except MemoryFailure as exc:
        return _result([{'status': exc.status, 'reason': str(exc), **exc.details}])


def check_record(repo, record, snapshot=None):
    """Verify pinned bytes, then current-checkout applicability, for each source."""
    if record['state'] != 'active':
        return []
    findings = []
    def add(status, reason):
        findings.append({'id': record['id'], 'status': status, 'reason': reason})
    expiry = record['freshness'].get('expires_at')
    if expiry:
        when = datetime.datetime.fromisoformat(expiry.replace('Z', '+00:00'))
        if when.tzinfo is None:
            when = when.replace(tzinfo=datetime.timezone.utc)
        if when <= datetime.datetime.now(datetime.timezone.utc):
            add('stale', 'record expired')
    sources = list(record['freshness'].get('dependencies', []))
    if 'target' in record:
        sources.append(record['target'])
    for item in record['evidence']:
        if item['type'] == 'repository':
            sources.append(item)
        elif item['type'] == 'external':
            add('unjudged', 'external reference revalidation adapter unavailable')
        elif item['type'] == 'test':
            try:
                tested = repo.resolve(item['revision'].split(':')[-1])
                if repo.current_code_changes(tested, item.get('path')):
                    add('stale', 'tested code changed since the pinned test observation')
                if 'path' not in item:
                    add('unjudged', 'test result artifact is not locally addressable')
                else:
                    data = repo.source_bytes(item['path'], snapshot)
                    if hashlib.sha256(data).hexdigest() != content_hash(item['artifact_digest']):
                        add('stale', 'test artifact digest changed')
                    if snapshot is not None and hashlib.sha256(repo.source_bytes(item['path'])).hexdigest() != content_hash(item['artifact_digest']):
                        add('stale', 'current test artifact changed')
            except MemoryFailure as exc:
                add(exc.status, str(exc))
    for source in sources:
        try:
            path, expected = source['path'], content_hash(source['content_digest'])
            data = repo.source_bytes(path, snapshot)
            if hashlib.sha256(data).hexdigest() != expected:
                add('stale', 'pinned source digest mismatch: ' + path)
                continue
            if snapshot is not None and hashlib.sha256(repo.source_bytes(path)).hexdigest() != expected:
                add('stale', 'current checkout source changed: ' + path)
            if 'revision' in source:
                version = source['revision'].split(':')[-1]
                if hashlib.sha256(repo.read_bytes(path, version)).hexdigest() != expected:
                    add('stale', 'evidence revision does not identify captured bytes: ' + path)
            if 'object_id' in source:
                algorithm, object_id = source['object_id'].split(':', 1)
                actual_algorithm = repo.git('rev-parse', '--show-object-format').decode().strip()
                computed = hashlib.new(algorithm, b'blob ' + str(len(data)).encode('ascii') + b'\x00' + data).hexdigest()
                if algorithm != actual_algorithm or computed != object_id:
                    add('stale', 'evidence Git object identity mismatch: ' + path)
            if 'lines' in source:
                lines = data.decode('utf-8').splitlines()
                first, last = source['lines']
                if last > len(lines):
                    add('stale', 'evidence excerpt range exceeds source: ' + path)
                elif 'excerpt' in source and '\n'.join(lines[first - 1:last]) != source['excerpt']:
                    add('stale', 'evidence excerpt differs from pinned source: ' + path)
        except (UnicodeError, OSError) as exc:
            add('unjudged', 'source cannot be inspected: ' + str(exc))
        except MemoryFailure as exc:
            add(exc.status, str(exc))
    return findings


def verify(repo):
    view = repo.view()
    findings = list(view.get('excluded', []))
    try:
        records = repo.record_files()
        findings.extend(validate_generation(records, repo.policy()))
        for record in records.values():
            findings.extend(check_record(repo, record))
    except MemoryFailure as exc:
        findings.append({'status': exc.status, 'reason': str(exc), **exc.details})
    result = _result(findings)
    result['receipt'] = view.get('receipt', {})
    return result


def validate_tree(repo, base=None, result=None):
    """Check an immutable proposed merge result against an explicitly trusted base.

    Missing inputs/history are unjudged. Result policy never grants authority to
    itself; the base policy owns namespace, constraints and source interpretation.
    """
    try:
        if base is None or result is None:
            raise MemoryFailure('unjudged', 'Both trusted accepted base and proposed result are required')
        anchor, accepted_tip, _ = repo._authority()
        base_oid, result_oid = repo.resolve(base), repo.resolve(result)
        if not repo._ancestor(base_oid, accepted_tip):
            raise MemoryFailure('unjudged', 'Specified base is outside trusted accepted history')
        if base_oid != accepted_tip:
            raise MemoryFailure('unjudged', 'Trusted base is behind latest known accepted tip; reconcile before validation')
        if not repo._ancestor(base_oid, result_oid):
            raise MemoryFailure('unjudged', 'Proposed result does not contain the trusted base')
        policy = validate_policy(parse_json(repo.read_bytes('.harness/memory/config.json', base_oid)))
        result_policy = validate_policy(parse_json(repo.read_bytes('.harness/memory/config.json', result_oid)))
        if result_policy['repository_id'] != policy['repository_id']:
            raise MemoryFailure('invalid', 'Repository namespace cannot change in a memory proposal')
        before, after = repo.record_files(base_oid), repo.record_files(result_oid)
        findings = validate_generation(after, policy)
        findings.extend(validate_transition(before, after))
        for current in after.values():
            # Sources are checked from the proposed immutable result, never the caller's checkout.
            findings.extend(_check_tree_sources(repo, current, result_oid))
        response = _result(findings)
        response['receipt'] = {'base': base_oid, 'result': result_oid, 'policy_digest': digest(policy),
                               'record_set_digest': digest(after), 'revocation_watermark': accepted_tip}
        return response
    except MemoryFailure as exc:
        return {'status': exc.status, 'code': exc.code, 'findings': [{'status': exc.status, 'reason': str(exc), **exc.details}]}


def _check_tree_sources(repo, record, revision):
    """Adapt source reading only; the gate cannot accidentally use dirty files."""
    class Snapshot:
        def read_bytes(self, path, ref=None):
            return repo.read_bytes(path, ref or revision)
        def resolve(self, ref):
            return revision if ref == 'HEAD' else repo.resolve(ref)
        def source_bytes(self, path, ref=None):
            return repo.read_bytes(path, ref or revision)
        def current_code_changes(self, tested, artifact=None):
            changed = repo.git('diff', '--no-ext-diff', '--no-textconv', '--name-only', '-z', tested, revision, '--')
            return [p.decode('utf-8') for p in changed.split(b'\x00') if p and
                    not p.decode('utf-8').startswith('.harness/memory/') and p.decode('utf-8') != artifact]
        def git(self, *args):
            if args and args[0] == 'hash-object':
                path = args[-1]
                row = repo.git('ls-tree', revision, '--', path).split(b'\t', 1)[0]
                return row.split()[-1] + b'\n'
            return repo.git(*args)
    return check_record(Snapshot(), record)
