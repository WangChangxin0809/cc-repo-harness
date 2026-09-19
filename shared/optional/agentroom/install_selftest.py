"""An opt-in install must preserve unrelated settings and stop on local edits."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from install import install, ENTRY
from selftest import init_repo


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="room-install-")
        self.root = init_repo(Path(self.tmp.name) / "repo")

    def tearDown(self):
        self.tmp.cleanup()

    def test_dry_run_does_not_write(self):
        install(self.root)
        self.assertFalse((self.root / "scripts").exists())
        self.assertFalse((self.root / ".mcp.json").exists())

    def test_repeat_install_and_unrelated_server_preserved(self):
        original = {"mcpServers": {"existing": {"type": "stdio", "command": "already-installed"}}}
        (self.root / ".mcp.json").write_text(json.dumps(original), encoding="utf-8")
        install(self.root, True)
        first = (self.root / ".mcp.json").read_bytes()
        install(self.root, True)
        self.assertEqual((self.root / ".mcp.json").read_bytes(), first)
        parsed = json.loads(first)
        self.assertEqual(parsed["mcpServers"]["existing"], original["mcpServers"]["existing"])
        self.assertEqual(parsed["mcpServers"]["room"], ENTRY)
        self.assertTrue((self.root / "scripts/room/manifest.json").exists())
        self.assertEqual(json.loads((self.root / ".git/cc-repo-harness-mcp-before-room.json").read_text()), original)

    def test_installed_store_works_without_plugin_import_path(self):
        install(self.root, True)
        copied = self.root / "scripts/room"
        env = dict(os.environ, PYTHONPATH="")
        proc = subprocess.run(
            [sys.executable, "-c",
             "from store import Room; r=Room('.'); "
             "assert r.claim('independent.py')['ok']; "
             "assert r.broadcast('detached','one')['ok']; r.close()"],
            cwd=copied, env=env, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_different_room_configuration_refused_before_writes(self):
        body = json.dumps({"mcpServers": {"room": {"command": "other"}}})
        (self.root / ".mcp.json").write_text(body, encoding="utf-8")
        with self.assertRaises(ValueError):
            install(self.root, True)
        self.assertFalse((self.root / "scripts").exists())
        self.assertEqual((self.root / ".mcp.json").read_text(encoding="utf-8"), body)

    def test_malformed_config_refused_before_writes(self):
        (self.root / ".mcp.json").write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError):
            install(self.root, True)
        self.assertFalse((self.root / "scripts").exists())

    def test_local_payload_edit_is_not_overwritten(self):
        install(self.root, True)
        changed = self.root / "scripts/room/store.py"
        changed.write_text("# local customization\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            install(self.root, True)
        self.assertEqual(changed.read_text(encoding="utf-8"), "# local customization\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
