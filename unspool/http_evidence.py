"""Bind an independently produced HTTP report in a trusted, pinned CI job."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from leakhunter.analyzers.sources import source_files
from unspool.http_acceptance import strict_json, validate


def validate_bound_evidence(evidence, source, contract):
    if (not isinstance(evidence, dict) or not isinstance(source, str)
            or not re.fullmatch(r"[0-9a-f]{40}", source)):
        raise ValueError("HTTP evidence requires an exact source commit")
    provenance = evidence.get("provenance", {})
    if not isinstance(provenance, dict) or provenance.get("kind") != "independent-http-acceptance-v1":
        raise ValueError("Independent HTTP provenance is required")
    if provenance.get("source_sha") != source:
        raise ValueError("HTTP evidence belongs to another source revision")
    for key in ("plan_sha256", "probe_sha256", "probe_image_id", "application_image_id", "host_filter_image_id"):
        if provenance.get(key) != contract[key]:
            raise ValueError("HTTP evidence does not match the operator contract")
    if provenance.get("host_isolation_verified") is not True:
        raise ValueError("HTTP host isolation verification is required")
    for key in ("application_image_id", "probe_image_id", "host_filter_image_id"):
        if not isinstance(provenance.get(key), str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", provenance[key]):
            raise ValueError("Exact HTTP image identities are required")
    for key in ("source_snapshot_sha256", "application_container_id", "probe_container_id"):
        if not isinstance(provenance.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", provenance[key]):
            raise ValueError("Exact snapshot and separate container identities are required")
    if provenance["application_container_id"] == provenance["probe_container_id"]:
        raise ValueError("Application and HTTP probe must use separate containers")
    runtime = evidence.get("runtime", {})
    if not isinstance(runtime, dict):
        raise ValueError("Invalid HTTP runtime evidence")
    cases = runtime.get("cases")
    gate = evidence.get("gate", {})
    if (not isinstance(gate, dict) or gate.get("passed") is not True
            or runtime.get("status") != "COMPLETED"
            or any(runtime.get(key) is not True for key in ("passed", "functional_passed", "security_passed"))
            or not isinstance(cases, list) or not cases
            or any(not isinstance(c, dict) for c in cases)
            or tuple(c.get("id") for c in cases) != tuple(contract["case_ids"])):
        raise ValueError("All configured HTTP cases must execute and pass")
    for case in cases:
        if (case.get("passed") is not True or case.get("security_passed") is not True
                or case.get("status") != "COMPLETED" or case.get("observations") != []
                or case.get("violations") != [] or "error_type" in case
                or type(case.get("http_status")) is not int or not 200 <= case["http_status"] <= 599
                or 300 <= case["http_status"] < 400):
            raise ValueError("HTTP case contains missing, failed or unsafe observations")


def bind(report, plan, source, *, probe_sha256, app_image, probe_image,
         snapshot_sha256, app_container, probe_container, filter_image, host_isolation_verified=False):
    validate(plan)
    if not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{40}", source):
        raise ValueError("Exact source commit is required")
    contract = {"plan_sha256": sha256(json.dumps(plan, allow_nan=False).encode()).hexdigest(),
                "probe_sha256": probe_sha256, "probe_image_id": probe_image,
                "application_image_id": app_image, "host_filter_image_id": filter_image,
                "case_ids": tuple(c["id"] for c in plan["cases"])}
    if (not isinstance(report, dict) or report.get("kind") != "external-json-http-acceptance"
            or report.get("plan_sha256") != contract["plan_sha256"]
            or not isinstance(report.get("marker_sha256"), list)
            or len(report["marker_sha256"]) != len(plan["markers"])
            or any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v) for v in report["marker_sha256"])):
        raise ValueError("HTTP report does not match the frozen plan")
    if not isinstance(probe_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", probe_sha256):
        raise ValueError("Exact probe module hash is required")
    # Project only known metadata; unknown target-provided fields never become artifacts.
    runtime = report.get("runtime", {})
    if not isinstance(runtime, dict) or not isinstance(report.get("gate"), dict):
        raise ValueError("Invalid HTTP report")
    cases = runtime.get("cases", [])
    if not isinstance(cases, list) or any(not isinstance(c, dict) for c in cases):
        raise ValueError("HTTP report has invalid cases")
    value = {"gate": {"passed": report.get("gate", {}).get("passed")},
             "runtime": {key: runtime.get(key) for key in ("status", "passed", "functional_passed", "security_passed")},
             "provenance": {"kind": "independent-http-acceptance-v1", "source_sha": source,
                            "plan_sha256": contract["plan_sha256"], "probe_sha256": probe_sha256,
                            "probe_image_id": probe_image, "application_image_id": app_image,
                            "host_filter_image_id": filter_image, "host_isolation_verified": host_isolation_verified,
                            "source_snapshot_sha256": snapshot_sha256,
                            "application_container_id": app_container, "probe_container_id": probe_container}}
    value["runtime"]["cases"] = [{key: c.get(key) for key in
                                    ("id", "passed", "status", "security_passed", "observations", "violations", "http_status")}
                                   for c in cases]
    if any("error_type" in c for c in cases):
        raise ValueError("HTTP report contains an execution error")
    validate_bound_evidence(value, source, contract)
    for case, expected in zip(value["runtime"]["cases"], plan["cases"]):
        if type(case["http_status"]) is not int or case["http_status"] != expected["status"]:
            raise ValueError("HTTP status differs from the configured contract")
    return value


def read_bytes(path, limit):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise ValueError("Evidence input must be a bounded regular file")
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Evidence input limit exceeded")
    return raw


def read_json(path, limit):
    return strict_json(read_bytes(path, limit))


def snapshot_digest(root):
    root = Path(root).resolve(strict=True)
    digest = sha256()
    for path, content in source_files(root, None, set()):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(sha256(content).digest())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--app-image", required=True)
    parser.add_argument("--probe-image", required=True)
    parser.add_argument("--filter-image", required=True)
    parser.add_argument("--host-isolation-verified", action="store_true")
    parser.add_argument("--app-container", required=True)
    parser.add_argument("--probe-container", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for name in ("evidence.json", "health.json"):
        (args.output / name).unlink(missing_ok=True)
    value = bind(read_json(args.report, 4 * 1024 * 1024), read_json(args.plan, 65536), args.source,
                 probe_sha256=sha256(read_bytes(args.probe, 1024 * 1024)).hexdigest(), app_image=args.app_image,
                 probe_image=args.probe_image, snapshot_sha256=snapshot_digest(args.snapshot),
                 app_container=args.app_container, probe_container=args.probe_container,
                 filter_image=args.filter_image, host_isolation_verified=args.host_isolation_verified)
    health = {"status": "ok", "commit": args.source, "verified": True}
    for name, content in (("evidence.json", value), ("health.json", health)):
        with tempfile.NamedTemporaryFile(mode="w", dir=args.output, delete=False) as temporary:
            json.dump(content, temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary.name, args.output / name)


if __name__ == "__main__":
    main()
