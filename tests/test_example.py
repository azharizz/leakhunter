import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from example import generator
from unspool.policy.engine import load_policy
from unspool.execution.runtime import load_manifest, run_suite

EXAMPLE = Path(__file__).resolve().parents[1] / "example"


class ExampleTest(unittest.TestCase):
    def test_complex_fixture_labels_match_actual_sink_observations(self):
        manifest = load_manifest(EXAMPLE / "runtime.yaml")
        result = run_suite(EXAMPLE / "fixtures", manifest,
                           load_policy(EXAMPLE / "unspool-policy.yaml"), backend="local")
        self.assertEqual(result["status"], "COMPLETED", result)
        self.assertTrue(result["functional_passed"], result)
        expected = {case["id"]: case["expected_violation"] for case in manifest["cases"]}
        for case in result["cases"]:
            self.assertEqual(bool(case["violations"]), expected[case["id"]], case)
        self.assertFalse(result["passed"], "Deliberately vulnerable baseline must fail the security gate")
        rendered = json.dumps(result)
        for case in manifest["cases"]:
            for source in case["sensitive"]:
                self.assertNotIn(source["marker"], rendered)

    def test_materialized_labels_follow_executed_code_not_metadata_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second = root / "first", root / "second"
            catalog = generator.materialize(first, count=8, seed=17)
            self.assertEqual(catalog, generator.materialize(second, count=8, seed=17))
            for entry in catalog["cases"]:
                for relative in (entry["manifest"], entry["repository"] + "/service.py"):
                    self.assertEqual((first / relative).read_bytes(), (second / relative).read_bytes())
            result = generator.evaluate_materialized(first, backend="local")
            self.assertEqual(result["status"], "COMPLETED", result)
            self.assertEqual(result["runtime"], {"tp": 4, "fp": 0, "fn": 0, "tn": 4,
                                                  "precision": 1.0, "recall": 1.0, "accuracy": 1.0})
            self.assertTrue(all(case["label_matches"] for case in result["cases"]), result)
            for case in result["cases"]:
                self.assertEqual(case["runtime_observed"], case["expected_violation"])
            # A mislabeled safe program must be exposed by execution, not its ID/count.
            safe = next(entry for entry in catalog["cases"]
                        if entry["family"] == "response" and not entry["expected_violation"])
            source_path = first / safe["repository"] / "service.py"
            source_path.write_text(source_path.read_text().replace(
                "return {'ok': True}", "return {'ok': True, 'value': customer.password_hash}"))
            observed = run_suite(first / safe["repository"], load_manifest(first / safe["manifest"]),
                                 load_policy(first / "policy.yaml"), backend="local")
            self.assertTrue(observed["functional_passed"], observed)
            self.assertTrue(observed["cases"][0]["violations"], observed)

    def test_launcher_defaults_isolate_and_explicit_local_overrides(self):
        from example import run

        for arguments, expected_backend in ((["--offline"], "docker"),
                                            (["--offline", "--trusted-local"], "local")):
            with patch("sys.argv", ["example.run", *arguments]), patch.object(run, "main") as main:
                run.run()
            passed = main.call_args.args[0]
            self.assertEqual(passed[passed.index("--runtime-backend") + 1], expected_backend)
            self.assertEqual(passed[passed.index("--runtime-manifest") + 1], str(EXAMPLE / "runtime.yaml"))
        with patch("sys.argv", ["example.run", "--runtime-backend", "local"]):
            with self.assertRaises(SystemExit):
                run.run()


if __name__ == "__main__":
    unittest.main()
