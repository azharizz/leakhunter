import json
from pathlib import Path
import re
import tempfile
import unittest

from benchmarks.cves import run as benchmark


class CVEBenchmarkTest(unittest.TestCase):
    def test_cases_are_real_advisories_with_exact_commits_and_policies(self):
        data = json.loads((benchmark.HERE / "cases.json").read_text())
        self.assertEqual(len(data["cases"]), 8)
        for case in data["cases"]:
            self.assertRegex(case["id"], r"^GHSA(-[23456789cfghjmpqrvwx]{4}){3}$")
            self.assertTrue(case["advisory"].startswith("https://github.com/advisories/"))
            for key in ("fix_commit", "vulnerable_commit"):
                self.assertRegex(case[key], r"^[0-9a-f]{40}$")
            self.assertNotEqual(case["fix_commit"], case["vulnerable_commit"])
            self.assertTrue(case["files"] and case["functions"])
            self.assertTrue(case["policy"]["sources"])

    def test_outcomes(self):
        self.assertEqual(benchmark.outcome(True, False), "HIT")
        self.assertEqual(benchmark.outcome(True, True), "FALSE_ALARM_ON_FIX")
        self.assertEqual(benchmark.outcome(False, False), "MISS")
        self.assertEqual(benchmark.outcome(False, True), "INVERTED")
        self.assertEqual(benchmark.outcome(None, False), "UNKNOWN")
        self.assertIsNone(benchmark.luna_flag({"luna_verdict": "UNCERTAIN"}))

    def test_evaluate_flags_only_the_named_functions(self):
        case = {"files": ["pkg/client.py"], "functions": ["Client.request"],
                "policy": {"version": 1, "classifications": {"PUBLIC": 0, "SECRET": 2},
                           "sources": [{"selector": "*.Authorization", "class": "SECRET"}],
                           "sinks": [{"kind": "APPLICATION_LOG", "allow": ["PUBLIC"]}]}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pkg").mkdir()
            (root / "pkg" / "client.py").write_text(
                "import logging\nlog = logging.getLogger(__name__)\n"
                "class Client:\n"
                "    def request(self, headers):\n"
                "        headers['User-Agent'] = 'client'\n"
                "        log.debug('request %s', headers)\n"
                "    def other(self, headers):\n"
                "        headers['User-Agent'] = 'client'\n"
                "        log.debug('other %s', headers)\n")
            stage = benchmark.evaluate(case, root)
        self.assertTrue(stage["static_flagged"])
        self.assertEqual({item["function"] for item in stage["findings"]}, {"pkg.client.Client.request"})


if __name__ == "__main__":
    unittest.main()
