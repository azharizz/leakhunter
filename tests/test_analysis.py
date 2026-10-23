import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from unspool.analyzers.python_ast import analyze_project, analyze_repository
from unspool.policy.engine import Policy


def policy(**extra):
    raw = {"version": 1, "classifications": {"PUBLIC": 0, "INTERNAL": 1, "PERSONAL": 2, "SECRET": 3},
           "sources": [{"selector": "*.password_hash", "class": "SECRET"}, {"selector": "*.email", "class": "PERSONAL"}],
           "sinks": [{"kind": "HTTP_RESPONSE", "allow": ["PUBLIC", "PERSONAL"]},
                     {"kind": "APPLICATION_LOG", "allow": ["PUBLIC"]}]}
    raw.update(extra)
    return Policy(raw)


class AnalysisTest(unittest.TestCase):
    def test_real_flow_overwrite_fields_and_nonflow(self):
        code = '''
import logging

def exposed(user):
    first = user.password_hash
    payload = {"password_hash": first, "public": "fine"}
    logging.info(payload)
    return payload

def safe(user):
    ignored = user.password_hash
    overwritten = user.password_hash
    overwritten = "redacted"
    payload = {"hidden": user.password_hash, "public": "fine"}
    payload["hidden"] = "redacted"
    logging.info("password_hash", overwritten)
    return {"password_hash": overwritten, "public": payload["public"], "missing": payload.get("password_hash")}

def literal_keys():
    return {"password_hash": "redacted"}

def branch(user, flag):
    result = "fine"
    if flag:
        result = user.password_hash
    return result

def loop(user, items):
    result = "fine"
    for item in items:
        result = user["password_hash"]
    return result
'''
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "app.py").write_text(code)
            result = analyze_project(root, policy())
            functions = {item["function"] for item in result["findings"]}
            self.assertEqual(functions, {"app.exposed", "app.branch", "app.loop"})
            nodes = {item["id"] for item in result["nodes"]}
            self.assertTrue(all(edge["source"] in nodes and edge["target"] in nodes for edge in result["edges"]))
            self.assertTrue(all(set(finding["path"]) <= nodes for finding in result["findings"]))
            self.assertTrue({"AST", "CFG", "DATA_FLOW"} <= {edge["type"] for edge in result["edges"]})

    def test_import_arguments_returns_and_no_helper_response(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "helpers.py").write_text('def identity(value):\n    return value\n\ndef discard(value):\n    return "safe"\n')
            (root / "api.py").write_text('from helpers import identity, discard\n\ndef leak(user):\n    return identity(user.password_hash)\n\ndef safe(user):\n    return discard(user.password_hash)\n')
            result = analyze_project(root, policy())
            self.assertEqual({item["function"] for item in result["findings"]}, {"api.leak"})
            self.assertIn("CALLS", {item["type"] for item in result["edges"]})
            self.assertEqual(result["index"]["files"]["api.py"]["dependencies"], ["helpers.py"])
            self.assertEqual(analyze_repository(root, policy()), (result["nodes"], result["edges"], result["findings"]))

    def test_cache_serialization_dependency_deletion_and_policy_invalidation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "helpers.py").write_text('def reveal(user):\n    return user.password_hash\n')
            (root / "api.py").write_text('from helpers import reveal\ndef endpoint(user):\n    return reveal(user)\n')
            (root / "unrelated.py").write_text('def okay():\n    return "safe"\n')
            first = analyze_project(root, policy())
            cache = json.loads(json.dumps(first["index"]))
            with patch("unspool.analyzers.python_ast.ast.parse", side_effect=AssertionError("cache reparsed")):
                unchanged = analyze_project(root, policy(), cache)
            for key in ("nodes", "edges", "findings", "coverage"):
                self.assertEqual(first[key], unchanged[key], key)
            (root / "helpers.py").write_text('def reveal(user):\n    return "safe"\n')
            incremental = analyze_project(root, policy(), cache)
            fresh = analyze_project(root, policy())
            for key in ("nodes", "edges", "findings", "coverage"):
                self.assertEqual(incremental[key], fresh[key], key)
            self.assertEqual(incremental["incremental"]["reused"], ["unrelated.py"])
            self.assertIn("api.py", incremental["incremental"]["invalidated"])
            (root / "helpers.py").unlink()
            deleted = analyze_project(root, policy(), incremental["index"])
            fresh = analyze_project(root, policy())
            for key in ("nodes", "edges", "findings", "coverage"):
                self.assertEqual(deleted[key], fresh[key], key)
            self.assertEqual(deleted["incremental"]["deleted"], ["helpers.py"])
            changed_policy = policy(invariants=["secret_fields_never_in_external_payloads"])
            self.assertEqual(analyze_project(root, changed_policy, deleted["index"])["incremental"]["mode"], "full")
    def test_unknown_context_is_visible_not_a_known_policy_violation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "app.py").write_text("def profile(user):\n    return user.email\n")
            configured = policy(sinks=[{"kind": "HTTP_RESPONSE", "allow": ["PERSONAL"], "audience": "authenticated_self"}])
            finding = analyze_project(root, configured)["findings"][0]
            self.assertEqual(finding["context_requirements"], ["audience_unknown"])
            self.assertFalse(finding["policy_violation"])
            self.assertEqual(finding["status"], "POSSIBLE")

    def test_manifest_entrypoint_is_not_hidden_by_an_internal_caller(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "app.py").write_text("def expose(user):\n    return user.password_hash\n")
            (root / "regression.py").write_text("from app import expose\nexpose(None)\n")
            previous = analyze_project(root, policy())
            result = analyze_project(root, policy(), previous["index"], entrypoints=["app.expose"])
            self.assertEqual({(f["function"], f["sink"], f["source"]) for f in result["findings"]},
                             {("app.expose", "HTTP_RESPONSE", "*.password_hash")})


    def test_context_rules_and_schema_fail_closed(self):
        configured = policy(sinks=[{"kind": "HTTP_RESPONSE", "allow": ["PERSONAL"], "audience": "authenticated_self",
                                   "recipient": ["customer"], "require_contract": "profile-v1", "deny_fields": ["*.password_hash"]}],
                            invariants=["cross_tenant_reads_must_be_authorized", "secret_fields_never_in_external_payloads", "no_real_secrets_in_test_artifacts"])
        context = {"audience": "authenticated_self", "recipient": "customer", "contract": "profile-v1",
                   "tenant": "a", "source_tenant": "a", "authorized": True}
        self.assertTrue(configured.evaluate("PERSONAL", "HTTP_RESPONSE", "user.email", context)["allowed"])
        self.assertFalse(configured.evaluate("PERSONAL", "HTTP_RESPONSE", "user.email")["allowed"])
        self.assertFalse(configured.evaluate("PERSONAL", "HTTP_RESPONSE", "user.email", {**context, "source_tenant": "b", "authorized": False})["allowed"])
        self.assertFalse(configured.evaluate("PERSONAL", "HTTP_RESPONSE", "user.email", {**context, "contract": False})["allowed"])
        missing_tenants = {key: value for key, value in context.items() if key not in {"tenant", "source_tenant"}}
        self.assertIn("tenant_context_unknown", configured.evaluate("PERSONAL", "HTTP_RESPONSE", "user.email", missing_tenants)["reasons"])
        self.assertIn("field_denied", configured.evaluate("SECRET", "HTTP_RESPONSE", "user.password_hash", context)["reasons"])
        self.assertIn("secret_fields_never_in_external_payloads", configured.evaluate("SECRET", "WEBHOOK")["reasons"])
        artifact_policy = policy(sinks=[{"kind": "TEST_ARTIFACT", "allow": ["SECRET"]}],
                                 invariants=["no_real_secrets_in_test_artifacts"])
        self.assertFalse(artifact_policy.evaluate("SECRET", "TEST_ARTIFACT")["allowed"])
        self.assertTrue(artifact_policy.evaluate("SECRET", "TEST_ARTIFACT", context={"synthetic": True})["allowed"])
        with self.assertRaises(ValueError):
            configured.evaluate("PERSONAL", "HTTP_RESPONSE", context={"authorized": "yes"})
        for raw in ({**configured.raw, "unknown": True}, {**configured.raw, "invariants": ["imaginary_rule"]},
                    {**configured.raw, "sinks": [{"kind": "HTTP_RESPONSE", "ignore_auth": True}]}):
            with self.assertRaises(ValueError):
                Policy(raw)
        lifecycle = copy.deepcopy(configured.raw)
        lifecycle.update(status="draft", approved_by="local-reviewer")
        self.assertEqual(Policy(lifecycle).digest, configured.digest)


if __name__ == "__main__":
    unittest.main()
