"""Conservative, provider-independent summaries of supplied review evidence."""
from __future__ import annotations


def _sink_rules(review: dict) -> dict:
    rules = review.get("policy", {}).get("rules", {})
    sinks = rules.get("sinks", []) if isinstance(rules, dict) else []
    if isinstance(sinks, list):
        return {item.get("kind"): item for item in sinks if isinstance(item, dict) and isinstance(item.get("kind"), str)}
    return {}


def _cases(review: dict) -> list[dict]:
    evidence = review.get("runtime_evidence", {})
    cases = evidence.get("cases", []) if isinstance(evidence, dict) else []
    return [case for case in cases if isinstance(case, dict)]


def _observed_sinks(case: dict) -> set[str]:
    return {item.get("sink") for item in case.get("observations", [])
            if isinstance(item, dict) and isinstance(item.get("sink"), str)}


def _has_possible_sink(review: dict, sink: str) -> bool:
    if any(path.get("sink") == sink for path in review.get("flow_paths", []) if isinstance(path, dict)):
        return True
    return any(finding.get("sink") == sink for finding in review.get("findings", []) if isinstance(finding, dict))


def _control(review: dict, role: str, required: bool, relevant: list[dict]) -> dict:
    refs = []
    if not required:
        return {"status": "NOT_REQUIRED_BY_POLICY", "evidence_refs": refs}
    if not relevant:
        return {"status": "UNPROVEN", "evidence_refs": refs,
                "reason": "No executed sensitive response case proves this control."}
    missing = []
    for case in relevant:
        case_id = case.get("id", "")
        events = [event for event in case.get("call_events", [])
                  if isinstance(event, dict) and event.get("role") == role]
        if any(event.get("returned_bool") is True for event in events):
            refs.append(f"runtime:{case_id}:guard:{role}")
        else:
            missing.append(case_id)
    if missing:
        return {"status": "UNPROVEN", "evidence_refs": refs,
                "missing_cases": missing,
                "reason": f"No explicit successful {role} observation covers every relevant case."}
    return {"status": "PROVEN_FOR_OBSERVED_CASES", "evidence_refs": refs,
            "scope": "Executed cases only; not universal path coverage."}


def aggregate_evidence(review: dict | None) -> dict:
    """Return a conservative summary without inferring guards from symbol names.

    This never converts missing evidence into a safe result. Guard roles must be
    explicitly supplied by runtime observations, and every conclusion is scoped
    to the supplied static paths and executed cases.
    """
    if not isinstance(review, dict):
        return {"version": 1, "status": "UNAVAILABLE", "safe_to_release": False,
                "effective_disclosure": {"status": "UNRESOLVED", "reason": "Review context unavailable."},
                "evidence_refs": [], "limitations": ["No review context was supplied."]}

    rules = _sink_rules(review)
    cases = _cases(review)
    response_cases = [case for case in cases if "HTTP_RESPONSE" in _observed_sinks(case)]
    possible_response = _has_possible_sink(review, "HTTP_RESPONSE")
    observed_violations = [case for case in cases if case.get("violations")]
    response_rule = rules.get("HTTP_RESPONSE", {})
    controls = {
        "authentication": _control(review, "authentication", response_rule.get("require_authorization") is True, response_cases),
        "ownership": {"status": "UNKNOWN", "evidence_refs": [],
                      "reason": "No ownership requirement is represented in the configured policy."},
        "tenant": _control(review, "tenant", response_rule.get("same_tenant") is True, response_cases),
    }

    if response_cases:
        projection = {"status": "SENSITIVE_FIELDS_OBSERVED", "evidence_refs": [f"runtime:{case.get('id', '')}:HTTP_RESPONSE"
                                                                              for case in response_cases],
                      "reason": "A declared sensitive marker reached an HTTP response."}
    elif possible_response:
        projection = {"status": "UNPROVEN_STATIC_RESPONSE_PATH", "evidence_refs": [],
                      "reason": "A static response path exists without an observed sensitive transfer proving its behavior."}
    else:
        projection = {"status": "NO_RESPONSE_PATH_IN_SCOPE", "evidence_refs": [],
                      "reason": "No sensitive response path was established in the supplied scope; this is not a safety proof."}

    refs = []
    for case in observed_violations:
        refs.append(f"runtime:{case.get('id', '')}:violation")
    refs.extend(f"flow:{path.get('id')}" for path in review.get("flow_paths", [])
                if isinstance(path, dict) and path.get("sink") == "HTTP_RESPONSE")
    blocked = bool(observed_violations or possible_response or projection["status"] in {
        "SENSITIVE_FIELDS_OBSERVED", "UNPROVEN_STATIC_RESPONSE_PATH"})
    reason = ("Observed policy violation or sensitive transfer." if observed_violations
              else "Sensitive response path is possible or unproven." if blocked
              else "No sensitive transfer was established, but release safety remains unresolved.")
    return {"version": 1, "status": "BLOCKED" if blocked else "UNRESOLVED",
            "effective_disclosure": {"status": "BLOCKED" if blocked else "UNRESOLVED", "reason": reason},
            "controls": controls, "public_projection": projection,
            "observed_policy_violations": bool(observed_violations),
            "possible_response_path": possible_response, "safe_to_release": False,
            "evidence_refs": refs,
            "limitations": ["Deterministic conclusions cover only supplied source paths and executed cases.",
                            "UNPROVEN is not equivalent to a confirmed vulnerability or a safe result."]}
