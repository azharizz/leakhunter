import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.gate_experiment import run as experiment


class GateExperimentHarnessTest(unittest.TestCase):
    def test_task_set_matches_the_frozen_protocol(self):
        plan = experiment.tasks()
        self.assertEqual(len(plan["tasks"]), 12)
        self.assertEqual(sum(task["held_out"] for task in plan["tasks"]), 4)
        self.assertEqual(sum(task["kind"] == "safe" for task in plan["tasks"]), 3)
        for task in plan["tasks"]:
            self.assertTrue((experiment.HERE / "tasks" / task["id"] / "start").is_dir())
            self.assertTrue((experiment.HERE / "tasks" / task["id"] / "reference").is_dir())
            self.assertEqual(task["has_shallow_fix"], task["kind"] == "leak")

    def test_agent_workspace_never_contains_probes_policy_or_gate_manifests(self):
        task = experiment.tasks()["tasks"][0]
        with tempfile.TemporaryDirectory() as directory:
            app = experiment.workspace(task, Path(directory))
            names = {path.name for path in app.rglob("*")}
            self.assertFalse({"probes", "gate"} & names)
            self.assertFalse(any(name.endswith((".yaml", ".yml")) for name in names))
            self.assertNotIn("SYNTHETIC_GX", "".join(path.read_text() for path in app.rglob("*.py")))

    def test_runs_refuse_unfrozen_or_changed_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            frozen = Path(directory) / "FROZEN.json"
            with patch.object(experiment, "FROZEN", frozen):
                with self.assertRaises(SystemExit):
                    experiment.check_frozen()
                frozen.write_text(json.dumps({**experiment.hashes(), "probe_set_sha256": "0" * 64}))
                with self.assertRaises(SystemExit):
                    experiment.check_frozen()
                frozen.write_text(json.dumps(experiment.hashes()))
                self.assertEqual(experiment.check_frozen()["case_set_sha256"], experiment.hashes()["case_set_sha256"])


if __name__ == "__main__":
    unittest.main()
