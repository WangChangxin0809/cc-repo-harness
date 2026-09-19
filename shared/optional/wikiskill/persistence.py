"""Crash-consistent checkpoints and immutable per-task evidence; never pickle.

State and audit events commit in one SQLite transaction. A process lock keeps
one runner in flight; it is released by the OS on abrupt exit. Exports are
rebuildable views, not the source of truth. Store outside the public repository.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(dumps(value).encode('utf-8')).hexdigest()


@contextmanager
def writer_lock(path):
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        if os.name == 'posix':
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        elif os.name == 'nt':
            import msvcrt
            os.write(fd, b'0'); os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            raise RuntimeError('no process-lock implementation')
        yield
    finally:
        os.close(fd)


class RunDB:
    def __init__(self, root):
        self.root = Path(root).absolute()
        for part in [self.root, *self.root.parents]:
            if part.is_symlink():
                raise ValueError('run directory ancestors cannot be symlinks')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / 'run.sqlite3'
        if self.path.is_symlink():
            raise ValueError('run database cannot be a symlink')
        with self.connect() as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.executescript('''
                CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL, body TEXT NOT NULL, time REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS evidence(key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, body TEXT NOT NULL);
            ''')
        if os.name == 'posix': os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try: yield c
        finally: c.close()

    def lock(self):
        return writer_lock(self.root / 'run.lock')

    def load(self):
        with self.connect() as c:
            row = c.execute('SELECT body FROM state WHERE id=1').fetchone()
        return json.loads(row[0]) if row else None

    def save(self, state, kind, detail=None):
        encoded = dumps(state)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                c.execute('INSERT OR REPLACE INTO state VALUES(1,?)', (encoded,))
                c.execute('INSERT INTO audit(kind,body,time) VALUES(?,?,?)',
                          (kind, dumps(detail or {'stage': state['stage']}), time.time()))
                c.commit()
            except BaseException:
                c.rollback(); raise

    def evidence(self, key, input_value, result=None):
        fp = digest(input_value)
        with self.connect() as c:
            row = c.execute('SELECT fingerprint,body FROM evidence WHERE key=?', (key,)).fetchone()
            if row:
                if row[0] != fp: raise ValueError('cached evidence input changed')
                prior = json.loads(row[1])
                if result is not None and dumps(prior) != dumps(result):
                    raise ValueError('immutable evidence cannot be replaced')
                return prior
            if result is not None:
                c.execute('INSERT INTO evidence VALUES(?,?,?)', (key, fp, dumps(result)))
            return result

    def audit(self):
        with self.connect() as c:
            return [{'seq': seq, 'kind': kind, 'body': json.loads(body), 'time': stamp}
                    for seq, kind, body, stamp in c.execute('SELECT * FROM audit ORDER BY seq')]
