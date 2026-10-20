import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location("external_evaluation", Path(__file__).parents[1] / "benchmarks/external/evaluate.py")
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


class ExternalEvaluationTest(unittest.TestCase):
    def test_missing_or_wrong_class_callable_cannot_be_counted_as_a_negative(self):
        case = {"file": "core/views.py", "entrypoint": "core.views.User.resolve_name", "function": "resolve_name"}
        source = b"class User:\n    def resolve_name(self):\n        return self.username\n"
        evaluation.verify_case_target(case, source)
        for changed in ({"entrypoint": "core.views.Other.resolve_name"}, {"function": "typo"}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                evaluation.verify_case_target(dict(case, **changed), source)

    def test_misses_unknowns_and_execution_errors_are_never_counted_safe(self):
        self.assertEqual(evaluation.classification(True, True), "TP")
        self.assertEqual(evaluation.classification(True, False), "FN")
        self.assertEqual(evaluation.classification(False, True), "FP")
        self.assertEqual(evaluation.classification(False, False), "TN")
        for observed in (True, False):
            self.assertEqual(evaluation.classification(None, observed), "UNKNOWN_LABEL")
            self.assertEqual(evaluation.classification(False, observed, True), "EXECUTION_ERROR")
