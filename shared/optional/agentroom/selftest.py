"""Black-box storage checks, including independent processes and a killed writer.

These test the implementation, NOT task success or a repository's readiness.
No model, SDK, repository hooks or external repository code is executed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import os
import platform
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from store import Room, MAX_MESSAGE_BYTES

HERE = Path(__file__).resolve().parent


def init_repo(path):
    Path(path).mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--quiet", str(path)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return Path(path)


def contend(root, barrier, output):
    room = Room(root, name="same-display-name")
    barrier.wait(timeout=15)
    output.put(room.claim("shared.txt"))


def crash_transaction(root):
    room = Room(root)
    conn = sqlite3.connect(str(room.db), isolation_level=None)
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("INSERT INTO events(owner,kind,body,created) VALUES('dead','broadcast','{}',0)")
    os._exit(17)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class RoomTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="room-selftest-")
        self.root = init_repo(Path(self.tmp.name) / "repo")
        self.clock = Clock()
        self.a = Room(self.root, name="A", clock=self.clock)
        self.b = Room(self.root, name="B", clock=self.clock)

    def tearDown(self):
        self.tmp.cleanup()

    def test_conflict_is_not_a_second_owner(self):
        first = self.a.claim("src/a.py")
        self.assertTrue(first["ok"])
        self.assertFalse(self.b.claim("src/a.py")["ok"])
        self.assertEqual(len(self.b.state()["claims"]), 1)
        self.assertEqual(self.b.state()["claims"][0]["owner"], first["owner"])

    def test_independent_paths_do_not_block(self):
        self.assertTrue(self.a.claim("src/a.py")["ok"])
        self.assertTrue(self.b.claim("src/b.py")["ok"])

    def test_ancestor_claims_and_existing_file_parents_are_refused(self):
        self.a.claim("new-file")
        self.assertFalse(self.b.claim("new-file/child")["ok"])
        self.b.claim("src/new-child")
        self.assertFalse(self.a.claim("src")["ok"])
        (self.root / "regular").write_text("x", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.a.claim("regular/child")

    def test_claim_retry_reuses_live_lease(self):
        first = self.a.claim("a.py")
        self.clock.now += 1
        self.assertEqual(self.a.claim("a.py")["lease"], first["lease"])

    def test_other_actor_cannot_release_even_with_token(self):
        first = self.a.claim("a.py")
        self.assertFalse(self.b.release("a.py", first["lease"])["ok"])
        self.assertTrue(self.a.release("a.py", first["lease"])["ok"])
        self.assertTrue(self.b.claim("a.py")["ok"])

    def test_stale_release_cannot_release_new_lease(self):
        first = self.a.claim("a.py")
        self.clock.now += 301
        second = self.a.claim("a.py")
        self.assertNotEqual(first["lease"], second["lease"])
        self.assertFalse(self.a.release("a.py", first["lease"])["ok"])
        self.assertFalse(self.b.claim("a.py")["ok"])

    def test_expiration_and_no_resurrection(self):
        self.a.claim("a.py")
        self.clock.now += 301
        self.assertEqual(self.a.state(renew=True)["claims"], [])
        self.assertTrue(self.b.claim("a.py")["ok"])
        kinds = [e["kind"] for e in self.b.read()["events"]]
        self.assertEqual(kinds.count("expired"), 1)

    def test_heartbeat_renews_only_own_live_claims(self):
        self.a.claim("a.py")
        self.b.claim("b.py")
        self.clock.now += 200
        self.a.state(renew=True)
        self.clock.now += 101
        paths = {c["path"] for c in self.a.state()["claims"]}
        self.assertEqual(paths, {"a.py"})

    def test_broadcast_retry_is_exactly_once_per_session(self):
        first = self.a.broadcast("interface returns integer balance", "message-1")
        self.assertEqual(first["id"], self.a.broadcast("interface returns integer balance", "message-1")["id"])
        with self.assertRaises(ValueError):
            self.a.broadcast("different", "message-1")
        events = self.b.read()["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["body"]["message"], "interface returns integer balance")

    def test_cursor_pages_have_no_loss_or_duplicates(self):
        for n in range(7):
            self.a.broadcast(str(n), str(n))
        seen, after = [], 0
        while True:
            page = self.b.read(after, 2)
            seen.extend(e["id"] for e in page["events"])
            after = page["next_cursor"]
            if not page["has_more"]:
                break
        self.assertEqual(len(seen), 7)
        self.assertEqual(len(set(seen)), 7)
        self.assertEqual(seen, sorted(seen))
        self.assertEqual(self.b.read(after)["events"], [])
        with self.assertRaises(ValueError):
            self.b.read(after + 100)

    def test_inputs_are_bounded_before_writing(self):
        for path in ("", "/etc/passwd", "../other", "src/../a", "a//b", "./a",
                     "a\\b", "C:/a", ".git/config", "src/*", "a\n.py"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.a.claim(path)
        with self.assertRaises(ValueError):
            self.a.broadcast("x" * (MAX_MESSAGE_BYTES + 1), "large")
        for bad in (True, -1, 2**80, "1"):
            with self.subTest(cursor=bad), self.assertRaises(ValueError):
                self.b.read(bad)
        for bad in (True, 0, 101):
            with self.subTest(limit=bad), self.assertRaises(ValueError):
                self.b.read(0, bad)
        self.assertEqual(self.b.read()["events"], [])

    def test_aliases_are_refused(self):
        (self.root / "file").write_text("unchanged", encoding="utf-8")
        try:
            (self.root / "alias").symlink_to(self.root / "file")
            os.link(self.root / "file", self.root / "hardlink")
        except OSError as exc:
            self.skipTest("host cannot create alias fixtures: " + str(exc))
        for path in ("alias", "hardlink", "file"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.a.claim(path)

    def test_reopen_keeps_messages_but_not_identity(self):
        self.a.broadcast("persist", "p")
        reopened = Room(self.root, name="A", clock=self.clock)
        self.assertNotEqual(reopened.owner, self.a.owner)
        self.assertEqual(reopened.read()["events"][0]["body"]["message"], "persist")

    def test_disconnection_releases_only_own_paths(self):
        self.a.claim("a")
        self.b.claim("b")
        self.a.close()
        self.assertEqual([c["path"] for c in self.b.state()["claims"]], ["b"])

    def test_repositories_are_isolated(self):
        other = init_repo(Path(self.tmp.name) / "other")
        room = Room(other, clock=self.clock)
        self.a.claim("same")
        self.assertTrue(room.claim("same")["ok"])
        self.assertNotEqual(self.a.db, room.db)

    def test_linked_worktrees_are_isolated(self):
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "-c", "core.hooksPath=/dev/null",
                        "commit", "--allow-empty", "-qm", "fixture"], check=True)
        linked = Path(self.tmp.name) / "linked"
        subprocess.run(["git", "-C", str(self.root), "-c", "core.hooksPath=/dev/null",
                        "worktree", "add", "--detach", str(linked)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        other = Room(linked, clock=self.clock)
        self.a.claim("same")
        self.assertTrue(other.claim("same")["ok"])
        self.assertNotEqual(self.a.db, other.db)

    def test_eight_processes_elect_one_owner(self):
        ctx = multiprocessing.get_context("spawn")
        barrier, output = ctx.Barrier(8), ctx.Queue()
        processes = [ctx.Process(target=contend, args=(str(self.root), barrier, output)) for _ in range(8)]
        try:
            for process in processes:
                process.start()
            results = [output.get(timeout=25) for _ in processes]
            for process in processes:
                process.join(10)
                self.assertEqual(process.exitcode, 0)
            self.assertEqual(sum(r["ok"] for r in results), 1)
            winner = next(r for r in results if r["ok"])
            self.assertEqual({r["held_by"] for r in results if not r["ok"]}, {winner["owner"]})
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                process.join(5)
            output.close()
            output.join_thread()

    def test_first_use_from_independent_processes(self):
        fresh = init_repo(Path(self.tmp.name) / "fresh")
        ctx = multiprocessing.get_context("spawn")
        barrier, output = ctx.Barrier(8), ctx.Queue()
        processes = [ctx.Process(target=contend, args=(str(fresh), barrier, output)) for _ in range(8)]
        try:
            for process in processes:
                process.start()
            results = [output.get(timeout=25) for _ in processes]
            for process in processes:
                process.join(10)
                self.assertEqual(process.exitcode, 0)
            self.assertEqual(sum(r["ok"] for r in results), 1)
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                process.join(5)
            output.close()
            output.join_thread()

    def test_killed_uncommitted_writer_is_rolled_back(self):
        ctx = multiprocessing.get_context("spawn")
        process = ctx.Process(target=crash_transaction, args=(str(self.root),))
        process.start()
        process.join(15)
        if process.is_alive():
            process.terminate()
            process.join(5)
            self.fail("crash fixture hung")
        self.assertEqual(process.exitcode, 17)
        self.assertEqual(self.b.read()["events"], [])
        self.assertTrue(self.b.broadcast("still usable", "after-crash")["ok"])

    def test_state_never_writes_source_files(self):
        (self.root / "source.txt").write_text("original", encoding="utf-8")
        self.a.claim("source.txt")
        self.a.broadcast("not executable", "x")
        self.a.state(renew=True)
        self.a.close()
        self.assertEqual((self.root / "source.txt").read_text(encoding="utf-8"), "original")
        result = subprocess.run(["git", "-C", str(self.root), "status", "--porcelain"],
                                capture_output=True, text=True, encoding="utf-8", check=True)
        self.assertEqual(result.stdout.strip(), "?? source.txt")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, help="write a machine-readable conformance report")
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RoomTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    code = 1 if not result.wasSuccessful() else 2 if result.skipped else 0
    if args.json:
        report = {
            "schema": 1, "scope": "implementation-conformance-not-repository-readiness",
            "tests": result.testsRun, "failed": len(result.failures) + len(result.errors),
            "skipped": len(result.skipped), "exit_code": code,
            "python": platform.python_version(), "platform": sys.platform,
            "sha256": {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest()
                       for n in ("store.py", "selftest.py")},
            "mcp_protocol": "not-tested-by-this-suite",
            "crdt": "not-tested-by-this-coordination-suite", "task_outcomes": "not-measured",
        }
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
