import unittest
from unittest.mock import patch

from unspool.handoff import complete, from_issue, validate_delivery_pipeline, validate_pipeline, validate_scope
from unspool.smoke import check


class HandoffTest(unittest.TestCase):
    def mr(self):
        return {"source_project_id": 1, "target_project_id": 1, "target_branch": "main",
                "source_branch": "unspool/repair-1", "state": "opened", "sha": "a" * 40,
                "diff_refs": {"base_sha": "b" * 40, "head_sha": "a" * 40},
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
        jobs = [{"name": name, "status": "success"} for name in
                ("python-tests", "dashboard-tests", "verify-exposure")]
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

    def test_delivery_requires_main_signature_and_attestation(self):
        pipeline = {"sha": "b" * 40, "status": "success", "ref": "main"}
        jobs = [{"name": name, "status": "success"} for name in
                ("verify-exposure", "sign-evidence", "verify-attestation", "deploy-pages",
                 "production-smoke", "deploy-cloud-run")]
        validate_delivery_pipeline(pipeline, jobs, "b" * 40)
        jobs[1]["status"] = "skipped"
        with self.assertRaises(ValueError):
            validate_delivery_pipeline(pipeline, jobs, "b" * 40)

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
        with patch("unspool.smoke.build_opener") as build:
            request = build.return_value.open
            request.return_value.__enter__.return_value.read.return_value = (
                '{"status":"ok","commit":"' + "b" * 40 + '","verified":true}').encode()
            with self.assertRaises(SystemExit):
                check("https://example.invalid", "a" * 40, attempts=1)
            request.assert_called_once()

    def test_verified_repair_merges_exact_sha_and_waits_for_delivery(self):
        mr, changes, calls = self.mr(), self.changes(), []
        merged = dict(mr, state="merged", merge_commit_sha="b" * 40)
        luna = {"mode": "required", "status": "DECIDED", "units": [], "flagged": [], "dismissed": []}
        evidence = {"base_sha": "b" * 40, "head_sha": "a" * 40,
                    "policy": {"base_sha256": "c" * 64, "head_sha256": "c" * 64},
                    "decision": {"luna": luna}, "gate": {"passed": True},
                    "runtime": {"status": "COMPLETED", "passed": True,
                                "cases": [{"id": "probe", "passed": True, "violations": []}]}}
        delivered_evidence = dict(evidence, base_sha="c" * 40, head_sha="b" * 40)

        class API:
            include_cloud = True
            health_verified = True

            def request(self, method, path, body=None):
                calls.append((method, path, body))
                if path.endswith("/changes"):
                    return changes
                if path == "projects/1":
                    return {"id": 1, "path_with_namespace": "group/project"}
                if "/repository/branches/" in path:
                    if path.endswith("/main"):
                        return {"protected": True, "commit": {"id": "b" * 40}}
                    return {"protected": False, "commit": {"id": "a" * 40}}
                if method == "PUT":
                    return merged
                if path.endswith("/artifacts/evidence.json"):
                    return delivered_evidence if "/jobs/1/" in path else evidence
                if path.endswith("/artifacts/public/health.json"):
                    commit = "b" * 40 if "/jobs/1/" in path else "a" * 40
                    return {"status": "ok", "commit": commit, "verified": self.health_verified}
                if path.endswith("/artifacts/attestation.statement.json"):
                    return {"statement": True}
                if path.endswith("/artifacts/attestation.bundle.json"):
                    return {"bundle": True}
                if "/pipelines?" in path:
                    return [{"id": 3, "source": "push", "ref": "main", "sha": "b" * 40,
                             "status": "success", "web_url": "https://gitlab.com/pipeline/3"}]
                if "/pipelines/" in path:
                    names = (("verify-exposure", "sign-evidence", "verify-attestation", "deploy-pages",
                              "production-smoke", "deploy-cloud-run") if "/3/" in path else
                             ("python-tests", "dashboard-tests", "verify-exposure"))
                    if not self.include_cloud:
                        names = tuple(name for name in names if name != "deploy-cloud-run")
                    return [{"id": index + 1, "name": name, "status": "success"} for index, name in enumerate(names)]
                if "/notes" in path:
                    return []
                return mr

        with patch("unspool.attestation.verify", return_value={}):
            result = complete(1, 1, api=API(), interval=0)
        self.assertEqual(result["status"], "DEPLOYED_AND_VERIFIED")
        self.assertEqual(next(body for method, _, body in calls if method == "PUT"), {"sha": "a" * 40})
        self.assertTrue(any(method == "POST" and "/notes" in path for method, path, _ in calls))
        self.assertTrue(any("/bridges?" in path for _, path, _ in calls))
        missing_cloud = API()
        missing_cloud.include_cloud = False
        with patch("unspool.attestation.verify", return_value={}):
            with self.assertRaises(ValueError):
                complete(1, 1, api=missing_cloud, interval=0)
            for value in (1, "true", None, False):
                calls.clear()
                forged = API()
                forged.health_verified = value
                with self.assertRaises(ValueError):
                    complete(1, 1, api=forged, interval=0)
                self.assertFalse(any(method == "PUT" for method, _, _ in calls))

    def test_issue_retry_reuses_the_existing_mr_without_retriggering_duo(self):
        calls = []
        mr = self.mr()

        class API:
            def request(self, method, path, body=None):
                calls.append(method)
                if path == "projects/1/issues/1":
                    return {"iid": 1, "description": "Plain issue without an Unspool finding block"}
                if path == "projects/1/merge_requests/2":
                    return mr
                return [{"iid": 2, "state": "opened"}]

        with patch("unspool.handoff.complete", return_value={"status": "verified"}) as finish:
            self.assertEqual(from_issue(1, 1, api=API())["status"], "verified")
            self.assertEqual(finish.call_args.args, (1, 2))
            self.assertNotIn("issue_binding", finish.call_args.kwargs)
        self.assertEqual(calls, ["GET", "GET", "GET"])

    def blocked_api(self, revisions):
        """A repair MR whose exposure job blocks each revision in turn until the list runs out."""
        test, posted, state = self, [], {"index": 0, "notes": []}

        class API:
            def request(self, method, path, body=None):
                if path == "projects/1/issues/1":
                    return {"iid": 1, "description": "Plain issue"}
                if path.startswith("projects/1/issues/1/notes"):
                    if method == "POST":
                        posted.append(body["body"])
                        state["notes"].append(body)
                        state["index"] = min(state["index"] + 1, len(revisions) - 1)  # Duo pushes the next revision
                        return {"id": len(posted)}
                    return state["notes"]
                sha, blocked = revisions[state["index"]]
                if path == "projects/1/merge_requests/2":
                    mr = test.mr()
                    mr.update(sha=sha, head_pipeline={"id": 10 + state["index"], "sha": sha,
                                                      "status": "failed" if blocked else "success"})
                    return mr
                if "/pipelines/" in path:
                    return [{"id": 7, "name": "verify-exposure", "status": "failed" if blocked else "success"}]
                if path.endswith("/artifacts/head-evidence.json"):
                    return {"gate": {"reasons": ["Configured probes for non-clear Luna boundaries are incomplete or failed"]},
                            "runtime": {"cases": [{"id": "csv-import-row-probe", "violations": [
                                {"sink": "HTTP_RESPONSE", "symbol": "customer.password_hash"}]}]}}
                return [{"iid": 2, "state": "opened"}]

        return API(), posted

    def test_a_blocked_repair_mr_is_handed_back_to_duo_with_the_evidence(self):
        api, posted = self.blocked_api([("a" * 40, True), ("c" * 40, False)])
        with patch("unspool.handoff.complete", return_value={"status": "READY_FOR_REVIEW"}) as finish:
            self.assertEqual(from_issue(1, 1, api=api, interval=0)["status"], "READY_FOR_REVIEW")
        self.assertEqual(finish.call_args.args, (1, 2))
        self.assertEqual(len(posted), 1)
        self.assertIn("@duo-developer-gitlab-ai-hackathon", posted[0])
        self.assertIn("probe `csv-import-row-probe` observed `customer.password_hash` at HTTP_RESPONSE", posted[0])
        self.assertIn("do not open a new MR", posted[0])
        self.assertIn("<!-- unspool-repair:" + "a" * 40 + " -->", posted[0])

    def test_repeated_blocks_are_bounded_and_never_double_posted(self):
        api, posted = self.blocked_api([("a" * 40, True), ("c" * 40, True), ("d" * 40, True)])
        with patch("unspool.handoff.complete") as finish:
            with self.assertRaises(ValueError):
                from_issue(1, 1, api=api, interval=0)
        finish.assert_not_called()
        self.assertEqual(len(posted), 2)
        self.assertEqual(len({body.rsplit("unspool-repair:", 1)[1] for body in posted}), 2)
