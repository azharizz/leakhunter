import unittest

from unspool.providers.evidence import aggregate_evidence


class EvidenceAggregationTests(unittest.TestCase):
    def policy(self):
        return {"sinks": [{"kind": "HTTP_RESPONSE", "allow": ["PUBLIC"],
                            "require_authorization": True, "same_tenant": True}]}

    def review(self, *, flow=True, observations=None, events=None):
        return {
            "policy": {"rules": self.policy()},
            "flow_paths": ([{"id": "flow-1", "status": "POSSIBLE_FLOW", "sink": "HTTP_RESPONSE"}]
                           if flow else []),
            "findings": [],
            "runtime_evidence": {"status": "COMPLETED", "cases": [{
                "id": "case-1", "observations": observations or [],
                "violations": [], "call_events": events or []
            }]}
        }

    def test_unproven_controls_block_possible_response_without_name_heuristics(self):
        result = aggregate_evidence(self.review(
            observations=[{"sink": "HTTP_RESPONSE", "symbol": "record.secret"}],
            events=[{"module": "auth", "callable": "is_admin", "role": "unrelated", "returned_bool": True}]))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["controls"]["authentication"]["status"], "UNPROVEN")
        self.assertEqual(result["controls"]["tenant"]["status"], "UNPROVEN")
        self.assertEqual(result["public_projection"]["status"], "SENSITIVE_FIELDS_OBSERVED")
        self.assertFalse(result["safe_to_release"])

    def test_missing_sensitive_marker_is_not_promoted_to_safe(self):
        result = aggregate_evidence(self.review(flow=False, events=[
            {"module": "auth", "callable": "check", "role": "authentication", "returned_bool": True}]))
        self.assertEqual(result["status"], "UNRESOLVED")
        self.assertEqual(result["public_projection"]["status"], "NO_RESPONSE_PATH_IN_SCOPE")
        self.assertFalse(result["safe_to_release"])

    def test_observed_guard_coverage_is_scoped_to_executed_response_cases(self):
        result = aggregate_evidence(self.review(
            observations=[{"sink": "HTTP_RESPONSE", "symbol": "record.secret"}],
            events=[
                {"module": "auth", "callable": "check", "role": "authentication", "returned_bool": True},
                {"module": "tenant", "callable": "check", "role": "tenant", "returned_bool": True},
            ]))
        self.assertEqual(result["controls"]["authentication"]["status"], "PROVEN_FOR_OBSERVED_CASES")
        self.assertEqual(result["controls"]["tenant"]["status"], "PROVEN_FOR_OBSERVED_CASES")
        self.assertEqual(result["controls"]["ownership"]["status"], "UNKNOWN")

    def test_unavailable_context_fails_closed(self):
        result = aggregate_evidence(None)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertFalse(result["safe_to_release"])


if __name__ == "__main__":
    unittest.main()
