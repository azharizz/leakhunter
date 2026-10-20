import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from unspool.handoff import GitLab, GitLabError
from unspool.handoff_state import RunJournal, trigger_issue


class StateTest(unittest.TestCase):
    def test_only_transient_reads_are_retried_and_mutations_are_never_replayed(self):
        api = GitLab()
        with patch.object(api, "_request", side_effect=[GitLabError("GET", 429, True), {"ok": True}]) as request, patch("unspool.handoff.time.sleep"):
            self.assertEqual(api.request("GET", "projects/1"), {"ok": True})
            self.assertEqual(request.call_count, 2)
        for method, error in (("POST", GitLabError("POST", 503, True)), ("PUT", GitLabError("PUT", 503, True)), ("GET", GitLabError("GET", 403))):
            with patch.object(api, "_request", side_effect=error) as request, self.assertRaises(GitLabError):
                api.request(method, "projects/1")
            self.assertEqual(request.call_count, 1)

    def test_restart_keeps_private_state_and_rejects_scope_change(self):
        with tempfile.TemporaryDirectory() as directory:
            with RunJournal(directory, 1, "main", "issue:2", "config-a") as first:
                first.save("DEPLOYING", merged_sha="a" * 40)
                self.assertEqual(first.path.stat().st_mode & 0o077, 0)
            with RunJournal(directory, 1, "main", "issue:2", "config-a") as resumed:
                self.assertEqual(resumed.data["merged_sha"], "a" * 40)
                self.assertEqual(resumed.data["state"], "DEPLOYING")
            with self.assertRaises(ValueError):
                with RunJournal(directory, 1, "main", "issue:2", "config-b"):
                    pass

    def test_two_controllers_cannot_promote_same_target_concurrently(self):
        with tempfile.TemporaryDirectory() as directory:
            with RunJournal(directory, 1, "main", "issue:1", "config"):
                with self.assertRaises(BlockingIOError):
                    with RunJournal(directory, 1, "main", "issue:2", "config"):
                        pass
                with RunJournal(directory, 2, "main", "issue:1", "config"):
                    pass

    def test_lost_post_response_is_reconciled_without_duplicate_trigger(self):
        notes, calls = [], []

        class API:
            def request(self, method, path, body=None):
                calls.append(method)
                if method == "POST":
                    notes.append({"id": 10, "body": body["body"]})
                    raise TimeoutError("Response lost after GitLab accepted the note")
                return notes

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(TimeoutError):
                with RunJournal(directory, 1, "main", "issue:2", "config") as journal:
                    trigger_issue(API(), 1, 2, "@agent task", journal)
            with RunJournal(directory, 1, "main", "issue:2", "config") as resumed:
                trigger_issue(API(), 1, 2, "@agent task", resumed)
                self.assertEqual(resumed.data["trigger_note_id"], 10)
                trigger_issue(API(), 1, 2, "@agent task", resumed)
        self.assertEqual(calls, ["POST", "GET"])

    def test_uncertain_delivery_stops_without_sending_again(self):
        calls = []

        class API:
            def request(self, method, path, body=None):
                calls.append(method)
                return []

        with tempfile.TemporaryDirectory() as directory:
            with RunJournal(directory, 1, "main", "issue:2", "config") as journal:
                journal.save("TRIGGER_INTENT", dispatch_started=True)
            with self.assertRaisesRegex(RuntimeError, "uncertain"):
                with RunJournal(directory, 1, "main", "issue:2", "config") as resumed:
                    trigger_issue(API(), 1, 2, "@agent task", resumed)
        self.assertEqual(calls, ["GET"])

    def test_shared_directory_or_symlink_state_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = root / "shared"
            shared.mkdir(mode=0o755)
            with self.assertRaises(ValueError):
                with RunJournal(shared, 1, "main", "issue:1", "config"):
                    pass
            with RunJournal(root, 1, "main", "issue:1", "config") as journal:
                path = journal.path
            path.unlink()
            victim = root / "other.json"
            victim.write_text("{}")
            path.symlink_to(victim)
            with self.assertRaises(OSError):
                with RunJournal(root, 1, "main", "issue:1", "config"):
                    pass
            self.assertEqual(json.loads(victim.read_text()), {})
