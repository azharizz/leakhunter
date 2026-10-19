import copy
import json
import os
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from leakhunter.policy.engine import Policy
from leakhunter.repairs.engine import _git, _parse_edits, _source_digest, propose_and_verify, resolve_context_findings
from leakhunter.execution.runtime import run_suite


SOURCE = '''import logging

def expose(record):
    logging.warning("record=%s", record["private_value"])
    return {"public": record["public"]}
'''
OLD = 'logging.warning("record=%s", record["private_value"])'
SAFE = 'logging.warning("processed public record")'


class RepairTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo, self.data = self.root / "target", self.root / "state"
        self.repo.mkdir()
        (self.repo / "app.py").write_text(SOURCE)
        (self.repo / "regression.py").write_text(
            'from app import expose\n'
            'assert expose({"private_value": "SYNTHETIC_REGRESSION", "public": "ok"}) == {"public": "ok"}\n')
        self.policy = Policy({"version": 1, "classifications": {"PUBLIC": 0, "SECRET": 1},
                              "sources": [{"selector": "*.private_value", "class": "SECRET"}],
                              "sinks": [{"kind": "APPLICATION_LOG", "allow": ["PUBLIC"]},
                                        {"kind": "HTTP_RESPONSE", "allow": ["PUBLIC"]}]})
        self.manifest = {"version": 1, "cases": [{
            "id": "log-secret", "module": "app", "callable": "expose", "args": [],
            "kwargs": {"record": {"private_value": "SYNTHETIC_REPAIR_MARKER", "public": "ok"}},
            "sensitive": [{"marker": "SYNTHETIC_REPAIR_MARKER", "class": "SECRET", "symbol": "record.private_value"}],
            "context": {"synthetic": True}, "expect": {"public": "ok"}, "expected_violation": True,
            "finding": {"file": "app.py", "function": "expose", "sink": "APPLICATION_LOG", "symbol": "record.private_value"}}],
            "regression_command": ["python", "-B", "regression.py"]}

    def baseline(self):
        runtime = run_suite(self.repo, self.manifest, self.policy, backend="local")
        self.assertEqual(runtime["status"], "COMPLETED", runtime)
        self.assertTrue(runtime["functional_passed"], runtime)
        self.assertTrue(runtime["cases"][0]["violations"], runtime)
        return {"revision_sha": _source_digest(self.repo), "runtime": runtime, "findings": []}

    def provider(self, new=SAFE, path="app.py", old=OLD):
        def respond(model, prompt):
            self.assertEqual(model, "test/model")
            self.assertIn('"app.py"', prompt)
            self.assertNotIn("SYNTHETIC_REPAIR_MARKER", prompt)
            self.assertNotIn("SYNTHETIC_REGRESSION", prompt)
            return ("```json\n" + json.dumps({"edits": [{"path": path, "old": old, "new": new}],
                                               "summary": "Remove secret from log; retain public response"}) + "\n```", 7, "ok")
        return respond

    def repair(self, provider=None, baseline=None, **kwargs):
        return propose_and_verify(self.repo, self.data, self.policy, self.manifest,
                                  self.baseline() if baseline is None else baseline,
                                  self.provider() if provider is None else provider,
                                  "test/model", backend="local", **kwargs)

    def test_real_git_differential_repair_preserves_target_and_pinned_tests(self):
        # Existing target hooks/config and host Git settings must not execute in the simulation.
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(parents=True)
        triggered = self.root / "HOOK_RAN"
        hook.write_text('#!/bin/sh\ntouch "' + str(triggered) + '"\nexit 1\n')
        hook.chmod(0o700)
        global_config = self.root / "gitconfig"
        global_config.write_text('[core]\n hooksPath = ' + str(hook.parent) + '\n[commit]\n gpgsign = true\n')
        (self.repo / ".env").write_text("DO_NOT_COPY=fixture-value\n")
        (self.repo / "data").mkdir()
        (self.repo / "data" / "private.py").write_text("raise RuntimeError('not source')\n")
        (self.repo / "linked.py").symlink_to(self.repo / "app.py")
        original = _source_digest(self.repo)
        # The direct runtime rejects target links; baseline is captured before adding a link.
        (self.repo / "linked.py").unlink()
        baseline = self.baseline()
        (self.repo / "linked.py").symlink_to(self.repo / "app.py")
        policy_before, manifest_before = copy.deepcopy(self.policy.raw), copy.deepcopy(self.manifest)
        with patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(global_config), "GIT_TEMPLATE_DIR": str(hook.parent),
                                    "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.hooksPath",
                                    "GIT_CONFIG_VALUE_0": str(hook.parent)}):
            result = self.repair(baseline=baseline)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["status"], "VERIFIED")
        self.assertTrue(result["verification"]["passed"])
        self.assertEqual(result["provider_latency_ms"], 7)
        self.assertEqual(_source_digest(self.repo), original)
        self.assertEqual((self.repo / "app.py").read_text(), SOURCE)
        self.assertEqual(self.policy.raw, policy_before)
        self.assertEqual(self.manifest, manifest_before)
        workspace = self.data / result["workspace"]
        self.assertFalse((workspace / ".env").exists())
        self.assertFalse((workspace / "data").exists())
        self.assertFalse((workspace / "linked.py").exists())
        self.assertFalse(triggered.exists())
        self.assertEqual((workspace / "regression.py").read_text(), (self.repo / "regression.py").read_text())
        self.assertIn("processed public record", (workspace / "app.py").read_text())
        control = workspace.parent / "control"
        self.assertEqual(_git(workspace, control, "rev-parse", "HEAD"), result["commit_sha"])
        self.assertEqual(_git(workspace, control, "branch", "--show-current"), result["branch"])
        self.assertEqual(_git(workspace, control, "rev-list", "--count", "HEAD"), "2")
        mr = json.loads((self.data / result["local_mr"]).read_text())
        self.assertTrue(mr["simulation"])
        self.assertFalse(mr["auto_merge"])
        self.assertEqual(mr["deployment"], "NOT_REQUESTED")
        self.assertFalse(result["verification"]["after"]["cases"][0]["violations"])
        self.assertEqual(result["verification"]["static_after"], [])

    def test_exact_edit_boundaries_and_fenced_json(self):
        updated, summary = _parse_edits('```json\n' + json.dumps({"edits": [{"path": "app.py", "old": OLD, "new": SAFE}]}) + '\n```',
                                        self.repo, {"app.py"})
        self.assertEqual(updated["app.py"], SOURCE.replace(OLD, SAFE))
        self.assertEqual(summary, "")
        (self.repo / "other.py").write_text("pass\n")
        (self.repo / "link.py").symlink_to(self.repo / "app.py")
        for name in ("config.py", "test_app.py", "runtime_worker.py"):
            (self.repo / name).write_text(SOURCE)
        for path in ("../app.py", "/app.py", "./app.py", "nested/../app.py", "app\\file.py",
                     "config.py", "test_app.py", "runtime_worker.py", "link.py", "other.py", ".env"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                _parse_edits(json.dumps({"edits": [{"path": path, "old": OLD, "new": SAFE}]}), self.repo, {"app.py"})
        for old in ("not present", "public", ""):
            with self.subTest(old=old), self.assertRaises(ValueError):
                _parse_edits(json.dumps({"edits": [{"path": "app.py", "old": old, "new": SAFE}]}), self.repo, {"app.py"})
        for payload in ({"edits": []}, {"edits": [{"path": "app.py", "old": OLD, "new": SAFE}] * 17},
                        {"edits": [{"path": "app.py", "old": OLD, "new": SAFE, "command": "echo unsafe"}]},
                        {"edits": [{"path": "app.py", "old": OLD, "new": SAFE}], "approve": True},
                        {"edits": [{"path": "app.py", "old": OLD, "new": "x" * (128 * 1024)}]}):
            with self.subTest(payload_type=list(payload)), self.assertRaises(ValueError):
                _parse_edits(json.dumps(payload), self.repo, {"app.py"})
        self.assertEqual((self.repo / "app.py").read_text(), SOURCE)

    def test_exact_edit_preserves_crlf_bytes(self):
        original = SOURCE.replace("\n", "\r\n")
        (self.repo / "app.py").write_bytes(original.encode())
        updated, _ = _parse_edits(json.dumps({"edits": [{"path": "app.py", "old": OLD, "new": SAFE}]}),
                                  self.repo, {"app.py"})
        self.assertEqual(updated["app.py"].encode(), original.replace(OLD, SAFE).encode())

    def test_invalid_json_has_no_fallback(self):
        for response in ("not JSON", "```json\n{}\n```\nextra", '{"edits":null}'):
            with self.subTest(response=response), self.assertRaises(ValueError):
                _parse_edits(response, self.repo, {"app.py"})

    def test_independent_before_execution_does_not_trust_saved_violation(self):
        baseline = self.baseline()
        (self.repo / "app.py").write_text(SOURCE.replace(OLD, SAFE))
        called = []
        def forbidden(*args):
            called.append(True)
            return "{}", 0, "ok"
        result = self.repair(provider=forbidden, baseline=baseline)
        self.assertFalse(result["passed"])
        self.assertFalse(called)
        self.assertTrue(any(g["name"] == "baseline_reproduced" and not g["passed"]
                            for g in result["verification"]["gates"]), result)


    def test_missing_execution_blocks_provider(self):
        def forbidden(*args):
            self.fail("Provider must not be called without observed baseline evidence")
        result = self.repair(provider=forbidden, baseline={"runtime": {"status": "NOT_RUN"}})
        self.assertFalse(result["passed"])
        self.assertIsNone(result["workspace"])
        self.assertEqual(result["provider_status"], "not_run")
        result = propose_and_verify(self.repo, self.data, self.policy, None, {}, forbidden, "test/model", backend="local")
        self.assertFalse(result["passed"])
        self.assertIsNone(result["workspace"])

    def test_rejected_provider_patch_never_creates_repair_commit_or_mr(self):
        result = self.repair(provider=self.provider(path="../app.py"))
        self.assertEqual(result["status"], "REJECTED", result)
        self.assertFalse(result["passed"])
        self.assertIsNone(result["commit_sha"])
        self.assertNotIn("local_mr", result)
        workspace = self.data / result["workspace"]
        self.assertEqual((workspace / "app.py").read_text(), SOURCE)
        self.assertEqual(_git(workspace, workspace.parent / "control", "rev-list", "--count", "HEAD"), "1")

    def test_broken_functionality_is_not_a_security_fix(self):
        result = self.repair(provider=self.provider(new=SAFE + '\n    return {"public": "broken"}'))
        self.assertFalse(result["passed"])
        self.assertIsNone(result["commit_sha"])
        self.assertNotIn("local_mr", result)
        self.assertTrue(any(g["name"] in {"functional_regression", "after_execution"} and not g["passed"]
                            for g in result["verification"]["gates"]), result)

    def test_possible_unexecuted_flow_cannot_silently_pass(self):
        # Runtime succeeds, but a conditional source path remains statically possible.
        replacement = SAFE + '\n    if record.get("emit_secret"):\n        ' + OLD
        result = self.repair(provider=self.provider(new=replacement))
        self.assertFalse(result["passed"])
        self.assertTrue(result["verification"]["after"]["passed"], result)
        self.assertTrue(result["verification"]["static_after"], result)
        self.assertNotIn("local_mr", result)
        self.assertTrue(any(g["name"] in {"scoped_context_evidence", "no_new_static_findings"} and not g["passed"]
                            for g in result["verification"]["gates"]), result)

    def test_unsupported_syntax_cannot_be_verified(self):
        result = self.repair(provider=self.provider(new=SAFE + "\n    ignored = lambda: None"))
        self.assertFalse(result["passed"])
        self.assertTrue(any(g["name"] == "after_static_scan" and not g["passed"]
                            for g in result["verification"]["gates"]), result)
        self.assertNotIn("local_mr", result)

    def test_context_only_transfer_requires_real_pinned_observation(self):
        raw = copy.deepcopy(self.policy.raw)
        raw["classifications"].update(PERSONAL=1, SECRET=2)
        raw["sources"].append({"selector": "*.email", "class": "PERSONAL"})
        raw["sinks"][1].update(allow=["PERSONAL"], audience="authenticated_self")
        self.policy = Policy(raw)
        source = SOURCE.replace('return {"public": record["public"]}',
                                'return {"public": record["public"], "email": record["email"]}')
        (self.repo / "app.py").write_text(source)
        (self.repo / "regression.py").write_text(
            'from app import expose\n'
            'record = {"private_value": "SYNTHETIC_REGRESSION", "public": "ok", "email": "regression@example.invalid"}\n'
            'assert expose(record) == {"public": "ok", "email": "regression@example.invalid"}\n')
        case = self.manifest["cases"][0]
        case["kwargs"]["record"]["email"] = "person@example.invalid"
        case["sensitive"].append({"marker": "person@example.invalid", "class": "PERSONAL", "symbol": "record.email"})
        case["context"]["audience"] = "authenticated_self"
        case["expect"]["email"] = "person@example.invalid"
        response = copy.deepcopy(case)
        response.update(id="permitted-email", expected_violation=False)
        response["finding"].update(sink="HTTP_RESPONSE", symbol="record.email")
        self.manifest["cases"].append(response)
        result = self.repair()
        self.assertTrue(result["passed"], result)
        verification = result["verification"]
        self.assertEqual(verification["unresolved_static_findings"], [])
        # Removing mapping, changing source identity or losing marker evidence fails closed.
        for kind in ("mapping", "function", "symbol", "marker", "context", "policy_violation", "runtime"):
            manifest, runtime = copy.deepcopy(self.manifest), copy.deepcopy(verification["after"])
            findings = copy.deepcopy(verification["static_after"])
            if kind == "mapping":
                for item in manifest["cases"]:
                    item.pop("finding", None)
            elif kind == "function":
                for item in manifest["cases"]:
                    item["finding"]["function"] = "different"
            elif kind == "symbol":
                for item in runtime["cases"]:
                    for observation in item["observations"]:
                        observation["symbol"] = "unrelated.email"
            elif kind == "marker":
                for item in runtime["cases"]:
                    for observation in item["observations"]:
                        observation["marker_hash"] = hashlib.sha256(b"wrong marker").hexdigest()
            elif kind == "context":
                for item in manifest["cases"]:
                    item["context"]["audience"] = "public"
            elif kind == "policy_violation":
                for finding in findings:
                    finding["policy_violation"] = True
            else:
                runtime["passed"] = False
            with self.subTest(boundary=kind):
                resolved = resolve_context_findings(findings, runtime, manifest, self.policy)
                self.assertEqual(resolved["discharged"], [])
                self.assertEqual(resolved["unresolved"], findings)

    def test_pinned_regression_cannot_be_authorized_for_model_edits(self):
        def forbidden(*args):
            self.fail("Pinned regression source must never be disclosed for editing")
        result = self.repair(provider=forbidden, allowed_paths=["app.py", "regression.py"])
        self.assertFalse(result["passed"])
        self.assertIn("regression", result["error"])
        self.assertEqual(result["provider_status"], "not_run")

    def test_embedded_credential_blocks_disclosure(self):
        baseline = self.baseline()
        # Deliberately synthetic fixture shaped like an embedded credential.
        (self.repo / "app.py").write_text(SOURCE + '\nAPI_KEY = "fixture-only-secret-value"\n')
        def forbidden(*args):
            self.fail("Credential-shaped source must never reach a provider")
        result = self.repair(provider=forbidden, baseline=baseline)
        self.assertFalse(result["passed"])
        self.assertIn("credential", result["error"])
        self.assertNotIn("fixture-only-secret-value", json.dumps(result))
        self.assertEqual(result["provider_status"], "not_run")


if __name__ == "__main__":
    unittest.main()
