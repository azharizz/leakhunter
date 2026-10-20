import base64
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from unspool.handoff import complete, validate_scope
from unspool.handoff_config import HandoffConfig, preflight


class ConfigTest(unittest.TestCase):
    def data(self):
        return {"version": 1, "project_id": 42, "project_path": "another-team/invoices",
                "target_branch": "release", "branch_prefix": "security/", "trigger_username": "duo-developer-another-team",
                "allowed_paths": ["src/invoice.py"], "verification_jobs": ["tests", "exposure"],
                "deployment_jobs": ["deploy", "smoke"], "evidence_job": "exposure",
                "evidence_path": "evidence.json", "health_path": "public/health.json",
                "protected_files": {"policy.yaml": hashlib.sha256(b"contract").hexdigest(),
                                    "runtime.yaml": hashlib.sha256(b"contract").hexdigest()}}

    def load(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "operator.json"
            path.write_text(json.dumps(data))
            return HandoffConfig.load(path)

    def test_other_repository_defaults_to_review_and_is_bound_to_project(self):
        config = self.load(self.data())
        self.assertEqual(config.mode, "review")
        self.assertEqual(config.digest, self.load(self.data()).digest)
        mr = {"source_project_id": 42, "target_project_id": 42, "target_branch": "release",
              "source_branch": "security/repair-1", "state": "opened", "sha": "a" * 40}
        diff = {"sha": "a" * 40, "overflow": False, "changes": [{"old_path": "src/invoice.py", "new_path": "src/invoice.py"}]}
        validate_scope(mr, diff, 42, config)
        for change in ({"source_project_id": 99}, {"target_branch": "main"}, {"source_branch": "unspool/repair-1"}):
            with self.assertRaises(ValueError):
                validate_scope(dict(mr, **change), diff, 42, config)
        with self.assertRaises(ValueError):
            validate_scope(mr, dict(diff, sha="b" * 40), 42, config)

    def test_malformed_or_scope_expanding_configuration_is_rejected(self):
        cases = [{"project_id": True}, {"version": True}, {"mode": []}, {"timeout": True},
                 {"poll_interval": 0}, {"project_path": "https://evil.invalid/owner/repo"},
                 {"trigger_username": "agent\n@another"}, {"deployment_jobs": ["ok", "ok"]},
                 {"evidence_job": "optional"}, {"evidence_path": "../evidence.json"},
                 {"token": "do-not-accept-secrets"}, {"mode": "auto", "protected_files": {}},
                 {"mode": "auto", "deployment_jobs": []}]
        cases += [{"allowed_paths": [path]} for path in
                  ("../src/a.py", "/tmp/a.py", "src/*.py", "src//a.py", ".git/config.py", "tests/test_a.py", "setup.py", "src\\a.py")]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.load(dict(self.data(), **change))

    def test_duplicate_keys_and_group_writable_operator_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "operator.json"
            path.write_text('{"version":1,"version":1}')
            with self.assertRaises(ValueError):
                HandoffConfig.load(path)
            path.write_text(json.dumps(self.data()))
            path.chmod(0o666)
            with self.assertRaises(ValueError):
                HandoffConfig.load(path)

    def test_operator_file_links_special_files_and_oversize_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "original.json"
            source.write_text(json.dumps(self.data()))
            link = root / "linked.json"
            link.symlink_to(source)
            with self.assertRaises(OSError):
                HandoffConfig.load(link)
            link.unlink()
            os.link(source, link)
            with self.assertRaises(ValueError):
                HandoffConfig.load(source)
            link.unlink()
            source.write_text(" " * 65537)
            with self.assertRaisesRegex(ValueError, "large"):
                HandoffConfig.load(source)
            fifo = root / "fifo"
            os.mkfifo(fifo)
            with self.assertRaises(ValueError):
                HandoffConfig.load(fifo)
            with self.assertRaises(ValueError):
                HandoffConfig.load(root)

    def api(self, *, merge_method="ff", contract=b"contract"):
        calls = []

        class API:
            def request(self, method, path, body=None):
                calls.append((method, path))
                if path == "projects/42":
                    return {"id": 42, "path_with_namespace": "another-team/invoices", "merge_method": merge_method}
                if "/branches/" in path:
                    return {"protected": True, "commit": {"id": "b" * 40}}
                if "/repository/files/" in path:
                    return {"encoding": "base64", "content": base64.b64encode(contract).decode()}
                if path.endswith("/changes"):
                    return {"sha": "a" * 40, "overflow": False, "changes": [{"old_path": "src/invoice.py", "new_path": "src/invoice.py"}]}
                if "/pipelines/" in path:
                    return [{"id": 2, "name": name, "status": "success"} for name in ("tests", "exposure")]
                if path.endswith("/artifacts/evidence.json"):
                    return {"gate": {"passed": True}, "runtime": {"status": "COMPLETED", "passed": True, "cases": [{"passed": True}]}}
                if path.endswith("/artifacts/public/health.json"):
                    return {"status": "ok", "verified": True, "commit": "a" * 40}
                if method != "GET":
                    raise AssertionError("Review or failed validation must never mutate GitLab")
                return {"source_project_id": 42, "target_project_id": 42, "target_branch": "release",
                        "source_branch": "security/repair-1", "state": "opened", "sha": "a" * 40,
                        "diff_refs": {"base_sha": "b" * 40},
                        "head_pipeline": {"id": 1, "sha": "a" * 40, "status": "success"}}

        return API(), calls

    def test_preflight_is_readonly_and_rejects_project_confusion(self):
        config = self.load(self.data())
        api, calls = self.api()
        self.assertEqual(preflight(config, api)["status"], "PREFLIGHT_PASSED")
        self.assertTrue(all(method == "GET" for method, _ in calls))
        with self.assertRaises(ValueError):
            preflight(replace(config, project_path="other/project"), api)
        with self.assertRaises(ValueError):
            complete(99, 1, api=api, config=config)

    def test_other_repository_can_verify_without_merging(self):
        config = self.load(self.data())
        api, calls = self.api()
        result = complete(42, 1, api=api, config=config)
        self.assertEqual(result["status"], "READY_FOR_REVIEW")
        self.assertEqual(result["sha"], "a" * 40)
        self.assertTrue(all(method == "GET" for method, _ in calls))
        api, calls = self.api(contract=b"changed contract")
        with self.assertRaises(ValueError):
            complete(42, 1, api=api, config=config)
        self.assertTrue(all(method == "GET" for method, _ in calls))

    def test_automatic_promotion_refuses_stale_target_and_non_ff_projects(self):
        config = replace(self.load(self.data()), mode="auto")
        api, calls = self.api(merge_method="merge")
        with self.assertRaises(ValueError):
            complete(42, 1, api=api, config=config)
        self.assertTrue(all(method == "GET" for method, _ in calls))
        api, calls = self.api()
        original = api.request

        def changed_target(method, path, body=None):
            if "/branches/" in path:
                return {"protected": True, "commit": {"id": "c" * 40}}
            return original(method, path, body)

        api.request = changed_target
        with self.assertRaisesRegex(ValueError, "Target branch changed"):
            complete(42, 1, api=api, config=config)
        self.assertTrue(all(method == "GET" for method, _ in calls))
