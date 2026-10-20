import unittest
from unittest.mock import patch

from unspool.handoff import complete, from_issue, validate_pipeline, validate_scope
from unspool.smoke import check


class HandoffTest(unittest.TestCase):
    def mr(self):
        return {"source_project_id": 1, "target_project_id": 1, "target_branch": "main",
                "source_branch": "unspool/repair-1", "state": "opened", "sha": "a" * 40,
                "head_pipeline": {"id": 2, "sha": "a" * 40, "status": "success"}}

    def changes(self):
        return {"overflow": False, "changes": [{"old_path": "demo/target/service.py", "new_path": "demo/target/service.py"}]}

    def test_only_the_bounded_repair_can_be_promoted(self):
        validate_scope(self.mr(), self.changes(), 1)
        for changes in ({"overflow": True, "changes": self.changes()["changes"]},
                        {"overflow": False, "changes": [{"old_path": ".gitlab-ci.yml", "new_path": ".gitlab-ci.yml"}]}):
            with self.assertRaises(ValueError):
                validate_scope(self.mr(), changes, 1)
        other_project = self.mr()
        other_project["source_project_id"] = 2
        with self.assertRaises(ValueError):
            validate_scope(other_project, self.changes(), 1)

    def test_skipped_allowed_failure_and_stale_checks_do_not_pass(self):
        jobs = [{"name": name, "status": "success"} for name in ("python-tests", "dashboard-tests", "verify-exposure")]
        validate_pipeline(self.mr()["head_pipeline"], jobs, "a" * 40)
        for status in ("skipped", "failed"):
            jobs[-1]["status"] = status
            with self.assertRaises(ValueError):
                validate_pipeline(self.mr()["head_pipeline"], jobs, "a" * 40)
        jobs[-1].update(status="success", allow_failure=True)
        with self.assertRaises(ValueError):
            validate_pipeline(self.mr()["head_pipeline"], jobs, "a" * 40)
        with self.assertRaises(ValueError):
            validate_pipeline(self.mr()["head_pipeline"], jobs, "b" * 40)

    def test_failed_pipeline_never_calls_merge(self):
        mr = self.mr()
        mr["head_pipeline"]["status"] = "failed"
        calls = []
        changes = self.changes()

        class API:
            def request(self, method, path, body=None):
                calls.append(method)
                return changes if path.endswith("/changes") else mr

        with self.assertRaises(ValueError):
            complete(1, 1, api=API(), interval=0)
        self.assertNotIn("PUT", calls)

    def test_smoke_rejects_a_stale_deployment(self):
        with patch("unspool.smoke.urlopen") as request:
            request.return_value.__enter__.return_value.read.return_value = b'{"status":"ok","commit":"old","verified":true}'
            with self.assertRaises(SystemExit):
                check("https://example.invalid", "new", attempts=1)

    def test_verified_repair_merges_exact_sha_and_waits_for_delivery(self):
        mr, changes, calls = self.mr(), self.changes(), []
        merged = dict(mr, state="merged", merge_commit_sha="b" * 40)

        class API:
            def request(self, method, path, body=None):
                calls.append((method, path, body))
                if path.endswith("/changes"):
                    return changes
                if method == "PUT":
                    return merged
                if path.endswith("/artifacts/evidence.json"):
                    return {"gate": {"passed": True}, "runtime": {"status": "COMPLETED", "passed": True, "cases": [{"passed": True}]}}
                if path.endswith("/artifacts/public/health.json"):
                    return {"status": "ok", "commit": "a" * 40, "verified": True}
                if "/pipelines?" in path:
                    return [{"id": 3, "source": "push", "status": "success", "web_url": "https://gitlab.com/pipeline/3"}]
                if "/pipelines/" in path:
                    names = ("deploy-pages", "production-smoke", "deploy-cloud-run") if "/3/" in path else ("python-tests", "dashboard-tests", "verify-exposure")
                    return [{"id": 4, "name": name, "status": "success"} for name in names]
                if "/notes" in path:
                    return []
                return mr

        result = complete(1, 1, api=API(), interval=0)
        self.assertEqual(result["status"], "DEPLOYED_AND_VERIFIED")
        self.assertEqual(next(body for method, _, body in calls if method == "PUT"), {"sha": "a" * 40})
        self.assertTrue(any(method == "POST" and "/notes" in path for method, path, _ in calls))
        self.assertTrue(any("/bridges?" in path for _, path, _ in calls))

    def test_issue_retry_reuses_the_existing_mr_without_retriggering_duo(self):
        calls = []

        class API:
            def request(self, method, path, body=None):
                calls.append(method)
                return [{"iid": 2, "state": "opened"}]

        with patch("unspool.handoff.complete", return_value={"status": "verified"}) as finish:
            self.assertEqual(from_issue(1, 1, api=API())["status"], "verified")
            self.assertEqual(finish.call_args.args, (1, 2))
        self.assertEqual(calls, ["GET"])
