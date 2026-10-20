import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location("security_audit", Path(__file__).parents[1] / "ci/security_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class SecurityAuditTest(unittest.TestCase):
    def test_unknown_errors_and_high_findings_cannot_pass(self):
        for report in ({}, {"errors": ["parse failed"], "results": []},
                       {"errors": [], "results": [{"issue_severity": "HIGH"}]},
                       {"errors": [], "results": [{"issue_severity": "unknown"}]}):
            with self.subTest(report=report), self.assertRaises(ValueError):
                audit.review_static(report)
        self.assertEqual(audit.review_static({"errors": [], "results": [
            {"issue_severity": "MEDIUM"}, {"issue_severity": "LOW"}]}), {"MEDIUM": 1, "LOW": 1})
