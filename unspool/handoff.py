"""Complete a bounded demo repair through GitLab verification and deployment."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import tempfile
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
from urllib.parse import quote

from unspool.handoff_config import HandoffConfig, preflight, verify_contracts
from unspool.http_evidence import validate_bound_evidence
from unspool.issue_binding import parse_issue_binding, validate_issue_evidence
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
    if (not isinstance(pipeline, dict) or pipeline.get("sha") != sha
            or pipeline.get("status") != "success" or not isinstance(jobs, list)):
        raise ValueError("The exact repair revision has not passed CI")
    passed = {job["name"] for job in jobs if isinstance(job, dict) and isinstance(job.get("name"), str)
              and job.get("status") == "success" and not job.get("allow_failure")}
    required = set(config.verification_jobs if config else REQUIRED_JOBS)
    if not required <= passed:
        raise ValueError("All mandatory verification jobs must pass, not skip or allow failure")


def _verify_attestation(api, project, project_path, branch_name, expected_sha, jobs, evidence, config, evidence_job):
    from unspool.attestation import verify

    if not isinstance(branch_name, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", branch_name):
        raise ValueError("The signing branch is not a valid Git ref")
    branch = api.request("GET", f"projects/{project}/repository/branches/{quote(branch_name, safe='')}")
    commit = branch.get("commit") if isinstance(branch, dict) else None
    if (not isinstance(commit, dict) or branch.get("protected") is not True
            or commit.get("id") != expected_sha):
        raise ValueError("Evidence must be signed by a protected branch at the exact delivery revision")
    attestation_job = config.attestation_job if config else "sign-evidence"
    job = next((item for item in jobs if item.get("name") == attestation_job and item.get("status") == "success"
                and not item.get("allow_failure")), None)
    if not job:
        raise ValueError("The required evidence-signing job did not pass")
    job_id = job.get("id")
    if type(job_id) is not int or job_id <= 0:
        raise ValueError("The evidence-signing job has no valid GitLab job ID")
    statement_path = config.attestation_statement_path if config else "attestation.statement.json"
    bundle_path = config.attestation_bundle_path if config else "attestation.bundle.json"
    evidence_job_id = evidence_job.get("id") if isinstance(evidence_job, dict) else None
    if type(evidence_job_id) is not int or evidence_job_id <= 0:
        raise ValueError("The exposure-evidence job has no valid statement artifact ID")
    statement_value = api.request("GET", f"projects/{project}/jobs/{evidence_job_id}/artifacts/{quote(statement_path, safe='/')}")
    bundle_value = api.request("GET", f"projects/{project}/jobs/{job_id}/artifacts/{quote(bundle_path, safe='/')}")
    if not isinstance(statement_value, dict) or not isinstance(bundle_value, dict):
        raise ValueError("Signed evidence artifacts are missing or malformed")
    expected_identity = f"https://gitlab.com/{project_path}//.gitlab-ci.yml@refs/heads/{branch_name}"
    with tempfile.TemporaryDirectory(prefix="unspool-attestation-") as directory:
        root = Path(directory)
        evidence_file, statement_file, bundle_file = (root / "evidence.json", root / "statement.json", root / "bundle.json")
        for path, value in ((evidence_file, evidence), (statement_file, statement_value), (bundle_file, bundle_value)):
            path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        verify(evidence_file, statement_file, bundle_file, expected_identity=expected_identity,
               expected_head_sha=expected_sha)
    return expected_identity


def validate_delivery_pipeline(pipeline, jobs, sha, config=None):
    if (not isinstance(pipeline, dict) or pipeline.get("sha") != sha
            or pipeline.get("status") != "success" or not isinstance(jobs, list)):
        raise ValueError("The exact merged revision has not passed its delivery pipeline")
    passed = {job["name"] for job in jobs if isinstance(job, dict) and isinstance(job.get("name"), str)
              and job.get("status") == "success" and not job.get("allow_failure")}
    required = set(config.deployment_jobs if config else
                   ("deploy-pages", "production-smoke", "deploy-cloud-run"))
    if not config or config.verification_profile == "unspool_closed_loop":
        required.update((config.evidence_job, config.attestation_job, config.attestation_verify_job) if config else
                        ("verify-exposure", "sign-evidence", "verify-attestation"))
    if not required <= passed:
        raise ValueError("Protected-main evidence signing, attestation, deployment, and smoke checks must pass")


def complete(project, iid, *, api=None, timeout=1200, interval=10, config=None, journal=None,
             issue_binding=None):
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
                reviewed = (journal is not None and journal.data.get("merge_request") == iid
                            and journal.data.get("source_sha") == mr.get("sha"))
                status = "MERGED_AFTER_REVIEW" if reviewed else "ALREADY_MERGED"
                if journal:
                    journal.save(status)
                return {"status": status, "merge_request": iid, "sha": mr.get("sha"),
                        "configuration_sha256": config.digest,
                        "verification_profile": config.verification_profile}
            if (not journal or journal.data.get("promotion_authorized_sha") != mr.get("sha")
                    or journal.data.get("merge_request") != iid):
                if not (config and config.mode == "review" and journal
                        and journal.data.get("merge_request") == iid
                        and journal.data.get("source_sha") == mr.get("sha")):
                    raise ValueError("MR was merged before this controller authorized its exact revision")
        pipeline = mr.get("head_pipeline") or {}
        if pipeline.get("status") in {"failed", "canceled", "skipped", "manual"}:
            raise ValueError("Repair verification failed or requires intervention; promotion stopped")
        if pipeline.get("status") == "success":
            jobs = api.request("GET", f"{prefix}/pipelines/{pipeline['id']}/jobs?per_page=100")
            validate_pipeline(pipeline, jobs, mr["sha"], config)
            evidence_job = next((job for job in jobs if isinstance(job, dict)
                                 and job.get("name") == (config.evidence_job if config else "verify-exposure")
                                 and job.get("status") == "success" and not job.get("allow_failure")), None)
            if not evidence_job or type(evidence_job.get("id")) is not int or evidence_job["id"] <= 0:
                raise ValueError("The required exposure-evidence job has no valid GitLab job ID")
            evidence_path = quote(config.evidence_path if config else "evidence.json", safe="/")
            health_path = quote(config.health_path if config else "public/health.json", safe="/")
            evidence = api.request("GET", f"{prefix}/jobs/{evidence_job['id']}/artifacts/{evidence_path}")
            health = api.request("GET", f"{prefix}/jobs/{evidence_job['id']}/artifacts/{health_path}")
            if not isinstance(evidence, dict):
                raise ValueError("Independent exposure evidence is missing or malformed")
            runtime = evidence.get("runtime")
            decision = evidence.get("decision")
            luna = decision.get("luna") if isinstance(decision, dict) else None
            diff_refs = mr.get("diff_refs")
            base_sha = diff_refs.get("base_sha") if isinstance(diff_refs, dict) else None
            diff_head_sha = diff_refs.get("head_sha") if isinstance(diff_refs, dict) else None
            project_record = api.request("GET", f"projects/{project}")
            if not isinstance(project_record, dict):
                raise ValueError("GitLab returned an unexpected project record")
            project_path = config.project_path if config else project_record.get("path_with_namespace")
            closed_loop = not config or config.verification_profile == "unspool_closed_loop"
            if issue_binding is not None and not closed_loop:
                raise ValueError("Issue-bound repairs require the Unspool closed-loop evidence profile")
            if (not isinstance(project_path, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+", project_path)
                    or not isinstance(base_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", base_sha)
                    or not isinstance(diff_head_sha, str) or diff_head_sha != mr.get("sha")):
                raise ValueError("The merge request does not identify exact base and head revisions")
            if closed_loop and (evidence.get("base_sha") != base_sha or evidence.get("head_sha") != mr.get("sha")
                                or not isinstance(luna, dict) or luna.get("mode") != "required"
                                or luna.get("status") != "DECIDED"):
                raise ValueError("Evidence must bind the exact MR revisions and complete required Luna decisions")
            gate = evidence.get("gate")
            if (not isinstance(runtime, dict) or not isinstance(gate, dict) or gate.get("passed") is not True
                    or runtime.get("status") != "COMPLETED"
                    or runtime.get("passed") is not True or not runtime.get("cases")
                    or any(not isinstance(case, dict) or case.get("passed") is not True or case.get("error")
                           or case.get("violations") for case in runtime["cases"])
                    or not isinstance(health, dict) or health.get("verified") is not True
                    or health != {"status": "ok", "commit": mr["sha"], "verified": True}):
                raise ValueError("Independent exposure evidence is missing, failed, or for another revision")
            # Signing runs on protected main after merge, before any deployment job.
            signer_identity = None
            if config:
                if config.http_contract:
                    validate_bound_evidence(evidence, mr["sha"], dict(config.http_contract))
                verify_contracts(config, api, mr["sha"])
            current = api.request("GET", mr_path)
            current_changes = api.request("GET", mr_path + "/changes")
            validate_scope(current, current_changes, project, config)
            current_pipeline = current.get("head_pipeline") or {}
            current_refs = current.get("diff_refs") if isinstance(current, dict) else None
            if (current.get("state") != mr.get("state") or current.get("sha") != mr.get("sha")
                    or not isinstance(current_refs, dict) or current_refs.get("base_sha") != base_sha
                    or current_refs.get("head_sha") != mr.get("sha")
                    or current_changes != changes
                    or any(current_pipeline.get(key) != pipeline.get(key) for key in ("id", "sha", "status"))):
                raise ValueError("Candidate or pipeline changed during verification; rerun before review or promotion")
            target_branch = config.target_branch if config else "main"
            branch = api.request("GET", f"{prefix}/repository/branches/{quote(target_branch, safe='')}")
            branch_commit = branch.get("commit") if isinstance(branch, dict) else None
            if not isinstance(branch_commit, dict):
                raise ValueError("GitLab returned an unexpected target-branch record")
            expected_target = base_sha
            if mr["state"] == "merged":
                expected_target = mr.get("merge_commit_sha") or mr.get("squash_commit_sha") or mr.get("sha")
            if branch_commit.get("id") != expected_target:
                raise ValueError("Target branch changed; rebase and reverify before review or promotion")
            if mr["state"] == "opened" and branch.get("protected") is not True:
                raise ValueError("Promotion requires a protected target branch")
            if issue_binding is not None:
                validate_issue_evidence(
                    evidence, issue_binding,
                    base_sha=base_sha,
                    allowed_paths=config.allowed_paths if config else (ALLOWED_PATH,),
                    head_sha=mr["sha"],
                )
            if mr["state"] == "merged":
                break
            if config and config.mode == "review":
                if journal:
                    journal.save("READY_FOR_REVIEW", source_sha=mr["sha"], pipeline_id=pipeline["id"])
                return {"status": "READY_FOR_REVIEW", "merge_request": iid, "sha": mr["sha"],
                        "configuration_sha256": config.digest, "pipeline_id": pipeline["id"],
                        "verification_profile": config.verification_profile,
                        "attestation_identity": signer_identity}
            if journal:
                journal.save("PROMOTION_AUTHORIZED", merge_request=iid, source_sha=mr["sha"],
                             promotion_authorized_sha=mr["sha"], pipeline_id=pipeline["id"])
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
                target_branch = config.target_branch if config else "main"
                if deployed.get("ref") != target_branch:
                    raise ValueError("Delivery pipeline did not run on the configured protected branch")
                validate_delivery_pipeline(deployed, jobs, merged_sha, config)
                if not config or config.verification_profile == "unspool_closed_loop":
                    evidence_job = next((job for job in jobs if isinstance(job, dict)
                                         and job.get("name") == (config.evidence_job if config else "verify-exposure")
                                         and job.get("status") == "success" and not job.get("allow_failure")), None)
                    if not evidence_job or type(evidence_job.get("id")) is not int or evidence_job["id"] <= 0:
                        raise ValueError("The protected-main evidence job has no valid artifact ID")
                    evidence_path = quote(config.evidence_path if config else "evidence.json", safe="/")
                    health_path = quote(config.health_path if config else "public/health.json", safe="/")
                    delivered_evidence = api.request("GET", f"{prefix}/jobs/{evidence_job['id']}/artifacts/{evidence_path}")
                    delivered_health = api.request("GET", f"{prefix}/jobs/{evidence_job['id']}/artifacts/{health_path}")
                    runtime = delivered_evidence.get("runtime") if isinstance(delivered_evidence, dict) else None
                    gate = delivered_evidence.get("gate") if isinstance(delivered_evidence, dict) else None
                    decision = delivered_evidence.get("decision") if isinstance(delivered_evidence, dict) else None
                    luna = decision.get("luna") if isinstance(decision, dict) else None
                    if (not isinstance(delivered_evidence, dict) or delivered_evidence.get("head_sha") != merged_sha
                            or (not config or config.verification_profile == "unspool_closed_loop")
                            and (not isinstance(luna, dict) or luna.get("mode") != "required"
                                 or luna.get("status") != "DECIDED")
                            or not isinstance(gate, dict) or gate.get("passed") is not True
                            or not isinstance(runtime, dict) or runtime.get("status") != "COMPLETED"
                            or runtime.get("passed") is not True or not runtime.get("cases")
                            or any(not isinstance(case, dict) or case.get("passed") is not True or case.get("error")
                                   or case.get("violations") for case in runtime["cases"])
                            or delivered_health != {"status": "ok", "commit": merged_sha, "verified": True}):
                        raise ValueError("Protected-main evidence or live health is missing, failed, or for another revision")
                    if not config or config.verification_profile == "unspool_closed_loop":
                        _verify_attestation(api, project, project_path, target_branch, merged_sha, jobs,
                                            delivered_evidence, config, evidence_job)
                summary = f"Unspool completed the verified repair.\n\nMerged revision: `{merged_sha}`\n\nAll configured mandatory deployment and smoke-check jobs passed.\n\nPipeline: {deployed['web_url']}"
                notes = api.request("GET", mr_path + "/notes?per_page=100")
                if not any(note.get("body") == summary for note in notes):
                    api.request("POST", mr_path + "/notes", {"body": summary})
                if journal:
                    journal.save("DEPLOYED_AND_VERIFIED", pipeline_url=deployed["web_url"])
                return {"merged_sha": merged_sha, "pipeline_url": deployed["web_url"], "status": "DEPLOYED_AND_VERIFIED"}
        time.sleep(interval)
    raise TimeoutError("Merge completed, but production verification has not completed")


REPAIR_ATTEMPTS = 2
_RUNNING = {"created", "waiting_for_resource", "preparing", "pending", "running", "scheduled"}


def blocked_by_evidence(api, project, mr, config=None):
    """Return the failed exposure-evidence job's head evidence when it alone decides the verdict, else None."""
    pipeline = mr.get("head_pipeline") or {}
    if pipeline.get("status") != "failed" or pipeline.get("sha") != mr.get("sha"):
        return None
    jobs = api.request("GET", f"projects/{project}/pipelines/{pipeline['id']}/jobs?per_page=100")
    name = config.evidence_job if config else "verify-exposure"
    job = next((item for item in jobs if isinstance(item, dict) and item.get("name") == name), None) \
        if isinstance(jobs, list) else None
    if not job or job.get("status") != "failed" or type(job.get("id")) is not int:
        return None
    try:
        evidence = api.request("GET", f"projects/{project}/jobs/{job['id']}/artifacts/head-evidence.json")
    except (GitLabError, ValueError):
        evidence = None
    return evidence if isinstance(evidence, dict) else {}


def verdict_summary(evidence):
    """The gate's reasons and observed violations, by symbol and sink; probe values are never included."""
    gate = evidence.get("gate") if isinstance(evidence.get("gate"), dict) else {}
    lines = [f"- {reason}" for reason in gate.get("reasons", []) if isinstance(reason, str)]
    runtime = evidence.get("runtime") if isinstance(evidence.get("runtime"), dict) else {}
    seen = sorted({f"- probe `{case.get('id')}` observed `{item.get('symbol')}` at {item.get('sink')}"
                   for case in runtime.get("cases", []) if isinstance(case, dict)
                   for item in case.get("violations") or [] if isinstance(item, dict)})
    return "\n".join(lines + seen) or "- the exposure-evidence job failed"


def repair_blocked(api, project, issue_iid, mr_iid, branch, *, config=None, journal=None, deadline, interval):
    """Hand a candidate blocked by exposure evidence back to Duo, on the same branch and MR, then wait."""
    requested = set(journal.data.get("repair_requested_shas", [])) if journal else set()
    attempts = 0
    while True:
        mr = api.request("GET", f"projects/{project}/merge_requests/{mr_iid}")
        if not isinstance(mr, dict):
            return
        pipeline = mr.get("head_pipeline") or {}
        sha = mr.get("sha")
        if pipeline.get("status") not in _RUNNING:
            evidence = blocked_by_evidence(api, project, mr, config)
            if evidence is None:
                return
            if sha not in requested:
                marker = f"<!-- unspool-repair:{sha} -->"
                notes = api.request("GET", f"projects/{project}/issues/{issue_iid}/notes?per_page=100")
                if not any(marker in note.get("body", "") for note in notes if isinstance(note, dict)):
                    if attempts >= REPAIR_ATTEMPTS:
                        raise ValueError(f"Still blocked by exposure evidence after {REPAIR_ATTEMPTS} repair requests")
                    trigger = config.trigger_username if config else "duo-developer-gitlab-ai-hackathon"
                    paths = ", ".join(config.allowed_paths if config else (ALLOWED_PATH,))
                    body = (f"@{trigger} The candidate on `{branch}` (MR !{mr_iid}, `{str(sha)[:12]}`) is blocked by "
                            f"Unspool's independent exposure gate:\n\n{verdict_summary(evidence)}\n\n"
                            f"Fix it on the existing branch `{branch}` so MR !{mr_iid} updates; do not open a new MR. "
                            f"Change only {paths}, keep the requested behaviour, follow AGENTS.md, and run the "
                            "independent checks. The authenticated local handoff controller re-verifies the new "
                            "revision and handles promotion.\n\n" + marker)
                    if journal:
                        journal.check_stop()
                    api.request("POST", f"projects/{project}/issues/{issue_iid}/notes", {"body": body})
                    attempts += 1
                requested.add(sha)
                if journal:
                    journal.save("REPAIR_REQUESTED", merge_request=mr_iid, repair_requested_shas=sorted(requested))
        if time.monotonic() >= deadline:
            raise TimeoutError("No new candidate revision was verified before the deadline")
        time.sleep(interval)


def from_issue(project, iid, *, api=None, timeout=1200, interval=10, config=None, journal=None):
    """Use local glab authentication to orchestrate Duo without expanding its token."""
    api = api or GitLab(journal)
    if journal:
        api = JournalAPI(api, journal)
    if config:
        if project != config.project_id:
            raise ValueError("Project does not match the operator configuration")
        preflight(config, api)
    issue = api.request("GET", f"projects/{project}/issues/{iid}")
    if not isinstance(issue, dict):
        raise ValueError("GitLab returned an unexpected issue record")
    # Issue text is data: a finding block can only add checks, never relax them.
    issue_binding = parse_issue_binding(issue.get("description") or "")
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
            if usable[0].get("state") == "opened":
                repair_blocked(api, project, iid, usable[0]["iid"], branch, config=config, journal=journal,
                               deadline=deadline, interval=interval)
            options = {"config": config} if config else {}
            if journal:
                options["journal"] = journal
            if issue_binding is not None:
                options["issue_binding"] = issue_binding
            return complete(project, usable[0]["iid"], api=api,
                            timeout=max(0, deadline - time.monotonic()), interval=interval, **options)
        if requests:
            raise ValueError("The existing repair MR is closed; no duplicate created")
        if time.monotonic() >= deadline:
            raise TimeoutError("Duo did not produce a repair MR before the deadline")
        time.sleep(interval)
        requests = api.request("GET", path)


def watch(project, label, start, *, api=None, interval=60, once=False):
    """Hands-off intake: start the issue workflow once for each open issue carrying ``label``, oldest first.

    Only project members can label issues, so the label is the operator's go-ahead. Yields (iid, result).
    """
    api = api or GitLab()
    started = set()
    while True:
        issues = api.request("GET", f"projects/{project}/issues?state=opened&labels={quote(label, safe='')}"
                                    "&order_by=created_at&sort=asc&per_page=100")
        for issue in issues if isinstance(issues, list) else []:
            iid = issue.get("iid") if isinstance(issue, dict) else None
            if type(iid) is int and iid > 0 and iid not in started:
                started.add(iid)
                yield iid, start(iid)
        if once:
            return
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=int)
    parser.add_argument("--config", help="Trusted operator-owned JSON configuration")
    parser.add_argument("--state-dir", type=Path, default=Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "unspool" / "handoff")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--preflight", action="store_true", help="Read-only project and configuration checks")
    target.add_argument("--merge-request", type=int)
    target.add_argument("--issue", type=int)
    target.add_argument("--watch", metavar="LABEL", help="Hands-off: run every open issue with this label")
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
    options = {"config": config, "timeout": config.timeout, "interval": config.poll_interval} if config else {}
    if args.watch:
        def start(issue):
            # One issue's failure stops that issue's workflow, never the intake; nothing it left is promoted.
            try:
                with RunJournal(args.state_dir, project, config.target_branch if config else "main",
                                f"issue:{issue}", config.digest if config else "legacy-synthetic-demo-v1") as journal:
                    return from_issue(project, issue, journal=journal, **options)
            except (HandoffCanceled, KeyboardInterrupt):
                raise
            except Exception as error:
                return {"status": "STOPPED", "reason": str(error)}
        try:
            for issue, result in watch(project, args.watch, start):
                print(json.dumps({"issue": issue, **result}), flush=True)
        except (HandoffCanceled, KeyboardInterrupt):
            print(json.dumps({"status": "CANCELED", "remote_work_may_continue": True}))
            raise SystemExit(130) from None
        return
    iid = args.issue if args.issue is not None else args.merge_request
    if iid <= 0:
        parser.error("Issue and merge request numbers must be positive")
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
