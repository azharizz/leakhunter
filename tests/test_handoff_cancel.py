import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from unspool.handoff import GitLab, GitLabError, main
from unspool.handoff_state import HandoffCanceled, JournalAPI, RunJournal, trigger_issue


class CancellationTest(unittest.TestCase):
    def test_keyboard_interrupt_is_recorded_as_canceled(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with patch("sys.argv", ["handoff", "--project", "87860005", "--issue", "1", "--state-dir", directory]), \
                    patch("unspool.handoff.from_issue", side_effect=KeyboardInterrupt), \
                    contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as exit:
                main()
            self.assertEqual(exit.exception.code, 130)
            self.assertEqual(json.loads(output.getvalue())["status"], "CANCELED")
            record = json.loads(next(Path(directory).glob("*.json")).read_text())
            self.assertEqual(record["state"], "CANCELED")

    def test_cli_stop_flag_prevents_all_requests_and_records_cancellation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "STOP").touch()
            output = io.StringIO()
            with patch("sys.argv", ["handoff", "--project", "87860005", "--issue", "1", "--state-dir", directory]), \
                    patch.object(GitLab, "_request") as request, contextlib.redirect_stdout(output), \
                    self.assertRaises(SystemExit) as exit:
                main()
            self.assertEqual(exit.exception.code, 130)
            self.assertEqual(json.loads(output.getvalue()), {"status": "CANCELED", "remote_work_may_continue": True})
            request.assert_not_called()
            record = json.loads(next(root.glob("*.json")).read_text())
            self.assertEqual(record["state"], "CANCELED")

    def test_stop_between_read_and_mutation_blocks_promotion_and_false_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            api = Mock()
            with self.assertRaises(HandoffCanceled):
                with RunJournal(root, 1, "main", "issue:1", "config") as journal:
                    guarded = JournalAPI(api, journal)
                    guarded.request("GET", "projects/1")
                    (root / "STOP").touch()
                    with self.assertRaises(HandoffCanceled):
                        guarded.request("PUT", "projects/1/merge_requests/1/merge")
                    with self.assertRaises(HandoffCanceled):
                        trigger_issue(api, 1, 1, "@agent", journal)
                    journal.save("DEPLOYED_AND_VERIFIED")
            self.assertEqual(api.request.call_count, 1)
            with RunJournal(root, 1, "main", "issue:1", "config") as resumed:
                self.assertEqual(resumed.data["state"], "CANCELED")
                (root / "STOP").unlink()
                resumed.check_stop()
                resumed.save("READY_FOR_REVIEW")

    def test_stop_is_checked_between_transient_read_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            with RunJournal(directory, 1, "main", "issue:1", "config") as journal:
                def fail(*args):
                    (Path(directory) / "STOP").touch()
                    raise GitLabError("GET", 429, True)

                api = GitLab(journal)
                with patch.object(api, "_request", side_effect=fail) as request, \
                        patch("unspool.handoff.time.sleep"), self.assertRaises(HandoffCanceled):
                    api.request("GET", "projects/1")
                self.assertEqual(request.call_count, 1)

    def test_broken_symlink_flag_stops_without_reading_its_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "STOP").symlink_to(root / "missing")
            with RunJournal(root, 1, "main", "issue:1", "config") as journal:
                with self.assertRaises(HandoffCanceled):
                    journal.check_stop()
