"""Single-host advisory coordination; no source-file writes and no CRDT.

One SQLite database per canonical Git worktree, shared by independent stdio
servers. Every state transition is committed before it is returned. A lease
is coordination, NOT a filesystem lock, authorization boundary, or safe proof
that a timed-out process stopped writing.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

try:
    from .localio import file_lock
except ImportError:
    from localio import file_lock

SCHEMA = 1
MAX_MESSAGE_BYTES = 8192
MAX_PAGE = 100


def git_paths(root):
    """Resolve the worktree and its private git-dir; linked worktrees stay apart."""
    def query(flag):
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", flag],
            capture_output=True, text=True, encoding="utf-8", timeout=10,
        )
        if result.returncode:
            raise ValueError("a non-bare Git worktree is required")
        return Path(result.stdout.strip()).resolve()
    return query("--show-toplevel"), query("--absolute-git-dir")


def text(value, label, maximum):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be a nonempty string")
    if len(value.encode("utf-8")) > maximum or "\x00" in value:
        raise ValueError(label + " is too long or contains NUL")
    return value


class Room:
    def __init__(self, root, *, name="agent", ttl=300.0, clock=time.time, owner=None):
        if isinstance(ttl, bool) or not isinstance(ttl, (int, float)):
            raise ValueError("ttl must be numeric")
        if not math.isfinite(ttl) or not 0 < ttl <= 3600:
            raise ValueError("ttl must be finite, positive and <= 3600 seconds")
        self.root, gitdir = git_paths(root)
        self.name = text(name, "name", 128)
        self.owner = owner or uuid.uuid4().hex
        self.ttl, self.clock = ttl, clock
        state_dir = gitdir / "cc-repo-harness-room"
        if state_dir.is_symlink():
            raise ValueError("room state directory must not be a symlink")
        state_dir.mkdir(mode=0o700, exist_ok=True)
        self.db = state_dir / "state.sqlite3"
        if self.db.is_symlink():
            raise ValueError("room database must not be a symlink")
        # WAL selection and first-schema creation need a cross-process critical
        # section. SQLite transaction timeouts protect normal writes, but several
        # processes racing the first PRAGMA journal_mode=WAL can fail before the
        # schema exists (observed on Python 3.13).
        with file_lock(state_dir / "init.lock"):
            with self._connection() as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, SCHEMA):
                    raise ValueError("unsupported room schema; do not delete a live database")
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS agents(owner TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL, seen REAL NOT NULL);
                    CREATE TABLE IF NOT EXISTS claims(path TEXT PRIMARY KEY, owner TEXT NOT NULL, lease TEXT NOT NULL, expires REAL NOT NULL);
                    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL, created REAL NOT NULL);
                    CREATE TABLE IF NOT EXISTS receipts(owner TEXT NOT NULL, request TEXT NOT NULL, message TEXT NOT NULL, event_id INTEGER NOT NULL, PRIMARY KEY(owner, request));
                """)
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("INSERT OR IGNORE INTO metadata VALUES('root', ?)", (str(self.root),))
                stored = conn.execute("SELECT value FROM metadata WHERE key='root'").fetchone()[0]
                if stored != str(self.root):
                    conn.rollback()
                    raise ValueError("worktree moved; archived state must be migrated explicitly")
                conn.execute("PRAGMA user_version=1")
                conn.commit()
            if os.name == "posix":
                os.chmod(self.db, 0o600)

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(str(self.db), timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _event(conn, owner, kind, body, now):
        return conn.execute(
            "INSERT INTO events(owner,kind,body,created) VALUES(?,?,?,?)",
            (owner, kind, json.dumps(body, ensure_ascii=False), now),
        ).lastrowid

    @contextmanager
    def _transaction(self, status=None):
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                now = self.clock()
                for row in conn.execute("SELECT * FROM claims WHERE expires<=?", (now,)).fetchall():
                    self._event(conn, row["owner"], "expired", {"path": row["path"]}, now)
                conn.execute("DELETE FROM claims WHERE expires<=?", (now,))
                conn.execute(
                    "INSERT INTO agents VALUES(?,?,?,?) ON CONFLICT(owner) DO UPDATE SET "
                    "seen=excluded.seen, status=COALESCE(?, agents.status)",
                    (self.owner, self.name, status or "working", now, status),
                )
                yield conn, now
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def path_key(self, path):
        """Exact relative file paths only; reject aliases with mutable targets."""
        text(path, "path", 4096)
        if any(ord(c) < 32 for c in path) or "\\" in path or ":" in path:
            raise ValueError("use a relative POSIX file path, not an alias or control character")
        parts = path.split("/")
        if path.startswith("/") or any(p in ("", ".", "..") for p in parts):
            raise ValueError("absolute paths, empty segments and dot traversal are not allowed")
        if any(p.lower() == ".git" for p in parts) or any(c in path for c in "*?[]"):
            raise ValueError("Git metadata and wildcard claims are not allowed")
        target = self.root
        for index, part in enumerate(parts):
            target = target / part
            if target.is_symlink():
                raise ValueError("symlink paths are not claimable")
            if index < len(parts) - 1 and target.exists() and not target.is_dir():
                raise ValueError("a parent path is not a directory")
        if target.exists():
            if not target.is_file() or target.stat().st_nlink > 1:
                raise ValueError("claim one regular file, not a directory or hard link")
        return os.path.normcase(path).replace("\\", "/")

    def claim(self, path):
        path = self.path_key(path)
        with self._transaction() as (conn, now):
            current = conn.execute("SELECT * FROM claims WHERE path=?", (path,)).fetchone()
            if current and current["owner"] != self.owner:
                self._event(conn, self.owner, "conflict", {"path": path, "held_by": current["owner"]}, now)
                return {"ok": False, "reason": "conflict", "path": path,
                        "held_by": current["owner"], "expires": current["expires"]}
            if not current:
                for row in conn.execute("SELECT path, owner FROM claims"):
                    if path.startswith(row["path"] + "/") or row["path"].startswith(path + "/"):
                        return {"ok": False, "reason": "overlapping-path", "path": path, "held_by": row["owner"]}
                if conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] >= 256:
                    return {"ok": False, "reason": "room-claim-capacity", "path": path}
            lease = current["lease"] if current else uuid.uuid4().hex
            conn.execute(
                "INSERT INTO claims VALUES(?,?,?,?) ON CONFLICT(path) DO UPDATE SET expires=excluded.expires",
                (path, self.owner, lease, now + self.ttl),
            )
            if not current:
                self._event(conn, self.owner, "claimed", {"path": path}, now)
            return {"ok": True, "path": path, "owner": self.owner, "lease": lease, "expires": now + self.ttl}

    def release(self, path, lease):
        path = self.path_key(path)
        text(lease, "lease", 128)
        with self._transaction() as (conn, now):
            changed = conn.execute(
                "DELETE FROM claims WHERE path=? AND owner=? AND lease=?",
                (path, self.owner, lease),
            ).rowcount
            if changed:
                self._event(conn, self.owner, "released", {"path": path}, now)
            return {"ok": bool(changed), "path": path,
                    "reason": "released" if changed else "not-owned-or-stale"}

    def state(self, status="working", renew=False):
        text(status, "status", 256)
        if not isinstance(renew, bool):
            raise ValueError("renew must be a boolean")
        with self._transaction(status) as (conn, now):
            if renew:
                conn.execute("UPDATE claims SET expires=? WHERE owner=?", (now + self.ttl, self.owner))
            claims = [dict(r) for r in conn.execute("SELECT * FROM claims ORDER BY path")]
            peers = [dict(r) for r in conn.execute("SELECT * FROM agents ORDER BY seen DESC, owner LIMIT 65")]
            cursor = conn.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]
            return {"owner": self.owner, "claims": claims, "agents": peers[:64],
                    "agents_truncated": len(peers) > 64, "cursor": cursor, "now": now,
                    "advisory_only": True, "crdt": False}

    def broadcast(self, message, request_id):
        text(message, "message", MAX_MESSAGE_BYTES)
        text(request_id, "request_id", 128)
        with self._transaction() as (conn, now):
            old = conn.execute("SELECT * FROM receipts WHERE owner=? AND request=?",
                               (self.owner, request_id)).fetchone()
            if old:
                if old["message"] != message:
                    raise ValueError("request_id already used with different message")
                return {"ok": True, "id": old["event_id"], "replayed": True}
            seq = self._event(conn, self.owner, "broadcast", {"message": message}, now)
            conn.execute("INSERT INTO receipts VALUES(?,?,?,?)", (self.owner, request_id, message, seq))
            return {"ok": True, "id": seq, "replayed": False}

    def read(self, after=0, limit=50):
        if type(after) is not int or after < 0 or after > 2**63 - 1:
            raise ValueError("after must be a nonnegative 64-bit integer")
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
            raise ValueError("limit must be between 1 and 100")
        with self._transaction() as (conn, _now):
            high = conn.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]
            if after > high:
                raise ValueError("cursor is ahead of this room; use after=0 for a new room")
            rows = conn.execute("SELECT * FROM events WHERE id>? ORDER BY id LIMIT ?", (after, limit + 1)).fetchall()
            events = [{**dict(r), "body": json.loads(r["body"])} for r in rows[:limit]]
            return {"events": events, "next_cursor": events[-1]["id"] if events else after,
                    "has_more": len(rows) > limit, "untrusted_content": True}

    def close(self):
        """Best-effort clean disconnect; SIGKILL is recovered by lease expiry."""
        with self._transaction("disconnected") as (conn, now):
            paths = [r[0] for r in conn.execute("SELECT path FROM claims WHERE owner=?", (self.owner,))]
            conn.execute("DELETE FROM claims WHERE owner=?", (self.owner,))
            for path in paths:
                self._event(conn, self.owner, "released", {"path": path, "disconnect": True}, now)
