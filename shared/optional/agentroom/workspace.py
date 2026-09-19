"""Snapshot-bound CRDT edits with a durable projection outbox.

SQLite is the authority; disk files are a projection. Commit CRDT state and
projection intent first, fsync/replace the projection second, clear intent last.
Recovery never overwrites a third-party disk change. Source snapshots are
bounded and actor-bound; a retry ID identifies exactly one mutation.

All cooperating writers MUST use open/apply. This does not intercept arbitrary
Bash/Write calls, nor claim to recover bytes overwritten before capture.
"""
from __future__ import annotations

import ast
import json
import uuid
from contextlib import contextmanager

try:
    from .crdt import backend, checked_text, encode
    from .localio import atomic_write, file_lock, read_bytes, sha, sync_directory
except ImportError:
    from crdt import backend, checked_text, encode
    from localio import atomic_write, file_lock, read_bytes, sha, sync_directory


class Conflict(ValueError):
    def __init__(self, code, detail):
        self.code = code
        super().__init__(detail)


class Workspace:
    def __init__(self, room, engine='rga', strict_claims=False):
        self.room, self.engine = room, backend(engine)
        self.strict = bool(strict_claims)
        self.lock = room.db.parent / 'workspace.lock'
        with file_lock(self.lock), room._connection() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS room_documents(
                    path TEXT PRIMARY KEY, generation TEXT NOT NULL,
                    backend TEXT NOT NULL, state TEXT NOT NULL, revision INTEGER NOT NULL,
                    disk_sha TEXT, deleted INTEGER NOT NULL DEFAULT 0, mode INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS room_snapshots(
                    token TEXT PRIMARY KEY, owner TEXT NOT NULL, path TEXT NOT NULL,
                    generation TEXT NOT NULL, state TEXT NOT NULL, revision INTEGER NOT NULL,
                    expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS room_mutations(
                    owner TEXT NOT NULL, request TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    result TEXT NOT NULL, PRIMARY KEY(owner,request));
                CREATE TABLE IF NOT EXISTS room_projection(
                    path TEXT PRIMARY KEY, old_sha TEXT, body BLOB, mode INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS room_updates(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL,
                    generation TEXT NOT NULL, owner TEXT NOT NULL, request TEXT NOT NULL,
                    backend TEXT NOT NULL, delta TEXT NOT NULL, created REAL NOT NULL);
            ''')

    def _target(self, path):
        return self.room.root / self.room.path_key(path)

    def _recover(self):
        with self.room._connection() as c:
            for row in c.execute('SELECT * FROM room_projection ORDER BY path').fetchall():
                target = self._target(row['path'])
                actual = sha(read_bytes(target))
                desired = sha(row['body'])
                if actual != desired:
                    if actual != row['old_sha']:
                        raise Conflict('external-drift', 'projection conflicts with an external write: ' + row['path'])
                    if row['body'] is None:
                        target.unlink(missing_ok=True)
                        sync_directory(target.parent)
                    else:
                        atomic_write(target, row['body'], row['mode'])
                c.execute('DELETE FROM room_projection WHERE path=?', (row['path'],))

    @contextmanager
    def _tx(self):
        with file_lock(self.lock):
            self._recover()
            with self.room._transaction() as pair:
                yield pair
            self._recover()

    def _doc(self, c, path):
        row = c.execute('SELECT * FROM room_documents WHERE path=?', (path,)).fetchone()
        if row and row['backend'] != self.engine.name:
            raise Conflict('backend-mismatch', 'never reinterpret an existing document with another CRDT backend')
        if row and sha(read_bytes(self._target(path))) != row['disk_sha']:
            raise Conflict('external-drift', 'disk changed outside captured edits: ' + path)
        return row

    def _snapshot(self, c, row, now):
        c.execute('DELETE FROM room_snapshots WHERE expires<=?', (now,))
        if c.execute('SELECT COUNT(*) FROM room_snapshots').fetchone()[0] >= 512:
            raise Conflict('snapshot-capacity', '512 live read versions; wait for expiry or finish a run')
        token = uuid.uuid4().hex
        c.execute('INSERT INTO room_snapshots VALUES(?,?,?,?,?,?,?)',
                  (token, self.room.owner, row['path'], row['generation'], row['state'], row['revision'], now + 3600))
        return {'path': row['path'], 'snapshot': token, 'revision': row['revision'],
                'text': self.engine.text(json.loads(row['state'])), 'backend': self.engine.name,
                'snapshot_expires': now + 3600}

    def open(self, path, create=False):
        if type(create) is not bool:
            raise ValueError('create must be boolean')
        path = self.room.path_key(path)
        with self._tx() as (c, now):
            row = self._doc(c, path)
            if row is None or row['deleted']:
                content = read_bytes(self._target(path))
                if content is None and not create:
                    raise Conflict('not-found', 'use create=true to prepare a new file')
                body = '' if content is None else content.decode('utf-8')
                checked_text(body)
                state = encode(self.engine.initial(body))
                target = self._target(path)
                mode = (target.stat().st_mode & 0o777) if target.exists() else 0o644
                c.execute('INSERT OR REPLACE INTO room_documents VALUES(?,?,?,?,?,?,?,?)',
                          (path, uuid.uuid4().hex, self.engine.name, state, 0, sha(content), 0, mode))
                row = self._doc(c, path)
            return self._snapshot(c, row, now)

    def _read_version(self, c, token, now):
        row = c.execute('SELECT * FROM room_snapshots WHERE token=? AND owner=?',
                        (token, self.room.owner)).fetchone()
        if not row or row['expires'] <= now:
            raise Conflict('invalid-snapshot', 'read token is foreign, unknown, or expired; read again')
        doc = self._doc(c, row['path'])
        if doc is None or doc['deleted'] or doc['generation'] != row['generation']:
            raise Conflict('stale-generation', 'file was deleted, renamed or explicitly reconciled')
        return row, doc

    def _claim(self, c, path, now, structural=False):
        row = c.execute('SELECT * FROM claims WHERE path=?', (path,)).fetchone()
        owned = bool(row and row['owner'] == self.room.owner and row['expires'] > now)
        if not owned:
            if self.strict or structural:
                raise Conflict('claim-required', 'a live claim owned by this actor is required: ' + path)
            self.room._event(c, self.room.owner, 'unclaimed-write', {'path': path}, now)
        return owned

    def _receipt(self, c, request, body):
        if not isinstance(request, str) or not request or len(request) > 128:
            raise ValueError('mutation requires a nonempty request_id of at most 128 characters')
        fingerprint = sha(encode(body).encode())
        row = c.execute('SELECT * FROM room_mutations WHERE owner=? AND request=?',
                        (self.room.owner, request)).fetchone()
        if row:
            if row['fingerprint'] != fingerprint:
                raise Conflict('request-reuse', 'same request_id used for another mutation')
            return fingerprint, {**json.loads(row['result']), 'replayed': True}
        return fingerprint, None

    def _record(self, c, request, fingerprint, result):
        c.execute('INSERT INTO room_mutations VALUES(?,?,?,?)',
                  (self.room.owner, request, fingerprint, encode(result)))
        return result

    def _project(self, c, path, old_sha, content, mode):
        c.execute('INSERT INTO room_projection VALUES(?,?,?,?)', (path, old_sha, content, mode))

    def apply(self, snapshot, text, request_id):
        checked_text(text)
        with self._tx() as (c, now):
            fp, replay = self._receipt(c, request_id, ['apply', snapshot, text])
            if replay:
                return replay
            read, doc = self._read_version(c, snapshot, now)
            claimed = self._claim(c, doc['path'], now)
            delta = self.engine.delta(json.loads(read['state']), text)
            merged = self.engine.merge(json.loads(doc['state']), delta)
            content = self.engine.text(merged)
            checked_text(content)
            body = content.encode('utf-8')
            revision = doc['revision'] + 1
            c.execute('UPDATE room_documents SET state=?,revision=?,disk_sha=? WHERE path=?',
                      (encode(merged), revision, sha(body), doc['path']))
            c.execute('INSERT INTO room_updates(path,generation,owner,request,backend,delta,created) VALUES(?,?,?,?,?,?,?)',
                      (doc['path'], doc['generation'], self.room.owner, request_id, self.engine.name, encode(delta), now))
            self._project(c, doc['path'], doc['disk_sha'], body, doc['mode'])
            event = self.room._event(c, self.room.owner, 'edit',
                {'path': doc['path'], 'revision': revision, 'base_revision': read['revision'],
                 'sha256': sha(body), 'claimed': claimed, 'capture': 'snapshot-bound'}, now)
            return self._record(c, request_id, fp, {'ok': True, 'path': doc['path'], 'revision': revision,
                'event': event, 'merged_concurrent': read['revision'] != doc['revision'],
                'text': content, 'claimed': claimed, 'sanity': sanity(doc['path'], content), 'replayed': False})

    def delete(self, snapshot, request_id):
        with self._tx() as (c, now):
            fp, replay = self._receipt(c, request_id, ['delete', snapshot])
            if replay:
                return replay
            read, doc = self._read_version(c, snapshot, now)
            self._claim(c, doc['path'], now, structural=True)
            if read['revision'] != doc['revision']:
                raise Conflict('stale-delete', 'delete cannot discard unseen edits; read again')
            c.execute('UPDATE room_documents SET deleted=1,revision=revision+1,disk_sha=NULL WHERE path=?', (doc['path'],))
            self._project(c, doc['path'], doc['disk_sha'], None, doc['mode'])
            self.room._event(c, self.room.owner, 'deleted', {'path': doc['path']}, now)
            return self._record(c, request_id, fp, {'ok': True, 'deleted': doc['path'], 'replayed': False})

    def rename(self, snapshot, destination, request_id):
        destination = self.room.path_key(destination)
        with self._tx() as (c, now):
            fp, replay = self._receipt(c, request_id, ['rename', snapshot, destination])
            if replay:
                return replay
            read, doc = self._read_version(c, snapshot, now)
            self._claim(c, doc['path'], now, structural=True)
            self._claim(c, destination, now, structural=True)
            if read['revision'] != doc['revision']:
                raise Conflict('stale-rename', 'rename needs a fresh read')
            dest = self._doc(c, destination)
            if (dest and not dest['deleted']) or self._target(destination).exists():
                raise Conflict('destination-exists', 'rename never overwrites its destination')
            body = self.engine.text(json.loads(doc['state'])).encode('utf-8')
            c.execute('UPDATE room_documents SET deleted=1,revision=revision+1,disk_sha=NULL WHERE path=?', (doc['path'],))
            c.execute('INSERT OR REPLACE INTO room_documents VALUES(?,?,?,?,?,?,?,?)',
                      (destination, uuid.uuid4().hex, self.engine.name, doc['state'], 0, sha(body), 0, doc['mode']))
            self._project(c, destination, None, body, doc['mode'])
            self._project(c, doc['path'], doc['disk_sha'], None, doc['mode'])
            self.room._event(c, self.room.owner, 'renamed', {'from': doc['path'], 'to': destination}, now)
            return self._record(c, request_id, fp, {'ok': True, 'from': doc['path'], 'to': destination, 'replayed': False})

    def status(self):
        with self.room._connection() as c:
            return {'backend': self.engine.name, 'capture': 'mediated-tools-only',
                    'strict_claims': self.strict, 'documents': [dict(r) for r in c.execute(
                        'SELECT path,revision,deleted,backend FROM room_documents ORDER BY path')],
                    'pending_projections': [r[0] for r in c.execute('SELECT path FROM room_projection')]}

    def reconcile(self, path, strategy, expected_disk_sha):
        if strategy not in ('disk', 'room'):
            raise ValueError('strategy must be disk or room')
        path = self.room.path_key(path)
        with file_lock(self.lock), self.room._transaction() as (c, now):
            content = read_bytes(self._target(path))
            if sha(content) != expected_disk_sha:
                raise Conflict('changed-again', 'disk no longer matches the reviewed digest')
            doc = c.execute('SELECT * FROM room_documents WHERE path=?', (path,)).fetchone()
            if not doc or doc['backend'] != self.engine.name:
                raise ValueError('no compatible managed document')
            backup = {'path': path, 'disk_hex': content.hex() if content is not None else None,
                      'room_state': json.loads(doc['state']), 'backend': doc['backend'], 'time': now}
            atomic_write(self.room.db.parent / 'conflicts' / (uuid.uuid4().hex + '.json'), encode(backup).encode())
            c.execute('DELETE FROM room_projection WHERE path=?', (path,))
            if strategy == 'disk':
                body = '' if content is None else content.decode('utf-8')
                checked_text(body)
                state = encode(self.engine.initial(body))
                c.execute('UPDATE room_documents SET generation=?,state=?,revision=revision+1,disk_sha=?,deleted=? WHERE path=?',
                          (uuid.uuid4().hex, state, sha(content), int(content is None), path))
            else:
                body = None if doc['deleted'] else self.engine.text(json.loads(doc['state'])).encode()
                self._project(c, path, sha(content), body, doc['mode'])
            self.room._event(c, self.room.owner, 'reconciled', {'path': path, 'strategy': strategy}, now)
        with file_lock(self.lock):
            self._recover()
        return {'ok': True, 'strategy': strategy, 'path': path}


def sanity(path, text):
    if path.endswith('.py'):
        try:
            ast.parse(text)
            return {'kind': 'python-parse-only', 'ok': True, 'semantic_validation': False}
        except SyntaxError as exc:
            return {'kind': 'python-parse-only', 'ok': False, 'line': exc.lineno, 'message': exc.msg}
    stack, pairs = [], {')': '(', ']': '[', '}': '{'}
    good = True
    for ch in text:
        if ch in '([{':
            stack.append(ch)
        elif ch in pairs and (not stack or stack.pop() != pairs[ch]):
            good = False; break
    return {'kind': 'raw-bracket-heuristic', 'ok': good and not stack, 'semantic_validation': False}
