"""Single-host OS locks, bounded reads, and durable same-directory replacement.

An OS lock coordinates participants, not arbitrary shell writers. Paths must
be owned by the current user/trusted process. This is not a sandbox.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def read_bytes(path, limit=128_000):
    path = Path(path)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError('expected one regular non-symlink file')
    with path.open('rb') as fh:
        data = fh.read(limit + 1)
    if len(data) > limit:
        raise ValueError('file size exceeds limit')
    return data


@contextmanager
def file_lock(path, blocking=True):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('lock cannot be a symlink')
    flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    try:
        if os.name == 'posix':
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        elif os.name == 'nt':
            import msvcrt
            # Windows can lock a byte beyond EOF. Do not initialize the file
            # before acquiring the lock: concurrent first users can race while
            # writing the same byte and fail with a sharing violation.
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK, 1)
        else:
            raise RuntimeError('no supported process-lock backend')
        yield
    finally:
        os.close(fd)


def sync_directory(path):
    if os.name == 'posix':
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try: os.fsync(fd)
        finally: os.close(fd)


def atomic_write(path, data, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('destination cannot be a symlink')
    fd, tmp = tempfile.mkstemp(prefix='.room-stage-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as fh:
            fh.write(data); fh.flush(); os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
