import unittest
from unittest.mock import patch

from leakhunter.app import attach_evidence, main, release_gate


class ReleaseGateTest(unittest.TestCase):
    def test_evaluation_accuracy_cannot_authorize_a_release(self):
        arguments = ["--repository", ".", "--policy", "policy.yaml", "--data-dir", "/tmp/evidence"]
        # Perfect detection can include a real leak; accuracy cannot approve release.
        metrics = {"status": "COMPLETED", "runtime": {"tp": 1, "tn": 0, "fp": 0, "fn": 0}}
        for mode in (["--once", "evaluate"], []):
            with self.subTest(mode=mode):
                with patch("leakhunter.app.configure") as configure, \
                        patch("leakhunter.app.evaluate", return_value=metrics), patch("sys.stderr"), \
                        patch("builtins.print"), self.assertRaises(SystemExit) as error:
                    main(arguments + mode + ["--gate"])
                self.assertEqual(error.exception.code, 2)
                configure.assert_not_called()
        with patch("leakhunter.app.configure"), patch("leakhunter.app.evaluate", return_value=metrics) as evaluate, \
                patch("builtins.print"):
            main(arguments + ["--once", "evaluate"])
        evaluate.assert_called_once_with()

    def test_advice_and_unexecuted_evidence_cannot_open_gate(self):
        approved = {"status": "approved"}
        self.assertFalse(release_gate([], {"status": "NOT_RUN", "passed": False}, approved)["passed"])
        self.assertFalse(release_gate([], {"status": "ERROR", "passed": True}, approved)["passed"])
        self.assertFalse(release_gate([{"status": "POSSIBLE"}], {"status": "COMPLETED", "passed": True}, approved)["passed"])
        self.assertFalse(release_gate([], {"status": "COMPLETED", "passed": True}, {"status": "draft"})["passed"])
        self.assertTrue(release_gate([], {"status": "COMPLETED", "passed": True}, approved)["passed"])
        for coverage in ({"analyzed_files": 0}, {"analyzed_files": 1, "parse_errors": [{"error": "SyntaxError"}]},
                         {"analyzed_files": 1, "unsupported_constructs": [{"kind": "Lambda"}]}):
            self.assertFalse(release_gate([], {"status": "COMPLETED", "passed": True}, approved, coverage)["passed"])

    def test_confirmation_requires_exact_function_and_source_scope(self):
        for function, symbol, expected in (("app.expose", "record.email", "CONFIRMED_IN_TEST"),
                                            ("app.other", "record.email", "POSSIBLE"),
                                            ("app.expose", "record.password", "POSSIBLE")):
            finding = {"function": function, "file": "app.py", "path": ["ast-node-1"],
                       "source": "*.email", "classification": "PERSONAL", "sink": "APPLICATION_LOG", "status": "POSSIBLE"}
            manifest = {"cases": [{"id": "case", "module": "app", "finding":
                                  {"file": "app.py", "function": "expose", "sink": "APPLICATION_LOG"}}]}
            runtime = {"status": "COMPLETED", "cases": [{"id": "case", "violations": [
                       {"sink": "APPLICATION_LOG", "symbol": symbol, "classification": "PERSONAL"}]}]}
            attach_evidence([finding], runtime, manifest, "revision")
            self.assertEqual(finding["status"], expected)


if __name__ == "__main__":
    unittest.main()
