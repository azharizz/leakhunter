import copy
from pathlib import Path
import tempfile
import unittest

from unspool.execution.runtime import load_manifest, run_suite
from unspool.policy.engine import load_policy
from unspool.providers.probes import baseline_manifest


class DemoGateTest(unittest.TestCase):
    def test_safe_profile_passes_and_a_secret_leak_is_blocked(self):
        demo = Path(__file__).resolve().parents[1] / "demo"
        manifest = baseline_manifest(load_manifest(demo / "runtime.yaml"))
        policy = load_policy(demo / "policy.yaml")
        safe = run_suite(demo / "target", manifest, policy, backend="local")
        self.assertTrue(safe["passed"], safe)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "service.py").write_text("def profile(record):\n    return record\n")
            unsafe = run_suite(root, copy.deepcopy(manifest), policy, backend="local")
        self.assertTrue(unsafe["functional_passed"])
        self.assertFalse(unsafe["passed"])
        self.assertTrue(unsafe["cases"][0]["violations"])


class ProbeLibraryTest(unittest.TestCase):
    """Check the on-demand library itself on fixed fixtures; candidates are judged by the gate."""

    def run_library(self, source):
        demo = Path(__file__).resolve().parents[1] / "demo"
        manifest = load_manifest(demo / "runtime.yaml")
        library = [case for case in manifest["cases"] if case.get("on_demand")]
        self.assertGreaterEqual(len(library), 4)
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "service.py").write_text(source)
            return run_suite(Path(directory), dict(manifest, cases=library), load_policy(demo / "policy.yaml"),
                             backend="local")

    def test_edge_probes_pass_on_a_safe_profile_and_catch_a_whole_record(self):
        safe = self.run_library(
            'def profile(record):\n'
            '    name = " ".join(record["display_name"].replace("\\u200b", " ").split())\n'
            '    return {"customer_id": record["customer_id"], "display_name": name or record["customer_id"]}\n')
        self.assertTrue(safe["passed"], safe)
        leaking = self.run_library("def profile(record):\n    return dict(record)\n")
        self.assertFalse(leaking["passed"])
        self.assertTrue(all(case["violations"] for case in leaking["cases"]))
