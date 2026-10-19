"""Deterministic metadata exploration plus executable, labeled flow families.

The large Cartesian space is metadata only. Materialized programs exercise four
concrete flow families, each with a positive and safe implementation; repeated
families vary synthetic markers, not coverage claims.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

import yaml

DIMENSIONS = {
    "source": ("email", "password_hash", "session_token", "salary", "customer_id", "address", "api_key"),
    "sink": ("http_response", "application_log", "analytics", "webhook", "trace", "csv_export", "ai_prompt"),
    "classification": ("PUBLIC", "INTERNAL", "PERSONAL", "SECRET"),
    "audience": ("self", "operator", "external_vendor", "approved_partner", "public"),
    "transform": ("identity", "serializer", "redactor", "hash", "allowlist"),
    "tenant": ("same_tenant", "cross_tenant"),
    "authorization": ("authorized", "unauthorized"),
    "execution": ("unit", "integration", "browser", "queue", "cron", "worker", "migration"),
}
ORDER = tuple(DIMENSIONS)
SPACE_SIZE = 1
for values in DIMENSIONS.values():
    SPACE_SIZE *= len(values)
FAMILIES = ("response", "logging", "analytics", "tenant")


def case_at(index: int, seed: int = 104729) -> dict:
    """Return metadata in O(dimensions); this does not execute any program."""
    if not 0 <= index < SPACE_SIZE:
        raise IndexError(f"case index must be between 0 and {SPACE_SIZE - 1}")
    values = {}
    remainder = index
    for name in reversed(ORDER):
        choices = DIMENSIONS[name]
        remainder, offset = divmod(remainder, len(choices))
        values[name] = choices[(offset + seed) % len(choices)]
    values["case_id"] = hashlib.sha256(f"{seed}:{index}".encode()).hexdigest()[:16]
    values["index"] = index
    return values


def evaluate(case: dict) -> dict:
    """Metadata heuristic only, not a runtime or static-analysis evaluation."""
    secret_external = (case["classification"] == "SECRET"
                       and case["audience"] in {"external_vendor", "public"}
                       and case["transform"] in {"identity", "serializer"})
    personal_log = case["sink"] == "application_log" and case["classification"] in {"PERSONAL", "SECRET"}
    cross_tenant = case["tenant"] == "cross_tenant" and case["authorization"] == "unauthorized"
    return {**case, "leak": secret_external or personal_log or cross_tenant,
            "label_kind": "unexecuted_metadata_heuristic",
            "reason": "secret_external_egress" if secret_external else "personal_log" if personal_log
            else "cross_tenant_access" if cross_tenant else "allowed"}


def sample_cases(count: int = 3, seed: int = 104729) -> list[dict]:
    if count < 1:
        raise ValueError("count must be positive")
    indexes = random.Random(seed).sample(range(SPACE_SIZE), min(count, SPACE_SIZE))
    return [evaluate(case_at(index, seed)) for index in indexes]


def materialize(destination: Path, count: int = 8, seed: int = 104729) -> dict:
    """Write independently executable targets, pinned policy, and labeled manifests.

    Refuse an existing catalog rather than silently overwriting a prior run.
    Eight cases cover all implemented family/label pairs, not the metadata space.
    """
    if count < 1:
        raise ValueError("count must be positive")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError("materialize destination must be empty")
    policy_text = (Path(__file__).parent / "leakhunter-policy.yaml").read_text()
    (destination / "policy.yaml").write_text(policy_text)
    entries = []
    for index in range(count):
        family = FAMILIES[(index // 2) % len(FAMILIES)]
        positive = index % 2 == 0
        ident = hashlib.sha256(f"executable:{seed}:{index}".encode()).hexdigest()[:16]
        marker = f"SYNTHETIC_{family.upper()}_{ident}"
        field = {"response": "password_hash", "logging": "email",
                 "analytics": "email", "tenant": "address"}[family]
        classification = "SECRET" if family == "response" else "PERSONAL"
        directory = destination / ident
        repository = directory / "repository"
        repository.mkdir(parents=True)
        (repository / "records.py").write_text(
            "from types import SimpleNamespace\n\n"
            f"customer = SimpleNamespace({field}={marker!r}, tenant_id='tenant-b')\n")
        (repository / "analytics.py").write_text(
            "OUTBOX = []\n\ndef track(event, payload):\n"
            "    OUTBOX.append({'event': event, 'payload': payload})\n"
            "    return {'accepted': True}\n")
        code = "import logging\nimport analytics\nfrom records import customer\n\nlogger = logging.getLogger('generated')\nlogger.setLevel(logging.INFO)\n\n\ndef run():\n"
        if family == "response":
            code += ("    return {'ok': True, 'value': customer.password_hash}\n" if positive
                     else "    return {'ok': True}\n")
        elif family == "logging":
            code += ("    logger.info('customer=%s', customer.email)\n" if positive
                     else "    logger.info('profile viewed')\n")
            code += "    return {'ok': True}\n"
        elif family == "analytics":
            code += ("    analytics.track('view', {'email': customer.email})\n" if positive
                     else "    analytics.track('view', {'page': 'catalog'})\n")
            code += "    return {'ok': True}\n"
        else:
            code += ("    return {'ok': True, 'value': customer.address}\n" if positive else
                     "    if customer.tenant_id != 'tenant-a':\n"
                     "        return {'ok': True, 'error': 'forbidden'}\n"
                     "    return {'ok': True, 'value': customer.address}\n")
        (repository / "service.py").write_text(code)
        (repository / "regression.py").write_text(
            "from service import run\n\nif __name__ == '__main__':\n"
            "    assert run()['ok'] is True\n")
        context = {"audience": "authenticated_self", "tenant": "tenant-a",
                   "source_tenant": "tenant-b" if family == "tenant" else "tenant-a",
                   "authorized": family != "tenant", "synthetic": True}
        if family == "analytics":
            context.update(recipient="synthetic_analytics", contract="aggregate_only")
        case = {"id": ident, "module": "service", "callable": "run", "args": [], "kwargs": {},
                "sensitive": [{"marker": marker, "class": classification, "symbol": f"customer.{field}"}],
                "context": context, "expect": {"ok": True}, "expected_violation": positive}
        sink = {"response": "HTTP_RESPONSE", "logging": "APPLICATION_LOG",
                "analytics": "THIRD_PARTY_ANALYTICS", "tenant": "HTTP_RESPONSE"}[family]
        if positive:
            case["finding"] = {"file": "service.py", "function": "run", "sink": sink,
                               "symbol": f"customer.{field}"}
        if family == "analytics":
            case["capture_calls"] = [{"module": "analytics", "callable": "track", "sink": sink,
                                      "return_value": {"accepted": True}}]
        manifest = {"version": 1, "regression_command": ["python", "regression.py"], "cases": [case]}
        (directory / "runtime.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))
        entries.append({"id": ident, "family": family, "expected_violation": positive,
                        "repository": f"{ident}/repository", "manifest": f"{ident}/runtime.yaml"})
    catalog = {"version": 1, "seed": seed, "implemented_flow_families": list(FAMILIES),
               "policy": "policy.yaml", "cases": entries}
    (destination / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n")
    return catalog


def _metrics(pairs: list[tuple[bool, bool]]) -> dict:
    tp = sum(expected and actual for expected, actual in pairs)
    fp = sum(not expected and actual for expected, actual in pairs)
    fn = sum(expected and not actual for expected, actual in pairs)
    tn = sum(not expected and not actual for expected, actual in pairs)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "accuracy": (tp + tn) / len(pairs) if pairs else None}


def evaluate_materialized(destination: Path, *, backend: str = "docker") -> dict:
    """Measure analyzer candidates and actual runtime violations against labels."""
    from leakhunter.analyzers.python_ast import analyze_project
    from leakhunter.policy.engine import load_policy
    from leakhunter.execution.runtime import load_manifest, run_suite

    destination = Path(destination)
    catalog = json.loads((destination / "catalog.json").read_text())
    policy = load_policy(destination / catalog["policy"])
    results, static_pairs, runtime_pairs = [], [], []
    for entry in catalog["cases"]:
        repository = destination / entry["repository"]
        manifest = load_manifest(destination / entry["manifest"])
        findings = analyze_project(repository, policy, entrypoints=[f"{case['module']}.{case['callable']}" for case in manifest["cases"]])["findings"]
        runtime = run_suite(repository, manifest, policy, backend=backend)
        expected = entry["expected_violation"]
        static_pairs.append((expected, bool(findings)))
        completed = runtime["status"] == "COMPLETED" and runtime.get("functional_passed", False)
        observed = any(case.get("violations") for case in runtime.get("cases", []))
        if completed:
            runtime_pairs.append((expected, observed))
        results.append({"id": entry["id"], "family": entry["family"], "expected_violation": expected,
                        "static_predicted": bool(findings), "runtime_observed": observed if completed else None,
                        "label_matches": observed == expected if completed else None, "runtime": runtime})
    return {"status": "COMPLETED" if len(runtime_pairs) == len(results) else "INCOMPLETE",
            "backend": backend, "case_count": len(results), "measured_runtime_cases": len(runtime_pairs),
            "static": _metrics(static_pairs), "runtime": _metrics(runtime_pairs), "cases": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Explore metadata or generate and evaluate executable cases")
    parser.add_argument("--sample", type=int, default=0, help="sample metadata only")
    parser.add_argument("--seed", type=int, default=104729)
    parser.add_argument("--output", type=Path, help="write JSON result")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--materialize", type=Path, help="create executable cases in an empty directory")
    operation.add_argument("--evaluate", type=Path, help="evaluate an existing executable catalog")
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--runtime-backend", choices=("docker", "local"), default="docker")
    parser.add_argument("--trusted-local", action="store_true")
    args = parser.parse_args()
    if args.runtime_backend == "local" and not args.trusted_local:
        parser.error("--runtime-backend local requires --trusted-local")
    try:
        if args.materialize:
            result = materialize(args.materialize, args.count, args.seed)
        elif args.evaluate:
            result = evaluate_materialized(args.evaluate, backend="local" if args.trusted_local else args.runtime_backend)
        else:
            result = {"metadata_space_size": SPACE_SIZE,
                      "dimensions": {key: len(values) for key, values in DIMENSIONS.items()},
                      "coverage": "metadata only; no generated or executed programs"}
            if args.sample:
                result["cases"] = sample_cases(args.sample, args.seed)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n")
    else:
        print(rendered)
    if args.evaluate and (result["status"] != "COMPLETED" or not all(case["label_matches"] for case in result["cases"])):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
