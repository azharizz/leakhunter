"""Adapt the pinned HTTP acceptance result to Unspool's handoff evidence contract.

This is a known-exposure acceptance gate, not an analyzer discovery result.
Run in the trusted controller job, outside the application container.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


def evidence(raw, commit, image):
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("Exact source and runtime image identities are required")
    required = {"http_functionality_passed": True, "security_passed": True,
                "secret_observed_at_http_response": False,
                "expected_behavior_reproduced": True,
                "evaluation_type": "known_intentionally_vulnerable_external_application",
                "canary_sha256": "1940b6aaf9f43a73dfd3c0de02b3bbff73cbf0efa57af4e2282da7271e4f1aaa"}
    if not isinstance(raw, dict) or any(type(raw.get(k)) is not type(v) or raw[k] != v for k, v in required.items()):
        raise ValueError("HTTP security and functionality acceptance did not pass")
    return {"gate": {"passed": True},
            "runtime": {"status": "COMPLETED", "passed": True,
                        "cases": [{"id": "vampi-published-http-exposure", "passed": True}]},
            "provenance": {"kind": "known-exposure-http-acceptance", "source_sha": commit,
                           "runtime_image_id": image,
                           "probe_result_sha256": hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-result", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    # A failed invocation must not leave a previous successful health artifact.
    for name in ("evidence.json", "health.json"):
        (args.output / name).unlink(missing_ok=True)
    raw = json.loads(args.probe_result.read_text())
    result = evidence(raw, args.commit, args.image)
    (args.output / "evidence.json").write_text(json.dumps(result))
    (args.output / "health.json").write_text(json.dumps({"status": "ok", "commit": args.commit, "verified": True}))


if __name__ == "__main__":
    main()
