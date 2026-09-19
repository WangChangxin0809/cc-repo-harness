"""Opt-in install; no dependencies installed and no server automatically started.

Default is a dry run. --apply copies a versioned payload and adds ONE .mcp.json
entry. Existing other servers survive; edited payload/config conflicts abort
before writing. Stop agent sessions before installing. Upgrades are deliberately
not guessed: differing installed files require a reviewed migration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from store import git_paths

HERE = Path(__file__).resolve().parent
FILES = ("store.py", "server.py", "crdt.py", "localio.py", "workspace.py", "protocol.py",
         "room_cli.py", "requirements.txt", "selftest.py", "protocol_selftest.py", "README.md", "__init__.py")
VERSION = "0.3.0"
ENTRY = {"type": "stdio", "command": "${ROOM_PYTHON:-python3}",
         "args": ["${CLAUDE_PROJECT_DIR:-.}/scripts/room/server.py", "--profile", "paper"]}


def prepare(root, profile="paper"):
    if profile not in ("paper", "reference"): raise ValueError("unknown runtime profile")
    entry = dict(ENTRY, args=[*ENTRY["args"][:-1], profile])
    root, gitdir = git_paths(root)
    target = root / "scripts" / "room"
    config_path = root / ".mcp.json"
    for path in (root / "scripts", target, config_path):
        if path.is_symlink():
            raise ValueError("refusing to install through symlink: " + path.name)
    old = config_path.read_bytes() if config_path.exists() else None
    config = json.loads(old) if old is not None else {}
    if not isinstance(config, dict) or not isinstance(config.get("mcpServers", {}), dict):
        raise ValueError(".mcp.json must contain an object of mcpServers")
    servers = config.setdefault("mcpServers", {})
    if "room" in servers and servers["room"] != entry:
        raise ValueError("existing room server differs; merge by hand, not by overwriting it")
    payload = {name: (HERE / name).read_bytes() for name in FILES}
    manifest = {"version": VERSION,
                "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()}}
    payload["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    if target.exists():
        if not target.is_dir():
            raise ValueError("scripts/room exists and is not a directory")
        for name, data in payload.items():
            path = target / name
            if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
                raise ValueError("installed payload differs: " + name + "; review an upgrade")
    servers["room"] = entry
    new = (json.dumps(config, indent=2, ensure_ascii=False) + "\n").encode()
    return root, gitdir, target, config_path, old, new, payload


def install(root, apply=False, profile="paper"):
    root, gitdir, target, config_path, old, new, payload = prepare(root, profile)
    plan = {"apply": apply, "profile": profile, "payload": "scripts/room", "files": sorted(payload),
            "config": ".mcp.json", "starts_server": False, "installs_dependencies": False}
    if not apply:
        return plan
    lock = gitdir / "cc-repo-harness-room-install.lock"
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError("installer lock exists; inspect other installers before removing it") from exc
    os.close(fd)
    staging, config_tmp = None, None
    try:
        root, gitdir, target, config_path, old, new, payload = prepare(root, profile)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            staging = Path(tempfile.mkdtemp(prefix=".room-stage-", dir=target.parent))
            for name, data in payload.items():
                (staging / name).write_bytes(data)
        fd, tmp = tempfile.mkstemp(prefix=".room-config-", dir=root)
        config_tmp = Path(tmp)
        with os.fdopen(fd, "wb") as out:
            out.write(new); out.flush(); os.fsync(out.fileno())
        if (config_path.read_bytes() if config_path.exists() else None) != old:
            raise ValueError(".mcp.json changed during installation; retry after review")
        if staging is not None:
            staging.rename(target); staging = None
        if old != new:
            if old is not None:
                backup = gitdir / "cc-repo-harness-mcp-before-room.json"
                if not backup.exists():
                    with backup.open("xb") as out: out.write(old)
                    if os.name == "posix": os.chmod(backup, 0o600)
            config_tmp.replace(config_path); config_tmp = None
        return plan
    finally:
        if staging is not None: shutil.rmtree(staging)
        if config_tmp is not None: config_tmp.unlink(missing_ok=True)
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--profile", choices=["paper", "reference"], default="paper")
    args = parser.parse_args()
    try: print(json.dumps(install(args.root, args.apply, args.profile), indent=2))
    except (OSError, ValueError) as exc:
        print("could not install: " + str(exc), file=sys.stderr); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
