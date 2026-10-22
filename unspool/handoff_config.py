"""Operator-owned configuration for GitLab.com handoffs; never load issue content."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from urllib.parse import quote


def repository_path(value):
    if (not isinstance(value, str) or not value or "\\" in value
            or any(c in value for c in "\x00\r\n:*?[]")
            or value.startswith("/") or str(PurePosixPath(value)) != value
            or any(part in {".", "..", ".git"} for part in value.split("/"))):
        raise ValueError("Use exact normalized repository-relative paths")
    return value


def _strings(value, name, *, empty=False, maximum=32):
    if (not isinstance(value, list) or (not value and not empty) or len(value) > maximum
            or any(not isinstance(item, str) or not item.strip() or len(item) > 200
                   or any(c in item for c in "\x00\r\n") for item in value)
            or len(set(value)) != len(value)):
        raise ValueError(f"{name} must be a list of distinct nonempty strings")
    return tuple(value)


@dataclass(frozen=True)
class HandoffConfig:
    project_id: int
    project_path: str
    target_branch: str
    branch_prefix: str
    trigger_username: str
    allowed_paths: tuple[str, ...]
    verification_jobs: tuple[str, ...]
    deployment_jobs: tuple[str, ...]
    evidence_job: str
    evidence_path: str
    health_path: str
    protected_files: tuple[tuple[str, str], ...]
    mode: str = "review"
    timeout: int = 1200
    poll_interval: int = 10
    version: int = 1
    http_contract: tuple = ()
    attestation_job: str = "sign-evidence"
    attestation_statement_path: str = "attestation.statement.json"
    attestation_bundle_path: str = "attestation.bundle.json"
    attestation_verify_job: str = "verify-attestation"

    @property
    def verification_profile(self):
        """External apps are verified by their pinned HTTP contract; Unspool-owned flows by Luna-decided,
        base/head-bound and signed evidence."""
        return "external_http_contract" if self.http_contract else "unspool_closed_loop"

    @property
    def digest(self):
        value = asdict(self)
        if not self.http_contract:
            value.pop("http_contract")
        # Optional fields left at their defaults must not change existing journal identities.
        for name in ("attestation_job", "attestation_statement_path", "attestation_bundle_path",
                     "attestation_verify_job"):
            if value[name] == type(self).__dataclass_fields__[name].default:
                value.pop(name)
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    @classmethod
    def load(cls, path):
        path = Path(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o022 or info.st_nlink != 1):
                raise ValueError("Operator configuration must be an owned regular file without shared writes or links")
            if info.st_size > 65536:
                raise ValueError("Operator configuration is unexpectedly large")
        except BaseException:
            os.close(fd)
            raise
        with os.fdopen(fd) as source:
            text = source.read(65537)
            if len(text) > 65536:
                raise ValueError("Operator configuration is unexpectedly large")

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"Duplicate configuration key: {key}")
                result[key] = value
            return result

        data = json.loads(text, object_pairs_hook=unique)
        if not isinstance(data, dict):
            raise ValueError("Configuration must be a JSON object")
        allowed = set(cls.__dataclass_fields__)
        required = allowed - {"mode", "timeout", "poll_interval", "http_contract", "attestation_job",
                             "attestation_statement_path", "attestation_bundle_path", "attestation_verify_job"}
        if set(data) - allowed or required - set(data):
            raise ValueError("Configuration has missing or unknown fields")
        if type(data["version"]) is not int or data["version"] != 1:
            raise ValueError("Unsupported configuration version")
        if type(data["project_id"]) is not int or data["project_id"] <= 0:
            raise ValueError("project_id must be a positive integer")
        if not isinstance(data["project_path"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+", data["project_path"]):
            raise ValueError("project_path must identify one GitLab.com namespace/project")
        for name in ("target_branch", "branch_prefix"):
            value = data[name]
            if (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]*", value)
                    or ".." in value or "//" in value or value.endswith(".lock")):
                raise ValueError(f"Invalid {name}")
        if not data["branch_prefix"].endswith("/") or data["target_branch"].endswith("/"):
            raise ValueError("branch_prefix must end in / and target_branch must not")
        if not isinstance(data["trigger_username"], str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", data["trigger_username"]):
            raise ValueError("Invalid trigger username")
        data["allowed_paths"] = _strings(data["allowed_paths"], "allowed_paths")
        for value in data["allowed_paths"]:
            repository_path(value)
            parts = value.lower().split("/")
            if (not value.endswith(".py") or parts[-1] in {"setup.py", "conftest.py"}
                    or any(part.startswith(".") or part in {"tests", "test", "deploy", "unspool"}
                           or part.startswith("test_") for part in parts)):
                raise ValueError("Only existing Python application files may be allowlisted")
        for name in ("verification_jobs", "deployment_jobs"):
            data[name] = _strings(data[name], name, empty=name == "deployment_jobs")
        if data["evidence_job"] not in data["verification_jobs"]:
            raise ValueError("evidence_job must be a mandatory verification job")
        for name in ("evidence_path", "health_path"):
            repository_path(data[name])
        for name, default in (("attestation_statement_path", "attestation.statement.json"),
                              ("attestation_bundle_path", "attestation.bundle.json")):
            repository_path(data.get(name, default))
        for name, default in (("attestation_job", "sign-evidence"),
                              ("attestation_verify_job", "verify-attestation")):
            value = data.get(name, default)
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", value):
                raise ValueError(f"Invalid {name}")
        if data.get("attestation_job", "sign-evidence") == data.get("attestation_verify_job", "verify-attestation"):
            raise ValueError("Evidence signing and verification must be separate mandatory jobs")
        if data.get("evidence_job") in {data.get("attestation_job", "sign-evidence"),
                                         data.get("attestation_verify_job", "verify-attestation")}:
            raise ValueError("Evidence collection, signing, and verification must use separate jobs")
        pins = data["protected_files"]
        if not isinstance(pins, dict) or len(pins) > 32:
            raise ValueError("protected_files must map repository paths to SHA-256 digests")
        for file, digest in pins.items():
            repository_path(file)
            if file in data["allowed_paths"] or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("Protected contracts must be immutable and have SHA-256 pins")
        data["protected_files"] = tuple(sorted(pins.items()))
        if "http_contract" in data:
            contract = data["http_contract"]
            if (not isinstance(contract, dict)
                    or set(contract) != {"plan_sha256", "probe_sha256", "probe_image_id", "case_ids",
                                         "application_image_id", "host_filter_image_id"}
                    or any(not isinstance(contract[name], str) or not re.fullmatch(r"[0-9a-f]{64}", contract[name])
                           for name in ("plan_sha256", "probe_sha256"))
                    or any(not isinstance(contract[name], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", contract[name])
                           for name in ("probe_image_id", "application_image_id", "host_filter_image_id"))):
                raise ValueError("HTTP contract requires exact plan/probe/image pins and case IDs")
            contract["case_ids"] = _strings(contract["case_ids"], "HTTP case IDs", maximum=64)
            data["http_contract"] = tuple(sorted(contract.items()))
        if not isinstance(data.get("mode", "review"), str) or data.get("mode", "review") not in {"review", "auto"}:
            raise ValueError("mode must be review or auto")
        for name, default, minimum, maximum in (("timeout", 1200, 1, 3600), ("poll_interval", 10, 1, 60)):
            value = data.get(name, default)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"{name} must be between {minimum} and {maximum}")
        if data.get("mode") == "auto" and (len(pins) < 2 or not data["deployment_jobs"]):
            raise ValueError("Automatic promotion requires pinned verification contracts and deployment jobs")
        return cls(**data)


def verify_contracts(config, api, sha):
    for path, digest in config.protected_files:
        file = api.request("GET", f"projects/{config.project_id}/repository/files/{quote(path, safe='')}?ref={quote(sha, safe='')}")
        if (file.get("encoding") != "base64" or hashlib.sha256(base64.b64decode(file["content"], validate=True)).hexdigest() != digest):
            raise ValueError("A verification contract differs from the operator's pinned content")


def preflight(config, api):
    """Read-only identity and branch checks; does not prove merge authorization."""
    project = api.request("GET", f"projects/{config.project_id}")
    if project.get("id") != config.project_id or project.get("path_with_namespace") != config.project_path:
        raise ValueError("Configured project ID and path do not match GitLab")
    branch = api.request("GET", f"projects/{config.project_id}/repository/branches/{quote(config.target_branch, safe='')}")
    if config.mode == "auto" and (branch.get("protected") is not True or project.get("merge_method") != "ff"):
        raise ValueError("Automatic promotion requires a protected fast-forward-only target; use review mode otherwise")
    sha = branch["commit"]["id"]
    for path in config.allowed_paths:
        api.request("GET", f"projects/{config.project_id}/repository/files/{quote(path, safe='')}?ref={quote(sha, safe='')}")
    verify_contracts(config, api, sha)
    return {"status": "PREFLIGHT_PASSED", "project": config.project_path,
            "project_id": config.project_id, "target_branch": config.target_branch,
            "mode": config.mode, "configuration_sha256": config.digest,
            "verification_profile": config.verification_profile,
            "target_sha": sha,
            "limitations": ["Runner isolation, trigger availability, CI contracts and deployment permissions require separate execution evidence"]}
