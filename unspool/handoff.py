"""Complete a bounded demo repair through GitLab verification and deployment."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


REQUIRED_JOBS = {"python-tests", "dashboard-tests", "verify-exposure"}
ALLOWED_PATH = "demo/target/service.py"


class GitLab:
    def request(self, method, path, body=None):
        token = os.environ.get("GITLAB_TOKEN")
        if token:
            data = json.dumps(body).encode() if body is not None else None
            request = Request("https://gitlab.com/api/v4/" + path, data=data, method=method,
                              headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
            try:
                with urlopen(request, timeout=30) as response:
                    return json.load(response)
            except HTTPError as error:
                raise RuntimeError(f"GitLab refused {method} {path}: HTTP {error.code}") from None
        command = ["glab", "api", "--hostname", "gitlab.com", "-X", method, path]
        if body is not None:
            command += ["-H", "Content-Type: application/json", "--input", "-"]
        result = subprocess.run(command, input=json.dumps(body) if body is not None else None,
                                capture_output=True, text=True, timeout=45)
        if result.returncode:
            raise RuntimeError(f"GitLab refused {method} {path}; check authentication and project permissions")
        return json.loads(result.stdout)


def validate_scope(mr, changes, project):
    if mr.get("source_project_id") != project or mr.get("target_project_id") != project:
        raise ValueError("Cross-project repairs cannot be promoted")
    if mr.get("target_branch") != "main" or not mr.get("source_branch", "").startswith("unspool/"):
        raise ValueError("Only Unspool demo repair branches targeting main can be promoted")
    if mr.get("draft") or mr.get("state") not in {"opened", "merged"}:
        raise ValueError("The repair MR is draft or closed")
    items = changes.get("changes", [])
    if changes.get("overflow") is not False or len(items) != 1:
        raise ValueError("The complete single-file repair diff is required")
    change = items[0]
    if (change.get("old_path") != ALLOWED_PATH or change.get("new_path") != ALLOWED_PATH
            or any(change.get(flag) for flag in ("deleted_file", "new_file", "renamed_file"))):
        raise ValueError("Repair may only update the existing synthetic service; policy, tests, CI and tooling are locked")


def validate_pipeline(pipeline, jobs, sha):
    if pipeline.get("sha") != sha or pipeline.get("status") != "success":
        raise ValueError("The exact repair revision has not passed CI")
    passed = {job["name"] for job in jobs if job.get("status") == "success" and not job.get("allow_failure")}
    if not REQUIRED_JOBS <= passed:
        raise ValueError("All mandatory verification jobs must pass, not skip or allow failure")


def complete(project, iid, *, api=None, timeout=1200, interval=10):
    api = api or GitLab()
    prefix = f"projects/{project}"
    mr_path = f"{prefix}/merge_requests/{iid}"
    deadline = time.monotonic() + timeout
    while True:
        mr = api.request("GET", mr_path)
        changes = api.request("GET", mr_path + "/changes")
        validate_scope(mr, changes, project)
        if mr["state"] == "merged":
            break
        pipeline = mr.get("head_pipeline") or {}
        if pipeline.get("status") in {"failed", "canceled", "skipped", "manual"}:
            raise ValueError("Repair verification failed or requires intervention; promotion stopped")
        if pipeline.get("status") == "success":
            jobs = api.request("GET", f"{prefix}/pipelines/{pipeline['id']}/jobs?per_page=100")
            validate_pipeline(pipeline, jobs, mr["sha"])
            evidence_job = next(job for job in jobs if job["name"] == "verify-exposure")
            evidence = api.request("GET", f"{prefix}/jobs/{evidence_job['id']}/artifacts/evidence.json")
            health = api.request("GET", f"{prefix}/jobs/{evidence_job['id']}/artifacts/public/health.json")
            runtime = evidence.get("runtime", {})
            if (evidence.get("gate", {}).get("passed") is not True or runtime.get("status") != "COMPLETED"
                    or runtime.get("passed") is not True or not runtime.get("cases")
                    or health != {"status": "ok", "commit": mr["sha"], "verified": True}):
                raise ValueError("Independent exposure evidence is missing, failed, or for another revision")
            mr = api.request("PUT", mr_path + "/merge", {"sha": mr["sha"]})
            if mr.get("state") != "merged":
                raise RuntimeError("GitLab did not merge the verified revision")
            break
        if time.monotonic() >= deadline:
            raise TimeoutError("Timed out waiting for repair verification; no merge performed")
        time.sleep(interval)
    merged_sha = mr.get("merge_commit_sha") or mr.get("squash_commit_sha")
    if not merged_sha:
        raise ValueError("GitLab did not return the merged revision")
    while time.monotonic() < deadline:
        pipelines = api.request("GET", f"{prefix}/pipelines?sha={merged_sha}&ref=main&per_page=20")
        pipelines = [pipeline for pipeline in pipelines if pipeline.get("source") == "push"]
        if pipelines:
            deployed = pipelines[0]
            if deployed.get("status") in {"failed", "canceled", "skipped", "manual"}:
                raise RuntimeError("Merged revision failed delivery; inspect the production pipeline")
            if deployed.get("status") == "success":
                jobs = api.request("GET", f"{prefix}/pipelines/{deployed['id']}/jobs?per_page=100")
                passed = {job["name"] for job in jobs if job.get("status") == "success"}
                if not {"deploy-pages", "production-smoke"} <= passed:
                    raise ValueError("The deployment and live revision smoke check must both pass")
                summary = f"Unspool completed the verified demo repair.\n\nMerged revision: `{merged_sha}`\n\nProduction deployment and exact-revision smoke check passed.\n\nPipeline: {deployed['web_url']}"
                notes = api.request("GET", mr_path + "/notes?per_page=100")
                if not any(note.get("body") == summary for note in notes):
                    api.request("POST", mr_path + "/notes", {"body": summary})
                return {"merged_sha": merged_sha, "pipeline_url": deployed["web_url"], "status": "DEPLOYED_AND_VERIFIED"}
        time.sleep(interval)
    raise TimeoutError("Merge completed, but production verification has not completed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=int, required=True)
    parser.add_argument("--merge-request", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(complete(args.project, args.merge_request)))
