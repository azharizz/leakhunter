import copy
from pathlib import Path
import tempfile
import unittest

from leakhunter.execution.runtime import load_manifest, run_suite
from leakhunter.policy.engine import load_policy


class DemoGateTest(unittest.TestCase):
    def test_safe_profile_passes_and_a_secret_leak_is_blocked(self):
        demo = Path(__file__).resolve().parents[1] / "demo"
        manifest = load_manifest(demo / "runtime.yaml")
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
