import copy
from pathlib import Path
import tempfile
import unittest

from leakhunter.execution.runtime import load_manifest, run_suite
from leakhunter.policy.engine import load_policy
from leakhunter.providers.probes import baseline_manifest


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
    def test_on_demand_edge_probes_pass_on_the_current_service(self):
        demo = Path(__file__).resolve().parents[1] / "demo"
        manifest = load_manifest(demo / "runtime.yaml")
        library = [case for case in manifest["cases"] if case.get("on_demand")]
        self.assertGreaterEqual(len(library), 4)
        result = run_suite(demo / "target", dict(manifest, cases=library), load_policy(demo / "policy.yaml"),
                           backend="local")
        self.assertTrue(result["passed"], result)
