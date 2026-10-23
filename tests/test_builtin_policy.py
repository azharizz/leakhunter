from pathlib import Path
import tempfile
import unittest

from leakhunter.analyzers.python_ast import analyze_project
from leakhunter.policy.engine import load_policy

CHECKOUT = '''
import logging

log = logging.getLogger("checkout")


def charge(order):
    log.info("charging card %s", order["card_number"])
    return {"order_id": order["order_id"], "email": order["email"]}
'''


def analyze(code, policy, entry="service.profile"):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "service.py").write_text(code)
        return analyze_project(root, policy, entrypoints=[entry])["findings"]


class BuiltinPolicyTest(unittest.TestCase):
    def test_without_a_policy_unlisted_sensitive_fields_are_still_found(self):
        findings = analyze(CHECKOUT, load_policy(None), "service.charge")
        flows = {(item["source"], item["classification"], item["sink"]) for item in findings}
        self.assertIn(("*.card_number", "SECRET", "APPLICATION_LOG"), flows)
        self.assertIn(("*.email", "PII", "HTTP_RESPONSE"), flows)

    def test_extends_builtin_adds_the_catalogue_under_operator_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.yaml"
            path.write_text("version: 1\nextends: builtin\nclassifications: {PUBLIC: 0, PII: 1, SECRET: 2}\n"
                            "sources:\n  - {selector: '*.email', class: PUBLIC}\n"
                            "sinks:\n  - {kind: HTTP_RESPONSE, allow: [PUBLIC]}\n")
            policy = load_policy(path)
        self.assertEqual(policy.classify("order.email"), "PUBLIC")      # the operator's own entry wins
        self.assertEqual(policy.classify("order.cvv"), "SECRET")        # the catalogue fills the gaps
        self.assertIn("APPLICATION_LOG", policy.sinks)

    def test_policies_without_extends_are_unchanged(self):
        demo = load_policy(Path(__file__).resolve().parents[1] / "demo" / "policy.yaml")
        self.assertEqual(demo.classify("customer.card_number"), "PUBLIC")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.yaml"
            path.write_text("version: 1\nextends: other\n")
            with self.assertRaises(ValueError):
                load_policy(path)


class ComputedGetKeyTest(unittest.TestCase):
    def test_get_with_names_from_a_constant_tuple_selects_fields_not_the_record(self):
        code = ('FIELDS = ("user_id", "avatar_url")\n\n\ndef profile(user):\n    out = {}\n'
                '    for name in FIELDS:\n        out[name] = user.get(name)\n    return out\n')
        self.assertEqual(analyze(code, load_policy(None)), [])

    def test_get_with_keys_taken_from_the_record_still_exposes_it(self):
        code = 'def profile(user):\n    out = {}\n    for name in user:\n        out[name] = user.get(name)\n    return out\n'
        findings = analyze(code, load_policy(None))
        self.assertTrue(any(item.get("exposure") == "WHOLE_RECORD" and item["source"] == "*.card_number"
                            for item in findings))


if __name__ == "__main__":
    unittest.main()
