"""Application orchestration independent of the HTTP and CLI transports."""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import math
import os
import shutil
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from leakhunter.analyzers.registry import analyze_project
from leakhunter.analyzers.sources import exclusions, source_files
from leakhunter.application.decorators import exclusive
from leakhunter.execution.runtime import load_manifest, run_suite
from leakhunter.languages import LANGUAGES, extensions, finding_function, manifest_entrypoints, manifest_language, runtime_image
from leakhunter.policy.engine import Policy, load_policy
from leakhunter.providers.context import build_review_contexts
from leakhunter.providers.evidence import aggregate_evidence
from leakhunter.providers.probes import (baseline_manifest, calibration_report, merge_runtime,
                                         probe_evidence_complete, probe_evidence_report,
                                         select_targeted_probes)
from leakhunter.providers.reviews import review_contexts
from leakhunter.providers.verdict import MODES as DECISION_MODES, decide
from leakhunter.repairs.engine import propose_and_verify, resolve_context_findings
from leakhunter.storage.knowledge import KnowledgeBank, encoded, now, policy_digest


MODEL_CALL = None
LANGUAGE = "python"
DECISION_MODE = "required"
LOCK = threading.RLock()
OPERATIONS = threading.Lock()
MODEL_USAGE = threading.local()


def _reset_model_usage() -> None:
    MODEL_USAGE.calls = 0
    MODEL_USAGE.priced_calls = 0
    MODEL_USAGE.cost_usd = 0.0


def record_model_usage(usage: dict | None) -> None:
    """Keep provider-reported cost totals for the current analysis or repair operation."""
    MODEL_USAGE.calls = getattr(MODEL_USAGE, "calls", 0) + 1
    cost = usage.get("cost") if isinstance(usage, dict) else None
    if (isinstance(cost, (int, float)) and not isinstance(cost, bool)
            and math.isfinite(cost) and cost >= 0):
        MODEL_USAGE.priced_calls = getattr(MODEL_USAGE, "priced_calls", 0) + 1
        MODEL_USAGE.cost_usd = getattr(MODEL_USAGE, "cost_usd", 0.0) + float(cost)


def _model_cost() -> dict:
    calls = getattr(MODEL_USAGE, "calls", 0)
    priced = getattr(MODEL_USAGE, "priced_calls", 0)
    return {"calls": calls, "priced_calls": priced,
            "total_usd": round(MODEL_USAGE.cost_usd, 8) if calls and priced == calls else None}


def configure(args: argparse.Namespace, model_call) -> None:
    global REPOSITORY, POLICY_FILE, DATA, BANK, API_URL, API_KEY, DECISION_MODEL, DUO_MODEL
    global MANIFEST, MANIFEST_FILE, RUNTIME_BACKEND, TIMEOUT, MODEL_CALL, LANGUAGE, DECISION_MODE
    REPOSITORY = args.repository.resolve(strict=True)
    POLICY_FILE = args.policy.resolve(strict=True) if args.policy else None  # None: built-in catalogue
    DATA = args.data_dir.resolve()
    package = Path(__file__).resolve().parent.parent
    if not REPOSITORY.is_dir() or POLICY_FILE is not None and not POLICY_FILE.is_file():
        raise ValueError("Repository must be a directory and policy must be a file")
    if DATA == package or package in DATA.parents:
        raise ValueError("Runtime data must be stored outside the application package")
    if DATA == REPOSITORY or REPOSITORY in DATA.parents:
        raise ValueError("Runtime data must be outside the target repository")
    policy = load_policy(POLICY_FILE)
    MANIFEST_FILE = args.runtime_manifest.resolve(strict=True) if args.runtime_manifest else None
    MANIFEST = load_manifest(MANIFEST_FILE) if MANIFEST_FILE else None
    LANGUAGE = getattr(args, "language", None) or (manifest_language(MANIFEST) if MANIFEST else "python")
    if LANGUAGE not in LANGUAGES or (MANIFEST and LANGUAGE != manifest_language(MANIFEST)):
        raise ValueError("Configured language must match the runtime manifest")
    RUNTIME_BACKEND, TIMEOUT = args.runtime_backend, args.runtime_timeout
    if not 1 <= TIMEOUT <= 600:
        raise ValueError("Runtime timeout must be between 1 and 600 seconds")
    API_URL, API_KEY = args.provider_url, os.getenv("AGENT_PROVIDER_API_KEY", "")
    DECISION_MODEL, DUO_MODEL = args.decision_model, args.repair_model
    DECISION_MODE = getattr(args, "decision_mode", "required")
    if DECISION_MODE not in DECISION_MODES:
        raise ValueError(f"Decision mode must be one of {DECISION_MODES}")
    MODEL_CALL = model_call
    if API_URL:
        url = urlsplit(API_URL)
        if url.scheme != "https" and not (url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost", "::1"}):
            raise ValueError("Provider URL must use HTTPS (loopback HTTP is allowed for testing)")
        if url.username or url.password or not url.hostname:
            raise ValueError("Invalid provider URL")
    BANK = KnowledgeBank(DATA)
    BANK.register_policy(policy.raw)


def current_policy() -> tuple[Policy, dict]:
    policy = load_policy(POLICY_FILE)
    record = BANK.register_policy(policy.raw)
    raw = dict(policy.raw, status=record["status"])
    if record["approved_by"]:
        raw["approved_by"] = record["approved_by"]
    return Policy(raw), record


def runtime_config() -> dict:
    language = LANGUAGE
    return {"backend": RUNTIME_BACKEND, "configured": MANIFEST is not None,
            "language": language,
            "manifest": {"path": str(MANIFEST_FILE)} if MANIFEST_FILE else None,
            "docker_image": runtime_image(MANIFEST) if MANIFEST else None,
            "case_count": len(MANIFEST.get("cases", [])) if MANIFEST else 0,
            "manifest_sha": hashlib.sha256(encoded(MANIFEST).encode()).hexdigest() if MANIFEST else None,
            "docker_available": shutil.which("docker") is not None,
            "prerequisites": (["Docker daemon and configured image; network disabled"] if RUNTIME_BACKEND == "docker"
                              else ["Trusted repository only: local subprocesses are NOT a security sandbox"]),
            "cases": [{"id": case["id"], **({"module": case["module"], "callable": case["callable"]}
                                           if language == "python" else {"entrypoint": case["entrypoint"]})}
                      for case in MANIFEST.get("cases", [])] if MANIFEST else []}


def graph() -> dict:
    with LOCK:
        value = BANK.graph()
        evaluations = BANK.records("evaluations")
        value["latest_evaluation"] = evaluations[0] if evaluations else None
        value["runtime_config"] = runtime_config()
        return value




def revision_sha(root: Path) -> str:
    root = Path(root).resolve()
    digest = hashlib.sha256()
    language = LANGUAGE
    files = source_files(root, extensions(language), exclusions(language))
    for suffix in extensions(language):
        for path, content in files:
            if path.suffix != suffix:
                continue
            digest.update(path.relative_to(root).as_posix().encode() + b"\0")
            digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def mapped_finding(finding: dict, case: dict) -> bool:
    mapping = case.get("finding", {})
    return (mapping.get("file") == finding.get("file") and finding_function(case) == finding.get("function")
            and (not mapping.get("sink") or mapping["sink"] == finding.get("sink")))


def attach_evidence(findings: list[dict], runtime: dict, manifest: dict | None, revision: str) -> None:
    cases = {case["id"]: case for case in (manifest or {}).get("cases", [])}
    for finding in findings:
        finding["revision_sha"] = revision
        evidence = {"version": 1, "status": "NOT_RUN", "observed": False, "case_ids": []}
        if runtime["status"] == "COMPLETED":
            evidence["status"] = "NOT_OBSERVED"
            for case in runtime.get("cases", []):
                if not mapped_finding(finding, cases.get(case["id"], {})):
                    continue
                for violation in case.get("violations", []):
                    symbol = str(violation.get("symbol", ""))
                    if (violation.get("sink") == finding["sink"] and violation.get("classification") == finding["classification"]
                            and fnmatch.fnmatchcase(symbol, finding["source"])):
                        evidence["observed"] = True
                        evidence["status"] = "CONFIRMED_IN_TEST"
                        evidence["case_ids"].append(case["id"])
            if evidence["observed"]:
                finding["status"] = "CONFIRMED_IN_TEST"
        elif runtime["status"] != "NOT_RUN":
            evidence["status"] = "ERROR"
        finding["runtime_evidence"] = evidence


def release_gate(findings: list[dict], runtime: dict, policy_record: dict, coverage: dict | None = None,
                 luna: dict | None = None) -> dict:
    """Require complete configured evidence; Luna triages but cannot approve or veto alone."""
    reasons = []
    if not isinstance(policy_record, dict) or policy_record.get("status") != "approved":
        reasons.append("Policy is not approved")
    if findings:
        reasons.append("Unresolved static candidates require review or repair")
    cases = runtime.get("cases") if isinstance(runtime, dict) else None
    if (not isinstance(runtime, dict) or runtime.get("status") != "COMPLETED"
            or runtime.get("passed") is not True or runtime.get("functional_passed") is not True
            or not isinstance(cases, list) or not cases
            or any(not isinstance(case, dict) or case.get("passed") is not True or case.get("error")
                   or case.get("violations") != [] for case in cases)):
        reasons.append("Runtime security and functional verification has not passed")
    if (not isinstance(coverage, dict) or coverage.get("parse_errors")
            or coverage.get("unsupported_constructs") or not coverage.get("analyzed_files")):
        reasons.append("Static coverage is incomplete or contains unsupported constructs")
    if isinstance(luna, dict) and luna.get("mode") == "required":
        if luna.get("status") != "DECIDED":
            reasons.extend(luna.get("reasons") or ["Required Luna review is incomplete"])
        probe_evidence = luna.get("probe_evidence")
        if not probe_evidence_complete(probe_evidence):
            reasons.append("Configured probes for non-clear Luna boundaries are incomplete or failed")
    elif luna is None:
        reasons.append("Required Luna triage evidence is missing")
    language = coverage.get("language", "Python") if coverage else "Python"
    return {"passed": not reasons, "status": "PASSED" if not reasons else "BLOCKED", "reasons": reasons,
            "scope": f"Configured {language} analysis, complete required review and configured synthetic probes only;"
                     " Luna verdicts are triage signals, not standalone approval or rejection. No automatic merge or deployment."}


@exclusive(OPERATIONS)
def analyze(*, branch: str = "main", base_snapshot_id: str | None = None) -> dict:
    if not isinstance(branch, str) or not branch.strip() or len(branch) > 200:
        raise ValueError("Invalid branch name")
    started = time.perf_counter()
    _reset_model_usage()
    policy, record = current_policy()
    previous = BANK.snapshot(base_snapshot_id) if base_snapshot_id else BANK.snapshot(branch=branch)
    if base_snapshot_id and previous is None:
        raise KeyError(base_snapshot_id)
    revision = revision_sha(REPOSITORY)
    language = LANGUAGE
    result = analyze_project(REPOSITORY, policy, previous=previous.get("index") if previous else None,
                             entrypoints=manifest_entrypoints(MANIFEST), language=language)
    if revision != revision_sha(REPOSITORY):
        raise RuntimeError("Repository changed during static analysis; run analysis again")
    baseline = baseline_manifest(MANIFEST)
    runtime = run_suite(REPOSITORY, baseline, policy, backend=RUNTIME_BACKEND, timeout=TIMEOUT) if baseline and baseline["cases"] else {
        "status": "NOT_RUN", "passed": False, "cases": [],
        "reason": "No always-run runtime cases configured" if MANIFEST else "No runtime manifest configured"}
    findings = result["findings"]
    attach_evidence(findings, runtime, MANIFEST, revision)
    contextual = resolve_context_findings(findings, runtime, MANIFEST, policy)
    contexts = build_review_contexts(REPOSITORY, result, policy, runtime, MANIFEST, revision)
    decision, decision_ms, decision_status = review_contexts(contexts, MODEL_CALL, DECISION_MODEL)
    targeted_cases = select_targeted_probes(decision, MANIFEST) if MANIFEST else []
    targeted_runtime = None
    if targeted_cases:
        targeted_runtime = run_suite(REPOSITORY, dict(MANIFEST, cases=targeted_cases), policy,
                                     backend=RUNTIME_BACKEND, timeout=TIMEOUT)
        # Model-selected probes are ordinary runtime evidence once executed.
        runtime = merge_runtime(runtime, targeted_runtime)
        attach_evidence(findings, runtime, MANIFEST, revision)
        contextual = resolve_context_findings(findings, runtime, MANIFEST, policy)
        updated_contexts = build_review_contexts(REPOSITORY, result, policy, runtime, MANIFEST, revision)
        context_by_id = {review.get("review_id"): review for review in updated_contexts.get("reviews", [])
                         if isinstance(review, dict)}
        for review in decision.get("reviews", []):
            updated = context_by_id.get(review.get("review_id")) if isinstance(review, dict) else None
            if updated:
                review["post_probe_evidence"] = aggregate_evidence(updated)
    decision["targeted_runtime"] = targeted_runtime or {"status": "NOT_SELECTED", "cases": []}
    decision["calibration"] = calibration_report(decision, runtime, MANIFEST)
    # Luna triages boundaries; configured probe and static/runtime evidence decide the gate.
    luna = decide(decision, findings, DECISION_MODE)
    decision["luna"] = luna
    luna["probe_evidence"] = probe_evidence_report(decision, MANIFEST, runtime)
    verdicts = {(unit["file"], unit["function"]): unit for unit in luna["units"]}
    for finding in findings:
        unit = verdicts.get((finding.get("file"), finding.get("function")))
        if unit:
            finding["luna"] = {key: unit[key] for key in ("verdict", "disclosure", "basis")}
    unresolved = contextual["unresolved"]
    metric = {
        "timestamp": now(),
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "findings": len(findings),
        "confirmed": sum(f["status"] == "CONFIRMED_IN_TEST" for f in findings),
        "policy_version": policy.version,
        "policy_digest": record["digest"],
        "decision_model": DECISION_MODEL,
        "decision_status": decision_status,
        "decision_latency_ms": decision_ms,
        "decision_review_status": decision["status"],
        "decision_reviews": len(decision["reviews"]),
        "decision_omitted_reviews": decision["scope"]["omitted_review_units"],
        "targeted_probe_cases": len(targeted_cases),
        "decision_mode": DECISION_MODE,
        "luna_status": luna["status"],
        "luna_flagged": len(luna["flagged"]),
        "luna_cleared_findings": len(luna["dismissed"]),
        "decision_calibration_samples": decision["calibration"]["sample_count"],
        "model_cost": _model_cost(),
        "runtime_status": runtime["status"],
        "runtime_duration_ms": runtime.get("duration_ms"),
        "runtime_confirmation_rate": (sum(f["status"] == "CONFIRMED_IN_TEST" for f in findings) / len(findings))
        if findings else None,
        "incremental": result.get("incremental", {})}
    value = dict(result, revision_sha=revision, runtime=runtime, decision=decision, metric=metric, last_run=now(),
                 policy=record, runtime_config=runtime_config(), context_evidence=contextual,
                 gate=release_gate(unresolved, runtime, record, result["coverage"], luna))
    if revision != revision_sha(REPOSITORY):
        raise RuntimeError("Repository changed during verification; run analysis again")
    with LOCK:
        snapshot = BANK.save_snapshot(value, branch, previous["snapshot_id"] if previous else None)
        BANK.append("metrics", dict(metric, snapshot_id=snapshot["snapshot_id"]))
    return dict(snapshot, graph={key: snapshot[key] for key in ("nodes", "edges", "findings")})


@exclusive(OPERATIONS)
def repair(allowed_paths: list[str] | None = None) -> dict:
    baseline = BANK.snapshot()
    if baseline is None:
        raise ValueError("Run analysis before requesting a repair")
    policy, record = current_policy()
    if record["status"] != "approved":
        raise ValueError("Repair requires an approved policy")
    if baseline["policy"]["digest"] != record["digest"]:
        raise ValueError("Policy changed; run analysis again before repair")
    if baseline["revision_sha"] != revision_sha(REPOSITORY):
        raise ValueError("Repository changed; run analysis again before repair")
    _reset_model_usage()
    result = propose_and_verify(REPOSITORY, DATA, policy, MANIFEST, baseline, MODEL_CALL, DUO_MODEL,
                                backend=RUNTIME_BACKEND, timeout=TIMEOUT, allowed_paths=allowed_paths)
    result["model_cost"] = _model_cost()
    result["baseline_snapshot_id"] = baseline["snapshot_id"]
    result = BANK.append("repairs", result)
    BANK.append("metrics", {"kind": "repair", "repair_id": result["id"],
                            "repair_verification_passed": bool(result.get("passed")),
                            "provider_status": result.get("provider_status"),
                            "provider_latency_ms": result.get("provider_latency_ms")})
    return result


@exclusive(OPERATIONS)
def evaluate() -> dict:
    """Score independently labeled, actually executed manifest cases; no guessed labels."""
    if not MANIFEST:
        raise ValueError("Evaluation requires a runtime manifest with expected_violation labels")
    labels = {case["id"]: case["expected_violation"] for case in MANIFEST["cases"]
              if isinstance(case.get("expected_violation"), bool)}
    if not labels:
        raise ValueError("No independently labeled cases configured")
    policy, _ = current_policy()
    runtime = run_suite(REPOSITORY, MANIFEST, policy, backend=RUNTIME_BACKEND, timeout=TIMEOUT)
    analysis = analyze_project(REPOSITORY, policy, entrypoints=manifest_entrypoints(MANIFEST),
                               language=manifest_language(MANIFEST))
    tp = fp = tn = fn = unknown = 0
    static_tp = static_fp = static_tn = static_fn = static_unknown = 0
    case_specs = {case["id"]: case for case in MANIFEST["cases"]}
    cases = {case["id"]: case for case in runtime.get("cases", [])}
    for ident, unsafe in labels.items():
        case = cases.get(ident)
        if runtime.get("status") != "COMPLETED" or not case or case.get("error") or not case.get("passed"):
            unknown += 1
        else:
            detected = bool(case.get("violations"))
            tp += int(unsafe and detected)
            fn += int(unsafe and not detected)
            fp += int(not unsafe and detected)
            tn += int(not unsafe and not detected)
        mapping = case_specs[ident].get("finding", {})
        if not mapping.get("file") or not mapping.get("function"):
            static_unknown += 1
            continue
        if analysis["coverage"].get("parse_errors") or analysis["coverage"].get("unsupported_constructs"):
            static_unknown += 1
            continue
        detected_static = any(mapped_finding(f, case_specs[ident]) for f in analysis["findings"])
        static_tp += int(unsafe and detected_static)
        static_fn += int(unsafe and not detected_static)
        static_fp += int(not unsafe and detected_static)
        static_tn += int(not unsafe and not detected_static)

    def scores(a, b, c, d, missing):
        return {"tp": a, "fp": b, "tn": c, "fn": d, "unknown": missing,
                "precision": a / (a + b) if a + b else None,
                "recall": a / (a + d) if a + d else None,
                "false_safe_rate": d / (a + d) if a + d else None}

    repairs = BANK.records("repairs")
    value = {
        "status": "COMPLETED" if runtime["status"] == "COMPLETED" and not unknown else "INCOMPLETE",
        "scope": "Configured synthetic case labels only; not a population accuracy estimate",
        "runtime": scores(tp, fp, tn, fn, unknown),
        "static": scores(static_tp, static_fp, static_tn, static_fn, static_unknown),
        "labeled_cases": len(labels),
        "runtime_status": runtime["status"],
        "repair_success_rate": sum(bool(item.get("passed")) for item in repairs) / len(repairs) if repairs else None,
        "repair_attempts": len(repairs)}
    return BANK.append("evaluations", value)
