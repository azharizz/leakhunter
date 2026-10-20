"""Complete a bounded demo repair through GitLab verification and deployment."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
from urllib.parse import quote

from unspool.handoff_config import HandoffConfig, preflight, verify_contracts
from unspool.handoff_state import HandoffCanceled, JournalAPI, RunJournal, trigger_issue
from unspool.smoke import NoRedirect


REQUIRED_JOBS = {"python-tests", "dashboard-tests", "verify-exposure"}
ALLOWED_PATH = "demo/target/service.py"


class GitLabError(RuntimeError):
    def __init__(self, method, status=None, transient=False):
        self.transient = transient
        super().__init__(f"GitLab {method} request failed" + (f": HTTP {status}" if status else "; check connectivity and authentication"))


class GitLab:
    def __init__(self, journal=None):
        self.journal = journal

    def request(self, method, path, body=None):
        for attempt in range(3):
            if self.journal:
                self.journal.check_stop()
            try:
                return self._request(method, path, body)
            except GitLabError as error:
                if method != "GET" or not error.transient or attempt == 2:
                    raise
                time.sleep(2 ** attempt)

    def _request(self, method, path, body=None):
        token = os.environ.get("GITLAB_TOKEN")
        if token:
            data = json.dumps(body).encode() if body is not None else None
            request = Request("https://gitlab.com/api/v4/" + path, data=data, method=method,
                              headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
            try:
                with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=30) as response:
                    raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise ValueError("GitLab JSON response exceeded the controller limit")
                return json.loads(raw)
            except HTTPError as error:
                raise GitLabError(method, error.code, error.code == 429 or error.code >= 500) from None
            except (URLError, TimeoutError):
                raise GitLabError(method, transient=True) from None
        command = ["glab", "api", "--hostname", "gitlab.com", "-X", method, path]
        if body is not None:
            command += ["-H", "Content-Type: application/json", "--input", "-"]
        try:
            result = subprocess.run(command, input=json.dumps(body) if body is not None else None,
                                    capture_output=True, text=True, timeout=45)
        except subprocess.TimeoutExpired:
            raise GitLabError(method, transient=True) from None
        if result.returncode:
            match = re.search(r"HTTP (\d{3})", result.stderr)
            status = int(match[1]) if match else None
            raise GitLabError(method, status, status == 429 or (status is not None and status >= 500))
        return json.loads(result.stdout)


def validate_scope(mr, changes, project, config=None):
    if mr.get("source_project_id") != project or mr.get("target_project_id") != project:
        raise ValueError("Cross-project repairs cannot be promoted")
    target = config.target_branch if config else "main"
    branch_prefix = config.branch_prefix if config else "unspool/"
    if mr.get("target_branch") != target or not mr.get("source_branch", "").startswith(branch_prefix):
        raise ValueError("Only Unspool demo repair branches targeting main can be promoted")
    if mr.get("draft") or mr.get("state") not in {"opened", "merged"}:
        raise ValueError("The repair MR is draft or closed")
    items = changes.get("changes", [])
    allowed = set(config.allowed_paths if config else (ALLOWED_PATH,))
    if changes.get("overflow") is not False or not 0 < len(items) <= len(allowed):
        raise ValueError("The complete allowlisted repair diff is required")
    if config and changes.get("sha") != mr.get("sha"):
        raise ValueError("The diff and MR refer to different revisions; retry observation")
    for change in items:
        if (change.get("old_path") not in allowed or change.get("new_path") != change.get("old_path")
                or any(change.get(flag) for flag in ("deleted_file", "new_file", "renamed_file"))):
            raise ValueError("Repair may only update allowlisted application files; policy, tests, CI and tooling are locked")


def validate_pipeline(pipeline, jobs, sha, config=None):
    if pipeline.get("sha") != sha or pipeline.get("status") != "success":
        raise ValueError("The exact repair revision has not passed CI")
    passed = {job["name"] for job in jobs if job.get("status") == "success" and not job.get("allow_failure")}
    if not set(config.verification_jobs if config else REQUIRED_JOBS) <= passed:
        raise ValueError("All mandatory verification jobs must pass, not skip or allow failure")


def complete(project, iid, *, api=None, timeout=1200, interval=10, config=None, journal=None):
    api = api or GitLab(journal)
    if journal:
        api = JournalAPI(api, journal)
    if config:
        if project != config.project_id:
            raise ValueError("Project does not match the operator configuration")
        preflight(config, api)
    prefix = f"projects/{project}"
    mr_path = f"{prefix}/merge_requests/{iid}"
    deadline = time.monotonic() + timeout
    if journal:
        journal.save("VERIFYING", merge_request=iid)
    while True:
        mr = api.request("GET", mr_path)
        changes = api.request("GET", mr_path + "/changes")
        validate_scope(mr, changes, project, config)
        if mr["state"] == "merged":
            if config and config.mode == "review":
                if journal:
                    journal.save("ALREADY_MERGED")
                return {"status": "ALREADY_MERGED", "merge_request": iid,
                        "configuration_sha256": config.digest}
            break
        pipeline = mr.get("head_pipeline") or {}
        if pipeline.get("status") in {"failed", "canceled", "skipped", "manual"}:
            raise ValueError("Repair verification failed or requires intervention; promotion stopped")
        if pipeline.get("status") == "success":
            jobs = api.request("GET", f"{prefix}/pipelines/{pipeline['id']}/jobs?per_page=100")
            validate_pipeline(pipeline, jobs, mr["sha"], config)
            evidence_job = next(job for job in jobs if job["name"] == (config.evidence_job if config else "verify-exposure"))
            evidence_path = quote(config.evidence_path if config else "evidence.json", safe="/")
            health_path = quote(config.health_path if config else "public/health.json", safe="/")
            evidence = api.request("GET", f"{prefix}/jobs/{evidence_job['id']}/artifacts/{evidence_path}")
            health = api.request("GET", f"{prefix}/jobs/{evidence_job['id']}/artifacts/{health_path}")
            runtime = evidence.get("runtime", {})
            if (evidence.get("gate", {}).get("passed") is not True or runtime.get("status") != "COMPLETED"
                    or runtime.get("passed") is not True or not runtime.get("cases")
                    or any(case.get("passed") is not True for case in runtime["cases"])
                    or not isinstance(health, dict) or health.get("verified") is not True
                    or health != {"status": "ok", "commit": mr["sha"], "verified": True}):
                raise ValueError("Independent exposure evidence is missing, failed, or for another revision")
            if config:
                verify_contracts(config, api, mr["sha"])
                if config.mode == "review":
                    if journal:
                        journal.save("READY_FOR_REVIEW", source_sha=mr["sha"], pipeline_id=pipeline["id"])
                    return {"status": "READY_FOR_REVIEW", "merge_request": iid, "sha": mr["sha"],
                            "configuration_sha256": config.digest, "pipeline_id": pipeline["id"]}
                branch = api.request("GET", f"{prefix}/repository/branches/{quote(config.target_branch, safe='')}")
                if branch["commit"]["id"] != mr.get("diff_refs", {}).get("base_sha"):
                    raise ValueError("Target branch changed; rebase and reverify before promotion")
            mr = api.request("PUT", mr_path + "/merge", {"sha": mr["sha"]})
            if mr.get("state") != "merged":
                raise RuntimeError("GitLab did not merge the verified revision")
            break
        if time.monotonic() >= deadline:
            raise TimeoutError("Timed out waiting for repair verification; no merge performed")
        time.sleep(interval)
    merged_sha = (mr.get("merge_commit_sha") or mr.get("squash_commit_sha")
                  or (mr.get("sha") if config and config.mode == "auto" else None))
    if not merged_sha:
        raise ValueError("GitLab did not return the merged revision")
    if journal:
        journal.save("DEPLOYING", merged_sha=merged_sha)
    while time.monotonic() < deadline:
        target = quote(config.target_branch if config else "main", safe="")
        pipelines = api.request("GET", f"{prefix}/pipelines?sha={merged_sha}&ref={target}&per_page=20")
        pipelines = [pipeline for pipeline in pipelines if pipeline.get("source") == "push"]
        if pipelines:
            deployed = pipelines[0]
            if deployed.get("status") in {"failed", "canceled", "skipped", "manual"}:
                raise RuntimeError("Merged revision failed delivery; inspect the production pipeline")
            if deployed.get("status") == "success":
                jobs = api.request("GET", f"{prefix}/pipelines/{deployed['id']}/jobs?per_page=100")
                jobs += api.request("GET", f"{prefix}/pipelines/{deployed['id']}/bridges?per_page=100")
                passed = {job["name"] for job in jobs if job.get("status") == "success" and not job.get("allow_failure")}
                required = set(config.deployment_jobs if config else ("deploy-pages", "production-smoke", "deploy-cloud-run"))
                if not required <= passed:
                    raise ValueError("The deployment and live revision smoke check must both pass")
                summary = f"Unspool completed the verified repair.\n\nMerged revision: `{merged_sha}`\n\nAll configured mandatory deployment and smoke-check jobs passed.\n\nPipeline: {deployed['web_url']}"
                notes = api.request("GET", mr_path + "/notes?per_page=100")
                if not any(note.get("body") == summary for note in notes):
                    api.request("POST", mr_path + "/notes", {"body": summary})
                if journal:
                    journal.save("DEPLOYED_AND_VERIFIED", pipeline_url=deployed["web_url"])
                return {"merged_sha": merged_sha, "pipeline_url": deployed["web_url"], "status": "DEPLOYED_AND_VERIFIED"}
        time.sleep(interval)
    raise TimeoutError("Merge completed, but production verification has not completed")


def from_issue(project, iid, *, api=None, timeout=1200, interval=10, config=None, journal=None):
    """Use local glab authentication to orchestrate Duo without expanding its token."""
    api = api or GitLab(journal)
    if journal:
        api = JournalAPI(api, journal)
    if config:
        if project != config.project_id:
            raise ValueError("Project does not match the operator configuration")
        preflight(config, api)
    branch = f"{config.branch_prefix if config else 'unspool/'}repair-{iid}"
    path = f"projects/{project}/merge_requests?source_branch={quote(branch, safe='')}&state=all&per_page=100"
    deadline = time.monotonic() + timeout
    requests = api.request("GET", path)
    if not requests:
        trigger = config.trigger_username if config else "duo-developer-gitlab-ai-hackathon"
        paths = ", ".join(config.allowed_paths if config else (ALLOWED_PATH,))
        body = (
            f"@{trigger} Implement this bounded issue following AGENTS.md. "
            f"Use {branch}, change only {paths}, run the independent checks, "
            "and open a non-draft MR. The authenticated local handoff controller handles promotion; "
            "do not merge through another route or change permissions.")
        if journal:
            trigger_issue(api, project, iid, body, journal)
            journal.save("WAITING_FOR_MR")
        else:
            api.request("POST", f"projects/{project}/issues/{iid}/notes", {"body": body})
    while True:
        usable = [mr for mr in requests if mr.get("state") in {"opened", "merged"}]
        if len(usable) > 1:
            raise ValueError("Multiple repair MRs exist; refuse ambiguous promotion")
        if usable:
            options = {"config": config} if config else {}
            if journal:
                options["journal"] = journal
            return complete(project, usable[0]["iid"], api=api,
                            timeout=max(0, deadline - time.monotonic()), interval=interval, **options)
        if requests:
            raise ValueError("The existing repair MR is closed; no duplicate created")
        if time.monotonic() >= deadline:
            raise TimeoutError("Duo did not produce a repair MR before the deadline")
        time.sleep(interval)
        requests = api.request("GET", path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=int)
    parser.add_argument("--config", help="Trusted operator-owned JSON configuration")
    parser.add_argument("--state-dir", type=Path, default=Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "unspool" / "handoff")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--preflight", action="store_true", help="Read-only project and configuration checks")
    target.add_argument("--merge-request", type=int)
    target.add_argument("--issue", type=int)
    args = parser.parse_args()
    config = HandoffConfig.load(args.config) if args.config else None
    if config and args.project is not None and args.project != config.project_id:
        parser.error("--project differs from --config")
    project = config.project_id if config else args.project
    if not config and (project != 87860005 or args.preflight):
        parser.error("Use --config for project portability and preflight; --project alone is the legacy synthetic demo")
    if args.preflight:
        print(json.dumps(preflight(config, GitLab())))
        return
    iid = args.issue if args.issue is not None else args.merge_request
    if iid <= 0:
        parser.error("Issue and merge request numbers must be positive")
    options = {"config": config, "timeout": config.timeout, "interval": config.poll_interval} if config else {}
    run = from_issue if args.issue is not None else complete
    intent = f"issue:{iid}" if args.issue is not None else f"mr:{iid}"
    try:
        with RunJournal(args.state_dir, project, config.target_branch if config else "main", intent,
                        config.digest if config else "legacy-synthetic-demo-v1") as journal:
            print(json.dumps(run(project, iid, journal=journal, **options)))
    except (HandoffCanceled, KeyboardInterrupt):
        print(json.dumps({"status": "CANCELED", "remote_work_may_continue": True}))
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
