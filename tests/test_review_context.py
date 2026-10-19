import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from leakhunter.analyzers.python_ast import analyze_project
from leakhunter.policy.engine import Policy
from leakhunter.providers.context import build_review_contexts
from leakhunter.providers.disclosure import MAX_CONTEXT_BYTES, MAX_SOURCE_BYTES


class ReviewContextTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.policy = Policy({"version": 1, "classifications": {"PUBLIC": 0}, "sources": [],
                              "sinks": [{"kind": "HTTP_RESPONSE", "allow": ["PUBLIC"],
                                         "require_authorization": True, "same_tenant": True}],
                              "approved_by": "private-policy-approver"})

    def invoice(self):
        (self.root / "invoices.py").write_text(
            'from repository import get_invoice\nfrom framework import app\nVERSION = 1\n\n'
            '@app.get("/invoices/<invoice_id>")\ndef download_invoice(invoice_id):\n'
            '    return get_invoice(invoice_id)\n\ndef unrelated_local():\n    return "not-selected-local"\n')
        (self.root / "repository.py").write_text(
            'from database import db\n\ndef get_invoice(invoice_id):\n'
            '    return db.fetch_invoice(invoice_id)\n')
        (self.root / "disconnected.py").write_text('def separate():\n    return "disconnected-payload"\n')
        return analyze_project(self.root, self.policy, entrypoints=["invoices.download_invoice"])

    def build(self, analysis, runtime=None, manifest=None):
        return build_review_contexts(self.root, analysis, self.policy,
                                     runtime or {"status": "NOT_RUN", "cases": []}, manifest, "revision-test")

    def endpoint(self, contexts):
        return next(review for review in contexts["reviews"]
                    if review["boundary"]["function"] == "invoices.download_invoice")

    def test_public_only_endpoint_has_connected_auditable_source_and_graph_without_findings(self):
        analysis = self.invoice()
        self.assertEqual(analysis["findings"], [])
        contexts = self.build(analysis)
        review = self.endpoint(contexts)
        self.assertEqual(review["boundary"]["kind"], "HTTP_RESPONSE")
        self.assertTrue(review["boundary"]["entrypoint"]["declared"])
        self.assertIn("analysis", review["boundary"]["entrypoint"]["declared_by"])
        self.assertEqual(review["boundary"]["input_fields"], ["invoice_id"])
        self.assertEqual(review["boundary"]["output_recipients"], ["HTTP_RESPONSE"])
        self.assertEqual(review["flow_paths"], [])
        self.assertFalse(review["scope"]["complete"])
        self.assertEqual(review["findings"], [])
        self.assertEqual({entry["file"] for entry in review["code"]}, {"invoices.py", "repository.py"})
        self.assertTrue({"AST", "CFG", "CALLS"} <= {edge["type"] for edge in review["graph"]["edges"]})
        text = "".join(entry["text"] for entry in review["code"])
        self.assertIn('from repository import get_invoice', text)
        self.assertIn('@app.get("/invoices/<invoice_id>")', text)
        self.assertIn('VERSION = 1', text)
        self.assertIn('return db.fetch_invoice(invoice_id)', text)
        self.assertNotIn("not-selected-local", text)
        self.assertNotIn("disconnected-payload", json.dumps(review))
        unknowns = " ".join(review["unknowns"])
        self.assertIn("db.fetch_invoice", unknowns)
        self.assertNotIn("private-policy-approver", json.dumps(review))
        self.assertTrue(review["policy"]["rules"]["sinks"][0]["require_authorization"])
        self.assertTrue(review["policy"]["rules"]["sinks"][0]["same_tenant"])
        for entry in review["code"]:
            source = (self.root / entry["file"]).read_bytes()
            self.assertEqual(entry["sha256"], hashlib.sha256(source).hexdigest())
            self.assertEqual(entry["text"], "".join(source.decode().splitlines(keepends=True)[entry["start_line"] - 1:entry["end_line"]]))
            self.assertTrue(any(entry["file"] in ref and entry["sha256"] in ref for ref in review["evidence_refs"]))

    def test_flow_paths_include_data_steps_and_candidate_branch_predicates(self):
        policy = Policy({"version": 1, "classifications": {"PUBLIC": 0, "SECRET": 1},
                         "sources": [{"selector": "*.secret", "class": "SECRET"}],
                         "sinks": [{"kind": "HTTP_RESPONSE", "allow": ["PUBLIC"]}]})
        (self.root / "flow.py").write_text(
            "from flask import jsonify\n\n"
            "def endpoint(record):\n"
            "    if record['secret']:\n"
            "        value = record['secret']\n"
            "        return jsonify(value)\n"
            "    return jsonify({'ok': True})\n")
        analysis = analyze_project(self.root, policy, entrypoints=["flow.endpoint"])
        review = build_review_contexts(self.root, analysis, policy,
                                       {"status": "NOT_RUN", "cases": []}, None, "revision-test")["reviews"][0]
        self.assertTrue(review["flow_paths"])
        self.assertTrue(review["flow_paths"][0]["steps"])
        self.assertTrue(review["flow_paths"][0]["branch_predicates"])

    def test_route_decorator_creates_review_unit_without_findings_or_manifest(self):
        (self.root / "route.py").write_text(
            "from framework import app\n\n"
            "@app.get('/health')\n"
            "def health(request):\n"
            "    return {'status': 'ok'}\n")
        analysis = analyze_project(self.root, self.policy)
        self.assertEqual(analysis["findings"], [])
        contexts = self.build(analysis)
        review = next(item for item in contexts["reviews"] if item["boundary"]["function"] == "route.health")
        self.assertEqual(review["boundary"]["kind"], "HTTP_RESPONSE")
        self.assertIn("route_decorator", review["boundary"]["entrypoint"]["declared_by"])
        self.assertEqual(review["boundary"]["input_fields"], ["request"])

    def test_runtime_is_scoped_and_never_sends_fixture_inputs_results_markers_or_tenants(self):
        analysis = self.invoice()
        case = {"id": "invoice", "module": "invoices", "callable": "download_invoice",
                "args": ["private-argument"], "kwargs": {"other": "private-kwarg"},
                "sensitive": [{"marker": "synthetic-marker-value", "class": "PUBLIC", "symbol": "Invoice.total"}],
                "expect": {"data": "private-expected-value"},
                "context": {"audience": "authenticated", "recipient": "customer", "authorized": False,
                            "contract": "billing", "synthetic": True, "tenant": "tenant-private-a", "source_tenant": "tenant-private-b"}}
        other = {**case, "id": "unmatched-private-case", "module": "disconnected", "callable": "separate"}
        runtime = {"status": "COMPLETED", "cases": [
            {"id": "invoice", "passed": True, "observed": True, "result": "private-result-value",
             "observations": [{"sink": "HTTP_RESPONSE", "symbol": "Invoice.total", "marker_hash": "private-marker-hash"}],
             "violations": [{"sink": "HTTP_RESPONSE", "symbol": "Invoice.total", "classification": "PUBLIC",
                             "reasons": ["authorization_required", "same_tenant_required"], "raw": "private-raw-value"}]},
            {"id": other["id"], "passed": True, "observations": [], "violations": []}]}
        review = self.endpoint(self.build(analysis, runtime, {"version": 1, "cases": [case, other]}))
        evidence = review["runtime_evidence"]
        self.assertEqual([item["id"] for item in evidence["cases"]], ["invoice"])
        self.assertEqual(evidence["cases"][0]["context"],
                         {"audience": "authenticated", "recipient": "customer", "authorized": False,
                          "contract": "billing", "synthetic": True, "same_tenant": False})
        self.assertTrue(evidence["cases"][0]["observed"])
        self.assertEqual(evidence["cases"][0]["violations"][0]["reasons"],
                         ["authorization_required", "same_tenant_required"])
        encoded = json.dumps(review)
        for forbidden in ("private-argument", "private-kwarg", "synthetic-marker-value", "private-expected-value",
                          "tenant-private-a", "tenant-private-b", "private-result-value", "private-marker-hash",
                          "private-raw-value", "unmatched-private-case"):
            self.assertNotIn(forbidden, encoded)

    def test_explicit_manifest_mapping_matches_without_classified_finding(self):
        analysis = self.invoice()
        manifest = {"cases": [{"id": "mapped", "module": "invoices", "callable": "test_wrapper",
                               "finding": {"file": "invoices.py", "function": "download_invoice", "sink": "HTTP_RESPONSE"},
                               "context": {"synthetic": True}}]}
        review = self.endpoint(self.build(analysis, {"status": "COMPLETED", "cases": [{"id": "mapped", "passed": True}]}, manifest))
        self.assertEqual([case["id"] for case in review["runtime_evidence"]["cases"]], ["mapped"])

    def test_unsafe_sources_are_withheld_with_visible_omissions(self):
        for mode in ("credential", "changed", "symlink", "oversized", "invalid-path"):
            with self.subTest(mode=mode):
                source = 'def endpoint():\n    return "original-safe-value"\n'
                if mode == "credential":
                    source += 'api_key = "' + 'sk-' + 'a' * 24 + '"\n'
                if mode == "oversized":
                    source += '#' + 'x' * MAX_SOURCE_BYTES + '\n'
                path = self.root / "unsafe.py"
                if path.is_symlink():
                    path.unlink()
                path.write_text(source)
                analysis = analyze_project(self.root, self.policy, entrypoints=["unsafe.endpoint"])
                if mode == "changed":
                    path.write_text(source + '# changed-private-value\n')
                elif mode == "symlink":
                    target = self.root / "replacement.txt"
                    target.write_text(source)
                    path.unlink()
                    path.symlink_to(target)
                elif mode == "invalid-path":
                    for node in analysis["nodes"]:
                        node["file"] = "../unsafe.py"
                    analysis["index"]["files"]["../unsafe.py"] = analysis["index"]["files"].pop("unsafe.py")
                contexts = self.build(analysis)
                review = next(item for item in contexts["reviews"] if item["boundary"]["function"].endswith(".endpoint"))
                self.assertEqual(review["code"], [])
                self.assertNotIn("original-safe-value", json.dumps(contexts))
                self.assertNotIn("changed-private-value", json.dumps(contexts))
                self.assertNotIn('sk-' + 'a' * 24, json.dumps(contexts))
                self.assertFalse(contexts["scope"]["selection_complete"])

    def test_unresolved_call_alone_creates_a_module_review_unit(self):
        (self.root / "module.py").write_text('from external_sdk import send\nsend("public")\n')
        analysis = analyze_project(self.root, self.policy)
        self.assertEqual(analysis["findings"], [])
        contexts = self.build(analysis)
        self.assertEqual(len(contexts["reviews"]), 1)
        review = contexts["reviews"][0]
        self.assertEqual(review["boundary"]["kind"], "UNRESOLVED_CALL")
        self.assertIn('send("public")', review["code"][0]["text"])

    def test_unit_graph_and_request_bounds_are_explicit(self):
        (self.root / "many.py").write_text(''.join(f'def endpoint_{index}():\n    return {index}\n\n' for index in range(30)))
        analysis = analyze_project(self.root, self.policy)
        contexts = self.build(analysis)
        self.assertEqual(len(contexts["reviews"]), 24)
        self.assertEqual(contexts["scope"]["omitted_review_units"], 6)
        self.assertFalse(contexts["scope"]["selection_complete"])
        (self.root / "many.py").write_text('def large():\n' + ''.join(f'    value_{index} = {index}\n' for index in range(180)) + '    return 1\n')
        contexts = self.build(analyze_project(self.root, self.policy))
        review = contexts["reviews"][0]
        self.assertLessEqual(len(review["graph"]["nodes"]), 256)
        self.assertFalse(contexts["scope"]["selection_complete"])
        self.assertLess(len(json.dumps(json.dumps(review)).encode()), MAX_CONTEXT_BYTES - 16 * 1024)

    def test_connected_scope_bound_is_visible(self):
        (self.root / "chain.py").write_text(''.join(
            f'def function_{index}():\n    return function_{index + 1}()\n\n' for index in range(15))
            + 'def function_15():\n    return external.fetch()\n')
        analysis = analyze_project(self.root, self.policy, entrypoints=["chain.function_0"])
        review = self.build(analysis)["reviews"][0]
        self.assertLessEqual(sum(node["kind"] == "FunctionDef" for node in review["graph"]["nodes"]), 12)
        self.assertFalse(review["scope"]["complete"])

    def test_request_budget_omits_whole_excerpts_not_truncated_code(self):
        for index in range(3):
            prefix = f"from part_{index + 1} import run as next_run\n" if index < 2 else ""
            returned = "next_run()" if index < 2 else '"public"'
            source = prefix + 'def run():\n    """' + "harmless " * 5500 + '"""\n    return ' + returned + '\n'
            (self.root / f"part_{index}.py").write_text(source)
        contexts = self.build(analyze_project(self.root, self.policy, entrypoints=["part_0.run"]))
        review = contexts["reviews"][0]
        self.assertFalse(contexts["scope"]["selection_complete"])
        self.assertLessEqual(len(json.dumps(json.dumps(review)).encode()), MAX_CONTEXT_BYTES - 16 * 1024)
        for entry in review["code"]:
            source = (self.root / entry["file"]).read_text()
            self.assertEqual(entry["text"], "".join(source.splitlines(keepends=True)[entry["start_line"] - 1:entry["end_line"]]))

    def test_relevant_findings_retain_flow_and_context_requirements_not_arbitrary_data(self):
        self.policy = Policy({"version": 1, "classifications": {"PUBLIC": 0, "SECRET": 1},
                              "sources": [{"selector": "*.private", "class": "SECRET"}],
                              "sinks": [{"kind": "HTTP_RESPONSE", "allow": ["PUBLIC"], "require_authorization": True}]})
        (self.root / "module.py").write_text("def endpoint(user):\n    return user.private\n")
        analysis = analyze_project(self.root, self.policy)
        finding = analysis["findings"][0]
        finding["runtime_evidence"] = {"status": "NOT_RUN", "observed": False, "case_ids": [], "result": "private-result"}
        finding["args"] = ["private-argument"]
        review = self.build(analysis)["reviews"][0]
        self.assertEqual([item["id"] for item in review["findings"]], [finding["id"]])
        self.assertIn("authorization_required", review["findings"][0]["context_requirements"])
        self.assertIn("DATA_FLOW", {edge["type"] for edge in review["graph"]["edges"]})
        self.assertEqual(review["findings"][0]["runtime_evidence"]["status"], "NOT_RUN")
        self.assertNotIn("private-result", json.dumps(review))
        self.assertNotIn("private-argument", json.dumps(review))

    def test_cached_ast_is_reused_and_crlf_source_is_exact(self):
        (self.root / "module.py").write_bytes(b'from external import db\r\n\r\ndef endpoint():\r\n    return db.fetch()\r\n')
        analysis = analyze_project(self.root, self.policy)
        cached = json.loads(json.dumps(analysis))
        with patch("leakhunter.analyzers.python_ast.ast.parse", side_effect=AssertionError("must use cached spans")):
            contexts = self.build(cached)
        self.assertEqual(contexts, self.build(analysis))
        self.assertIn("\r\n", contexts["reviews"][0]["code"][0]["text"])


if __name__ == "__main__":
    unittest.main()
