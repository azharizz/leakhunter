import copy
import json
import unittest
from unittest.mock import Mock

from leakhunter.providers.disclosure import MAX_CONTEXT_BYTES
from leakhunter.providers.reviews import review_contexts


QUESTION_IDS = {
    "unauthorized_disclosure_plausible",
    "additional_context_required",
    "targeted_runtime_test_required",
}


def context(review_id="boundary-1"):
    return {
        "review_id": review_id,
        "objective": "Review a potential outbound boundary",
        "boundary": {"node_id": "node-1", "kind": "unresolved_call", "file": "module.py",
                     "line": 1, "function": "module"},
        "scope": {"complete": False, "omissions": ["External implementation unavailable."]},
        "code": [{"file": "module.py", "start_line": 1, "end_line": 1,
                  "text": "pass\n", "sha256": "synthetic-revision"}],
        "graph": {"nodes": [], "edges": []},
        "findings": [],
        "policy": {"origin": "configured_policy", "rules": {}},
        "runtime_evidence": {"status": "not_run", "cases": [], "scope": "No runtime coverage."},
        "unknowns": ["Recipient contract unavailable."],
        "evidence_refs": ["module.py:1"],
    }


def bundle(*reviews, complete=False):
    omitted = 0 if complete else 2
    return {
        "version": 1, "revision_sha": "revision-1", "policy_digest": "policy-1",
        "scope": {"review_unit_count": len(reviews) + omitted, "omitted_review_units": omitted,
                  "selection_complete": complete,
                  "limitations": [] if complete else ["Two review units omitted."]},
        "reviews": list(reviews),
    }


def answer(probability):
    return {"model": "test/decision", "answers": {
        name: {"type": "noul", "noul": probability} for name in QUESTION_IDS},
        "usage": {"total_tokens": 17}}


class ReviewContextsTests(unittest.TestCase):
    def test_empty_and_unavailable_source_never_call_provider(self):
        callback = Mock(side_effect=AssertionError("Must not disclose unavailable source"))
        result, latency, status = review_contexts(bundle(), callback, "test/decision")
        self.assertEqual((result["status"], latency, status), ("no_review_units", 0, "skipped"))
        self.assertFalse(result["safe_to_release"])
        self.assertEqual(result["scope"]["omitted_review_units"], 2)
        for code in (None, [], [{}], [{"text": " \n"}]):
            with self.subTest(code=code):
                unit = context()
                unit["code"] = code
                result, latency, status = review_contexts(bundle(unit), callback, "test/decision")
                self.assertEqual((result["status"], latency, status), ("error", 0, "error"))
                self.assertEqual(result["reviews"][0]["provider_status"], "context_unavailable")
                review = result["reviews"][0]
                self.assertEqual(review["context"]["boundary"], unit["boundary"])
                self.assertIn("External implementation unavailable.", review["missing_evidence"])
                self.assertFalse(result["safe_to_release"])
        callback.assert_not_called()

    def test_secret_and_oversized_contexts_are_not_disclosed_or_retained(self):
        secret = "sk-or-v1-" + "x" * 24
        rejected = []
        unit = context("secret-source")
        unit["code"][0]["text"] = secret
        rejected.append(unit)
        unit = context("secret-policy")
        unit["policy"]["rules"]["description"] = 'password = "credential-value"'
        rejected.append(unit)
        unit = context("oversize")
        unit["unknowns"] = ["é" * MAX_CONTEXT_BYTES]
        rejected.append(unit)
        unit = context("escaped-envelope")
        unit["code"][0]["text"] = '"' * (MAX_CONTEXT_BYTES // 3)
        rejected.append(unit)
        callback = Mock(side_effect=AssertionError("Must not disclose rejected context"))
        result, latency, status = review_contexts(bundle(*rejected), callback, "test/decision")
        callback.assert_not_called()
        self.assertEqual((result["status"], latency, status), ("error", 0, "error"))
        for review in result["reviews"]:
            self.assertEqual(review["provider_status"], "context_blocked")
            self.assertEqual(review["decision"], "Review context disclosure blocked.")
            self.assertIsNone(review["context"])
            self.assertFalse(review["safe_to_release"])
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn("credential-value", json.dumps(result))
        self.assertLess(len(json.dumps(result).encode()), MAX_CONTEXT_BYTES)

    def test_probabilities_remain_unresolved_and_preserve_audit_evidence(self):
        for probability in (0, 0.001, 0.999, 1):
            with self.subTest(probability=probability):
                unit = context()
                contexts = bundle(unit)
                original = copy.deepcopy(contexts)
                raw_answer = answer(probability)
                callback = Mock(return_value=(raw_answer, 17, "ok"))
                result, latency, status = review_contexts(contexts, callback, "test/decision")
                self.assertEqual((result["status"], latency, status), ("partial", 17, "ok"))
                review = result["reviews"][0]
                self.assertEqual(review["decision"], raw_answer)
                self.assertEqual(review["context"], unit)
                self.assertEqual(review["evidence_refs"], unit["evidence_refs"])
                self.assertIn("Recipient contract unavailable.", review["missing_evidence"])
                self.assertIn("External implementation unavailable.", review["missing_evidence"])
                self.assertTrue(review["next_checks"])
                self.assertEqual(review["assessment"], "UNRESOLVED")
                self.assertEqual(review["verification"], "UNRESOLVED")
                self.assertFalse(review["safe_to_release"])
                self.assertEqual(review["deterministic_evidence"]["safe_to_release"], False)
                self.assertFalse(result["safe_to_release"])
                self.assertEqual(result["scope"], original["scope"])
                self.assertEqual(contexts, original)
        result, _, status = review_contexts(bundle(context(), complete=True),
                                           Mock(return_value=(answer(0), 1, "ok")), "test/decision")
        self.assertEqual((result["status"], status), ("completed", "ok"))
        self.assertFalse(result["safe_to_release"])

    def test_mixed_provider_outcomes_are_retained_without_fallback(self):
        raw_answer = answer(0.5)
        callback = Mock(side_effect=[(raw_answer, 5, "ok"),
                                     ("Provider HTTP 429 (rate limited)", 7, "error"),
                                     ("Model provider not configured", 0, "skipped")])
        result, latency, status = review_contexts(
            bundle(context("a"), context("b"), context("c")), callback, "test/decision")
        self.assertEqual(callback.call_count, 3)
        self.assertEqual((result["status"], latency, status), ("partial", 12, "error"))
        self.assertEqual([review["provider_status"] for review in result["reviews"]],
                         ["ok", "error", "skipped"])
        self.assertEqual(result["reviews"][0]["decision"], raw_answer)
        self.assertEqual(result["reviews"][1]["decision"], "Provider HTTP 429 (rate limited)")
        self.assertEqual(result["reviews"][2]["decision"], "Model provider not configured")
        self.assertTrue(all(review["missing_evidence"] for review in result["reviews"]))
        self.assertEqual(result["scope"]["limitations"], ["Two review units omitted."])
        self.assertTrue(all(not review["safe_to_release"] for review in result["reviews"]))

    def test_uniform_provider_failures_and_skips_are_honest(self):
        for provider_status, overall_status in (("error", "error"), ("skipped", "skipped")):
            with self.subTest(provider_status=provider_status):
                callback = Mock(return_value=("Provider unavailable", 2, provider_status))
                result, latency, status = review_contexts(bundle(context()), callback, "test/decision")
                self.assertEqual((result["status"], latency, status), (overall_status, 2, provider_status))
                self.assertFalse(result["safe_to_release"])

    def test_callback_exception_is_generic_and_does_not_abort_other_reviews(self):
        callback = Mock(side_effect=[RuntimeError("private provider exception details"),
                                     (answer(0.9), 4, "ok")])
        result, latency, status = review_contexts(bundle(context("a"), context("b")), callback,
                                                 "test/decision")
        self.assertEqual((result["status"], latency, status), ("partial", 4, "error"))
        self.assertEqual(callback.call_count, 2)
        self.assertEqual(result["reviews"][0]["provider_status"], "error")
        self.assertNotIn("private provider exception details", json.dumps(result))

    def test_secret_scope_blocks_all_requests_without_echoing_scope(self):
        contexts = bundle(context())
        contexts["scope"]["limitations"] = ['api_key = "credential-value"']
        callback = Mock(side_effect=AssertionError("Must not disclose rejected scope"))
        result, latency, status = review_contexts(contexts, callback, "test/decision")
        callback.assert_not_called()
        self.assertEqual((result["status"], latency, status), ("error", 0, "error"))
        self.assertFalse(result["scope"]["selection_complete"])
        self.assertNotIn("credential-value", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
