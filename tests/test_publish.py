import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from unspool.publish import publish


class PublishTest(unittest.TestCase):
    def evidence(self):
        return {"gate": {"passed": True}, "runtime": {"status": "COMPLETED", "passed": True,
                "cases": [{"id": "demo", "passed": True, "raw_payload": "must not publish"}]},
                "nodes": [{"id": "n", "label": "profile", "kind": "FunctionDef", "source": "private source"}],
                "edges": [], "provider_key": "must not publish"}

    def test_publish_is_relative_readonly_and_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            publish(self.evidence(), target, "a" * 40)
            html = (target / "index.html").read_text()
            self.assertIn('data-mode="published"', html)
            self.assertIn('src="./static/app.js"', html)
            data = (target / "workspace.json").read_text()
            self.assertNotIn("must not publish", data)
            self.assertNotIn("private source", data)
            self.assertEqual(json.loads((target / "health.json").read_text())["commit"], "a" * 40)

    def test_failed_unknown_or_unexecuted_evidence_cannot_deploy(self):
        for change in ({"gate": {"passed": False}}, {"gate": {"passed": "true"}},
                       {"runtime": {"status": "NOT_RUN", "passed": True}}, {"nodes": []}):
            evidence = copy.deepcopy(self.evidence())
            evidence.update(change)
            with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
                publish(evidence, Path(directory), "a" * 40)

    def test_unspool_cli_alias_runs(self):
        result = subprocess.run([sys.executable, "-m", "unspool", "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--repository", result.stdout)
