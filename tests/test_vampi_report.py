import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location("vampi_report", Path(__file__).parents[1] / "benchmarks/vampi/report.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class VAmPIReportTests(unittest.TestCase):
    def test_only_exact_positive_acceptance_produces_evidence(self):
        raw = {"http_functionality_passed": True, "security_passed": True,
               "secret_observed_at_http_response": False, "expected_behavior_reproduced": True,
               "evaluation_type": "known_intentionally_vulnerable_external_application",
               "canary_sha256": "1940b6aaf9f43a73dfd3c0de02b3bbff73cbf0efa57af4e2282da7271e4f1aaa"}
        sha, image = "a" * 40, "sha256:" + "b" * 64
        self.assertTrue(report.evidence(raw, sha, image)["gate"]["passed"])
        for key, value in raw.items():
            for bad in (None, 1 if isinstance(value, bool) else "wrong"):
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    report.evidence({**raw, key: bad}, sha, image)
        for source, runtime in (("main", image), (sha, "python:latest")):
            with self.assertRaises(ValueError):
                report.evidence(raw, source, runtime)
