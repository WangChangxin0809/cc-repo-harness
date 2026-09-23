"""Standard-library selftests for the optional WikiSkill and reviewed-knowledge preview."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from adapters import CommandAdapter
from knowledge import Knowledge
from model import CannotJudge, Evolution, Proposal, Task, Trace, WikiEdit
from runner import Runner


class WikiSkillTests(unittest.TestCase):
    def test_process_demo_accepts_skill_and_reserves_final_test(self):
        dataset = json.loads((HERE / "examples/demo-dataset.json").read_text(encoding="utf-8"))
        adapter = CommandAdapter([sys.executable, str(HERE / "examples/demo_adapter.py")], allow_exec=True)
        with tempfile.TemporaryDirectory(prefix="wikiskill-demo-") as tmp:
            state = Runner(tmp, dataset, adapter, iterations=2).run()
        self.assertEqual(state["stage"], "complete")
        self.assertEqual(state["best"], 1.0)
        self.assertEqual(state["final_test"], 1.0)
        self.assertIn("uppercase_text", state["skills"])
        self.assertEqual(state["impacts"][0]["verdict"], "accepted")

    def test_equal_validation_score_is_rejected_and_wiki_survives(self):
        splits = {
            "train": tuple(Task(f"tr{i}", f"tg{i}") for i in range(4)),
            "val": (Task("v", "vg"),),
            "test": (Task("t", "xg"),),
        }
        def rollout(inp):
            return [Trace(t.name, 0.5, "trace-" + t.name) for t in inp.tasks]
        def maintain(wiki, traces):
            return WikiEdit("kept", "learned")
        def propose(view):
            for path in [f"traces/tr{i}" for i in range(4)]:
                view.read_file(path)
            return Proposal("create", "same_score",
                "---\nname: same_score\ndescription: Same score\n---\nDo the same.\n", "test")
        state = Evolution(splits, rollout, maintain, propose, iterations=1).run()
        self.assertEqual(state.skills, {})
        self.assertEqual(state.impacts[0]["verdict"], "rejected")
        self.assertEqual(state.wiki["index.md"], "kept")

    def test_proposer_must_read_four_distinct_current_traces(self):
        splits = {
            "train": tuple(Task(f"tr{i}", f"tg{i}") for i in range(4)),
            "val": (Task("v", "vg"),),
            "test": (Task("t", "xg"),),
        }
        def rollout(inp):
            return [Trace(t.name, 0.0, "trace-" + t.name) for t in inp.tasks]
        def maintain(wiki, traces):
            return WikiEdit("index", "log")
        def propose(view):
            view.read_file("traces/tr0")
            return Proposal("create", "bad",
                "---\nname: bad\ndescription: Bad\n---\nBad.\n", "bad")
        with self.assertRaises(CannotJudge):
            Evolution(splits, rollout, maintain, propose, iterations=1).run()

    def test_reviewed_knowledge_goes_stale_after_source_update(self):
        with tempfile.TemporaryDirectory(prefix="knowledge-") as tmp:
            kb = Knowledge(tmp)
            first = kb.ingest("source", "alpha\nbeta", "fixture")
            spec = {"title": "Alpha", "content": "beta is present",
                    "evidence": [{"source": "source", "sha256": first["sha256"], "start": 2, "end": 2}],
                    "claims": [{"key": "answer", "value": "beta"}], "supersedes": []}
            kb.draft("page", spec)
            kb.approve("page", "reviewer")
            self.assertEqual(kb.query("beta")["hits"][0]["page"], "page")
            kb.ingest("source", "alpha\ngamma", "fixture")
            self.assertEqual(kb.query("beta")["hits"], [])
            self.assertTrue(any(i["kind"] == "stale-source" for i in kb.lint()["issues"]))

    def test_parent_symlink_is_canonicalized_but_final_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="knowledge-path-") as tmp:
            root = Path(tmp)
            real_parent = root / "real"
            real_parent.mkdir()
            alias_parent = root / "alias"
            try:
                alias_parent.symlink_to(real_parent, target_is_directory=True)
            except OSError as exc:
                self.skipTest("host cannot create directory symlink fixture: " + str(exc))

            # An ancestor alias is resolved once to its canonical target.
            kb = Knowledge(alias_parent / "child")
            self.assertEqual(kb.root, (real_parent / "child").resolve())
            self.assertTrue(kb.root.is_dir())

            # The caller's final target may not itself be a symlink.
            real_target = root / "target"
            real_target.mkdir()
            direct_alias = root / "direct-alias"
            direct_alias.symlink_to(real_target, target_is_directory=True)
            with self.assertRaises(ValueError):
                Knowledge(direct_alias)

    def test_publication_exports_only_approved_pages(self):
        with tempfile.TemporaryDirectory(prefix="knowledge-") as tmp, tempfile.TemporaryDirectory(prefix="publish-parent-") as out:
            kb = Knowledge(tmp)
            source = kb.ingest("source", "one\ntwo", "fixture")
            spec = {"title": "Reviewed", "content": "Two.",
                    "evidence": [{"source": "source", "sha256": source["sha256"], "start": 2, "end": 2}],
                    "claims": [], "supersedes": []}
            kb.draft("reviewed", spec); kb.approve("reviewed", "human")
            target = Path(out) / "site"
            result = kb.publish(target)
            self.assertEqual(result, {"pages": 1, "raw_exported": False})
            self.assertTrue((target / "reviewed.md").exists())
            self.assertFalse((target / "source").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
