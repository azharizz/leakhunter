import base64
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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
                    if "security%2Frepair-1" in path:
                        return {"protected": True, "commit": {"id": "a" * 40}}
                    return {"protected": True, "commit": {"id": "b" * 40}}
                if "/repository/files/" in path:
                    return {"encoding": "base64", "content": base64.b64encode(contract).decode()}
                if path.endswith("/changes"):
                    return {"sha": "a" * 40, "overflow": False, "changes": [{"old_path": "src/invoice.py", "new_path": "src/invoice.py"}]}
                if "/pipelines/" in path:
                    names = ("deploy", "smoke") if "/pipelines/3/" in path else (
                        "tests", "exposure", "sign-evidence", "verify-attestation")
                    return [{"id": index + 1, "name": name, "status": "success"}
                            for index, name in enumerate(names)]
                if path.endswith("/artifacts/evidence.json"):
                    return {"base_sha": "b" * 40, "head_sha": "a" * 40,
                            "policy": {"base_sha256": "c" * 64, "head_sha256": "c" * 64},
                            "decision": {"luna": {"mode": "required", "status": "DECIDED", "units": []}},
                            "gate": {"passed": True},
                            "runtime": {"status": "COMPLETED", "passed": True,
                                        "cases": [{"id": "probe", "passed": True, "violations": []}]}}
                if path.endswith("/artifacts/public/health.json"):
                    return {"status": "ok", "verified": True, "commit": "a" * 40}
                if path.endswith("/artifacts/attestation.statement.json"):
                    return {"statement": True}
                if path.endswith("/artifacts/attestation.bundle.json"):
                    return {"bundle": True}
                if method != "GET":
                    raise AssertionError("Review or failed validation must never mutate GitLab")
                return {"source_project_id": 42, "target_project_id": 42, "target_branch": "release",
                        "source_branch": "security/repair-1", "state": "opened", "sha": "a" * 40,
                        "diff_refs": {"base_sha": "b" * 40, "head_sha": "a" * 40},
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
        with patch("unspool.attestation.verify", return_value={}):
            result = complete(42, 1, api=api, config=config)
        self.assertEqual(result["status"], "READY_FOR_REVIEW")
        self.assertEqual(result["sha"], "a" * 40)
        self.assertTrue(all(method == "GET" for method, _ in calls))
        api, calls = self.api(contract=b"changed contract")
        with patch("unspool.attestation.verify", return_value={}), self.assertRaises(ValueError):
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
            if "/branches/release" in path:
                return {"protected": True, "commit": {"id": "c" * 40}}
            return original(method, path, body)

        api.request = changed_target
        with patch("unspool.attestation.verify", return_value={}), self.assertRaisesRegex(ValueError, "Target branch changed"):
            complete(42, 1, api=api, config=config)
        self.assertTrue(all(method == "GET" for method, _ in calls))

    def test_review_and_auto_refuse_changes_during_evidence_checks(self):
        changes = ("source", "pipeline", "pipeline_status", "base", "target", "closed", "missing_base")
        for mode, change in ((mode, change) for mode in ("review", "auto") for change in changes):
            with self.subTest(mode=mode, change=change):
                config = replace(self.load(self.data()), mode=mode)
                api, calls = self.api()
                original = api.request
                observed_evidence = False

                def changed(method, path, body=None):
                    nonlocal observed_evidence
                    result = original(method, path, body)
                    if path.endswith("/artifacts/public/health.json"):
                        observed_evidence = True
                    if observed_evidence and path == "projects/42/merge_requests/1":
                        if change == "source":
                            result["sha"] = "c" * 40
                        elif change == "pipeline":
                            result["head_pipeline"]["id"] = 9
                        elif change == "pipeline_status":
                            result["head_pipeline"]["status"] = "running"
                        elif change == "base":
                            result["diff_refs"]["base_sha"] = "c" * 40
                        elif change == "closed":
                            result["state"] = "closed"
                        elif change == "missing_base":
                            result.pop("diff_refs")
                    if observed_evidence and "/branches/release" in path and change == "target":
                        result["commit"]["id"] = "c" * 40
                    return result

                api.request = changed
                with patch("unspool.attestation.verify", return_value={}), self.assertRaises(ValueError):
                    complete(42, 1, api=api, config=config)
                self.assertTrue(observed_evidence)
                self.assertTrue(all(method == "GET" for method, _ in calls))

    def test_auto_refuses_protection_removed_after_preflight(self):
        config = replace(self.load(self.data()), mode="auto")
        api, calls = self.api()
        original = api.request
        branch_reads = 0

        def unprotected(method, path, body=None):
            nonlocal branch_reads
            result = original(method, path, body)
            if "/branches/release" in path:
                branch_reads += 1
                result["protected"] = branch_reads == 1
            return result

        api.request = unprotected
        with patch("unspool.attestation.verify", return_value={}), self.assertRaisesRegex(ValueError, "protected target"):
            complete(42, 1, api=api, config=config)
        self.assertEqual(branch_reads, 2)
        self.assertTrue(all(method == "GET" for method, _ in calls))


class ReviewMergeAndProfileTest(unittest.TestCase):
    def merged_api(self):
        api, calls = ConfigTest().api()
        original = api.request

        def request(method, path, body=None):
            value = original(method, path, body)
            if path == "projects/42/merge_requests/1" and isinstance(value, dict):
                value = dict(value, state="merged")
            return value

        api.request = request
        return api, calls

    def test_a_person_merging_in_review_mode_is_reported_not_treated_as_an_error(self):
        fixture = ConfigTest()
        config = fixture.load(fixture.data())
        self.assertEqual(config.verification_profile, "unspool_closed_loop")

        class Journal:
            def __init__(self, data):
                self.data = data
                self.saved = []

            def save(self, state, **values):
                self.saved.append(state)
                self.data.update(values, state=state)

            def check_stop(self):
                pass

        api, calls = self.merged_api()
        reviewed = Journal({"merge_request": 1, "source_sha": "a" * 40})
        with patch("unspool.handoff.JournalAPI", lambda inner, journal: inner):
            self.assertEqual(complete(42, 1, api=api, config=config, journal=reviewed)["status"], "MERGED_AFTER_REVIEW")
            other = Journal({"merge_request": 1, "source_sha": "f" * 40})
            self.assertEqual(complete(42, 1, api=api, config=config, journal=other)["status"], "ALREADY_MERGED")
        self.assertEqual(complete(42, 1, api=api, config=config)["status"], "ALREADY_MERGED")
        self.assertTrue(all(method == "GET" for method, _ in calls))
