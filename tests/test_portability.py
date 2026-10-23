import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from unspool.analyzers.python_ast import analyze_repository
from unspool.policy.engine import Policy


class PortabilityTest(unittest.TestCase):
    def test_relocation_preserves_results_without_example_package(self):
        policy = Policy({"version": 1, "classifications": {"PUBLIC": 0, "SECRET": 1},
                         "sources": [{"selector": "*.private_value", "class": "SECRET"}],
                         "sinks": [{"kind": "HTTP_RESPONSE", "allow": ["PUBLIC"]}]})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second = root / "checkout-a", root / "checkout-b"
            for repo in (first, second):
                (repo / "nested").mkdir(parents=True)
                for file in (repo / "a.py", repo / "nested" / "a.py"):
                    file.write_text("def expose(record):\n    return record.private_value\n")
            result = analyze_repository(first, policy)
            self.assertEqual(result, analyze_repository(second, policy))
            nodes, edges, findings = result
            self.assertEqual({f["file"] for f in findings}, {"a.py", "nested/a.py"})
            self.assertEqual(len({f["id"] for f in findings}), 2)
            self.assertNotIn(str(root), json.dumps(result))
            self.assertTrue(all(f["status"] == "POSSIBLE" for f in findings))
            self.assertEqual(len({n["id"] for n in nodes}), len(nodes))
            ids = {n["id"] for n in nodes}
            self.assertTrue(all(e["source"] in ids and e["target"] in ids for e in edges))
            # Only the deployable package is copied: no sibling example, policy or .env.
            package = Path(__file__).resolve().parents[1] / "unspool"
            shutil.copytree(package, root / "unspool", ignore=shutil.ignore_patterns("__pycache__"))
            command = subprocess.run([sys.executable, "-B", "-m", "unspool.app", "--help"],
                                     cwd=root, capture_output=True, text=True)
            self.assertEqual(command.returncode, 0, command.stderr)
            self.assertFalse((root / "unspool" / "data").exists())

    def test_leakhunter_imports_alias_the_unspool_modules(self):
        import leakhunter.app
        import unspool.app
        from leakhunter.policy.engine import load_policy
        from unspool.policy import engine
        self.assertIs(leakhunter.app, unspool.app)
        self.assertIs(load_policy, engine.load_policy)
        self.assertEqual(unspool.app.__spec__.name, "unspool.app")


if __name__ == "__main__":
    unittest.main()
