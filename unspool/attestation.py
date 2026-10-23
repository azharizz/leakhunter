"""Create and verify Sigstore-signed in-toto statements for bounded evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from unspool.providers.probes import probe_evidence_complete

_SHA1 = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_MAX_EVIDENCE_BYTES = 32 * 1024 * 1024
_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
_PREDICATE_TYPE = ("https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/"
                   "unspool/attestation/closed-loop/v1")


def _read(path: Path) -> bytes:
    descriptor = os.open(Path(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_EVIDENCE_BYTES:
        os.close(descriptor)
        raise ValueError("Evidence files must be regular, bounded files")
    with os.fdopen(descriptor, "rb") as source:
        raw = source.read(_MAX_EVIDENCE_BYTES + 1)
    if len(raw) > _MAX_EVIDENCE_BYTES:
        raise ValueError("Evidence files must be regular, bounded files")
    return raw


def statement(evidence_path: Path, *, base_sha: str, head_sha: str) -> dict:
    raw = _read(evidence_path)
    evidence = json.loads(raw)
    if (not isinstance(evidence, dict) or not isinstance(base_sha, str) or not _SHA1.fullmatch(base_sha)
            or not isinstance(head_sha, str) or not _SHA1.fullmatch(head_sha) or base_sha == head_sha
            or evidence.get("base_sha") != base_sha or evidence.get("head_sha") != head_sha):
        raise ValueError("Evidence must bind the exact distinct base and head revisions")
    policy = evidence.get("policy")
    if (not isinstance(policy, dict) or policy.get("base_sha256") != policy.get("head_sha256")
            or not _SHA256.fullmatch(policy.get("head_sha256", ""))):
        raise ValueError("Evidence must bind one unchanged policy digest")
    runtime, gate = evidence.get("runtime"), evidence.get("gate")
    if (not isinstance(runtime, dict) or runtime.get("status") != "COMPLETED"
            or runtime.get("passed") is not True or not isinstance(runtime.get("cases"), list)
            or not isinstance(gate, dict) or gate.get("passed") is not True):
        raise ValueError("Only complete passing runtime and deterministic gate evidence can be attested")
    decision = evidence.get("decision")
    luna = decision.get("luna") if isinstance(decision, dict) else None
    if (not isinstance(luna, dict) or luna.get("mode") != "required"
            or luna.get("status") != "DECIDED"):
        raise ValueError("Only evidence with complete required Luna decisions can be attested")
    probe_evidence = luna.get("probe_evidence")
    if not probe_evidence_complete(probe_evidence):
        raise ValueError("Only evidence with complete configured-probe coverage can be attested")
    flow_diff = evidence.get("flow_diff")
    if not isinstance(flow_diff, list):
        raise ValueError("Evidence must include the exact-revision flow diff")
    probes = []
    for case in runtime["cases"]:
        if (not isinstance(case, dict) or not isinstance(case.get("id"), str)
                or type(case.get("passed")) is not bool or case.get("error")):
            raise ValueError("Probe evidence is incomplete or unknown")
        probes.append({"id": case["id"], "passed": case["passed"],
                       "violation_count": len(case.get("violations", []))
                       if isinstance(case.get("violations", []), list) else None})
    return {
        "_type": _STATEMENT_TYPE,
        "subject": [{"name": Path(evidence_path).name,
                     "digest": {"sha256": hashlib.sha256(raw).hexdigest()}}],
        "predicateType": _PREDICATE_TYPE,
        "predicate": {
            "base_sha": base_sha,
            "head_sha": head_sha,
            "policy_sha256": policy["head_sha256"],
            "flow_diff": flow_diff,
            "luna_diff": evidence.get("luna_diff", []),
            "probe_results": probes,
            "luna": {"mode": luna["mode"], "status": luna["status"],
                     "flagged": len(luna.get("flagged", [])),
                     "dismissed": len(luna.get("dismissed", [])),
                     "probe_coverage": probe_evidence},
            "gate": gate,
        },
    }


def write_statement(evidence_path: Path, output: Path, *, base_sha: str, head_sha: str) -> dict:
    value = statement(evidence_path, base_sha=base_sha, head_sha=head_sha)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(output, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        json.dump(value, target, sort_keys=True, separators=(",", ":"))
        target.flush()
        os.fsync(target.fileno())
    return value


def sign(statement_path: Path, bundle_path: Path, *, cosign: str = "cosign") -> None:
    if not os.environ.get("SIGSTORE_ID_TOKEN"):
        raise ValueError("GitLab SIGSTORE_ID_TOKEN is required for keyless signing")
    _read(statement_path)
    if Path(bundle_path).exists() or Path(bundle_path).is_symlink():
        raise ValueError("Refusing to overwrite Sigstore bundle")
    result = subprocess.run([cosign, "sign-blob", "--yes", "--bundle", str(bundle_path), str(statement_path)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
    if result.returncode:
        Path(bundle_path).unlink(missing_ok=True)
        raise ValueError("Cosign could not sign the evidence statement")


def verify(evidence_path: Path, statement_path: Path, bundle_path: Path, *,
           expected_identity: str, expected_head_sha: str, cosign: str = "cosign") -> dict:
    if (not isinstance(expected_identity, str) or not expected_identity.startswith("https://gitlab.com/")
            or not isinstance(expected_head_sha, str) or not _SHA1.fullmatch(expected_head_sha)):
        raise ValueError("An exact GitLab certificate identity and head SHA are required")
    if Path(bundle_path).is_symlink():
        raise ValueError("Sigstore bundle must be a regular file")
    result = subprocess.run([
        cosign, "verify-blob", "--bundle", str(bundle_path),
        "--certificate-identity", expected_identity,
        "--certificate-oidc-issuer", "https://gitlab.com", str(statement_path),
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
    if result.returncode:
        raise ValueError("Sigstore verification failed for the required GitLab identity")
    value = json.loads(_read(statement_path))
    predicate = value.get("predicate") if isinstance(value, dict) else None
    if (not isinstance(value, dict) or value.get("_type") != _STATEMENT_TYPE
            or value.get("predicateType") != _PREDICATE_TYPE or not isinstance(predicate, dict)):
        raise ValueError("Signed statement does not bind the current evidence and expected revision")
    expected = statement(evidence_path, base_sha=predicate.get("base_sha"), head_sha=expected_head_sha)
    if value != expected:
        raise ValueError("Signed statement does not bind the current evidence and expected revision")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--evidence", type=Path, required=True)
    prepare.add_argument("--base-sha", required=True)
    prepare.add_argument("--head-sha", required=True)
    prepare.add_argument("--output", type=Path, required=True)
    signing = commands.add_parser("sign")
    signing.add_argument("--statement", type=Path, required=True)
    signing.add_argument("--bundle", type=Path, required=True)
    signing.add_argument("--cosign", default="cosign")
    checking = commands.add_parser("verify")
    checking.add_argument("--evidence", type=Path, required=True)
    checking.add_argument("--statement", type=Path, required=True)
    checking.add_argument("--bundle", type=Path, required=True)
    checking.add_argument("--expected-identity", required=True)
    checking.add_argument("--expected-head-sha", required=True)
    checking.add_argument("--cosign", default="cosign")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        value = write_statement(args.evidence, args.output, base_sha=args.base_sha, head_sha=args.head_sha)
        print(json.dumps({"statement": str(args.output), "head_sha": value["predicate"]["head_sha"]}))
    elif args.command == "sign":
        sign(args.statement, args.bundle, cosign=args.cosign)
    else:
        value = verify(args.evidence, args.statement, args.bundle,
                       expected_identity=args.expected_identity, expected_head_sha=args.expected_head_sha,
                       cosign=args.cosign)
        print(json.dumps({"verified": True, "head_sha": value["predicate"]["head_sha"]}))


if __name__ == "__main__":
    main()
