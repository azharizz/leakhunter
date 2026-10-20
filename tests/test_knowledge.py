import sqlite3
import tempfile
import unittest
from pathlib import Path

from leakhunter.storage.knowledge import KnowledgeBank


class KnowledgeIntegrityTest(unittest.TestCase):
    def test_artifact_collection_names_cannot_inject_sql(self):
        with tempfile.TemporaryDirectory() as directory:
            bank = KnowledgeBank(Path(directory))
            for name in ("metrics; DROP TABLE snapshots;--", "metrics WHERE 1=1", "sqlite_master"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    bank.append(name, {"value": "synthetic"})
                with self.subTest(name=name), self.assertRaises(ValueError):
                    bank.records(name)
            payload = {"value": "'); DROP TABLE snapshots;--"}
            stored = bank.append("metrics", payload)
            self.assertEqual(bank.records("metrics")[0], stored)
            with bank.connect() as db:
                self.assertEqual(db.execute("SELECT count(*) FROM snapshots").fetchone()[0], 0)

    def test_annotation_crud_cannot_change_snapshot_or_other_branch(self):
        with tempfile.TemporaryDirectory() as directory:
            bank = KnowledgeBank(Path(directory))
            original = {"revision_sha": "r1", "nodes": [{"id": "a", "label": "original", "kind": "source"},
                                                       {"id": "b", "label": "sink", "kind": "sink"}],
                        "edges": [{"id": "ab", "source": "a", "target": "b", "type": "FLOWS_TO"}], "findings": []}
            baseline = bank.save_snapshot(original)
            bank.mutate("nodes", "update", {"label": "reviewed"}, "a")
            bank.mutate("edges", "update", {"type": "REVIEWED_FLOW"}, "ab")
            self.assertEqual(bank.graph()["nodes"][0]["label"], "reviewed")
            self.assertEqual(bank.graph()["edges"][0]["type"], "REVIEWED_FLOW")
            self.assertEqual(bank.snapshot(baseline["snapshot_id"])["nodes"][0]["label"], "original")
            overlay = bank.save_snapshot(dict(original, revision_sha="r2"), "mr/42", baseline["snapshot_id"])
            self.assertEqual(bank.snapshot()["revision_sha"], "r1")
            self.assertEqual(bank.snapshot(branch="mr/42")["snapshot_id"], overlay["snapshot_id"])
            bank.save_snapshot(dict(original, revision_sha="r3"), parent_id=baseline["snapshot_id"])
            self.assertEqual(bank.graph()["nodes"][0]["label"], "reviewed")
            bank.mutate("nodes", "delete", ident="a")
            self.assertEqual([node["id"] for node in bank.graph()["nodes"]], ["b"])
            self.assertEqual(bank.graph()["edges"], [])
            self.assertEqual(bank.snapshot(baseline["snapshot_id"])["edges"], original["edges"])
            with bank.connect() as db:
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute("UPDATE snapshots SET revision='forged'")

    def test_policy_semantics_are_immutable_across_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            bank = KnowledgeBank(Path(directory))
            raw = {"version": 1, "status": "draft", "classifications": {"PUBLIC": 0, "SECRET": 1}}
            record = bank.register_policy(raw)
            self.assertEqual(record["status"], "draft")
            approved = bank.register_policy(raw, approve_by="security-owner")
            self.assertEqual(approved["digest"], record["digest"])
            self.assertEqual(bank.register_policy(raw)["status"], "approved")
            with self.assertRaises(ValueError):
                bank.register_policy(dict(raw, classifications={"PUBLIC": 0, "SECRET": 99}))
            with self.assertRaises(ValueError):
                bank.register_policy(raw, approve_by=" ")

    def test_invalid_edges_and_renamed_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            bank = KnowledgeBank(Path(directory))
            bank.mutate("nodes", "create", {"id": "a", "label": "one", "kind": "source"})
            with self.assertRaises(ValueError):
                bank.mutate("edges", "create", {"source": "a", "target": "missing", "type": "FLOWS_TO"})
            with self.assertRaises(ValueError):
                bank.mutate("nodes", "update", {"id": "changed"}, "a")
            with self.assertRaises(KeyError):
                bank.mutate("nodes", "delete", ident="missing")


if __name__ == "__main__":
    unittest.main()
