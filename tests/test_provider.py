import io
import json
import unittest
from unittest.mock import patch

from unspool import app


class DecisionResponseTests(unittest.TestCase):
    def test_probabilities_are_structured_and_malformed_answers_are_errors(self):
        questions = {"review": {"type": "noul", "instructions": "Requires review?"}}
        invalid_answers = [
            {},
            {"other": {"type": "noul", "noul": 0.5}},
            {"review": "yes"},
            {"review": {"type": "choice", "choice": "yes"}},
        ]
        invalid_answers.extend({"review": {"type": "noul", "noul": value}}
                               for value in (None, True, "0.9", -0.01, 1.01, float("nan"), float("inf")))
        with patch.multiple(app, API_URL="https://provider.invalid/api/v1/chat/completions",
                            API_KEY="unit-test-only", create=True):
            for probability in (0, 0.375, 1):
                payload = {"model": "test/decision", "answers": {
                    "review": {"type": "noul", "noul": probability}}}
                with self.subTest(probability=probability), patch.object(
                        app, "urlopen", return_value=io.BytesIO(json.dumps(payload).encode())):
                    decision, _, status = app.call_model("test/decision", "synthetic", questions=questions)
                    self.assertEqual(status, "ok")
                    self.assertEqual(decision["answers"]["review"]["noul"], probability)
            for answers in invalid_answers:
                payload = {"model": "test/decision", "answers": answers}
                with self.subTest(answers=answers), patch.object(
                        app, "urlopen", return_value=io.BytesIO(json.dumps(payload).encode())):
                    error, _, status = app.call_model("test/decision", "synthetic", questions=questions)
                    self.assertEqual(status, "error")
                    self.assertIsInstance(error, str)
                    self.assertNotIn("unit-test-only", error)


if __name__ == "__main__":
    unittest.main()
