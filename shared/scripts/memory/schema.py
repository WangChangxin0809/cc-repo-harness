"""Strict version-one data schema and deterministic semantic checks.

Canonical hashes are SHA-256 over UTF-8 JSON with sorted keys, compact separators,
literal Unicode and no non-finite numbers. Paths always retain Git spelling.
"""
import datetime
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

from .errors import MemoryFailure

MAX_RECORD_BYTES = 65536
IDENTITY = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')
HASH = re.compile(r'^(?:sha256:)?[0-9a-f]{64}$')
SECRETS = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|'
                     r'AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|'
                     r'\bsk-[A-Za-z0-9_-]{20,}|(?:password|api[_-]?key|secret[_-]?key)\s*[:=]\s*["\x27]?[A-Za-z0-9_+/=-]{12,})', re.I)


def invalid(message):
    raise MemoryFailure('invalid', message)


def canonical_bytes(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        invalid('Not canonical JSON: ' + str(exc))


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def parse_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                invalid('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    try:
        if isinstance(data, bytes):
            data = data.decode('utf-8')
        return json.loads(data, object_pairs_hook=pairs,
                          parse_constant=lambda value: invalid('Non-finite JSON number: ' + value))
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        invalid('Malformed JSON: ' + str(exc))


def load_json(path):
    try:
        return parse_json(Path(path).read_bytes())
    except OSError as exc:
        raise MemoryFailure('unjudged', 'Cannot read JSON: ' + str(exc)) from exc


def obj(value, required, optional=(), label='object'):
    if not isinstance(value, dict):
        invalid(label + ' must be an object')
    missing = set(required) - value.keys()
    extra = value.keys() - set(required) - set(optional)
    if missing or extra:
        invalid('%s keys: missing=%s unknown=%s' % (label, sorted(missing), sorted(extra)))


def string(value, limit, label, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        invalid(label + ' must be a nonempty string')
    try:
        size = len(value.encode('utf-8'))
    except UnicodeError:
        invalid(label + ' contains invalid Unicode')
    if size > limit or '\x00' in value:
        invalid(label + ' exceeds byte limit or contains NUL')
    return value


def identity(value, label='id'):
    if not isinstance(value, str) or not IDENTITY.fullmatch(value) or value in ('.', '..'):
        invalid(label + ' must be a path-safe identifier')
    return value


def content_hash(value):
    if not isinstance(value, str) or not HASH.fullmatch(value):
        invalid('Expected SHA-256 content digest')
    return value.removeprefix('sha256:')


def safe_path(value, pattern=False):
    string(value, 1024, 'path')
    if pattern and value == '**':
        return value
    path = value[:-3] if pattern and value.endswith('/**') else value
    if not path or path.startswith('/') or any(c in path for c in '\\:*?[]{}!\x00'):
        invalid('Unsafe or unsupported relative path: ' + value)
    for part in path.split('/'):
        if part in ('', '.', '..') or part.rstrip('. ') != part or any(ord(c) < 32 for c in part):
            invalid('Unsafe path component: ' + value)
        if part.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
            invalid('Nonportable path: ' + value)
    if path.split('/')[0].lower() == '.git':
        invalid('Git administrative paths are forbidden')
    return value


def sequence(value, maximum, label):
    if not isinstance(value, list) or len(value) > maximum:
        invalid(label + ' must be a bounded array')
    return value


def timestamp(value):
    string(value, 64, 'timestamp')
    try:
        parsed = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if len(value) > 10 and parsed.tzinfo is None:
            invalid('Timestamp needs a timezone')
    except ValueError:
        invalid('Invalid ISO timestamp')


def scan_publication(value):
    """Recursively scan keys as well as values; this is a bounded pattern gate, not DLP."""
    if isinstance(value, str):
        if SECRETS.search(value):
            invalid('Potential credential in publication content')
    elif isinstance(value, dict):
        for key, item in value.items():
            scan_publication(key)
            scan_publication(item)
    elif isinstance(value, list):
        for item in value:
            scan_publication(item)


def source(value, optional=()):
    obj(value, ('path', 'content_digest'), optional, 'source')
    safe_path(value['path'])
    content_hash(value['content_digest'])
    if 'section' in value:
        string(value['section'], 256, 'section')


def validate_scope(value):
    obj(value, ('repository', 'paths'), ('tags', 'environment'), 'scope')
    identity(value['repository'], 'repository')
    if not sequence(value['paths'], 64, 'scope.paths'):
        invalid('scope.paths must not be empty')
    for path in value['paths']:
        safe_path(path, True)
    for tag in sequence(value.get('tags', []), 32, 'scope.tags'):
        string(tag, 80, 'tag')
    environment = value.get('environment', {})
    if not isinstance(environment, dict) or len(environment) > 16:
        invalid('environment must be a bounded predicate object')
    for key, values in environment.items():
        identity(key, 'environment key')
        if not sequence(values, 16, 'environment values'):
            invalid('environment predicate cannot be empty')
        for item in values:
            if type(item) not in (str, bool):
                invalid('Environment values must be strings or booleans')
            if isinstance(item, str):
                string(item, 128, 'environment value')


def validate_evidence(value):
    if not isinstance(value, dict):
        invalid('evidence must be an object')
    kind = value.get('type')
    if kind == 'decision':
        obj(value, ('type', 'reason'), ('attribution', 'revision'), 'decision evidence')
        string(value['reason'], 1024, 'decision reason')
        if 'attribution' in value:
            string(value['attribution'], 256, 'attribution')
    elif kind == 'repository':
        obj(value, ('type', 'path', 'content_digest'), ('revision', 'object_id', 'lines', 'excerpt'), 'repository evidence')
        safe_path(value['path'])
        content_hash(value['content_digest'])
    elif kind == 'test':
        obj(value, ('type', 'revision', 'command', 'artifact_digest'), ('path', 'content_digest'), 'test evidence')
        string(value['command'], 1024, 'test command identity')
        content_hash(value['artifact_digest'])
        if 'path' in value:
            safe_path(value['path'])
        if 'content_digest' in value:
            content_hash(value['content_digest'])
    elif kind == 'external':
        obj(value, ('type', 'url', 'content_digest', 'observed_at'), ('version', 'excerpt'), 'external evidence')
        string(value['url'], 2048, 'URL')
        try:
            url = urlsplit(value['url'])
        except ValueError:
            invalid('Invalid external evidence URL')
        if url.scheme not in ('https', 'http') or not url.netloc or url.username or url.password:
            invalid('External evidence needs an HTTP URL without credentials')
        content_hash(value['content_digest'])
        timestamp(value['observed_at'])
        if 'version' in value:
            string(value['version'], 256, 'external version')
    else:
        invalid('Unknown evidence type')
    if 'revision' in value:
        string(value['revision'], 128, 'revision')
        if not re.fullmatch(r'(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64}|[0-9a-f]{40}|[0-9a-f]{64})', value['revision']):
            invalid('Revision must be an immutable Git object identity')
    if 'object_id' in value:
        string(value['object_id'], 80, 'object_id')
        if not re.fullmatch(r'(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})', value['object_id']):
            invalid('Git object identity must be algorithm-qualified')
    if 'lines' in value:
        lines = value['lines']
        if not isinstance(lines, list) or len(lines) != 2 or any(type(n) is not int for n in lines) or not 1 <= lines[0] <= lines[1]:
            invalid('Evidence lines must be [first,last] positive inclusive range')
    if 'excerpt' in value:
        string(value['excerpt'], 4096, 'evidence excerpt')


def validate_record(record):
    if len(canonical_bytes(record)) > MAX_RECORD_BYTES:
        invalid('Record exceeds 64 KiB')
    if not isinstance(record, dict) or type(record.get('schema_version')) is not int or record['schema_version'] != 1:
        invalid('Unsupported record schema_version')
    identity(record.get('id'))
    safe_path(record['id'] + '.json')
    scan_publication(record)
    if record.get('state') == 'retired':
        obj(record, ('schema_version', 'id', 'state', 'retirement'), label='retired record')
        retirement = record['retirement']
        obj(retirement, ('previous_record_hash', 'reason'), ('replacement',), 'retirement')
        content_hash(retirement['previous_record_hash'])
        string(retirement['reason'], 512, 'retirement reason')
        if 'replacement' in retirement:
            identity(retirement['replacement'], 'replacement')
        return record
    obj(record, ('schema_version', 'id', 'state', 'kind', 'title', 'summary', 'scope', 'evidence', 'freshness'),
        ('body', 'target', 'claim', 'supersedes', 'replacement_reason', 'restores'), 'active record')
    if record['state'] != 'active' or record['kind'] not in ('decision', 'constraint', 'procedure', 'pitfall', 'context', 'reference'):
        invalid('Unknown record state or kind')
    string(record['title'], 160, 'title')
    string(record['summary'], 512, 'summary')
    if ('body' in record) == ('target' in record):
        invalid('Exactly one of body or target is required')
    if 'body' in record:
        lines = sequence(record['body'], 4096, 'body')
        for line in lines:
            string(line, 4096, 'body line', True)
            if '\n' in line or '\r' in line:
                invalid('Body lines cannot contain newline characters')
        string('\n'.join(lines), 4096, 'rendered body', True)
    else:
        source(record['target'], ('section',))
    validate_scope(record['scope'])
    if not sequence(record['evidence'], 16, 'evidence'):
        invalid('Active record needs evidence')
    for item in record['evidence']:
        validate_evidence(item)
    obj(record['freshness'], ('dependencies',), ('expires_at', 'verified_at'), 'freshness')
    for item in sequence(record['freshness']['dependencies'], 64, 'dependencies'):
        source(item)
    for key in ('expires_at', 'verified_at'):
        if key in record['freshness']:
            timestamp(record['freshness'][key])
    if 'claim' in record:
        obj(record['claim'], ('key', 'value'), label='claim')
        string(record['claim']['key'], 256, 'claim key')
    if 'supersedes' in record:
        for item in sequence(record['supersedes'], 64, 'supersedes'):
            identity(item)
        string(record.get('replacement_reason'), 512, 'replacement_reason')
    if 'replacement_reason' in record and 'supersedes' not in record:
        invalid('replacement_reason requires supersedes')
    if 'restores' in record:
        obj(record['restores'], ('retirement_record_hash', 'reason'), label='restores')
        content_hash(record['restores']['retirement_record_hash'])
        string(record['restores']['reason'], 512, 'restore reason')
    return record


def validate_policy(policy):
    obj(policy, ('schema_version', 'repository_id', 'accepted_ref', 'review'),
        ('limits', 'revocation', 'native_capture', 'relay', 'durable_private'), 'policy')
    if type(policy['schema_version']) is not int or policy['schema_version'] != 1:
        invalid('Unsupported policy schema_version')
    identity(policy['repository_id'], 'repository_id')
    ref = string(policy['accepted_ref'], 256, 'accepted_ref')
    if not ref.startswith('refs/') or any(x in ref for x in ('..', '@{', '\\', ' ', ':', '?', '*', '[', '~', '^')) or ref.endswith('/'):
        invalid('accepted_ref must be a full Git ref')
    obj(policy['review'], ('mode',), ('enforcement', 'required_checks'), 'review')
    if policy['review']['mode'] != 'git-review':
        raise MemoryFailure('unsupported', 'Only explicit Git review acceptance is implemented')
    if 'enforcement' in policy['review'] and policy['review']['enforcement'] not in ('unknown', 'verified', 'unverified'):
        invalid('Unknown enforcement declaration')
    for check in sequence(policy['review'].get('required_checks', []), 32, 'required_checks'):
        string(check, 128, 'required check')
    if 'limits' in policy:
        obj(policy['limits'], (), ('recall_bytes', 'candidate_bytes', 'candidate_count', 'dream_bytes'), 'limits')
        for value in policy['limits'].values():
            if type(value) is not int or not 1 <= value <= 1073741824:
                invalid('limits must be bounded positive integers')
    if 'revocation' in policy:
        obj(policy['revocation'], ('max_age_seconds',), ('kinds',), 'revocation')
        if type(policy['revocation']['max_age_seconds']) is not int or policy['revocation']['max_age_seconds'] < 0:
            invalid('Invalid revocation age')
        for kind in sequence(policy['revocation'].get('kinds', []), 6, 'revocation kinds'):
            if kind not in ('decision', 'constraint', 'procedure', 'pitfall', 'context', 'reference'):
                invalid('Invalid revocation kind')
    for key in ('native_capture', 'relay', 'durable_private'):
        if key in policy and not isinstance(policy[key], (dict, bool, str)):
            invalid(key + ' must describe an optional deployment profile')
    if len(canonical_bytes(policy)) > 65536:
        invalid('Policy exceeds 64 KiB')
    scan_publication(policy)
    return policy


def path_matches(pattern, path):
    return pattern == '**' or pattern == path or (pattern.endswith('/**') and (path == pattern[:-3] or path.startswith(pattern[:-2])))


def scopes_overlap(left, right):
    if left['repository'] != right['repository']:
        return False
    for key in set(left.get('environment', {})) & set(right.get('environment', {})):
        a = {canonical_bytes(v) for v in left['environment'][key]}
        b = {canonical_bytes(v) for v in right['environment'][key]}
        if not a & b:
            return False
    for a in left['paths']:
        for b in right['paths']:
            if path_matches(a, b[:-3] if b.endswith('/**') else b) or path_matches(b, a[:-3] if a.endswith('/**') else a):
                return True
    return False


def validate_generation(records, policy=None):
    values = list(records.values()) if isinstance(records, dict) else list(records)
    findings, by_id, aliases = [], {}, {}
    for record in values:
        validate_record(record)
        key = record['id']
        if key in by_id:
            findings.append({'status': 'conflict', 'id': key, 'reason': 'duplicate record identity'})
        alias = unicodedata.normalize('NFC', key).casefold()
        if alias in aliases and aliases[alias] != key:
            findings.append({'status': 'unjudged', 'id': key, 'reason': 'filesystem identity alias'})
        aliases[alias], by_id[key] = key, record
        if record['state'] == 'active' and policy and record['scope']['repository'] != policy['repository_id']:
            findings.append({'status': 'invalid', 'id': key, 'reason': 'repository namespace mismatch'})
    claims = {}
    for record in values:
        if record['state'] == 'active' and 'claim' in record:
            claims.setdefault(record['claim']['key'], []).append(record)
    for group in claims.values():
        for index, left in enumerate(group):
            for right in group[index + 1:]:
                a, b = left['claim'], right['claim']
                if canonical_bytes(a['value']) != canonical_bytes(b['value']):
                    if scopes_overlap(left['scope'], right['scope']):
                        findings.append({'status': 'conflict', 'ids': [left['id'], right['id']], 'reason': 'incompatible overlapping structured claims'})
                    else:
                        normalized = []
                        for record in (left, right):
                            normalized.append({**record['scope'], 'paths': [unicodedata.normalize('NFC', p).casefold() for p in record['scope']['paths']]})
                        if scopes_overlap(*normalized):
                            findings.append({'status': 'unjudged', 'ids': [left['id'], right['id']], 'reason': 'scope overlap depends on filesystem case or Unicode aliases'})
    colors = {}
    for key in by_id:
        stack = [(key, False)]
        while stack:
            current, leaving = stack.pop()
            if leaving:
                colors[current] = 2
                continue
            if colors.get(current) == 2:
                continue
            if colors.get(current) == 1:
                findings.append({'status': 'conflict', 'id': current, 'reason': 'supersession cycle'})
                continue
            colors[current] = 1
            stack.append((current, True))
            for predecessor in by_id[current].get('supersedes', []):
                if predecessor not in by_id:
                    findings.append({'status': 'invalid', 'id': current, 'reason': 'missing superseded record: ' + predecessor})
                else:
                    stack.append((predecessor, False))
    return findings


def validate_transition(before, after):
    """Lifecycle checks shared by immutable merge gates and provisional writes."""
    findings = []
    for key, previous in before.items():
        current = after.get(key)
        reason = None
        if current is None:
            reason = 'record deletion requires a retained retirement tombstone'
        elif previous['state'] == 'retired':
            if current['state'] == 'active':
                restored_hash = current.get('restores', {}).get('retirement_record_hash')
                if restored_hash is None or content_hash(restored_hash) != digest(previous):
                    reason = 'restore must name exact prior retirement hash'
            elif digest(current) != digest(previous):
                reason = 'retirement identity cannot be rewritten'
        elif current['state'] == 'retired' and content_hash(current['retirement']['previous_record_hash']) != digest(previous):
            reason = 'retirement does not name previous active record hash'
        if reason:
            findings.append({'id': key, 'status': 'invalid', 'reason': reason})
    for key, current in after.items():
        if key not in before and current['state'] == 'retired':
            findings.append({'id': key, 'status': 'invalid', 'reason': 'retirement has no prior accepted record'})
    return findings
